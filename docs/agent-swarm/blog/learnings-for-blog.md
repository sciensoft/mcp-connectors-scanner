# Learnings to capture in the blog post

Running notes, added as they happen. Raw material, not prose.

## From the apply-step QA (2026-10-29)

**Setup:** five workers each applied their verified findings to a copy of a notebook. The supervisor then reviewed every entry against the findings and scored it with the toolkit's QA commands. First notebook reviewed: personal-finance, 15 entries, 30 checks.

**Result:** 24 confirmed, 6 corrected, 0 wrong. Score 80%.

1. **The facts were right; the discipline slipped.** Every pin, env var name, name correction and attention label matched the findings. All six deviations were the worker "improving" something it was told to copy: adding a commit suffix to a git URL, switching an install from GitHub to npm, leaving a config header empty, leaving a stale intro line. None were wrong facts, all were unverified edits.

2. **"Copy character for character" is not enough of a rule.** The brief said run commands must be verbatim, and four of fifteen entries still broke it. Workers rationalised each edit as harmless (for example, "the git form was only used because no pin had been chosen"). The rule had to be rewritten to name the specific forbidden edits and give the worker somewhere to put the suggestion instead (Notes, marked UNVERIFIED).

3. **A plausible change is not a verified change.** Several edits were probably fine. That is exactly why they are dangerous: nobody tests them, and a wrong run command ships silently. The scoring needed a "corrected" verdict that is lighter than "wrong" so plausible-but-unverified is visible without being counted as a failure of the facts.

4. **Worker self-verification is not independent evidence.** Same lesson as the audit stage: the logs claimed everything matched, and the review found six exceptions.

5. **Score at the claim level, not the notebook level.** One entry yields several checks (pin, env vars, run command, config, label). Scoring per claim showed that content was strong and run commands were the weak spot, which a single per-entry pass or fail would have hidden.

6. **Review the output, not the log.** The apply log is the worker's own account. The check that mattered was opening the actual cell and the findings section side by side.

7. **Structural checks are cheap and catch a different class of problem.** A script confirmed same cell ids, same order, same entry count, same metadata and valid JSON for all five notebooks in under a second. It proves the files are well formed and says nothing about whether the content is right. Both checks are needed.

8. **Fix the brief, then rerun only the failures.** After the first review the brief was tightened (strict run-command rule, no empty config headers, fix stale intro text, not only Notes). The plan is to rerun only the entries that broke the rules, not whole notebooks.

## From tooling and operations

9. **Do the delegation the way you say you will.** The user pushed back mid-session: the research, fixes and version pinning belong to the workers, and the supervisor only reviews and assesses. The supervisor's job is task setup, launch, and independent checking.

10. **Verify "finished" against the files, not the status.** The registry said done; the check that counted was listing each sandbox for the applied notebook and the log, and confirming the user's repo had no new modifications.

11. **Workers wrote to a copy, never the repo.** A deny rule on editing the project plus per-worker sandboxes meant nothing touched the repo until review and approval.

12. **Shell guardrails shape the workflow.** The shell connector rejects pipes, substitution and wildcards, and even a dollar sign inside quoted text. Small helper scripts written to disk and run by name were the clean workaround.

13. **Voice mode adds its own failure modes.** Cut-off sentences, background noise transcribed as speech, and mixed languages all happened. Asking what the user meant, instead of guessing, avoided acting on noise.

## From the second notebook reviewed (shopping-and-commerce)

14. **The same failure repeated across independent workers.** Shopping-and-commerce scored 73% (22 confirmed, 8 corrected, 0 wrong) against personal-finance at 80%. Seven of the eight corrections were the identical edit: a version tag added to a run command the findings gave without one. Different workers, different notebooks, same shortcut. That is a signal about the instruction, not about one worker's quality.

15. **Both weak scores came from the same small rule, not from facts.** Across 60 checks and two notebooks, no fact was wrong. Every pin, env var name, name clash, alt and attention label matched. The only recurring loss was one rule about run commands. Scoring per claim is what made that visible.

16. **Honest scoring needs a judgment tier.** Adding a version tag that matches the findings' own pin is not the same as swapping an install source. Keeping a middle verdict (corrected) between confirmed and wrong let the review say 'plausible but not what you were told to do' without calling it an error.

17. **Ambiguous rules produce ambiguous output.** Etsy exposed a conflict in the brief: 'do not swap the primary' versus 'findings say this command cannot work'. The worker followed the first and left a known-broken command live. When two rules collide, the worker picks one silently, so the brief should say which wins.

18. **Dropped caveats are a quieter failure than wrong facts.** In one entry a second UNVERIFIED item was not carried over. The rest of the entry was perfect. A reviewer who only checks for wrong values would miss it. Review for omissions as well.

19. **Review at the start of a batch tells you what to fix in the next one.** The brief was tightened after the first review, but the five workers had already run. The real test of the new rule only comes with the next run, so the second batch of results is a baseline, not a verdict on the fix.

## From the third notebook reviewed (social-networks)

20. **The score fell again, and the cause was still one rule.** Social-networks scored 56% (18 confirmed, 14 corrected, 0 wrong), after 80% and 73%. Eleven of the 14 corrections were run commands that the worker edited: version tags added to npm and PyPI commands, commit suffixes added to git URLs. Across 92 checks and three notebooks there has still not been one wrong fact.

21. **A score can fall for reasons that have nothing to do with worker quality.** The notebook with the lowest score was also the one with the most entries where a version tag could be added. The score measures how often a tempting shortcut was available as much as how often it was taken. A raw percentage needs the denominator explained.

22. **Two different kinds of shortcut deserve two different severities.** Adding `==1.2.3` to a command whose version the findings already state is a small risk. Appending a commit to a git URL, or swapping an install source, changes what gets installed. The reviews scored both as corrected, which is honest but flat. A severity field on the verdict would have separated them.

23. **Empty headers are a quiet failure.** A 'Config file' heading with a description and no example looks finished. It appeared in several entries across notebooks. Brief rules should say what a section must contain, not only that it must exist.

24. **Review work scales badly by hand.** Reviewing 15 entries meant reading the applied cell and the findings side by side, then logging two to three checks each. It took about 45 calls per notebook. The review itself is the next thing to automate: run commands could be compared by script, leaving a human or model to judge only the entries the script flags.

## Final scores, all eight apply-findings tasks (2026-10-29)

| Notebook | Checks | Confirmed | Corrected | Wrong | Score |
|---|---|---|---|---|---|
| search-and-research | 15 | 15 | 0 | 0 | 100% |
| news-and-reading | 33 | 31 | 2 | 0 | 94% |
| productivity | 27 | 25 | 2 | 0 | 93% |
| travel-and-maps | 15 | 14 | 1 | 0 | 93% |
| personal-finance | 30 | 24 | 6 | 0 | 80% |
| vector-and-rag | 31 | 19 | 12 | 0 | 61% |
| shopping-and-commerce | 36 | 22 | 14 | 0 | 61% |
| social-networks | 32 | 18 | 14 | 0 | 56% |

Across 219 checks (168 confirmed, 51 corrected) there was not one wrong fact. Every loss was a discipline slip: an added version tag, a missing config example, or a leftover note.

**The brief change worked.** The three notebooks reviewed after rules 4, 4b and 4c were tightened scored 100%, 93% and 93%. The five reviewed before it scored between 56% and 94%. The notebooks differ in how many shortcuts were available, so the comparison is suggestive rather than clean.

**A faithful copy can look like a deviation.** Several run commands carried `@latest` or `@2`. Findings gave those exact strings, so they were correct. The review has to compare against findings, not against a general rule.

## To add later

- Real cost, token and duration numbers from the logs.
- Before and after of the run-command rule.
