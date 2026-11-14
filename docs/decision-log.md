# Scanner decision log

**Audience**: anyone who wants to know *why* the scanner grades the way it does. Each entry is what we saw, what we decided, and why. Newest at the bottom. How the scanner works is in [the guide](./connector-scanner.md); the founding decision is [ADR 0001](../docs/adrs/0001-connector-security-scanner-service.md).

**How we decide**: run it on the whole catalog, look at the real data, change one thing, run again and compare. We do not tune on a hunch or on a handful of examples.

## The runs so far

| Run | What changed | Time | A | B | C | D | Not assessed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | First version, one connector at a time | 20 min 58 s | 27 | 4 | 40 | 223 | 6 |
| 2 | Ten-plus at once, per-registry limits | 4 min 41 s | 28 | 4 | 39 | 222 | 7 |
| 3 | Evidence rules (below) | 4 min 8 s | 11 | 4 | 38 | 215 | 32 |

## 1. Scan in parallel, but politely

**Saw**: a full sweep took 21 minutes, mostly waiting on the network.
**Decided**: scan many connectors at once, with a small limit of five per registry (npm, PyPI, git, Maven, containers). A slot is held only while downloading, not during analysis. A rate-limit answer pauses that registry for everyone and retries once.
**Why**: registries limit per client, so each gets its own lane. A throttled npm must not stall git. Result: about five times faster.

## 2. Compare runs, and distrust what changed

**Saw**: three connectors changed grade between run 1 and run 2 with no code change.
**Found**: one was a network timeout, one was a scanner crash that still produced an A, one was a heuristic tool returning different hits on the same package.
**Decided**: every unexplained change is investigated before anything is tuned.

## 3. A grade needs evidence

**Saw**: 17 of 28 A grades had no packages behind them. The scanner found no lockfile, looked at nothing, and reported "clean".
**Decided**: if no package was resolved and examined, the result is **not yet assessed**, for every letter. A crashed scanner can never produce an A or B. Timeouts and dropped connections are retried once. A known-malicious advisory is its own evidence and still gives F.
**Why**: finding nothing in an empty tree proves nothing. Not assessed is not safe and never blocks anything.
**Effect**: A fell from 28 to 11. That is the honest number.

## 4. Only strong signals lower a grade

**Saw**: 215 D grades. 29 are real (a critical vulnerability with a fix). 186 come only from code heuristics.
The heuristic rules are of two kinds. *Capability* rules say what a package can do (network, files, processes), which a connector is meant to do. *Threat* rules are stronger, but even those fire on 152 connectors, and reading environment variables, needed for any API key, fires on 109.
**Decided**: capability findings never lower a grade. Only three signals give a D: obfuscated code, obfuscated base64 execution, and download-and-execute. Everything else is still recorded, and an A states how many capability notes it carries, so nothing is hidden.
**Checked first**: we replayed the saved run-3 data with the new rule before changing code. D would fall from 215 to 74, with 75 moving to A and 66 to C.
**Caveat**: the heuristic tool is not perfectly repeatable between runs, so the strong-signal list should be reviewed against more than one sweep.
