# mcp-connectors-scanner

Grades MCP connectors from **A to F** from real evidence, publishes the full dependency tree behind each grade, and states plainly what it does **not** check.

It is open source for one reason: trust. Anyone can read exactly how a grade is produced, check that the rules are applied the same way to everyone, and see what changed and why ([decision log](./docs/decision-log.md)). Running it yourself is welcome, but it is not the point.

## What it does

Once a week it takes the connector catalog, resolves each connector's dependencies **without installing or running anything**, and checks them with:

- **Trivy** and **OSV-Scanner**: known vulnerabilities and known-malicious package versions.
- **GuardDog**: suspicious code patterns (npm and PyPI packages).

Results are saved to the scanner's own database and served by a small read-only API.

## How a grade is decided

| Grade | Meaning |
| --- | --- |
| **A** | Clean across every scanner that ran, with real packages checked |
| **B** | Only low-severity findings |
| **C** | A high-severity vulnerability, or three or more medium |
| **D** | A critical vulnerability with a fix available, or a strong malicious-code signal |
| **F** | A known-malicious package version. Flagged for human review, never removed automatically |
| **?** | Not yet assessed: no evidence to grade on. Not the same as safe |

Every grade needs evidence. If nothing was resolved and examined, there is no grade. A scanner that crashed can never produce an A or B. The rules are in [`engine/grade.py`](./engine/grade.py), small enough to read in one sitting.

**What it does not check** is published with every result (`/v1/coverage`). A grade is a statement about the checks that ran, never a guarantee.

## Quick start

Tests: `make test`. Run: build the image (`podman build -t mcp-connectors-scanner .`) and start it with the compose file. It needs a Postgres database (its own role and database, created by `init-db.sh`), a catalog feed URL and token, and an API token. The scanner executes inside its container only, never on the host.

## Documentation

- [Guide](./docs/guide.md): how it works, how to run it, what to do when something looks wrong.
- [Decision log](./docs/decision-log.md): what we saw, what we decided, and why. Every change to the grading rules is recorded here.
- [Architecture decision](./docs/adrs/0001-connector-security-scanner-service.md): why it is a separate, isolated service.
- [Research](./docs/security/connector-scan-engine-research.md): which tools we looked at, which we chose, and the three-phase design (fixed checks first, then agent triage, then human QA).
- [Agent swarm](./docs/agent-swarm/README.md): the tool that runs many headless Claude workers from one registry. It is the planned triage phase, and it is not built into the scanner yet.
- **For contributors and agents**: [`AGENTS.md`](./AGENTS.md) is the cold-start brief, with the rules under [`.agents/rules/`](./.agents/rules/).

## Reporting problems

- **Bugs, ideas, questions**: open a [GitHub issue](../../issues).
- **Security vulnerabilities**: do **not** open a public issue. See [`SECURITY.md`](./SECURITY.md).

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md).

## License

Apache 2.0, see [`LICENSE`](./LICENSE).
