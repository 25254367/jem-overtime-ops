# NOTES

Draft — to be tightened in my own words before submission.

## Assumptions

- **Target week** is the Monday–Sunday week still in progress when the data
  stops (data runs through Wednesday). The pipeline derives the cutoff day from
  the export, so this isn't hard-coded.
- **Breach = `total_hours > 55.0`** for the week (45 ordinary + 10 overtime,
  BCEA). Hours = Σ(clock_out − clock_in); a blank clock_out counts 0h; a
  clock_out ≤ clock_in adds 24h. This reproduces the client's
  `weekly_summary.csv` exactly (2,122/2,122 rows).
- **Overtime is per person, not per payroll record.** Five people hold two
  `employee_id`s each (shared ID number, bank account, tax number). Their
  records are merged before the breach is computed.
- **All employees are in scope** — the BCEA overtime cap applies regardless of
  the earnings threshold for the sites in this data.
- **No roster is provided.** "Likely remaining shifts" are inferred from each
  person's own recent weekday pattern.
- The recorded hours **understate** reality: 184 shifts (2.1%) are clocked in
  but never out (logged 0h), shift length caps at 13.5h, and a no-show creates
  no row at all. So operational-failure overtime is a floor, not a point
  estimate.

## How the note-sorting was checked, and where it's wrong

Notes are classified by **rules** (deterministic, ~50 phrase templates, a small
isiZulu/Afrikaans lexicon) into seven categories. Two checks (full detail in
`docs/CLASSIFICATION.md` §5; reproduce with `python check/classify_check.py`):

1. **Against 180 hand-labelled notes** (100 random + 80 targeted at the rare
   categories, labelled blind): **100% category accuracy on the random 100,
   κ = 1.00**. Not one category disagreement in all 180. The sub-fields hold
   up too — absence reason 100%, authorised 100%, absentee name 98.9% (one
   miss, and that was a typo in *my* gold label).
2. **Against an independent model** (TF-IDF char n-grams + kNN, sklearn only):
   **95.1% agreement** across all 2,117 notes. I inspected every one of the 104
   disagreements — **none were a rule error**; they were the kNN guessing on
   sparse notes ("no incidents" → it picked absence_cover).

**Where it's weak:** the data is ~50 underlying templates from a handful of
supervisors, so this measures whether the rules capture *those writers'
phrasing* — not whether they generalise. A new site or writer needs the lexicon
extended, and the learned second method is what you'd lean on there. The
attribution split (21% of overtime hours have a note explaining them; of those,
78% are an operational failure) is only as good as that 21% note coverage — the
honest range on "operational-failure overtime" is 21% strict to 48% of
breach-weeks loose.

## What a trained model / LLM would add, and how to test it honestly

- **An LLM** would handle the garbled and code-switched notes without a
  hand-built lexicon, and generalise to a new supervisor's phrasing. It
  wouldn't change the headline much here (the rules already hit ~100% on
  clean notes) and it costs a paid API + per-run latency, which the brief
  rules out. The rules are also inspectable, which matters for a compliance
  tool.
- **A trained breach model** (small GBDT on person-week features) needs the
  roster to beat the current approach. The missing signal is *how many shifts
  is this person scheduled for the rest of the week* — without it, ~40% of
  breaches are invisible on Wednesday regardless of model.
- **Testing on hundreds without fooling yourself:** expanding-window backtest —
  for each historical week, pretend it's Wednesday, fit only on earlier weeks,
  predict, score (`backtest/simulate_wednesday.py`). Never fit on the week
  you're scoring. Report precision/recall/PR-AUC (not accuracy — the base rate
  is ~5%, so all-zeros scores 95%), lean toward recall because a missed breach
  is the expensive error, and check calibration bucket by bucket. Split out the
  five split-identity people, because they inflate the aggregate metric
  (PR-AUC 0.43 with them, 0.24 without).
