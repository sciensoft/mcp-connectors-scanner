# 26. Connector security scanner as a separate, isolated service

- **Status**: Proposed
- **Date**: 2026-11-14

## Context

The catalog holds roughly 250 third-party connectors that users install and run on their machines. We need recurring security analysis of them: known CVEs, known-malicious versions, malicious-code heuristics, and MCP tool poisoning. The research and tool selection are in `.docs/security/connector-scan-engine-research.md` (Trivy, OSV-Scanner, GuardDog, Cisco mcp-scanner; letter grades A to F).

Scanning executes or unpacks untrusted third-party code. The server holds user connections, tunnel state, the database, and secrets. Those two concerns must not share a trust boundary.

The owner also wants this to need very little ongoing involvement: results should appear on the catalogs page without manual runs.

## Decision

1. **New component: `scanner/`**, a sibling of `server/` and `desktop/`. It is a fourth architectural piece beside the desktop client, the tunnel server, and the database. Service name `mcp-scanner`, container `mcpc-scanner`, added to `docker-compose.yaml` on the `mcpc_vnet` network.
2. **Isolation.** The scanner runs in its own container image (later possibly its own Kubernetes pod). It gets no credentials for the server's database, no `env_file`, and no user secrets. It has its own separate database (decision 4). Executing untrusted packages happens only inside this boundary, and black-box scans of connectors need a further sandbox (no network, no HOME), decided in a follow-up.
3. **Scheduled and hands-off.** A timer triggers the run (monthly full scan as the baseline, weekly feasible for the deterministic phase). Connectors with zero findings are graded by script alone. Human involvement is limited to reviewing F grades.
4. **The scanner owns its data and exposes an API (microservice boundary).** The scanner has its own database, separate from the server's. All scan data (grades, findings, dependency trees, coverage matrices, history) lives there and nowhere else. The scanner serves a read-only HTTP API. The server is a thin consumer: it fetches grades and evidence from that API to render the catalogs page, and it holds no scan tables, no scoring logic, and no knowledge of how assessment works. The only thing the scanner needs from the server is the list of catalog entries to scan, obtained through a small read-only catalog feed. The scanner never receives database credentials or user secrets.
5. **Server side stays minimal.** The server stores nothing about scans. It calls the scanner API (internal network only), caches responses briefly, and shows a badge and a transparency page. If the scanner is down the catalogs page still works and simply shows no grade.
6. **Full transparency: store the evidence, not just the grade.** Alongside the letter grade, the scanner reports the complete resolved dependency tree (every direct and transitive package with its version) and the per-finding detail (advisory id, severity, affected package, fixed-in version, which scanner reported it). The scanner stores both and its API exposes them, and the server displays them, so users can see exactly what a connector contains and why it was graded as it was. The product goal is to show the whole truth, including for connectors that grade badly, rather than only a score.
7. **Grades are advisory.** An F flags the connector for human review and may produce a draft migration, but nothing is auto-removed, so a false positive cannot silently pull a connector.

## Consequences

- Positive: a compromised scan container cannot reach the database or user secrets, and the server stays small.
- Positive: the server stays small and knows nothing about assessment, so scan logic, data volume and schema can change without touching the server.
- Positive: grades become visible in the catalog UI with no manual runs.
- Cost: one more service plus its own Postgres to build, deploy, back up and monitor, and an authenticated scanner API to design.
- Cost: scanner findings can be noisy, so F handling stays human-approved.
- Deferred, to capture in `.docs/todos/`: scanner API shape and authentication, the server-side catalog feed, sandbox choice (bwrap or podman), final cadence, whether grades are user-visible or internal at first, and the Kubernetes pod migration.
- Related finding, not part of this decision: `docker-compose.yaml` uses a default database password and publishes Postgres on host port 5432. Worth a separate hardening item.
