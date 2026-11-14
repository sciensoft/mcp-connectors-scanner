<!-- best-practices: stub · refinement deferred · reason: not yet attempted -->
# Best Practices

> **This file is the generic baseline.** It contains language-agnostic patterns that apply across most projects. For *much* more value, refine it from current web sources for your specific Python + framework stack — see [§ Enable refinement](#enable-refinement) at the bottom of this file.

Patterns and conventions established in this project. Apply them when adding new features or refactoring. Expand this file with language- or framework-specific idioms as the project matures — the sections below are the language-agnostic core.

## Architecture

This repository is flat: modules organised by topic under `engine/`, with no layering and no dependency-injection container. Keep it that way unless a decision record says otherwise.

- One module per concern (`extract`, `scan`, `grade`, `coverage`, `store`, `api`, `gates`, `main`).
- Pure logic stays free of I/O so it can be tested without a database or network. `grade.py` is the model: it takes findings in and returns a grade, nothing else.
- Anything that talks to a tool or the network goes through one small function (`run` in `scan.py`), so timeouts, retries and fakes live in one place.

## Code style

- **Imports**: absolute across layers; relative imports only within the same package.
- **Async**: use the runtime's async primitives (`async`/`await` in Python or JS/TS, goroutines in Go, …) and run independent I/O concurrently where it helps. Don't mix sync and async carelessly inside a single call path.
- **Privacy**: prefer language-idiomatic privacy markers (`_underscore` for module-private in Python; `private` in TS; lowercase for unexported in Go). Reserve aggressive privacy mechanisms (double-underscore name mangling, sealed classes, etc.) for actual collision avoidance — don't reach for them as "more private".
- **Dates**: timezone-aware end-to-end. Never rely on system locale or naive datetimes for boundary work.
- **Avoid mutation**: prefer non-mutating operations where the language has them (`sorted(xs)` over `xs.sort()` in Python, spread/`map` over in-place updates in JS, immutable structs where the language supports them).
- **Type hints**: required for public function signatures and class attributes wherever the language supports them.
- **Validation**: validate at boundaries (UI input, external APIs, file parsing). Trust internal data shapes once they cross the boundary.
- **Errors**: raise specific exceptions in infrastructure; the application layer catches and converts to user-facing strings.

## File & Naming Conventions

- Module files: `snake_case.py`, one concern per module. Small related helpers may live alongside the code that uses them.
- Constants: `UPPER_SNAKE_CASE` at module level.
- Private members: `_single_underscore` (Python) or the equivalent for your language.
- Package directories use lowercase, no separators.

## Data & Formatting

- Always sort returned collections — dates ascending by default, stats descending by value.
- Format numbers and dates via a locale-aware library (Babel for Python, Intl for JS, `golang.org/x/text` for Go) where the audience matters.
- Section copy should be **generic** and explain what the stats represent — never hard-code narrative from a specific dataset.

## What NOT to do

- Don't add comments that restate the code; only document non-obvious *why*.
- Don't reach for a custom decorator/metaclass when a plain function or class fits.
- Don't track build artifacts or virtual envs in git — gitignore them.
- Don't bundle multiple unrelated changes in one commit; one prompt + one commit per request (see `.agents/rules/workflow.md`).

## Enable refinement

The bootstrap tried to refine this file from current Python + framework sources but couldn't reach the web from your agent host. Once you fix that, ask any agent to *"re-run the bootstrap's Step 4b best-practices refinement"* and a stack-specific version will replace this stub. **How to enable web access per host:**

| Agent host | What to enable |
| --- | --- |
| **Claude Code** | The `WebSearch` and `WebFetch` tools ship with the CLI. If calls prompt for permission, add `"WebSearch"` and `"WebFetch(domain:*)"` (or specific allowed domains) to the `permissions.allow` array in `.claude/settings.json`. For headless / cron runs, also pre-allow the domains you expect to fetch. |
| **Cursor** | Web search is built in (the `@web` symbol). If the agent doesn't pick it up automatically, prompt it explicitly: *"Use @web to research Python best practices, then refine .agents/rules/best-practices.md."* |
| **OpenAI Codex CLI** | The `--web` flag / web-tool capability must be enabled in your Codex config. See `codex --help` for the current flag name; web access is opt-in per session. |
| **Aider** | Aider doesn't ship native web search. Either pipe sources in via `aider --read <url-or-path>` after fetching them yourself (`curl`), or use the `/web` slash command if your Aider build supports it (newer versions). |
| **OpenCode** | Web search is available via the platform's tool config. Enable it in your OpenCode settings before re-running the refinement prompt. |
| **Continue.dev** | The `@web` context provider is opt-in — add `"web"` to your `.continue/config.json`'s `contextProviders` array. |
| **Windsurf** | Web search is available via the platform's tool palette. Confirm it's enabled in your Windsurf workspace settings. |
| **GitHub Copilot** | Copilot Chat in supported IDEs has the `@web` participant (Copilot Workspace + recent VS Code Insiders). If your host is older / web-less, fetch sources manually and paste excerpts into the chat, then ask Copilot to refine the file. |

**Can the agent self-configure?** Sometimes. If your host's gap is *permissions* (the tool exists but is gated), an agent with write access to the host's config file can add the right entry — Claude Code can edit `.claude/settings.json`, Continue.dev can edit `.continue/config.json`. Ask the agent to enable web search by editing its own config, then re-run the refinement. If your host's gap is *capability* (the tool doesn't exist), no agent can give itself a new tool — switch hosts or fetch sources manually.

When refinement runs successfully, the marker comment at the top of this file flips from `stub` to `refined` and `bootstrap.json`'s `BEST_PRACTICES_REFINED` flag becomes `true`. Re-running the bootstrap after that point leaves this file alone (it becomes user-owned).
