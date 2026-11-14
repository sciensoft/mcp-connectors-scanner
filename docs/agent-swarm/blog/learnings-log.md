# Learnings log for the blog post

Running notes, appended as the work happens. Each entry has the date, the notebook or stage it came from, and the lesson. Raw material for the blog draft, not polished prose.

## 2026-10-29 — personal-finance apply-findings review (score 80%, 30 checks, 24 confirmed, 6 corrected, 0 wrong)

1. **Workers "improve" when you tell them to copy.** Four of the six corrections were workers adding a commit-hash suffix to a git address, or switching an install source (GitHub to npm), on run commands the research stage had verified in a different exact form. The substituted commands were plausible and low risk, but nobody had tested them. Lesson: if a value must be copied exactly, the brief has to forbid even plausible improvements explicitly, and say where suggestions go instead (a Notes line marked UNVERIFIED).

2. **Verified research can still be mis-transcribed.** The research stage was checked and confirmed, then the apply stage drifted from it. A separate review stage with its own scoring caught this. Lesson: verification of the findings does not verify the application of the findings.

3. **The score is per task, not per notebook.** Each check is one claim, marked confirmed, corrected or wrong. Score is confirmed divided by total checks, tracked per worker task. A corrected verdict means the substance was right but the text deviated from instructions or was incomplete.

4. **The deny-tools rail did its job.** Workers were hard-blocked from editing anything under the real repo, so every deviation landed in a copy that could be reviewed before anything touched git.

5. **Original notebook entries contained fabricated details.** Invented environment variables for Plaid and Revolut Business, a variable copied from a different project into FreshBooks, and run commands that could never have worked (Plaid, Wise, Coinbase, Monarch, Splitwise, FreshBooks). The audit's value was mostly in catching these.

6. **Incomplete is a different failure from wrong.** Two of the corrections were a Config file header with no example block (Revolut Business, and minor cases in Splitwise and FreshBooks) and a stale intro sentence that contradicted the entry's own Notes (Monarch Money). Fix: the brief now has rules 4b and 4c for these.

7. **Tooling lesson, mid-session outage.** The shell and filesystem tools silently dropped from the active tool list. A generic tool search surfaced unrelated tools; a specific query naming the machine and the tool fixed it. The workers kept running as detached processes and were unaffected. Lesson: run workers detached from the chat connection, and never guess status when the tools are unreachable.

## 2026-10-29 — shopping-and-commerce apply-findings review (CORRECTED score 61%, 36 checks, 22 confirmed, 14 corrected, 0 wrong)

Correction note: an earlier version of this section reported 79% on 66 checks. That was wrong. I had reviewed every entry twice, once before and once after a context compaction, and the two passes disagreed. The registry was deduplicated (backup kept), keeping the first pass plus the six missing-config findings that only the second pass caught.

8. **Two kinds of correction.** Of 14 corrections, 8 were run-command deviations (Square, Amazon Orders, eBay, Etsy, WooCommerce, Walmart, Rakuten, Instacart): mostly an added or swapped version tag (Square, eBay, WooCommerce alt, Walmart, Rakuten, Instacart), plus extra steps in Amazon Orders and a known-broken command left live in Etsy, and 6 were a Config file section missing entirely (Shopify, Amazon Seller, Etsy alt, BigCommerce, DoorDash, Uber Eats). Both are worker deviations from the brief, not research errors.

9. **Same drift as personal-finance, same cause.** The version-tag habit appeared again in an independent notebook, so it is a property of the instruction, not of one worker.

10. **Preserving UNVERIFIED worked.** Etsy, eBay, Walmart, Instacart and DoorDash all carried explicit unverified caveats through to the applied entry. One drop: Instacart lost the second of two unverified items. Lesson: rules about not guessing hold well; rules about completeness hold less well.

11. **The no-swap rule held under pressure.** Etsy's primary repo is a 404 and WooCommerce's primary does not implement MCP at all. Both workers kept the primary, recorded the evidence, and put the working alternative in commented lines instead of replacing it. Lesson: a clear rule about what not to decide let workers handle the hardest entries safely.

12. **My own memory failed, and the registry caught it.** After a context compaction, my summary dropped the social-networks and vector-and-rag reviews I had already logged. I nearly told the user those scores were unexplained. Reading the registry's checked_by and checked_at fields showed they were mine, written at 14:32 and 14:34. Lesson: the audit trail is worth more than the narrator's memory. Record who and when on every check.

13. **I made the same mistake twice, in the opposite direction.** After the compaction I re-reviewed entries I had already scored. The second pass applied a looser standard and confirmed the same version tags the first pass had corrected. Two contradictory verdicts on one claim is a red flag that no scoring tool flagged. Lesson: a QA store needs a uniqueness check per entry and claim, and a reviewer needs a way to see what has already been reviewed before starting.

## 2026-10-29 — social-networks apply-findings review (score 56%, 32 checks, 18 confirmed, 14 corrected, 0 wrong)

14. **The weakest score, and the cause is the same one.** Of 14 corrections, 11 were run commands where the worker added a version tag, commit suffix or pinned `latest` to a number that findings did not state (Facebook, YouTube, Instagram, TikTok, LinkedIn, BulkPublish, PostEverywhere, X, Reddit, Discord, Bluesky). Weibo is a twelfth case in the same family and was logged as its own correction. None were research errors, and the pins were all real values from the PIN line.

15. **Replacing `@latest` is still a deviation.** LinkedIn and X had `@latest` in the findings RUN line and the worker swapped in the pinned number. That looks like an improvement, which is exactly why it slipped through. Lesson: "copy exactly" has to cover changes that are arguably better, because that is where workers drift.

16. **Missing Config blocks came back.** YouTube and Discord had the Config file header and a pointer to `.env.example` or `.env.template`, but no example block. Same failure as in shopping-and-commerce, and it happened even though rule 4b was in the brief by then for the later workers. Lesson: a rule added after a worker starts does not reach that worker.

## 2026-10-29 — vector-and-rag apply-findings review (score 61%, 31 checks, 19 confirmed, 12 corrected, 0 wrong)

17. **Eleven of twelve corrections were version tags again.** Pinecone, Qdrant, Zilliz Cloud, LanceDB, Turbopuffer, Meilisearch, Typesense, Astra DB, Redis Stack and MongoDB Atlas all gained a tag or equals-equals pin the findings did not state. Turbopuffer and Redis Stack replaced `latest` with a number. Several findings said outright that the bare command "works as given" or was "confirmed live", and the worker still added a tag.

18. **The drift is strongest when findings say nothing is wrong.** Where the research stage verified a command as working, workers felt free to polish it. Entries with a known problem were copied more carefully. Lesson: put the strictest wording where the temptation to improve is greatest.

19. **I logged two checks without reading the entry, and the user caught it.** The Elasticsearch verdicts were written from the findings alone. I removed them, read the applied cell and the findings section side by side with a helper script, and logged three checks that reflect what is actually there. The score went from 63% to 61%, then settled at 61% on 31 checks. Lesson: a reviewer's checks need evidence that points at the applied text, and the tooling should make reading both sides the easy path.

20. **Elasticsearch also got an unsourced extra.** The worker added a commented `podman run` line. It is probably equivalent to the docker line, but findings never mention it. That is a smaller version of the invented-details problem in the original notebooks, caught by the same kind of review.

## 2026-10-29 — news-and-reading apply-findings review (score 94%, 33 checks, 31 confirmed, 2 corrected, 0 wrong)

21. **The best score came from the notebook with the fewest run-command changes.** Both corrections were omissions rather than substitutions: the optional `--opml` flag for the generic RSS entry was not carried across, and Instapaper's `.env` example was left out because the apply log claimed the findings documented no config, which they did.

22. **A worker's own log can be wrong about the findings.** The Instapaper worker wrote that no config blocks were added because none were documented. Reading the findings section showed otherwise. Lesson: check the apply log against the findings, not as a substitute for them.

## 2026-10-29 — search-and-research apply-findings review (score 100%, 15 checks, 15 confirmed, 0 corrected, 0 wrong)

23. **The first perfect score came after the brief was tightened, not by luck.** Rules 4, 4b and 4c were all in place before this worker started. Every run command matched findings exactly, including the entries where findings itself keeps `@latest`. The two hardest entries, Google Search and Playwright, were handled correctly: both broken commands were replaced with the uv path, the Serper env var stayed marked unverified, and the Docker TODO was resolved with the right image name.

24. **A clean score still gets a second look.** Fifteen confirmed with no corrections was unusual enough that the highest-risk entries were re-read after the fact. They held up. Lesson: when a result is better than every earlier one, spot-check it rather than trusting the number, because the earlier reviewer may have been in a hurry.

## 2026-10-29 — travel-and-maps apply-findings review (score 93%, 15 checks, 14 confirmed, 1 corrected, 0 wrong)

25. **The one miss was a leftover audit note, not a wrong fact.** The Skyscanner entry correctly replaced the broken `uvx` command with a recursive clone, but its dated audit note still said a pywaze-style copy-paste error had been corrected. The entry text never mentions pywaze, so a reader cannot follow the note. Lesson: dated audit notes copied from findings need the context that makes them readable on their own.

26. **Workers handled the placeholder and the dead-alt cases well.** Lyft kept its placeholder and recorded the risky candidate in the notes without adopting it. OpenWeatherMap carried the dead jezweb alternative and the HTTP-only fgladisch alternative with its different env var name. No invented details appeared.

## 2026-10-29 — productivity apply-findings review (score 93%, 27 checks, 25 confirmed, 2 corrected, 0 wrong)

27. **Seven entries had broken run commands and all seven were fixed.** Google Calendar, Todoist, 1Password, Readwise, Raindrop, Toggl and Google Tasks each named a package or repo that does not exist or does not do what the entry claimed. The workers replaced them using findings, and several went further correctly: 1Password was rewritten to say the official server cannot return secrets at all, and Craft's stale placeholder was replaced by the hosted OAuth server.

28. **Honest uncertainty survived the apply step.** Craft's endpoint path was truncated at the source and the worker left it marked UNVERIFIED instead of guessing. Toggl's possible official CLI stayed flagged as unverified. This is the opposite of the invented-details failure in the first notebooks, and it is the behaviour the brief was written to produce.

29. **Both corrections were rule 4b gaps.** Google Tasks and Evernote each left the Config file section as prose with no example block, even though findings described the files and a sibling entry in the same notebook showed the exact format. This is the same omission seen in earlier notebooks, and it survived the brief change twice out of 27 entries.

30. **A worker's faithful copy can look like a deviation.** Obsidian's `@2`, Weather.gov's `@latest` and four productivity entries with `@latest` all looked like added version tags. In every case findings gave that exact string. Lesson: compare against the findings run line before calling a suffix a deviation.

## Scores so far, all apply-findings tasks

- news-and-reading: 94% (33 checks, 31 confirmed, 2 corrected)
- personal-finance: 80% (30 checks, 24 confirmed, 6 corrected)
- vector-and-rag: 61% (31 checks, 19 confirmed, 12 corrected)
- shopping-and-commerce: 61% (36 checks, 22 confirmed, 14 corrected) — corrected after deduplication
- social-networks: 56% (32 checks, 18 confirmed, 14 corrected)
- search-and-research: 100% (15 checks, 15 confirmed, 0 corrected)
- productivity: 93% (27 checks, 25 confirmed, 2 corrected)
- travel-and-maps: 93% (15 checks, 14 confirmed, 1 corrected)

## Brief changes made in response (APPLY-BRIEF.md)

- Rule 4 strengthened: run commands copied exactly, no version tags, no commit suffixes, no change of install source.
- Rule 4b added: a Config file section must contain the example block.
- Rule 4c added: when findings call an intro claim stale, fix the intro, not only the Notes.
