# Prediction model

How `predictions.csv` (`employee_id, will_breach, risk_score`) is produced, and
how it was checked. Code: `pipeline/features.py`, `pipeline/predict.py`.
Backtest: `backtest/simulate_wednesday.py`.

## The question

It is Wednesday. The Monday–Sunday week is half over. For each person: will
their **total hours exceed 55** (45 ordinary + 10 overtime, the BCEA cap) by
Sunday?

## Steps

1. **Hours.** `duration = clock_out − clock_in`; blank clock_out = 0h;
   clock_out ≤ clock_in adds 24h; no break deduction; no rounding. This
   reproduces the client's `weekly_summary.csv` exactly (2,122 / 2,122 rows).

2. **Consolidate identity.** Union-find over `employee_id`s that share an
   `id_number`, `tax_number`, or `account_number`. Five people hold two records
   each. Overtime is per person under the BCEA, so hours are summed per
   `person_id` before the breach is computed — otherwise the breach is
   invisible (two records, each under 45h). See [`data_checks.md`](data_checks.md) §3c.

3. **Split each person-week at the cutoff** into `observed` (hours through
   Wednesday) and `remaining` (Thu–Sun), from the 9 completed weeks of history.

4. **Project the remaining hours as a distribution.**
   `remaining ~ Normal(µ, σ)` where
   - `µ = rem_mean + slope · (observed − obs_mean)` — a person ahead of their
     usual mid-week pace is tilted up. `slope` is **one pooled within-person
     OLS slope** (de-meaned per person, then fit across everyone), re-fit for
     the actual cutoff day (≈ −0.75 at Wednesday: people who front-load ease
     off later). A single pooled slope beat per-person slopes in the backtest —
     nine weeks is too few to fit a slope per person.
   - `σ = rem_std · √(1 − corr²) · 1.15 + 2.0 · open_shift_rate` — the residual
     spread, nudged up, and widened when the person has un-clocked-out shifts
     this week (their real hours are understated).

5. **`risk_score = P(observed + remaining > 55)`** from that normal.
   `will_breach = risk_score ≥ threshold`.

## Any cutoff day

The pipeline reads `latest_cutoff_dow` from the export and re-fits the slope and
picks the threshold for that day. A Monday prediction and a Saturday one are
very different — the backtest PR-AUC runs 0.36 (Mon) → 0.43 (Wed) → 0.49 (Fri)
→ 0.65 (Sat). The dashboard banner states which day the data covers and how
much to trust it.

`THRESHOLD_BY_CUTOFF` is set on the backtest for a recall-leaning operating
point (default 0.24 at Wednesday).

## How it does — expanding-window backtest

For each historical week, pretend it is Wednesday, fit only on earlier weeks,
predict, score. 1,248 person-weeks, 65 breaches (5.2%).

| model | precision | recall | F1 |
|---|---|---|---|
| all-zero | – | 0.00 | 0.00 |
| naive: history mean > 55 | 0.63 | 0.19 | 0.29 |
| naive: linear extrapolation ×7 | 0.11 | 0.62 | 0.18 |
| ours: projected central estimate > 55 | 0.64 | 0.22 | 0.32 |
| **ours: risk_score ≥ 0.24 (default)** | **0.46** | **0.46** | **0.46** |

- **`risk_score` PR-AUC 0.43** (prevalence 0.052).
- **Ordinary employees only: PR-AUC 0.24** — the five split-identity people are
  much easier to flag (their combined hours breach most weeks), so they carry a
  large part of the headline number. Stated honestly.
- **Calibrated:** risk-score bucket → actual breach rate is
  0.0–0.1 → 2.6%, 0.1–0.25 → 12%, 0.25–0.5 → 35%, 0.5–0.75 → 50%, 0.75–1.0 → 88%.

## Metric choice

PR-AUC and recall-leaning precision/recall/F1 — **not accuracy**. The base rate
is ~5%, so predicting "no one breaches" scores 95% accuracy and is useless. A
missed breach (a compliance breach the manager didn't see coming) is the
expensive error, so the threshold is set for recall.

## Where it is weak

- **No roster in the data.** "Likely remaining shifts" are inferred from each
  person's own weekday pattern. The missing signal — *how many shifts is this
  person scheduled for the rest of the week* — is exactly what would close the
  gap.
- **~40% of the breaches score ≤ 0.10 on Wednesday.** They come from shifts
  added Thu–Sun that nothing on Wednesday predicts. This survived a 45-feature
  attack; it is a data limit, not a model one.
- **Nine weeks of history**, one site cluster, one season. The slopes and
  thresholds would need refitting on more data.
- Recorded hours understate reality (open shifts logged 0h, 13.5h shift cap,
  no-shows leave no row), so the true breach rate is a little above the
  recorded 5% — see [`data_checks.md`](data_checks.md) §3a.
