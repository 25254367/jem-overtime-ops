# data_next_week/ — synthetic "next week" export

There is no real next week in the assessment data (it stops Wednesday 12 Aug).
This folder is the assessment data rolled forward one week by
`scripts/make_next_week.py`, to demonstrate Requirement 4 — loading a new week
without a developer.

Drop these seven CSVs into the dashboard's **"Load next week's data"** panel:

- the newest week is now **Mon 17 – Sun 23 Aug**, running through **Friday**
  (not Wednesday), so the board re-fits to a Friday cutoff and the banner
  flips to "accuracy: good"
- more days of data → more confirmed breaches, a higher projected OT cost
- the five split-identity people are still detected
- `weekly_summary.csv` is regenerated from the shifted shifts, so it still
  reconciles exactly

`../data_next_week_broken/` is the same export with a column removed from
`shifts.csv` — upload it to see the validation fail loudly with a readable
message instead of a stack trace.
