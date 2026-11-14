# 26. Connector security scanner as a separate, isolated service

- **Status**: Proposed
- **Date**: 2026-11-14

## Context

The catalog holds roughly 250 third-party connectors that users install and run on their machines. We need recurring security analysis of them: known CVEs, known-malicious versions, malicious-code heuristics, and MCP tool poisoning. The research and tool selection are in `.docs/security/connector-scan-engine-research.md` (Trivy, OSV-Scanner, GuardDog, Cisco mcp-scanner; letter grades A to F).

Scanning executes or unpacks untrusted third-party code. The server holds user connections, tunnel state, the database, and secrets. Those two concerns must not share a trust boundary.

The owner also wants this to need very little ongoing involvement: results should appear on the catalogs page without manual runs.

## Decision

1. **New component: `scanner/`**, a sibling of `server/` and `desktop/`. It is a fourth architectural piece beside the desktop client, the tunnel server, and the database. Service name `mcp-scanner`, container `mcpc-scanner`, added to `docker-compose.yaml` on the `mcpc_vnet` network.
2. **Isolation.** The scanner runs in its own container image (later possibly its own Kubernetes pod). It gets no database credentials, no `env_file`, and no user secrets. Executing untrusted packages happens only inside this boundary, and black-box scans of connectors need a further sandbox (no network, no HOME), decided in a follow-up.
3. **Scheduled and hands-off.** A timer triggers the run (monthly full scan as the baseline, weekly feasible for the deterministic phase). Connectors with zero findings are graded by script alone. Human involvement is limited to reviewing F grades.
4. **One-way reporting.** The scanner pushes signed results to a narrow ingest endpoint on the server. The server never calls into the scanner. Reading the catalog is through a read-only feed, not database access.
5. **Simple server side.** The server only stores and displays grades. A `security_scans` table holds the history, with the latest grade and last-scanned time denormalized onto the catalog entry for badges on the catalogs page.
6. **Grades are advisory.** An F flags the connector for human review and may produce a draft migration, but nothing is auto-removed, so a false positive cannot silently pull a connector.

## Consequences

- Positive: a compromised scan container cannot reach the database or user secrets, and the server stays small.
- Positive: grades become visible in the catalog UI with no manual runs.
- Cost: one more service to build, deploy, and monitor, plus a signing and ingest mechanism to design.
- Cost: scanner findings can be noisy, so F handling stays human-approved.
- Deferred, to capture in `.docs/todos/`: ingest endpoint and signing scheme, sandbox choice (bwrap or podman), final cadence, whether grades are user-visible or internal at first, and the Kubernetes pod migration.
- Related finding, not part of this decision: `docker-compose.yaml` uses a default database password and publishes Postgres on host port 5432. Worth a separate hardening item.
