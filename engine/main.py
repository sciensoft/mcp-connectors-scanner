"""Scanner entrypoint: scheduled full sweep of the catalog.

Flow per sweep:
  1. Pull the list of ready catalog entries from the server's read-only feed.
  2. extract -> scan -> grade each one, never letting one failure stop the sweep.
  3. Write every result to SCAN_OUT_DIR as JSON (always, so a failed upload
     loses nothing), then push the batch to the server's ingest endpoint.

Environment (no database access, no .env passthrough, see ADR-0026):
  SCAN_FEED_URL      read-only catalog feed on the server
  SCAN_INGEST_URL    narrow endpoint that accepts signed grade batches
  SCAN_INGEST_TOKEN  shared secret used to sign the batch (HMAC-SHA256)
  SCAN_INTERVAL_HOURS  hours between sweeps, default 168 (weekly); 0 = run once
  SCAN_WORK_DIR / SCAN_OUT_DIR  ephemeral work dir and result dir
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

from .coverage import matrix
from .extract import extract
from .grade import grade
from .scan import cleanup_stale, scan

OUT_DIR = os.environ.get("SCAN_OUT_DIR", "/out")


def log(msg: str):
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def fetch_catalog() -> list:
    url = os.environ["SCAN_FEED_URL"]
    req = urllib.request.Request(url, headers={"User-Agent": "mcpc-scanner"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def sign(body: bytes) -> str:
    key = os.environ["SCAN_INGEST_TOKEN"].encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def push(results: list) -> bool:
    url = os.environ.get("SCAN_INGEST_URL")
    if not url or not os.environ.get("SCAN_INGEST_TOKEN"):
        log("push skipped: SCAN_INGEST_URL or SCAN_INGEST_TOKEN not set")
        return False
    body = json.dumps({"results": results}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Scanner-Signature": sign(body),
        "User-Agent": "mcpc-scanner",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            log(f"push ok: HTTP {r.status}, {len(results)} results")
            return True
    except Exception as e:  # noqa: BLE001 - results are already on disk
        log(f"push failed: {e}")
        return False


def sweep():
    started = datetime.now(timezone.utc)
    # Leftovers from a crash or restart: remove them before doing anything else.
    stale = cleanup_stale(max_age_seconds=0)
    if stale:
        log(f"removed {stale} stale work dir(s) from a previous run")
    entries = fetch_catalog()
    log(f"sweep start: {len(entries)} catalog entries")
    results = []
    for entry in entries:
        eid = entry.get("id", "?")
        try:
            target = extract(entry, entry.get("docs_url", ""))
            findings = scan(target)
            g = grade(findings)
            results.append({
                "entry_id": eid,
                "version": target.version or target.ref or target.image,
                "ecosystem": target.ecosystem,
                "grade": g.letter,
                "reason": g.reason,
                "cve_counts": findings.cve_counts,
                "mal_advisories": findings.mal_advisories,
                "heuristic_hits": findings.heuristic_hits,
                "errors": findings.errors,
                # Full evidence for the transparency page (ADR-0026, decision 6)
                "vulnerabilities": findings.vulnerabilities,
                "packages": findings.packages,
                "dependency_edges": findings.dependency_edges,
                "tools": findings.tools,
                "coverage": matrix(target.ecosystem, list(findings.tools)),
                "scanned_at": datetime.now(timezone.utc).isoformat(),
            })
            log(f"{eid}: {g.letter} ({g.reason})")
        except Exception as e:  # noqa: BLE001 - one connector must not stop the sweep
            log(f"{eid}: scanner error: {e}")
            results.append({"entry_id": eid, "grade": "?", "reason": f"scanner error: {e}"})

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"scan-{started.strftime('%Y%m%dT%H%M%SZ')}.json")
    with open(path, "w") as fh:
        json.dump({"started": started.isoformat(), "results": results}, fh, indent=2)
    log(f"results written: {path}")
    push(results)
    counts = {}
    for r in results:
        counts[r["grade"]] = counts.get(r["grade"], 0) + 1
    log(f"sweep done: {counts}")
    leftover = cleanup_stale(max_age_seconds=0)
    if leftover:
        log(f"end-of-sweep cleanup removed {leftover} leftover work dir(s)")


def main():
    interval_h = float(os.environ.get("SCAN_INTERVAL_HOURS", "168"))
    while True:
        try:
            sweep()
        except Exception as e:  # noqa: BLE001 - keep the scheduler alive
            log(f"sweep failed: {e}")
        if interval_h <= 0:
            return 0
        log(f"sleeping {interval_h}h until next sweep")
        time.sleep(interval_h * 3600)


if __name__ == "__main__":
    sys.exit(main())
