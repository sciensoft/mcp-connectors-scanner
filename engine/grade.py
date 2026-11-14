"""Deterministic grading, rule based, no judgement calls (research doc, section 6).

Input is a normalized findings summary for one connector. Output is a letter
grade plus the reason, so the catalogs page can say why something got an F.

Grades:
  F  quarantine candidate: any MAL-* advisory on the pinned version, or a
     confirmed malicious-code / tool-poisoning finding.
  D  CRITICAL CVE with a fix available, or an unresolved high-confidence
     heuristic finding.
  C  HIGH CVE, or three or more MEDIUM CVEs.
  B  only LOW, or one or two MEDIUM findings.
  A  clean across every scanner that ran.
  ?  not graded: nothing could be scanned (manual lane, resolution failed).

Reachability triage (the swarm phase in the research doc) is not implemented
yet, so v1 treats every finding as reachable. That is the conservative
direction: it can over-penalise, it cannot hide a real problem.
"""
from dataclasses import dataclass, field

SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


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
        return Grade("?", "not graded: " + why)

    crit = f.cve_counts.get("CRITICAL", 0)
    high = f.cve_counts.get("HIGH", 0)
    med = f.cve_counts.get("MEDIUM", 0)
    low = f.cve_counts.get("LOW", 0) + f.cve_counts.get("UNKNOWN", 0)

    if (crit and f.critical_with_fix) or f.heuristic_hits:
        bits = []
        if crit and f.critical_with_fix:
            bits.append(f"{crit} critical CVE(s) with a fix available")
        if f.heuristic_hits:
            bits.append(f"{len(f.heuristic_hits)} malicious-code heuristic hit(s)")
        return Grade("D", "; ".join(bits))
    if crit or high or med >= 3:
        return Grade("C", f"{crit} critical, {high} high, {med} medium CVE(s)")
    if med or low:
        return Grade("B", f"{med} medium, {low} low CVE(s) only")
    return Grade("A", "clean across all scanners that ran")
