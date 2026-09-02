# Task breakdown — status

Updated 2026-09-02. Status: `[x]` done · `[~]` in progress · `[ ]` to do

Send three links: **dashboard URL · repo · 5-min video.**
Repo must contain `predictions.csv`, `note_classifications.csv`, `NOTES.md`, code.

Cut order if short (say so in the video): 1. dashboard polish · 2. Requirement 2
(what to do) · 3. depth on the trained-model question in NOTES.md.
**Never cut:** the prediction answer, the note-sorting check, loading a new week.

---

## Done `[x]`

### Analysis & decisions
- [x] Brief understood, target week, BCEA rules, earnings threshold
- [x] Hours reconcile exactly with the client; breach = `total_hours > 55.0`
- [x] The 5 duplicate-identity people found & consolidation designed
- [x] Hours under-recording found (13.5h cap, open shifts = 0h, no-shows = no row)
- [x] No fixed rosters; −0.75 half-week correlation; the "invisible 40%"
- [x] Opus independent deep-analysis pass (`ANALYSIS_opus.md`)
- [x] Docs: `assumptions.md`, `data_checks.md`, `SUMMARY.md`,
      `CLASSIFICATION.md`, `DASHBOARD.md`

### Prediction — code
- [x] `pipeline/load.py` — schema validation, partial weeks first-class
- [x] `pipeline/hours.py` — durations, weekly totals, identity consolidation,
      `is_breach`, `latest_cutoff_dow`, chronological OT attribution
- [x] `pipeline/features.py` — per-person history, pooled per-cutoff slope
- [x] `pipeline/predict.py` — distributional projection, **any cutoff day**,
      per-cutoff threshold, stamped per employee_id
- [x] `backtest/simulate_wednesday.py` — expanding-window + `--by-cutoff`
- [x] Adopted the Opus slope simplification + fixed its 2 bugs
- [x] Backtest: PR-AUC 0.43 (0.24 ordinary employees), calibrated, beats
      naive baselines; documented

### Classification — code + check
- [x] `pipeline/classify.py` — 7-category rules, multilingual lexicon,
      precedence, sub-fields, surname canonicalisation
- [x] `pipeline/gold_sample.py` — frozen 180-note stratified sample + xlsx
- [x] Gold set hand-labelled (`outputs/gold_sample_labelled.csv`), reviewed
- [x] `check/classify_check.py` — rules vs gold: 100% random-100, κ 0.99,
      per-category + confusion + language + confidence slices + targeted audits
- [x] `check/second_method.py` — TF-IDF+kNN, 95% agreement, 0 rule errors,
      cluster alignment; outputs committed
- [x] `outputs/note_classifications.csv` — 2,117 rows, 0 unclassified
- [x] `CLASSIFICATION.md §4` split (measured) + `§5` full check writeup +
      `§5f/§5g` the writer-specific limitation and the rules-vs-LLM argument

### Overtime split
- [x] `pipeline/attribute.py` — chronological attribution → asked-for vs
      operational-failure; concentration by site/driver/absentee
- [x] Numbers: 21% attributable, 78% operational failure; loose 48% of
      breach-weeks

### Tests
- [x] 22 passing (`test_hours`, `test_predict`, `test_classify`,
      `test_attribute`, `test_second_method`)

---

## To do `[ ]`

### 1. Prediction — finish
- [x] `outputs/predictions.csv` generated (213 rows) + asserted in test_pipeline
- [x] Target-week answer + backtest numbers captured (README table, NOTES)
- [ ] Open-shift `risk_score` adjustment for partial-week open shifts
      (deterministic — `data_checks.md §3a`) — **cuttable, low priority**

### 2. "What to do about it" (Requirement 2)  `[x]` mostly
- [x] `pipeline/actions.py` — one rec per flagged person, strict priority:
      consolidate (+ roster cut if breaching) → close open shift → monitor
      (at risk, < 55h) → shift-swap (breach only, same site / role, receiver
      stays < 45h) → authorise OT / structural gap
- [x] Swap guardrail: same site only, receiver never past 45h, receiver dedup
- [x] Cost = 0.5× OT premium on hours that change status
- [x] `double_booking_alert()` — the 5 pairs, independent of this week's flag
- [x] `attribute.phantom_absences()` — the 5 split-identity people as an absence
      problem: 39 phantom no-shows / 10 wks (14 cross-site), ~510h double-paid;
      wired into alerts, why-split, ops-review, per-person action + the mockup
- [x] Finding logged: swaps rarely fire (roster at capacity) — that's honest,
      documented in `DASHBOARD.md §4`
- [x] Strategic recs (float pool, roster to 40h, upstream visibility, hard cap,
      Sunday rotation, re-price) → for NOTES/video, not the dashboard
- [x] Open-shift + repeat-absentee + phantom-absence data in the ops-review tab
- [x] Recommendations rewritten as headline + short bullets (actions.py `steps`)
- [x] tests: 6 in `test_actions.py`

### 3. Pipeline orchestration  `[x]`
- [x] `pipeline/aggregate.py` — build `dashboard_data.json` (headline, risk
      list w/ tiers, site triage, alerts, why-split + under-recording,
      per-person detail w/ open-shift markers, ops-review)
- [x] `pipeline/run.py` — `python -m pipeline.run data` → all 3 outputs
- [x] Under-recording finding wired into 3 tabs (why / person detail / ops)
- [x] tests for aggregate + run (test_pipeline.py, 3 tests) — 31 total green
- [ ] `Makefile` convenience target (optional)

### 4. Dashboard (deployed URL)
- [x] HTML mockup (Jem palette, 3-tab layout) as design + theme reference
      → artifact URL in memory
- [x] `app.py` — Streamlit, 3 tabs (Now / Why / Ops Review), Jem palette via
      `.streamlit/config.toml` + inline CSS; as-of banner, headline tiles,
      "fix these first" (phantom absences + open shifts), site triage,
      risk list w/ inline person detail + weekly bar chart, watch-tier toggle
- [x] Sidebar file-upload → schema check (7 named files) → pipeline re-runs →
      board updates + predictions/notes CSV download buttons
- [x] AppTest smoke test: 0 exceptions, reload path verified on the real export
- [ ] Deploy to Streamlit Community Cloud → URL
- [ ] Build a synthetic partial-week "next week" export, test the reload live
- [ ] Phone-legibility check on a real phone

### 5. `NOTES.md` (ships — ≤ ~½ page)
- [x] Draft written — assumptions · classifier check + where wrong ·
      trained-model / LLM question + honest backtesting
- [ ] **Your pass in your own words** — it currently reads as mine

### 6. Video (5 min, camera on)
- [ ] Outline + record
- [ ] Show it working
- [ ] Unexpected finding — the 5 ghost IDs / under-recording / −0.75 corr
- [ ] Baseline + which metric + **why that one** (recall-leaning, not accuracy)
- [ ] Where we don't trust it — the invisible 40%
- [ ] What we'd do with 2 more days — roster/leave data, daily refresh, LLM
- [ ] **Explain one number end-to-end**, simply — candidate: E1099's risk_score,
      or one classified note

### 7. Repo + submit
- [x] `git init`, `main` branch, first commit (f5e8e39)
- [x] Brief moved to `BRIEF.md`; wrote our own `README.md` (how to run, deploy,
      layout, backtest table)
- [x] `NOTES.md` drafted (assumptions · classifier check · trained-model
      question) — **needs a pass in your own words**
- [x] `requirements.txt` already has streamlit; app has a fallback that rebuilds
      `dashboard_data.json` from `data/` if it's missing (fresh-deploy safe)
- [x] All 31 tests green, tree clean
- [ ] **You:** create GitHub repo `jem-overtime-ops` (Public) + `git push`
- [ ] **You:** deploy on share.streamlit.io → get the `.streamlit.app` URL
- [ ] Decide: keep working docs (`ANALYSIS_opus.md`, `SUMMARY.md`, `TASKS.md`,
      `assumptions.md`, `data_checks.md`, `CLASSIFICATION.md`, `DASHBOARD.md`)
      or move to `docs/` — currently all shipping
- [ ] Public **or** invite `southafricanrob`
- [ ] Reply to the email with the 3 links (dashboard · repo · video)

---

## Dependency order for what's left
2 (actions) → 3 (aggregate + run) → 1 (predictions.csv, fits anywhere) →
4 (dashboard) → deploy → 5 (NOTES) → 6 (video) → 7 (submit)
