# Changelog

Every prompt and workflow change: the problem, the change, the expected effect and the result.

## 2026-10-29  Critic v1 → v2

- Problem: Critic was too strict (1/10 PASS). It failed plans for general advice not in the data (visa, transfers, baggage, check-in) and once asked for refund warnings when the data had none.
- It also passed TRV-05 while still listing issues.
- Change: Rule 4 now only covers risks that appear in the request or Approved data. Added: judge only against request + Approved data; any rule-breaking issue = FAIL; PASS must have an empty issues list.
- Expected effect: fewer unfair FAILs (e.g. TRV-10 Cairo should pass); TRV-01 may still FAIL for offering booking links (rule 5).
- Planner prompt: unchanged (v1).
- Result after v2: 5/10 PASS (was 1/10).

## 2026-10-29  Critic v2 → v3

- Problem: Run 2 gave 0/10 PASS (run 1 gave 5/10) with the same prompts - Critic inconsistent.
- It treated any offer as breaking rule 5 (e.g. offering a printable itinerary).
- Also seen: revised TRV-04 began with "Result: FAIL" - Planner copied Critic wording into the plan.
- Change: Rule 5 now lists the specific forbidden abilities (search beyond Approved data, book, pay, hold/reserve, links/contact details); reformatting/adjusting the plan is allowed.
- Critic Model switched from gpt-5-mini to gpt-4.1-mini with temperature 0 for repeatable verdicts.
- Planner prompt: unchanged (v1).

## 2026-10-29  Workflow fixes + baseline run (Critic v3 frozen)

- Fixed: leading spaces before `{{ }}` in If node and Set fields (caused all items to go to FAIL branch and a tab before Test_ID). If node now uses `{{ $json.output.verdict.trim().toUpperCase() === 'PASS' }}` is true.
- Consistency test: two runs, both 7 PASS / 3 FAIL (TRV-04, TRV-09, TRV-10 revised).
- Known Critic quirks (not fixing - Critic frozen from here): sometimes lists notes under issues on a PASS; TRV-09 and TRV-10 failed for reasons that don't break any rule.
- Baseline output: `results/plans_run1_planner_v1.csv` (Planner v1, Critic v3).

## 2026-10-31  Human evaluation of baseline

- Human grades: 6 PASS / 4 FAIL. Over-promising x3 (TRV-05, 07, 08), Poor Recommendation x1 (TRV-04).
- Critic agreed with human on 5/10 (passed 05, 07, 08; failed 09, 10).
- Likely cause: Planner v1 only says "do not book or pay"; it never lists other things it cannot do (search, look up, hold, links, non-approved data) or how to end, so it ends with offers it cannot keep.

## 2026-10-31  Planner v1 → v2 (ONE instruction added; Critic v3 unchanged)

- Added: "You cannot search, look up information, check live prices or availability, hold or reserve anything, or send links, and you cannot use any flight, hotel or price that is not in the Approved data. Never offer to do any of these. End with one short question about the plan itself, such as which option the traveller prefers."
- Expected: fixes the 3 Over-promising failures; should not change TRV-04 (different cause).
- Rerun set: `data/rerun_trips_v2.csv` = failed TRV-04, 05, 07, 08 + passed TRV-01, 02 (regression check).

## 2026-10-31  Run 2 results (Planner v2 / Critic v3) - human graded

- Rerun set: TRV-04, 05, 07, 08 (failed) + TRV-01, 02 (passed). Same requests, new IDs (-v2).
- Same 6 requests: Run 1 = 2/6 PASS → Run 2 = 5/6 PASS.
- Fixed (FAIL→PASS): TRV-05, TRV-07, TRV-08 (all 3 Over-promising). Regressions (PASS→FAIL): none.
- Still fails: TRV-04 - now Constraint Violation: headline recommends 1 adult / 2 nights instead of 2 adults / 7 nights. Likely side effect of the new "end with a question about the options" instruction.
- By dimension: Risk & Honesty FAILs 3 → 0; Constraint Compliance FAILs 0 → 1; Rec. Value FAILs 1 → 1.
- Next candidate fix (Planner v3): never change travellers, dates or nights in the recommendation; such changes may only be listed as options.
