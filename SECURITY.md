# Security Policy

## Reporting a vulnerability

If you've found a security issue in mcp-connectors-scanner, please **do not file a public issue**. Public disclosure before a fix is shipped exposes other users to the same risk.

Instead, report it privately, in this order of preference:

1. **GitHub private vulnerability reporting**: the *Report a vulnerability* button under this repository's **Security** tab. It reaches the maintainers directly and keeps the report private until a fix ships.
2. **The contact form** on the Sciensoft website, at <https://sciensoft.dev/contact>. Put "Security" in the subject and do not include exploit details in the first message; we will reply to arrange a private channel.
3. **Email** <hello@sciensoft.dev> with "Security" in the subject, with the same advice: say that you have found something, and wait for our reply before sending details.

Bugs, ideas and questions that are not vulnerabilities belong in the public [issue tracker](../../issues).

Please include:

- A description of the issue and its impact.
- Steps to reproduce.
- The affected version (commit SHA or release tag).
- Any proof-of-concept you have — code, request payloads, screenshots.

You'll get an acknowledgement within **5 business days**. We'll keep you posted on the fix timeline; coordinated disclosure happens once a fix is available and users have had a reasonable upgrade window.

## Scope

In scope:

- The code in this repository.
- Default configuration and recommended deployment instructions.
- Dependencies pinned by this project (we'll triage and forward upstream as appropriate).

Out of scope:

- Vulnerabilities in third-party services we don't control (cloud providers, CDNs, …).
- Social-engineering attacks.
- Self-XSS / requires-physical-access scenarios with no plausible attack path.

## Security posture

The project's overall security methodology, rubric, and the dated audit history live under [`docs/security/`](./docs/security/). See [`docs/security/methodology.md`](./docs/security/methodology.md) for the playbook reviewers follow.

The companion workflow rule at [`.agents/rules/workflow-security.md`](./.agents/rules/workflow-security.md) describes how security-sensitive changes are reviewed during day-to-day development.
