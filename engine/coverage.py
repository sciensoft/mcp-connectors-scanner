"""Coverage matrix: what a scan checks, and what it does not.

Single source of truth for the transparency page (ADR-0026, decision 6). Every
scan result carries this matrix, so a user can see exactly what "scanned"
means for a connector, including the limits. Keep it honest: when a check is
added or removed in scan.py, change it here in the same commit.

status values:
  checked      the scanner ran and covers this class for the connector's kind
  partial      covered for some connector kinds or with known gaps (see note)
  not_covered  deliberately outside this engine, stated openly
"""

# Which ecosystems each check applies to. "all" means every scannable kind.
CHECKS = [
    {
        "id": "known-cve",
        "title": "Known vulnerabilities (CVE and GHSA advisories)",
        "scanners": ["trivy", "osv-scanner"],
        "applies_to": ["npm", "pypi", "go", "git", "maven", "container"],
        "status": "checked",
        "note": "Vulnerability databases refresh automatically, so re-scanning an "
                "unchanged version still surfaces newly published advisories.",
    },
    {
        "id": "known-malicious",
        "title": "Known-malicious package versions (OpenSSF MAL advisories)",
        "scanners": ["osv-scanner"],
        "applies_to": ["npm", "pypi", "go", "git", "maven"],
        "status": "checked",
        "note": "A hit here is an instant F grade.",
    },
    {
        "id": "dependency-tree",
        "title": "Full dependency tree and licenses recorded",
        "scanners": ["trivy"],
        "applies_to": ["npm", "pypi", "go", "git", "maven", "container"],
        "status": "checked",
        "note": "Every direct and transitive package with its version is published "
                "with the result. Link detail depends on what the lockfile records.",
    },
    {
        "id": "malicious-code-heuristics",
        "title": "Suspicious code patterns (exfiltration, install-script payloads, obfuscation, typosquatting)",
        "scanners": ["guarddog"],
        "applies_to": ["npm", "pypi"],
        "status": "partial",
        "note": "Heuristic, so hits are signals rather than proof. Not yet run on Go, "
                "git-pinned, Maven or container connectors.",
    },
    {
        "id": "tool-poisoning",
        "title": "MCP tool poisoning (hidden instructions in tool descriptions, lookalike tools)",
        "scanners": ["cisco-mcp-scanner"],
        "applies_to": [],
        "status": "not_covered",
        "note": "Planned. It requires starting the connector, so it waits for the "
                "sandbox decision in ADR-0026.",
    },
    {
        "id": "install-time-execution",
        "title": "Install and resolve without running third-party code",
        "scanners": ["engine"],
        "applies_to": ["npm", "pypi", "maven"],
        "status": "checked",
        "note": "Dependency trees are resolved lockfile-only with install scripts "
                "disabled, so scanning never executes the package.",
    },
    {
        "id": "runtime-response-attacks",
        "title": "Malicious instructions inside tool responses at runtime",
        "scanners": [],
        "applies_to": [],
        "status": "not_covered",
        "note": "Description-level scanning cannot see attacks carried in responses. "
                "This is a runtime concern for the desktop client and gateway.",
    },
    {
        "id": "binary-provenance",
        "title": "Prebuilt binaries and unresolvable sources",
        "scanners": [],
        "applies_to": [],
        "status": "not_covered",
        "note": "Graded as not-graded (?) rather than guessed at.",
    },
]


def matrix(ecosystem: str, tools_run: list) -> list:
    """Per-result view: for this connector's ecosystem, what applied and what
    actually ran. A check that applies but whose scanner did not run is reported
    as 'skipped', never silently counted as passed."""
    out = []
    for c in CHECKS:
        applies = ecosystem in c["applies_to"]
        ran = [s for s in c["scanners"] if s in tools_run]
        if c["status"] == "not_covered":
            state = "not_covered"
        elif not applies:
            state = "not_applicable"
        elif ran:
            state = "checked"
        else:
            state = "skipped"
        out.append({"id": c["id"], "title": c["title"], "state": state,
                    "scanners_run": ran, "note": c["note"]})
    return out
