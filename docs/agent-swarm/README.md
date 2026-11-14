# Agent swarm

Spin up N headless Claude CLI workers from one JSON registry, give each a private sandbox and a task list, and watch what they are doing while they run. The number of workers and tasks is whatever you ask for. Nothing here is specific to the notebook audit that produced it.

## Layout

| Path | What it is |
|---|---|
| `schema/swarm.schema.json` | JSON Schema for the registry (draft 2020-12). |
| `bin/swarm.py` | Launcher, watcher, stopper, verifier, QA recorder, schema validator. Python standard library only; only the optional `validate` command needs the `jsonschema` package. |
| `runs/<swarm-id>/registry.json` | One registry per run. The single source of truth. |
| `runs/<swarm-id>/logs/<worker>.jsonl` | Full raw event stream per worker, nothing dropped. |
| `blog/` | Draft post about the approach. |

## Concepts

- **Worker**: one headless `claude -p` process with its own sandbox folder. Workers are detached, so they survive the shell that started them.
- **Sandbox**: the only folder a worker should write to. It persists between tasks, so clones and notes from task one are still there for task two.
- **Task list**: every worker carries an ordered list of tasks. A finished worker picks up the next queued task in the same sandbox.
- **Registry**: only `swarm.py` writes it, with atomic replace. Read it any time.

## Task statuses

`queued`, `running`, `done`, `partial`, `failed`, `blocked`, `unknown`, `skipped`.

A task becomes `done` only when every path in its `expected_outputs` exists and is non-empty. Process exit alone never counts. If the process is gone and the outputs are missing, the task is `partial` or `failed`, and `unknown` when there is no evidence either way. `swarm.py verify` re-checks those from disk.

## Worker statuses

`idle`, `starting`, `researching`, `thinking`, `writing`, `waiting`, `stalled`, `rate_limited`, `done`, `failed`, `stopped`.

They are derived from the stream: a tool call means `researching` (or `writing` for file writes), a reasoning block means `thinking`, a rate-limit event means `rate_limited`, and no event for 5 minutes means `stalled`. Each worker also keeps a rolling activity feed of its last 12 actions in `activities`, and `state_detail` shows the current one, for example the exact file being written.

## Models

The model is passed explicitly with `--model` on every launch. The CLI default is never relied on, because the default can be an expensive model. Set it per swarm in `defaults.model` and override per worker in `runtime.model`.

Verified on Claude Code 2.1.224:

| Alias | Resolved model |
|---|---|
| `sonnet` | `claude-sonnet-5` |
| `haiku` | `claude-haiku-4-5-20251001` |
| `fable`, `opus` | listed in the CLI help, expensive, not tested here |

The watcher reads the real model name from the stream into `model_seen`, so you can confirm the request was honoured. Effort is `low`, `medium`, `high`, `xhigh` or `max`; the default is `medium`.

## Usage

    python3 bin/swarm.py launch runs/<id>/registry.json            # start the next queued task of each idle worker
    python3 bin/swarm.py launch runs/<id>/registry.json --worker a # only one worker
    python3 bin/swarm.py status runs/<id>/registry.json            # refresh from the streams and print a table
    python3 bin/swarm.py watch  runs/<id>/registry.json            # refresh every 5 seconds until all are terminal
    python3 bin/swarm.py verify runs/<id>/registry.json            # re-check outputs on disk
    python3 bin/swarm.py stop   runs/<id>/registry.json            # SIGTERM the worker process groups
    python3 bin/swarm.py validate  runs/<id>/registry.json         # check the registry against the schema (pip install jsonschema)
    python3 bin/swarm.py qa-add    runs/<id>/registry.json --worker a --task t --claim "..." --verdict confirmed   # record one QA check
    python3 bin/swarm.py qa-report runs/<id>/registry.json         # per-task QA score
    python3 bin/swarm.py qa-report runs/<id>/registry.json --pending   # only tasks whose QA is not complete

To give existing workers a new job, append a task with status `queued` to each worker's `tasks` and run `launch` again. Finished workers are `idle` and pick it up in the same sandbox.

## Independent QA of worker output

A worker finishing a task only proves the output files exist. It does not prove the content is right. To measure correctness, the operator's own session (not the worker) re-checks a sample of the worker's claims against live sources, and records each check on the task itself, under an optional `qa` block.

Each check has the worker's claim, the worker's value, the value the checker observed, a verdict, and the evidence (the command or URL used, so anyone can repeat it).

| Verdict | Meaning |
|---|---|
| `confirmed` | The claim matches what the checker found. |
| `corrected` | Partly right, a detail needed fixing. |
| `wrong` | The claim was false. |
| `inconclusive` | The checker could not decide (rate limit, no access). |

The tally is recomputed on every `qa-add`, and the score is confirmed divided by confirmed plus corrected plus wrong. Inconclusive checks are left out of the denominator, because they reflect a limit of the checker, not a mistake by the worker.

`qa.status` is `pending`, `in_progress` or `complete`. Tasks with no `qa` block count as pending. When asked to validate, check only the tasks `qa-report --pending` lists, because earlier tasks already went through QA. Each task is scored on its own, so a retry task is measured separately from the attempt it replaced.

A score from a handful of checks is a spot check, not a full audit. Read it together with the number of checks behind it.

## Rules every worker gets

Put these in a brief file and point `brief_path` at it. The launcher prepends it to every prompt.

1. Never guess. Every claim comes from something fetched or read in the session; otherwise write `UNVERIFIED`.
2. Write only inside your sandbox.
3. Keep the same primary project per entry unless it is gone, and report evidence instead of swapping.

## Lessons from the first run

- Eight parallel workers at extra-high effort exhausted a five-hour usage limit within minutes. Use `medium` effort and a cheaper model, and stagger launches.
- The usage limit hit mid-task. Two of eight workers ended `partial`: they had written part files but never assembled the final output. Splitting a task into smaller tasks with their own `expected_outputs` would have made the partial results usable.
- All workers share one IP, so they share GitHub's anonymous API limit of about 60 requests an hour. During the verification pass, workers slept and polled the rate-limit endpoint, or scheduled themselves to wake up later. The no-guessing rule made them wait instead of inventing answers. Fix: a public-read GitHub token passed through an environment variable (about 5,000 requests an hour). An SSH key does not help, because it only authenticates git over SSH, not API calls over HTTPS.
- Deny rules for write protection need the `Edit(path)` form; `Write(path)` is not matched by the file permission checks.
- The first run used plain-text output, which cannot be monitored. Those logs are marked `stream_format: plain-text` and are never parsed. All new runs use `stream-json`.
- Validating the registry against the schema after a real test caught a bug in the watcher itself: it was writing private bookkeeping fields the schema did not allow.
- Worker self-verification is not independent evidence. In the verification pass, workers corrected real errors in the earlier findings: a repo wrongly called archived, a stale version pin, a missing environment variable, an overstated capability claim. That is why the QA record lives on each task, scored by a separate session.
- A smoke test with one tiny Haiku task proved the whole loop: launch, live status changes (`writing` with the file path, then `done`), model confirmed from the stream, output file verified. It cost about four cents.

## Not done yet

- No automatic splitting of a big task into smaller ones.
- No retry policy; a `partial` task needs a human decision.
- The `resume` flag on a task is passed through to `--resume` but has not been tested.
- Not yet committed to git.
