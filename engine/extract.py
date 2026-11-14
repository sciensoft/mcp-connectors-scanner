"""Turn one catalog entry into a scan target: ecosystem, package, version, repo.

Pure functions, no network, no execution, so they are trivially testable.
The catalog has no structured package columns, so everything is derived from
the preferred runtime's command/args (see the research doc, section 3). Old rows
use capitalized Kind/Command/Args keys, pinned rows use lowercase.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Target:
    entry_id: str
    ecosystem: str          # npm | pypi | go | git | container | manual | unknown
    package: str = ""
    version: str = ""
    repo: str = ""          # git URL or owner/repo when known
    ref: str = ""           # git ref/sha for git-pinned entries
    image: str = ""         # container image reference
    runtime_kind: str = ""
    notes: list = field(default_factory=list)


def _pick(d: dict, *keys):
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def _split_npm(spec: str):
    """pkg@1.2.3 or @scope/pkg@1.2.3 -> (name, version)."""
    if spec.startswith("@"):
        head, sep, ver = spec[1:].partition("@")
        return "@" + head, ver if sep else ""
    name, sep, ver = spec.partition("@")
    return name, ver if sep else ""


def _github_repo(text: str) -> str:
    m = re.search(r"github\.com[/:]([^/\s]+/[^/@#.\s]+)", text)
    return m.group(1) if m else ""


def extract(entry: dict, docs_url: str = "") -> Target:
    entry_id = entry["id"]
    kind = entry.get("preferred_runtime") or ""
    runtimes = entry.get("runtimes") or {}
    rt = runtimes.get(kind) or {}
    args = list(_pick(rt, "args", "Args") or [])
    t = Target(entry_id=entry_id, ecosystem="unknown", runtime_kind=kind)

    if not rt:
        t.notes.append("no runtime for preferred_runtime")
        return t

    if kind == "npx":
        toks = [a for a in args if not a.startswith("-")]
        pkg = args[args.index("--package") + 1] if "--package" in args else (toks[0] if toks else "")
        if pkg == "mcp-remote":
            t.ecosystem = "manual"
            t.notes.append("remote via mcp-remote, scan the remote surface not a package")
        elif pkg.startswith("github:"):
            repo, _, ref = pkg[7:].partition("#")
            t.ecosystem, t.repo, t.ref = "git", repo, ref
        elif pkg:
            t.ecosystem = "npm"
            t.package, t.version = _split_npm(pkg)
            t.repo = _github_repo(docs_url)
        return t

    if kind == "uvx":
        if "--from" in args:
            src = args[args.index("--from") + 1]
            t.ecosystem = "git"
            t.repo = _github_repo(src)
            t.ref = src.rsplit("@", 1)[1] if "@" in src.split("//", 1)[-1] else ""
            return t
        toks, skip = [], False
        for a in args:
            if skip:
                skip = False
                continue
            if a.startswith("--"):
                skip = "=" not in a
                continue
            if a.startswith("-"):
                continue
            toks.append(a)
        if toks:
            spec = toks[0]
            t.ecosystem = "pypi"
            t.package = re.split(r"[\[=<>@]", spec)[0]
            m = re.search(r"==([^\s,;]+)", spec)
            t.version = m.group(1) if m else ""
            t.repo = _github_repo(docs_url)
        return t

    if kind in ("go", "binary"):
        if len(args) >= 2 and args[0] in ("install", "run"):
            mod, _, ver = args[1].partition("@")
            t.ecosystem, t.package, t.version = "go", mod, ver
            t.repo = _github_repo(mod) or _github_repo(docs_url)
        else:
            t.ecosystem = "manual"
            t.notes.append("binary entry, manual lane")
        return t

    if kind in ("container", "docker", "podman"):
        imgs = [a for a in args if "/" in a and not a.startswith("-") and "=" not in a]
        if imgs:
            t.ecosystem, t.image = "container", imgs[-1]
        return t

    if kind == "jbang":
        # Args[1] is whatever `jbang run <X>` accepts (ADR-0018): a GitHub repo,
        # a Maven coordinate groupId:artifactId:version, a gist, or an https URL.
        spec = next((a for a in args if a not in ("run",) and not a.startswith("-")), "")
        if re.fullmatch(r"[\w.\-]+:[\w.\-]+(:[\w.\-]+)?", spec):
            parts = spec.split(":")
            t.ecosystem = "maven"
            t.package = parts[0] + ":" + parts[1]
            t.version = parts[2] if len(parts) > 2 else ""
            t.repo = _github_repo(docs_url)
        elif "github.com" in spec:
            t.ecosystem = "git"
            t.repo = _github_repo(spec)
        elif _github_repo(docs_url):
            t.ecosystem = "git"
            t.repo = _github_repo(docs_url)
            t.notes.append("jbang spec not a repo, scanning docs_url repository")
        else:
            t.ecosystem = "manual"
            t.notes.append("jbang spec is a gist or URL with no known repository")
        return t

    if kind in ("node", "python"):
        t.ecosystem = "git"
        t.repo = next((_github_repo(a) for a in args if "github.com" in a), "") or _github_repo(docs_url)
        return t

    t.notes.append(f"runtime kind {kind!r} not handled")
    return t
