"""Deterministic grading, rule based, no judgement calls (research doc, section 6).

Input is a normalized findings summary for one connector. Output is a letter
grade plus the reason, so the catalogs page can say why something got an F.

Grades:
  F  quarantine candidate: any MAL-* advisory on the pinned version, or a
     confirmed malicious-code / tool-poisoning finding.
  D  CRITICAL CVE with a fix available, or a strong malicious-code signal
     (obfuscated code, download-and-execute). Capability findings never count.
  C  HIGH CVE, or three or more MEDIUM CVEs.
  B  only LOW, or one or two MEDIUM findings.
  A  clean across every scanner that ran.
  ?  not yet assessed: no evidence to grade on. Used whenever no package was
     resolved and examined (manual lane, resolution failed, empty repo), for every
     letter. Not graded is not safe, and never blocks anything.
     Also used when a scanner crashed or timed out and the rest looked clean:
     partial evidence never earns an A or B.
     Also used when no package was resolved: an A or B needs real evidence,
     never an empty result.

Reachability triage (the swarm phase in the research doc) is not implemented
yet, so v1 treats every finding as reachable. That is the conservative
direction: it can over-penalise, it cannot hide a real problem.
"""
from dataclasses import dataclass, field

SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Which code-heuristic findings can lower a grade. Decision log, entry 4: the
# "capability" rules only say what a package can do (network, files, processes),
# which a connector is meant to do, so they are listed as information and never
# lower a grade. Of the "threat" rules, only these describe hiding or running
# something, so only these give a D. Everything else is still recorded and shown.
STRONG_HEURISTICS = frozenset({
    "threat-runtime-obfuscation-base64exec",
    "threat-runtime-obfuscation",
    "threat-process-download-exec",
})


@dataclass
class Findings:
    scanned: bool = False                 # at least one scanner actually ran
    cve_counts: dict = field(default_factory=dict)   # severity -> count
    critical_with_fix: bool = False
    mal_advisories: list = field(default_factory=list)   # OSV MAL-* ids
    poisoning_hits: list = field(default_factory=list)   # mcp-scanner findings
    heuristic_hits: list = field(default_factory=list)   # guarddog findings
    errors: list = field(default_factory=list)
    # Evidence kept for transparency (ADR-0026 decision 6): the grade alone is
    # never the whole story, users can see what is inside and why.
    vulnerabilities: list = field(default_factory=list)  # one dict per finding
    packages: list = field(default_factory=list)         # flat resolved package list
    dependency_edges: list = field(default_factory=list) # {"from": id, "to": [ids]}
    tools: dict = field(default_factory=dict)            # scanner name -> version
    seen_vulns: set = field(default_factory=set)         # dedupe keys, internal
    seen_packages: set = field(default_factory=set)      # dedupe keys, internal


@dataclass
class Grade:
    letter: str
    reason: str


def grade(f: Findings) -> Grade:
    if f.mal_advisories:
        return Grade("F", "known-malicious package advisory: " + ", ".join(f.mal_advisories[:3]))
    if f.poisoning_hits:
        return Grade("F", f"{len(f.poisoning_hits)} MCP tool-poisoning finding(s)")

    if not f.scanned:
        why = f.errors[0] if f.errors else "no scanner could run"
        return Grade("?", "not yet assessed: " + why)

    # Every grade has to rest on evidence. With no resolved package there is nothing
    # that was actually examined, so there is no basis for any letter, good or bad.
    # (F is above this: a named advisory is evidence by itself.) Not graded is not
    # the same as safe, and it never blocks anything.
    if not f.packages:
        why = f.errors[0][:120] if f.errors else "nothing was resolved, so there was nothing to check"
        return Grade("?", "not yet assessed: " + why)

    crit = f.cve_counts.get("CRITICAL", 0)
    high = f.cve_counts.get("HIGH", 0)
    med = f.cve_counts.get("MEDIUM", 0)
    low = f.cve_counts.get("LOW", 0) + f.cve_counts.get("UNKNOWN", 0)

    strong = [h for h in f.heuristic_hits if h in STRONG_HEURISTICS]
    if (crit and f.critical_with_fix) or strong:
        bits = []
        if crit and f.critical_with_fix:
            bits.append(f"{crit} critical CVE(s) with a fix available")
        if strong:
            bits.append(f"{len(strong)} strong malicious-code signal(s): " + ", ".join(sorted(strong)))
        return Grade("D", "; ".join(bits))
    if crit or high or med >= 3:
        return Grade("C", f"{crit} critical, {high} high, {med} medium CVE(s)")
    # A scanner that crashed or timed out means the result is incomplete. A bad grade
    # can only get worse with more data, so C, D and F stand. But a clean-looking A or
    # B must never be awarded on partial evidence: say so instead of implying safety.
    if f.errors:
        return Grade("?", "partially scanned, not graded: " + f.errors[0][:120])
    if med or low:
        return Grade("B", f"{med} medium, {low} low CVE(s) only")
    noted = len(f.heuristic_hits)
    extra = f"; {noted} capability note(s) listed, none concerning" if noted else ""
    return Grade("A", "clean across all scanners that ran, "
                      f"{len(f.packages)} package(s) checked" + extra)
