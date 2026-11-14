#!/usr/bin/env python3
"""Collect the latest grades from the scanner API and write two PUBLIC files.

  full.json     everything the API holds per connector (for the release artifact)
  summary.json  grades, reasons and counts only (for the results branch)

Nothing here is published as-is. Every string passes through scrub(), which removes
what must never reach a public repository: internal paths and host names, private
addresses, and anything shaped like a credential. After scrubbing, a final guard
scans the finished files and REFUSES to write them if anything suspicious remains.

Environment: SCANNER_URL (default http://mcp-scanner:9090), SCANNER_API_TOKEN.
Usage: collect.py OUTDIR
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

# (pattern, replacement). Order matters: specific first.
_SCRUBS = [
    (re.compile(r"/work/[A-Za-z0-9_.\-]+(?:/[^\s\"',)]*)?"), "<work-dir>"),
    (re.compile(r"/(?:home|proj|srv|run|tmp|mnt)/[^\s\"',)]+"), "<path>"),
    # Internal names only when they stand alone: not inside a longer public package name
    # such as awslabs-aws-diagram-mcp-server. A hyphen or word character on either side
    # means it is part of something else.
    (re.compile(r"(?:(?<=://)|(?<=@)|(?<![\w.\-/]))(?:mcp-server|mcp-db|mcp-scanner|mcpc-(?:server|scanner|db|sweep)[a-z-]*|sciensoft-ws-\d+|hrollers|doorsystems)(?![\w\-])(?=[:/\s\"',)\]]|$)"), "<internal-host>"),
    (re.compile(r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b|\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"), "<private-ip>"),
    (re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b"), "<private-ip>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer <redacted>"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}"), "<redacted-token>"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), "<redacted-token>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-token>"),
    (re.compile(r"postgres(?:ql)?://[^\s\"']+"), "<redacted-url>"),
]

# What must NOT survive scrubbing. If any matches, abort rather than publish.
_GUARD = re.compile(
    r"/work/|/home/|/proj/|/srv/|sciensoft-ws|hrollers|doorsystems"
    r"|(?:(?<=://)|(?<=@)|(?<![\w.\-/]))(?:mcp-server|mcp-db|mcp-scanner|mcpc-(?:server|scanner|db|sweep))(?![\w\-])"
    r"|\b(?:10|127)\.\d+\.\d+\.\d+\b|\b192\.168\.|postgres(?:ql)?://"
    r"|(?i:bearer\s+[A-Za-z0-9._\-]{8,})|\b(?:ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}"
    r"|\bsk-[A-Za-z0-9_\-]{20,}|\bAKIA[0-9A-Z]{16}\b"
)

SUMMARY_KEYS = ("entry_id", "version", "ecosystem", "grade", "reason", "cve_counts", "scanned_at")


def scrub(value):
    if isinstance(value, str):
        for pat, rep in _SCRUBS:
            value = pat.sub(rep, value)
        return value
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def get(path: str):
    base = os.environ.get("SCANNER_URL", "http://mcp-scanner:9090").rstrip("/")
    token = os.environ["SCANNER_API_TOKEN"]
    req = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def guard(label: str, text: str) -> None:
    m = _GUARD.search(text)
    if m:
        # Report the kind of match and where, never the matched text itself.
        line = text.count("\n", 0, m.start()) + 1
        raise SystemExit(f"collect: REFUSING to write {label}: forbidden pattern near line {line}")


def main(outdir: str) -> int:
    os.makedirs(outdir, exist_ok=True)
    listing = get("/v1/grades")
    rows = listing.get("grades") or listing.get("items") or next(
        (v for v in listing.values() if isinstance(v, list)), [])
    if not rows:
        raise SystemExit("collect: the scanner returned no grades; not publishing an empty file")

    full, summary = [], []
    for row in rows:
        detail = get(f"/v1/grades/{row['entry_id']}")
        detail.pop("id", None)  # internal database ids are not part of the public record
        detail.pop("run_id", None)
        full.append(scrub(detail))
        summary.append(scrub({k: row.get(k) for k in SUMMARY_KEYS}))

    full.sort(key=lambda d: d["entry_id"])
    summary.sort(key=lambda d: d["entry_id"])
    counts = {}
    for s in summary:
        counts[s["grade"]] = counts.get(s["grade"], 0) + 1

    meta = {"generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "connectors": len(summary), "grade_counts": dict(sorted(counts.items()))}
    out_summary = json.dumps({"meta": meta, "grades": summary}, indent=1, sort_keys=True) + "\n"
    out_full = json.dumps({"meta": meta, "grades": full}, indent=1, sort_keys=True) + "\n"

    guard("summary.json", out_summary)
    guard("full.json", out_full)
    open(os.path.join(outdir, "summary.json"), "w", encoding="utf-8").write(out_summary)
    open(os.path.join(outdir, "full.json"), "w", encoding="utf-8").write(out_full)
    print(f"collect: wrote {len(summary)} connectors {meta['grade_counts']}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv[1]))
