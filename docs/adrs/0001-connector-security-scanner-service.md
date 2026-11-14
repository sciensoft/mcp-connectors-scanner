# 1. Connector security scanner as a separate, isolated service

- **Status**: Accepted
- **Date**: 2026-11-14

## Context

The Sciensoft catalog lists roughly 300 third-party MCP connectors that users install and run on their machines. Those connectors need recurring security analysis: known CVEs, known-malicious versions, and malicious-code heuristics.

Scanning unpacks and analyses untrusted third-party code. The application that serves the catalog holds user connections, tunnel state, a database and secrets. Those two concerns must not share a trust boundary.

The owner also wants it to need very little ongoing involvement, and wants the way grades are produced to be open to inspection, because a security grade is only worth something if people can check how it was made.

## Decision

1. **A separate service in its own repository.** The scanner is its own container image and its own codebase, open source. It is not part of the application it grades.
2. **Isolation.** It runs hardened: read-only filesystem, no capabilities, unprivileged user, in-memory work space, no published ports. It receives no credentials for the application's data and no user secrets.
3. **It owns its data.** All scan data (grades, findings, dependency trees, coverage matrices, history) lives in the scanner's own database, reached with its own login that cannot open any other database. The application stores no scan data. It only reads grades from the scanner's read-only API, so if the scanner is off the application simply shows no badge.
4. **It never executes what it scans.** Dependencies are resolved without installing packages or running scripts.
5. **Scheduled and hands-off.** A timer starts a sweep (weekly by default). Connectors are scanned in parallel with a small limit per registry, so no registry sees more than a few of our requests at once.
6. **Full transparency.** Alongside the letter grade, the scanner reports the complete resolved dependency tree, the per-finding detail, the tool versions, and a coverage matrix stating what is and is not checked.
7. **Every grade needs evidence.** With no resolved package there is no grade (`?`, not yet assessed). A crashed scanner can never produce an A or B. See the [decision log](../../docs/decision-log.md).
8. **Grades are advisory.** A bad grade puts a connector on a review list for a human. Nothing is removed automatically, so a false positive cannot silently pull a connector.

## Consequences

- Positive: a compromised scan cannot reach user data, and the application stays small and knows nothing about assessment.
- Positive: anyone can read the grading rules and the history of changes to them.
- Cost: one more service to build, deploy, back up and monitor, and a token-protected API.
- Cost: heuristic findings can be noisy, so only strong signals lower a grade and the rest are listed as information.
- Deferred: sandboxed analysis of how a connector behaves when run (needed for MCP tool-poisoning checks), and reachability analysis. Both are listed under "what it does not check".
