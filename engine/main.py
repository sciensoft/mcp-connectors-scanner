"""Scanner entrypoint: scheduled full sweep plus the read-only API.

The scanner is a microservice with its own database (ADR 0001, decision 3).
One process does two things:
  - a background thread serves the read-only API (api.py) that the server calls
  - the main thread runs a scheduled sweep of the whole catalog

Flow per sweep:
  1. Pull the list of ready catalog entries from the server's read-only feed.
  2. extract -> scan -> grade each one, never letting one failure stop the sweep.
  3. Save each result to the scanner's own database the moment it finishes.

Environment:
  SCANNER_DATABASE_URL   the scanner's OWN Postgres (never the server's)
  SCAN_FEED_URL          read-only catalog feed on the server
  SCAN_FEED_TOKEN        bearer token for that feed
  SCANNER_API_ADDR       address the read API listens on, default :9090
  SCANNER_API_TOKEN      bearer token the server presents to the API
  SCAN_INTERVAL_HOURS    hours between sweeps, default 168 (weekly); 0 = run once
  SCAN_CONCURRENCY       connectors scanned at the same time, default 10 (1 = one by one)
  SCAN_WORK_DIR          ephemeral work dir, wiped around every scan
"""
import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

from . import api, store
from .coverage import matrix
from .extract import extract
from .grade import grade
from concurrent.futures import ThreadPoolExecutor, as_completed
from .scan import cleanup_stale, scan


def log(msg: str):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def fetch_catalog() -> list:
    headers = {"User-Agent": "mcpc-scanner"}
    token = os.environ.get("SCAN_FEED_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(os.environ["SCAN_FEED_URL"], headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def scan_one(entry: dict) -> dict:
    target = extract(entry, entry.get("docs_url", ""))
    findings = scan(target)
    g = grade(findings)
    return {
        "entry_id": entry.get("id", "?"),
        "version": target.version or target.ref or target.image,
        "ecosystem": target.ecosystem,
        "grade": g.letter,
        "reason": g.reason,
        "cve_counts": findings.cve_counts,
        "mal_advisories": findings.mal_advisories,
        "heuristic_hits": findings.heuristic_hits,
        "errors": findings.errors,
        # Full evidence for the transparency page (ADR 0001, decision 6)
        "vulnerabilities": findings.vulnerabilities,
        "packages": findings.packages,
        "dependency_edges": findings.dependency_edges,
        "tools": findings.tools,
        "coverage": matrix(target.ecosystem, list(findings.tools)),
        "scanned_at": datetime.now(timezone.utc),
    }


def sweep():
    started = datetime.now(timezone.utc)
    # Leftovers from a crash or restart: remove them before doing anything else.
    stale = cleanup_stale(max_age_seconds=0)
    if stale:
        log(f"removed {stale} stale work dir(s) from a previous run")

    entries = fetch_catalog()
    run_id = store.start_run(started)
    log(f"sweep {run_id} start: {len(entries)} catalog entries")

    workers = max(1, int(os.environ.get("SCAN_CONCURRENCY", "10")))
    log(f"scanning with {workers} at a time")

    def work(entry: dict) -> dict:
        eid = entry.get("id", "?")
        try:
            return scan_one(entry)
        except Exception as e:  # noqa: BLE001 - one connector must not stop the sweep
            log(f"{eid}: scanner error: {e}")
            return {"entry_id": eid, "grade": "?", "reason": f"scanner error: {e}",
                    "errors": [str(e)], "scanned_at": datetime.now(timezone.utc)}

    # Only this (main) thread saves, logs and counts, so there is no shared state to
    # lock. Each scan has its own work dir; the wipe-everything cleanup runs only
    # before and after the pool, never while scans are in flight.
    counts = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, entry) for entry in entries]
        for fut in as_completed(futures):
            result = fut.result()
            eid = result["entry_id"]
            try:
                store.save_result(run_id, result)
            except Exception as e:  # noqa: BLE001 - a DB hiccup must not stop the sweep either
                log(f"{eid}: could not save result: {e}")
            counts[result["grade"]] = counts.get(result["grade"], 0) + 1
            done += 1
            log(f"[{done}/{len(entries)}] {eid}: {result['grade']} ({result['reason']})")

    store.finish_run(run_id, len(entries), counts)
    log(f"sweep {run_id} done: {counts}")
    leftover = cleanup_stale(max_age_seconds=0)
    if leftover:
        log(f"end-of-sweep cleanup removed {leftover} leftover work dir(s)")


def wait_for_db(attempts: int = 30):
    """The database container may still be starting. Retry instead of crashing."""
    for i in range(attempts):
        try:
            store.init_schema()
            return
        except Exception as e:  # noqa: BLE001
            log(f"database not ready ({e}); retry {i + 1}/{attempts}")
            time.sleep(2)
    raise SystemExit("scanner database never became ready")


def main():
    wait_for_db()

    srv = api.serve()
    threading.Thread(target=srv.serve_forever, daemon=True, name="api").start()
    log(f"api listening on {os.environ.get('SCANNER_API_ADDR', ':9090')}"
        + ("" if os.environ.get("SCANNER_API_TOKEN") else " (SCANNER_API_TOKEN unset: refusing all but /healthz)"))

    interval_h = float(os.environ.get("SCAN_INTERVAL_HOURS", "168"))
    while True:
        try:
            sweep()
        except Exception as e:  # noqa: BLE001 - keep the scheduler and API alive
            log(f"sweep failed: {e}")
        if interval_h <= 0:
            srv.shutdown()
            return 0
        log(f"sleeping {interval_h}h until next sweep")
        time.sleep(interval_h * 3600)


if __name__ == "__main__":
    sys.exit(main())
