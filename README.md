# scanner

Separate service that grades every catalog connector on a schedule and reports
the grades back to the server. Sibling of `server/` and `desktop/`.

Status: design only, nothing implemented yet.

## Principles

- Isolated: runs in its own container, later possibly its own Kubernetes pod.
  It executes untrusted third-party packages, so it gets no database
  credentials, no `.env`, and no user secrets.
- Scheduled and hands-off: a timer triggers a run, zero-finding connectors are
  graded automatically, no human involvement.
- One-way reporting: the scanner pushes signed results to a narrow ingest
  endpoint on the server. The server never calls into the scanner.
- Simple server side: the server only stores and shows grades (A to F) on the
  catalogs page. An F flags the connector for human review, never auto-removes.

## Design reference

See `.docs/security/connector-scan-engine-research.md` for the tool landscape
(Trivy, OSV-Scanner, GuardDog, Cisco mcp-scanner), the grading rules, and the
open questions (sandbox choice, cadence).

## Planned compose service

- service `mcp-scanner`, container `mcpc-scanner`, on the `mcpc_vnet` network
- no `env_file`, only a read-only catalog feed and a write-back token
