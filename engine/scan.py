"""Run the scanners against one Target and return normalized Findings.

Runs INSIDE the scanner container only. Resolution is lockfile-only with
install scripts disabled, so no third-party code executes during a scan.
Every external command goes through run() with a hard timeout, and a failed
tool is recorded as an error, never raised, so one bad connector cannot stop
the whole sweep.

v1 scope: Trivy and OSV-Scanner on resolved dependency trees, GuardDog
heuristics on npm and PyPI packages, Trivy image scan for containers.
The Cisco mcp-scanner stdio mode executes the connector, so it is deliberately
NOT wired in here until the sandbox decision in ADR-0026 is made.
"""
import json
import os
import shutil
import subprocess
import tempfile

from .extract import Target
from .grade import Findings

TIMEOUT = int(os.environ.get("SCAN_TOOL_TIMEOUT", "300"))


def run(cmd, cwd=None, timeout=TIMEOUT):
    """Return (exit_code, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timeout after {timeout}s: {' '.join(cmd[:3])}"
    except FileNotFoundError:
        return -2, "", f"tool not found: {cmd[0]}"


def _trivy(path, f: Findings, mode="fs"):
    code, out, err = run(["trivy", mode, "--quiet", "--format", "json",
                          "--scanners", "vuln", path])
    if code not in (0,):
        f.errors.append(f"trivy {mode}: {err.strip()[:200] or code}")
        return
    f.scanned = True
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        f.errors.append("trivy: unparseable output")
        return
    for res in data.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            sev = (v.get("Severity") or "UNKNOWN").upper()
            f.cve_counts[sev] = f.cve_counts.get(sev, 0) + 1
            if sev == "CRITICAL" and v.get("FixedVersion"):
                f.critical_with_fix = True


def _osv(path, f: Findings):
    code, out, err = run(["osv-scanner", "scan", "source", "--format", "json", "-r", path])
    # osv-scanner exits 1 when it finds vulnerabilities, which is not an error.
    if code not in (0, 1):
        f.errors.append(f"osv-scanner: {err.strip()[:200] or code}")
        return
    f.scanned = True
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return
    for r in data.get("results") or []:
        for pkg in r.get("packages") or []:
            for v in pkg.get("vulnerabilities") or []:
                vid = v.get("id", "")
                if vid.startswith("MAL-"):
                    f.mal_advisories.append(vid)


def _guarddog(eco, package, version, f: Findings):
    cmd = ["guarddog", eco, "scan", package, "--output-format", "json"]
    if version:
        cmd += ["--version", version]
    code, out, err = run(cmd)
    if code != 0:
        f.errors.append(f"guarddog: {err.strip()[:200] or code}")
        return
    f.scanned = True
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return
    for rule, hit in (data.get("results") or {}).items():
        if hit:
            f.heuristic_hits.append(rule)


def _resolve_npm(t: Target, work: str, f: Findings) -> bool:
    spec = f"{t.package}@{t.version}" if t.version else t.package
    code, _, err = run(["npm", "install", spec, "--package-lock-only",
                        "--ignore-scripts", "--no-audit", "--no-fund"], cwd=work)
    if code != 0:
        f.errors.append(f"npm resolve: {err.strip()[:200] or code}")
        return False
    return True


def _resolve_pypi(t: Target, work: str, f: Findings) -> bool:
    req = f"{t.package}=={t.version}" if t.version else t.package
    with open(os.path.join(work, "requirements.in"), "w") as fh:
        fh.write(req + "\n")
    code, out, err = run(["uv", "pip", "compile", "requirements.in",
                          "-o", "requirements.txt"], cwd=work)
    if code != 0:
        f.errors.append(f"uv resolve: {err.strip()[:200] or code}")
        return False
    return True


def _clone(t: Target, work: str, f: Findings) -> bool:
    if not t.repo:
        f.errors.append("no repository to clone")
        return False
    url = t.repo if "://" in t.repo else f"https://github.com/{t.repo}.git"
    code, _, err = run(["git", "clone", "--quiet", "--depth", "1", url, "src"], cwd=work)
    if code != 0:
        f.errors.append(f"git clone: {err.strip()[:200] or code}")
        return False
    if t.ref:
        run(["git", "fetch", "--quiet", "--depth", "1", "origin", t.ref], cwd=os.path.join(work, "src"))
        run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=os.path.join(work, "src"))
    return True


def scan(t: Target) -> Findings:
    f = Findings()
    if t.ecosystem in ("manual", "unknown"):
        f.errors.append("; ".join(t.notes) or f"ecosystem {t.ecosystem} not scannable in v1")
        return f

    base = os.environ.get("SCAN_WORK_DIR", tempfile.gettempdir())
    work = tempfile.mkdtemp(prefix=f"{t.entry_id}-", dir=base)
    try:
        if t.ecosystem == "container":
            _trivy(t.image, f, mode="image")
        elif t.ecosystem == "npm":
            if _resolve_npm(t, work, f):
                _trivy(work, f)
                _osv(work, f)
            _guarddog("npm", t.package, t.version, f)
        elif t.ecosystem == "pypi":
            if _resolve_pypi(t, work, f):
                _trivy(work, f)
                _osv(work, f)
            _guarddog("pypi", t.package, t.version, f)
        elif t.ecosystem in ("go", "git"):
            if _clone(t, work, f):
                src = os.path.join(work, "src")
                _trivy(src, f)
                _osv(src, f)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return f
