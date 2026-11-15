"""What this scanner is made of: tool versions and vulnerability database dates.

Published with every result set so anyone can see exactly what a scan was run with,
and reproduce it. Reads only version numbers and database timestamps. Never paths,
hosts or settings.
"""
import json
import os
import re
import subprocess

# (label, command, pattern that pulls the version out of the first lines of output)
_TOOLS = (
    ("trivy", ["trivy", "--version"], r"Version:\s*(\S+)"),
    ("osv-scanner", ["osv-scanner", "--version"], r"osv-scanner version:\s*(\S+)"),
    ("guarddog", ["guarddog", "--version"], r"(\d+\.\d+[\w.\-]*)"),
    ("uv", ["uv", "--version"], r"uv\s+(\S+)"),
)

# Trivy keeps one metadata.json next to each database it downloads.
_DATABASES = (
    ("trivy-db", "trivy/db"),
    ("trivy-java-db", "trivy/java-db"),
)
_META_KEYS = ("Version", "UpdatedAt", "DownloadedAt")


def _tool_version(cmd, pattern, run=subprocess.run):
    try:
        out = run(cmd, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(pattern, out)
    return m.group(1) if m else None


def _database(subdir, cache_root):
    try:
        with open(os.path.join(cache_root, subdir, "metadata.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return None
    return {k: meta[k] for k in _META_KEYS if k in meta}


def collect(cache_root=None, run=subprocess.run):
    """Return {'tools': {...}, 'databases': {...}}. A missing piece is None, never a guess."""
    cache_root = cache_root or os.path.join(os.environ.get("HOME", "/home/scanner"), ".cache")
    return {
        "tools": {label: _tool_version(cmd, pat, run) for label, cmd, pat in _TOOLS},
        "databases": {label: _database(sub, cache_root) for label, sub in _DATABASES},
    }
