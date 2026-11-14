# How we turned one Claude into a small team: auditing 8 notebooks in parallel

*Draft. Facts below come from the real run on 2026-10-28 and the review of its output on 2026-10-29. Numbers marked TODO still need pulling from the logs. Each part tells what we did at MCP Connectors, then shows the how-to behind it.*

## 1. The problem: a catalog that rots, and one pair of hands

MCP Connectors keeps a catalog of MCP servers as Jupyter notebooks: 20 notebooks, several hundred entries. Each entry is a project with an install command, environment variables, config files and auth steps. Catalog entries rot. Packages get renamed, repositories vanish, a name on npm turns out to belong to a different project, a service shuts down.

We audit them by hand, one entry at a time, checking every claim against live sources with an assistant. It works, and it is slow. Twelve notebooks were done. Eight were left, with about 15 entries each, and one assistant working through them in order would take days.

## 2. The idea: let one assistant run many

The Claude command-line tool has a headless mode: `claude -p "your task"` runs one task and exits, no human at the keyboard. If it is installed and logged in on a machine, an assistant with shell access can start several of them as background processes, each in its own folder, and collect the results later.

**How-to, the minimum version:**

1. One folder per worker, so they cannot trample each other's files.
2. One shared brief with the rules every worker must follow.
3. One headless process per worker, started detached so it survives your shell.
4. One file per worker where the result is written.

No framework, just a shell, a folder and a text file.

## 3. First attempt: fire and forget

We wrote one brief, then launched eight workers, one per notebook. The rules were what mattered most:

- Never guess. If you did not fetch it or read it this session, write UNVERIFIED.
- Keep the same primary project for each entry unless it is gone, and report evidence instead of swapping it.
- Write only inside your own folder. Never edit the notebook.
- Report exact run commands, exact environment variable names read from source code, and config file formats.

A checksum of all 20 notebooks before and after the run was identical, so the workers really had stayed in their lane. The findings were then verified and applied in later passes, and every applied entry was reviewed before it reached the real notebooks (sections 7 and 8).

**How-to tip:** make the workers read-only on the thing you care about, and prove it with a checksum.

## 4. What the swarm found

Six of eight workers finished with complete findings. The research caught what a quick read misses:

- One service was dead, not "winding down" as the notebook said: the API was shut down and the data deleted.
- One entry's primary repository did not exist at all, so the entry could not work as written.
- Two news entries used a Python runner for packages that are actually Node projects.
- A Booking.com entry pointed at a repository that turned out to be a generic scaffold, a New York hotel demo with mock data, not a Booking.com connector. We confirmed this ourselves in the actual files after the worker reported it.

## 5. What broke, and how to avoid it

**We could not see anything.** The first run used plain-text output, so each log stayed empty until the worker finished. We could not tell who was working, stuck or dead.

**The usage limit.** Eight workers at extra-high effort used up a five-hour allowance in minutes. Two workers, the 27-entry notebook and the travel notebook, hit it mid-task and ended with part files and no final result.

**A model scare.** The limit made us suspect the workers had silently picked our most expensive model. The session logs showed every request used Sonnet, so the cause was eight parallel workers at maximum effort, not the model. Pass the model explicitly anyway, because the default is a setting you may not control.

**A deny rule that did nothing.** A rule written as `Write(path)` was silently not matched. Only the `Edit(path)` form blocks file writes.

### Gotcha: parallel agents share one rate limit

Rate limits are usually counted per caller, and to a service all your workers look like the same caller.

The GitHub API is the example we hit. Our workers constantly look up commit dates, licenses and archived status. Anonymous calls are limited to roughly 60 requests an hour, counted per IP address, and all eight workers share the same IP. During the verification pass we saw workers sleeping for a minute and polling the rate-limit endpoint, and others scheduling themselves to wake up later. Our own spot-checks hit the same wall.

Nothing was broken. The no-guessing rule did its job: when the API said "rate limit exceeded", the workers could not fill in the answer from memory, so they waited. The cost was time, not accuracy.

Workarounds, roughly in order of effort:

- **Use an API token.** For GitHub, a personal access token with no extra permissions (public read-only) raises the limit from about 60 to 5,000 requests an hour. Pass it through an environment variable so it never appears in your registry, prompts or logs. An SSH key does not help: it only authenticates git over SSH, not API calls over HTTPS.
- **Cache lookups.** Several workers asked about the same repositories.
- **Stagger the launches**, so workers do not spend the budget in the same hour.
- **Read from somewhere not rate limited the same way**, such as cloning repositories. We rejected this: it moves a lot of data to answer questions a few API calls could.
- **Or let the workers wait.** Slower, but the work still finishes. That is what we did.

The general point applies to any service agents call in parallel: search engines, package registries, documentation sites. Before launching a swarm, ask what shared budget the workers draw from, and what they will do when it runs out.

## 6. The rework: a registry, task lists and a live status

Fixing what broke turned into a small toolkit:

- **One registry file per run.** Each worker has an id, a sandbox folder, a runtime (model and effort), a status and a task list. The number of workers and tasks is whatever you need.
- **Tasks with evidence.** A task is done only when its expected output files exist and are non-empty. A process exiting proves nothing. If outputs are missing, the task is partial or failed.
- **Streaming output.** Workers run with streaming JSON, so every step arrives as one event. A watcher keeps each worker's status current (researching, thinking, writing, stalled, rate limited), shows its latest action in an activity feed, and keeps the full stream in a log file for later review.
- **Persistent sandboxes.** A finished worker is idle, not dead. Append a new task and it continues in the same folder, with its clones and notes still there.

A one-task test with the cheapest model proved the loop: launched, then writing with the exact file path, then done. The stream confirmed the model really was Haiku 4.5, the output file existed, and it cost about four cents. Validating the registry against its schema during that test even caught a bug in our own watcher.

Then we used it for real. The two partial workers got a retry task. Travel-and-maps finished it in 11 turns, about 71 cents. The six finished workers each got a verification task: re-check your own findings against live sources. Seven workers ran at once, with live status.

**How-to tip:** give every task its own expected output file. A limit hit then costs you one task, not the whole worker.

## 7. Applying the findings, on copies

Findings are notes, not a catalog. The next pass turned each worker's verified findings into finished entries in the catalog's layout: a description, a **Pinned** line with the exact version or commit, a **Params** section, a **Config file** block when the project needs one, and a **Notes** line.

Each worker did this on a copy of its notebook. The same deny rule that kept workers out of the real repository during research stayed in place, so every change landed in a file we could read before anything touched git.

The main rules of the apply brief, in their final form (section 8 explains why they got stricter):

- Copy run commands, environment variable names and pins from the findings character for character. No version tags, no commit suffixes, no swapping the install source, even if the change looks safer. A suggestion goes in the notes, marked UNVERIFIED, not in the command.
- If the findings describe a config file, the entry must contain the example block, not just a pointer to it.
- If the findings call a claim in the intro stale, fix the intro itself, so the entry does not contradict its own notes.
- Keep the same primary project for each entry. If it is dead, record the evidence and put the working alternative in the notes.
- Carry every UNVERIFIED item across as UNVERIFIED.

Some entries were placeholders ("no public MCP yet"). Where the research found a real project, the worker replaced the placeholder: Medium and Overcast each got a real community server. Where it found nothing usable, the placeholder stayed and the notes said why, as with the WSJ, Reuters and Bloomberg entry.

**How-to tip:** have workers write to a copy and review that, not the live file. A mistake then costs a review comment instead of a revert.

## 8. Checking the workers' work

Verifying the research does not verify how it was applied. So after the apply pass, a reviewer (another assistant, not one of the workers) read every applied entry next to its findings section and logged what it saw.

The method is plain. One claim is one check, and each check gets a verdict:

- **confirmed**: the applied text matches the findings.
- **corrected**: the facts are right, but the worker broke a rule or left something out.
- **wrong**: a factual error.

The score for a task is confirmed divided by total checks. A small helper script prints the applied text beside the findings, so reading both sides is the easy path, and every check records who made it and when.

Results across 132 entries in 8 notebooks:

| Notebook | Entries | Checks | Confirmed | Corrected | Score |
|---|---|---|---|---|---|
| search-and-research | 15 | 15 | 15 | 0 | 100% |
| news-and-reading | 15 | 33 | 31 | 2 | 94% |
| productivity | 27 | 27 | 25 | 2 | 93% |
| travel-and-maps | 15 | 15 | 14 | 1 | 93% |
| personal-finance | 15 | 30 | 24 | 6 | 80% |
| vector-and-rag | 15 | 31 | 19 | 12 | 61% |
| shopping-and-commerce | 15 | 36 | 22 | 14 | 61% |
| social-networks | 15 | 32 | 18 | 14 | 56% |

In total: 219 checks, 168 confirmed, 51 corrected, none marked wrong. The score measures how closely the workers followed the apply rules, not how accurate the notebooks are. The corrected items were left as the workers wrote them and noted in the checkpoint.

### What the review caught

- **Workers improve what you tell them to copy.** The most common correction by far was a version tag, commit suffix or pinned number added to a run command that the findings gave without one, or `@latest` swapped for a number. In social-networks that was 11 of 14 corrections, in vector-and-rag 11 of 12. The substitutions were plausible and nobody had tested them. The drift was strongest where the findings said the command already worked.
- **Missing config examples.** A Config file header with no example block was the second most common slip, six times in shopping-and-commerce alone. A rule added to the brief after a worker has started does not reach that worker.
- **Notes that outlive their context.** One entry carried a dated audit note about something the entry never mentions, and another kept an intro sentence that contradicted its own notes.
- **Faithful copies that look like deviations.** Several entries ended in `@latest` or `@2`, which looks like an added tag. In each case the findings gave that exact string. Compare with the findings' run line before calling a suffix a deviation.

What the workers got right matters just as much. Dead primaries were not swapped: Etsy's repository returns 404, WooCommerce's primary does not implement MCP at all, and the Podcast Index repository does not exist. In each case the worker kept the primary, recorded the evidence and offered the working alternative in the notes. UNVERIFIED items mostly survived the trip, with a few dropped lines noted in the review. And the apply stage fixed real rot in the originals: invented environment variables for Plaid and Revolut Business, a variable copied from a different project into FreshBooks, and run commands that could never have worked.

### The reviewer made mistakes too

- **Double review.** After a context reset, our reviewing assistant scored shopping-and-commerce a second time without noticing it had already done so. The registry held 66 checks for 15 entries, and the two passes disagreed about the same version tags. We had reported 79% before spotting it. We kept the first pass plus the six config findings only the second pass caught, and the honest score was 61%.
- **Logging without reading.** Two checks on one entry were written from the findings alone, without opening the applied text. We caught it, the entry was reviewed properly, and vector-and-rag moved from 63% to 61%.

The lessons: a QA store needs a uniqueness check per entry and claim, evidence in a check must point at the applied text, and an audit trail (who, when) is more reliable than the reviewer's memory. After the reset, the registry's checked-by and checked-at fields showed which reviews already existed.

### Did tightening the brief work?

After the first review we tightened the brief into the rules in section 7. The three notebooks applied afterwards (search-and-research, productivity, travel-and-maps) scored 100%, 93% and 93%. The five applied before it scored between 56% and 94%.

That looks like cause and effect, but it is one run and not a controlled test. The notebooks differ in difficulty, and news-and-reading scored 94% before the change. A perfect score also deserves suspicion, so we re-read the riskiest search-and-research entries, and they held up.

**How-to tip:** make checking cheap and traceable. One claim per check, the applied text printed beside the source, who and when recorded, and a validator on the store so duplicates cannot hide.

### Cost, time and the verification pass: what the logs can and cannot tell us

The registry gives a few firm numbers, and some gaps worth stating plainly.

- **Model.** All 8 workers ran on Sonnet 5 (`claude-sonnet-5`, read from each worker's stream), as requested.
- **Cost.** The stored cost covers only each worker's last run. The toolkit overwrites a worker's cost and turn count at every result instead of adding to them, so what survives is the apply pass: $1.72 to $2.48 and 18 to 27 turns per worker, about $16.20 across the eight. Research and verification are not in that figure, so it understates the total.
- **Tokens.** Not recorded. The registry has no token fields.
- **Time.** The registry was created on 2026-10-28 at 12:51 and the last task ended on 2026-10-29 at 15:26, about 26 and a half hours of calendar time, with the passes spread across two days. The last three apply tasks took 7 to 9 minutes each. The first five show one shared end time (14:14:10), which is when the status was refreshed, not when they finished. The one sandbox we can check, news-and-reading, has its files stamped 13:25 after a 13:20 start, so about 5 minutes. Six of the eight verification tasks launched within five seconds of each other (17:25:55 to 17:26:00 on 10-28) and all show the same end time, 17:49:40, which also looks like a status refresh, so read it as an upper bound of under 24 minutes each. The other two, productivity and travel-and-maps, were verified on 10-29 and took about 9 minutes each.
- **Verification pass.** Each verifier's corrections are in its own `verification.md` in the audit cache, outside this repository, so per-notebook counts are not available here. The README records the kinds of error they fixed: a repository wrongly called archived, a stale version pin, a missing environment variable, and an overstated capability claim. Our own spot-check of the verifiers' work covers 7 checks on two notebooks, news-and-reading (3) and vector-and-rag (4): 6 confirmed and 1 inconclusive. The other six verification tasks have no spot-checks recorded. That is a sample, not a measure.

The fix is cheap: record cost, turns and tokens per task and add them up. Without that, the cost of a run can only be rebuilt from the raw stream logs afterwards.

## 9. Takeaways

- Treat workers like any distributed job: registry, explicit statuses, evidence-based completion.
- Pass the model and effort on every launch. Use the cheapest model that can do the task.
- Make no-guessing a hard rule, then expect the swarm to be slower where it cannot guess.
- Budget shared limits up front: every service workers call in parallel has a limit they all draw from, and an API token is often the cheapest fix.
- Keep a human or a separate agent in the loop. Workers produce findings, workers apply them to copies, and a separate reviewer scores every applied entry.
- Verifying the findings is not verifying their application. Review the apply stage on its own, with a score you can compare across workers.
- Put the strictest wording where the temptation to improve is greatest. "Copy exactly" has to cover changes that look arguably better.
- Give the reviewer evidence and an audit trail: the applied text beside the source, one claim per check, who and when. Trust the trail over anyone's memory, including the reviewer's.
- A clean score still gets a second look.
- Record cost, tokens and timestamps per task from the first run. Ours overwrote cost at every result and stamped end times at refresh, so the numbers had to be rebuilt afterwards.

## TODO before publishing

- Rebuild total cost, tokens and duration from the raw worker stream logs (`worker.log` in each sandbox, in the audit cache on the machine that ran the swarm; not reachable from this connector). The registry keeps only the last run's cost and no tokens. The figures in section 8 are what the registry can support.
- Done 2026-10-30: the section 8 table and totals (219 checks, 168 confirmed, 51 corrected, none wrong) were recounted from the registry and match, with no duplicate entry-and-claim pair in any task.
- Add per-notebook verifier correction counts, from each notebook's `verification.md` in the same audit cache.
- Decide whether to publish the toolkit as a standalone repo.
- Add the Shell connector configuration that the how-to in section 2 needs (the trusted setup with shell access), and confirm the catalog URL for the Shell entry.
