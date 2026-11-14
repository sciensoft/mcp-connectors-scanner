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
import stat
import tempfile
import time
import urllib.request

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


_VERSION_CACHE = {}


def _mark_ran(f: Findings, tool: str) -> None:
    """Record that a scanner really ran, with its version, so the coverage
    matrix never claims a check that was skipped or failed."""
    if tool not in _VERSION_CACHE:
        code, out, _ = run([tool, "--version"], timeout=30)
        _VERSION_CACHE[tool] = (out.strip().splitlines() or ["unknown"])[0][:80] if code == 0 else "unknown"
    f.tools[tool] = _VERSION_CACHE[tool]


def _add_vuln(f: Findings, v: dict) -> None:
    """Record one finding once. Trivy and OSV overlap, so dedupe by package+id."""
    key = (v.get("package", ""), v.get("installed", ""), v.get("id", ""))
    if key in f.seen_vulns:
        return
    f.seen_vulns.add(key)
    f.vulnerabilities.append(v)
    sev = v.get("severity", "UNKNOWN")
    f.cve_counts[sev] = f.cve_counts.get(sev, 0) + 1
    if sev == "CRITICAL" and v.get("fixed_in"):
        f.critical_with_fix = True


def _trivy(path, f: Findings, mode="fs"):
    code, out, err = run(["trivy", mode, "--quiet", "--format", "json",
                          "--scanners", "vuln", "--list-all-pkgs", path])
    if code not in (0,):
        f.errors.append(f"trivy {mode}: {err.strip()[:200] or code}")
        return
    f.scanned = True
    _mark_ran(f, "trivy")
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        f.errors.append("trivy: unparseable output")
        return
    for res in data.get("Results") or []:
        target = res.get("Target", "")
        for pkg in res.get("Packages") or []:
            pid = pkg.get("ID") or f"{pkg.get('Name', '')}@{pkg.get('Version', '')}"
            f.packages.append({
                "id": pid,
                "name": pkg.get("Name", ""),
                "version": pkg.get("Version", ""),
                "license": ", ".join(pkg.get("Licenses") or []),
                "direct": pkg.get("Relationship") == "direct",
                "source": target,
            })
            if pkg.get("DependsOn"):
                f.dependency_edges.append({"from": pid, "to": list(pkg["DependsOn"])})
        for v in res.get("Vulnerabilities") or []:
            _add_vuln(f, {
                "id": v.get("VulnerabilityID", ""),
                "severity": (v.get("Severity") or "UNKNOWN").upper(),
                "package": v.get("PkgName", ""),
                "installed": v.get("InstalledVersion", ""),
                "fixed_in": v.get("FixedVersion", ""),
                "title": (v.get("Title") or "")[:200],
                "url": v.get("PrimaryURL", ""),
                "source": "trivy",
            })


def _osv(path, f: Findings):
    code, out, err = run(["osv-scanner", "scan", "source", "--format", "json", "-r", path])
    # osv-scanner exits 1 when it finds vulnerabilities, which is not an error.
    if code not in (0, 1):
        f.errors.append(f"osv-scanner: {err.strip()[:200] or code}")
        return
    f.scanned = True
    _mark_ran(f, "osv-scanner")
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return
    for r in data.get("results") or []:
        for pkg in r.get("packages") or []:
            info = pkg.get("package") or {}
            for v in pkg.get("vulnerabilities") or []:
                vid = v.get("id", "")
                if vid.startswith("MAL-"):
                    f.mal_advisories.append(vid)
                sev = "UNKNOWN"
                for grp in pkg.get("groups") or []:
                    if vid in (grp.get("ids") or []) and grp.get("max_severity"):
                        score = float(grp["max_severity"])
                        sev = ("CRITICAL" if score >= 9 else "HIGH" if score >= 7
                               else "MEDIUM" if score >= 4 else "LOW")
                _add_vuln(f, {
                    "id": vid,
                    "severity": "CRITICAL" if vid.startswith("MAL-") else sev,
                    "package": info.get("name", ""),
                    "installed": info.get("version", ""),
                    "fixed_in": "",
                    "title": (v.get("summary") or "")[:200],
                    "url": f"https://osv.dev/{vid}" if vid else "",
                    "source": "osv-scanner",
                })


def _guarddog(eco, package, version, f: Findings):
    cmd = ["guarddog", eco, "scan", package, "--output-format", "json"]
    if version:
        cmd += ["--version", version]
    code, out, err = run(cmd)
    if code != 0:
        f.errors.append(f"guarddog: {err.strip()[:200] or code}")
        return
    f.scanned = True
    _mark_ran(f, "guarddog")
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
    f.tools["engine"] = "resolve-without-execution"
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
    f.tools["engine"] = "resolve-without-execution"
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


def _resolve_maven(t: Target, work: str, f: Findings) -> bool:
    """Fetch the package's pom.xml from Maven Central. No build, no execution:
    Trivy and OSV read the declared dependencies straight from the pom."""
    group, _, artifact = t.package.partition(":")
    if not (group and artifact and t.version):
        f.errors.append("maven coordinate needs groupId:artifactId:version")
        return False
    path = f"{group.replace('.', '/')}/{artifact}/{t.version}/{artifact}-{t.version}.pom"
    url = f"https://repo1.maven.org/maven2/{path}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(os.path.join(work, "pom.xml"), "wb") as fh:
            fh.write(r.read())
    except Exception as e:  # noqa: BLE001 - recorded, never raised
        f.errors.append(f"maven pom fetch: {e}")
        return False
    f.tools["engine"] = "resolve-without-execution"
    return True


def _remove_tree(path: str) -> None:
    """Delete a work dir and PROVE it is gone. Read-only files (git packs, npm
    caches) can make rmtree fail silently, so fix permissions and retry."""
    def _force(func, p, _exc):
        try:
            os.chmod(p, stat.S_IRWXU)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_force)
    if os.path.exists(path):
        subprocess.run(["rm", "-rf", path], check=False)
    if os.path.exists(path):
        print(f"WARNING: could not remove work dir {path}", flush=True)


def cleanup_stale(max_age_seconds: int = 3600) -> int:
    """Remove work dirs left behind by a crash or restart. Called at the start of
    every sweep so garbage can never accumulate across runs."""
    base = os.environ.get("SCAN_WORK_DIR", tempfile.gettempdir())
    removed = 0
    now = time.time()
    try:
        names = os.listdir(base)
    except OSError:
        return 0
    for name in names:
        p = os.path.join(base, name)
        try:
            if os.path.isdir(p) and now - os.path.getmtime(p) > max_age_seconds:
                _remove_tree(p)
                removed += 1
        except OSError:
            continue
    return removed


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
        elif t.ecosystem == "maven":
            if _resolve_maven(t, work, f):
                _trivy(work, f)
                _osv(work, f)
        elif t.ecosystem in ("go", "git"):
            if _clone(t, work, f):
                src = os.path.join(work, "src")
                _trivy(src, f)
                _osv(src, f)
    finally:
        _remove_tree(work)
    return f
