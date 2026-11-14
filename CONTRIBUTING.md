# Contributing to mcp-connectors-scanner

Thanks for considering a contribution. This file covers the bare minimum to get a change landed; the deeper conventions live in [`AGENTS.md`](./AGENTS.md) and the rules under [`.agents/rules/`](./.agents/rules/).

## Development setup

Tests: `make test`. Run: build the image (`podman build -t mcp-connectors-scanner .`) and start it with the compose file; it needs a Postgres database (own role and database, created by `init-db.sh`), a catalog feed URL and token, and an API token. The scanner executes inside its container only, never on the host.

## Branch and PR conventions

- Work on a feature branch off `main`; one logical change per PR.
- PR title is imperative and under 70 characters (it becomes the squash-merge commit subject).
- PR description explains *why* — the *what* is in the diff.
- Link the originating issue or discussion if one exists.

## Code style

- Follow [`.agents/rules/best-practices.md`](./.agents/rules/best-practices.md) — the flat module layout, naming, and language idioms. Keep pure logic free of I/O so it can be tested without a database or network.
- Run the project's formatter and linter before opening the PR (`make lint`, `ruff check`, `eslint`, `gofmt`, `cargo fmt` — whichever applies).
- Tests for new behaviour live next to the existing tests; the smoke test is the entry point.

## Filing issues

- **Bug reports**: include the steps to reproduce, the expected behaviour, the actual behaviour, and the environment (OS, language version, relevant deps).
- **Feature requests**: explain the use case before the implementation. The decision-record style at [`.docs/adrs/0000-adr-template.md`](./.docs/adrs/0000-adr-template.md) is a good frame for "what shape is the change, and what are the trade-offs?".
- **Security**: do not file public issues for vulnerabilities. Report them privately by following [`SECURITY.md`](./SECURITY.md). See [`.docs/security/methodology.md`](./.docs/security/methodology.md) for the project's overall security posture.

## Architecture decisions

Significant structural changes (a new library, a new layer, a new pattern, a shift in tier or pricing behaviour) need a new ADR under [`.docs/adrs/`](./.docs/adrs/) in the same PR. The discipline is described in [`.agents/rules/workflow.md`](./.agents/rules/workflow.md).
