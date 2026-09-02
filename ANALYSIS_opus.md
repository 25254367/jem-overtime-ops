# Independent analysis — can the breach prediction be improved?

*Produced by an independent Opus deep-analysis pass, 2026-09-01. Read-only on
the pipeline; all numbers on the same expanding-window splits as
`backtest/simulate_wednesday.py` (6 test weeks, 1,248 person-weeks, 65 breaches,
5.21%). Uncertainty = cluster bootstrap by week; bootstrap SD of PR-AUC ≈ 0.035,
so Δ < 0.02 PR-AUC is noise.*

## 0. Headline

1. **The 0.414 PR-AUC is mostly the ghost-ID fix, not the model.** The 5
   consolidated double-identity people are 30 of 1,248 rows (2.4%) but **18 of
   the 65 breaches (28%)**. Drop them and PR-AUC falls **0.414 → 0.223**. The
   identity consolidation is worth more than every modelling choice combined.
2. **One small, defensible change** — drop the per-person slope and the
   `MAX_SLOPE` cap, fix the pooled-slope estimator, use the pooled correlation
   in the conditional SD. PR-AUC 0.414 → 0.433, best-F1 0.444 → 0.451, and it
   *deletes* code. The metric gain is **inside the noise band** (Δ +0.019, 90%
   CI [−0.019, +0.041]); the honest case is that it is positive in every split
   and stratum, improves mid-range calibration, and removes a biased estimator.
3. **Everything else fails, informatively.** GBDT and regularised logistic are
   *significantly worse* (Δ −0.09 to −0.22, p < 0.05). Recency weighting:
   nothing. Per-weekday projection: algebraically identical to what exists.
   Isotonic: harmful. Note text: ROC-AUC 0.468 — worse than a coin. The
   invisible-40% claim **survives**.

**Verdict: the current approach is at the information ceiling for this data.**
The one change worth making is a simplification that happens to score
marginally better.

## 1. Baselines and current model, same splits

| Ranker | PR-AUC | ROC-AUC | best F1 | P | R |
|---|---|---|---|---|---|
| prevalence (all-zero) | 0.052 | 0.50 | — | — | — |
| naive: `hist_mean` | 0.347 | 0.828 | 0.400 | 0.337 | 0.492 |
| naive: linear ×7/3 | 0.184 | 0.745 | 0.247 | 0.173 | 0.431 |
| `observed` alone | 0.184 | 0.750 | 0.246 | 0.172 | 0.431 |
| `projected_total` (point) | 0.419 | 0.833 | 0.432 | 0.386 | 0.492 |
| **current `risk_score`** | **0.414** | 0.863 | 0.444 | 0.500 | 0.400 |

`hist_mean` alone scores 0.347. **The distributional projection buys +0.067
PR-AUC over "rank people by their historical average week"** — that is the
honest size of the model's contribution, and a better number for the video than
0.414 vs 0.052.

## 2. What did NOT work

### 2.1 Per-weekday projection — algebraically the same thing
`Σ_d P(work|d)·E(hours|d,worked)` over Thu–Sun **equals** the person's mean
Thu–Sun hours (agree to floating point on all 1,248 rows). No information at the
mean. Variance route: PR-AUC 0.381 vs 0.415. The "hard Mon–Wed then zero
Thu–Sun" mixture it exists to capture is **7 rows of 1,248**. Dead end.

### 2.2 Recency weighting — no drift to exploit
Half-life 2/3/4 weeks: ΔPR-AUC −0.006 / −0.000 / +0.002, all CI-straddling
zero. Thu–Sun MAE flat at 4.5h. Weekly totals are stationary (per-week
population mean 42.3–43.5h, no trend).

### 2.3 A trained model is *significantly worse*
Expanding-window training, features from each row's own history only:

| Model | PR-AUC | Δ vs projection (90% CI) |
|---|---|---|
| distributional projection | **0.415** | — |
| GBDT, 9 features | 0.323 | −0.093 [−0.155, −0.042] |
| GBDT, 36 features | 0.302 | −0.113 [−0.176, −0.062] |
| GBDT, 36 + role/site/pattern | 0.311 | −0.104 [−0.177, −0.044] |
| logistic 9f, balanced | 0.301 | −0.114 [−0.220, −0.017] |
| rank-ensemble (projection + GBDT) | 0.391 | −0.024 [−0.062, +0.012] |

ROC-AUC stays 0.82–0.85 while PR-AUC collapses — the learners rank the bulk
fine and wreck the head of the list, the only part anyone acts on. Even with an
**unfairly generous** leave-one-week-out protocol (training on future weeks),
GBDT 36f hits 0.435, Δ +0.020, p(Δ>0) = 0.69 — cheating does not significantly
beat a four-parameter closed form. That is the `NOTES.md` answer.

### 2.4 Calibration layers
Isotonic destroys 0.08 PR-AUC (ties blocks of scores; nothing to fit with 65
positives). Platt is monotone, improves log-loss by 0.003 — the §3 change gets
the same mid-range fix structurally without a layer to re-fit weekly.

### 2.5 Distribution shape does not matter for ranking
Student-t (df 3/5/8): ΔPR-AUC 0.000. Ranking by `projected_total` with **no
sigma at all** scores 0.431 vs 0.433 for the full per-person uncertainty model.
The uncertainty model is worth +0.002 PR-AUC — **keep it as a calibration
device that turns a projection into a readable probability, not as a ranking
device**, and say so in the docs.

### 2.6 The invisible 40% — confirmed after a serious attempt to break it
26 of 65 breaches score ≤ 0.10. Within that stratum (1,048 rows, 26 positives),
univariate AUC: `hist_max` 0.724, `observed` 0.717, `hist_mean` 0.697,
`max_shift` 0.664, `days_worked_wed` 0.654 — **everything the model already
uses**, plus `hist_max`. Every upstream operational-stress feature is noise:
`site_h_dev` 0.553, `own_abs` 0.536, `site_abs` 0.528, `prior_breaches` 0.507,
`site_open` 0.501–0.508. TF-IDF + logistic on the person's own Mon–Wed note
text: **PR-AUC 0.051 at 0.053 prevalence, ROC-AUC 0.468** — worse than random.

Exploiting `hist_max` (`σ += 0.25·(hist_max−hist_mean)` or `μ += 0.10·…`) →
0.435, Δ +0.002, noise. **The claim stands.** Missed breaches are the same
population shifted ~3h on `hist_max` and ~5h on `observed`; their Thu–Sun was
35.2h vs a pool mean of 24.2h — a +11h event with no Wednesday footprint.

## 3. What DID work — one change, and it is a deletion

### 3.1 Three defects in the current slope handling
**(a) The pooled slope estimator is biased.** `population_priors` uses the
**median of per-person `corr·σ_rem/σ_obs`**. With 4–8 weeks `|corr|` is
upward-biased, so it over-states reversion:

| fold | `population_priors` slope | pooled within-person OLS |
|---|---|---|
| 2026-06-29 | **−0.500** ← silent fallback | −0.711 |
| 2026-07-06 | −0.825 | −0.754 |
| 2026-07-13 | −0.776 | −0.743 |
| 2026-07-20 | −0.779 | −0.750 |
| 2026-07-27 | −0.771 | −0.755 |
| 2026-08-03 | −0.792 | −0.764 |

Truth is **−0.75**, stable. First fold: with 3 history weeks
`have = feats[n_weeks >= 4]` is empty, `len(have) > 5` fails, slope silently
becomes hard-coded `−0.5` — **the code path a fresh client with 3 weeks hits**
(README requirement 4).

**(b) `MAX_SLOPE = −0.65` was compensating for (a).** With the correct −0.75
the cap is unnecessary and costs accuracy.

**(c) The per-person branch only ever weakens reversion.**
`slope = max(slope, MAX_SLOPE)` uses a personal slope only when *shallower* than
−0.65 — steep personal slopes (regular people, ≈ −0.93) are clipped away, noisy
shallow ones kept. One-sided noise injector, binding on **205 of 1,248 rows**.

| | PR-AUC | Δ vs current (90% CI) |
|---|---|---|
| A: current logic | 0.415 | — |
| B: pooled −0.65 for everyone (drop branch) | 0.425 | +0.010 [−0.004, +0.027] |
| C: pooled fold-estimated slope, no cap | 0.426 | +0.011 [−0.012, +0.028] |

Direct evidence the current slope over-predicts hot runners:

| stratum | n | breaches | actual Thu–Sun | current `mu_remaining` | proposed |
|---|---|---|---|---|---|
| pace > 8h above personal norm | 217 | 24 | 16.5h | **19.1h** | 17.2h |
| pace > 12h | 80 | 11 | 14.9h | **17.7h** | 15.3h |

### 3.2 The proposed model
```
slope  = pooled within-person OLS of remaining on observed, from history weeks
         (≈ −0.75, re-estimated each run; no per-person branch, no cap)
mu_rem = max(0, rem_mean + slope · (observed − obs_mean))
sigma  = max(3.0, rem_std · √(1 − 0.75²)) · 1.15  +  2.0 · open_per_wk
risk   = P(observed + Normal(mu_rem, sigma) ≥ 55.25)
```

### 3.3 Results

| | PR-AUC | best F1 | P at R=0.5 | flags for R=0.5 | rec@top-100 |
|---|---|---|---|---|---|
| naive `hist_mean` | 0.347 | 0.400 | 0.327 | 101 | 0.492 |
| current | 0.414 | 0.444 | 0.306 | 108 | 0.492 |
| **proposed** | **0.433** | **0.460** | **0.418** | **79** | **0.523** |

ΔPR-AUC = **+0.019, 90% CI [−0.019, +0.041], p(Δ>0) = 0.81** — noise-level by
the stated rule. Worth doing because it is positive *everywhere*:
- Per-week: wins 3, loses 2, ties 1.
- Every pace stratum: hot 0.659 vs 0.638; middle 0.450 vs 0.420; cold 0.246 vs 0.156.
- Excluding the 5 consolidated: 0.238 vs 0.223.
- Honest threshold selection (pick on weeks 1–3 → apply 4–6): F1 0.426 vs 0.400.
- **Mid-range calibration improves** — the band the manager acts on:

| bucket | current pred / actual | proposed pred / actual |
|---|---|---|
| 0.10–0.20 | 0.143 / **0.072** | 0.143 / 0.117 |
| 0.20–0.35 | 0.271 / **0.120** | 0.258 / 0.311 |
| 0.35–0.50 | 0.421 / 0.321 | 0.394 / 0.455 |
| Σrisk vs 65 actual | 73.6 (over 13%) | 58.6 (under 10%) |

- **It deletes code:** the per-person branch, `MAX_SLOPE`, the median-of-ratios
  estimator, the silent `−0.5` fallback.

### 3.4 The threshold must move to ≈ 0.20–0.25

| threshold | P | R | F1 | flagged |
|---|---|---|---|---|
| 0.20 | 0.416 | 0.492 | **0.451** | 77 |
| 0.25 | 0.510 | 0.400 | 0.448 | 51 |
| 0.35 | 0.562 | 0.277 | 0.371 | 32 |

**0.20** (recall-leaning) dominates today's 0.35 on recall for 24 more names;
**0.25** matches today's recall at better precision.

### 3.5 What it does to the target-week answer — read before adopting

| | current @0.35 | proposed @0.35 | proposed @0.25 |
|---|---|---|---|
| flagged | 14 | 7 | 12 |
| Σrisk (expected breaches) | 18.0 | 12.4 | 12.4 |

**At 0.35 the proposed model drops E1099 Portia Fourie** (0.759 → 0.286) and
E1104 — E1099 being "the one near-certain breach" in the docs. She is 40h in by
Wednesday against a personal Mon–Wed norm of ~21h; pooled −0.75 reverts her
hard where her noisy personal slope did not. **At 0.25 she is back, ranked
12th.** Adopt the model change **and** move the threshold together. 40h observed
is at the edge of historical support (backtest max 43.25h, n=7 above 38h), so
the threshold move is what keeps the answer safe.

## 4. Things the existing docs miss

### 4.1 The score is carried by 5 people

| subset | n | breaches | prev | naive `hist_mean` | current | proposed |
|---|---|---|---|---|---|---|
| all 208 people | 1,248 | 65 | 5.2% | 0.347 | 0.414 | 0.433 |
| **excluding the 5 consolidated** | 1,218 | 47 | 3.9% | 0.153 | **0.223** | **0.238** |
| the 5 consolidated only | 30 | **18** | 60% | — | — | — |

On the 203 ordinary employees the model scores **0.223 vs 0.153 naive** — still
~5.7× prevalence, still real, but a very different number. Say it before the
interviewer does.

### 4.2 The target week is outside the backtest's support
Mon–Wed only: target week is **+4.7% hours, +1.6h/person (≈ 4 SD of the
between-week distribution)** above *every* history week. Not the holiday — Mon,
Tue, Wed are all up 6–9%.

**At the week level the correlation flips.** Across the 9 complete weeks,
corr(week Mon–Wed load, week total load) = **+0.57** — a hot first half means a
hot week, not a compensated one. The model applies a **within-person** −0.75
reversion to what looks like a **population-level** shock. The backtest (6 weeks
spanning 18.3–19.2 h/person) cannot tell us how the model behaves in a week 8%
busier. **Flag as extrapolation risk; do not fit a week-level correction on 6
points.**

### 4.3 MAE and PR-AUC disagree — MAE is the wrong objective

| estimator | MAE | PR-AUC as breach ranker |
|---|---|---|
| `hist_mean − observed` (slope −1.0) | **4.366** | 0.398 |
| proposed (slope ≈ −0.75) | 4.499 | **0.433** |
| current `mu_remaining` | 4.582 | 0.414 |

Full reversion has the best MAE and the worst PR-AUC — it wins on the average
person by assuming everyone hits their weekly target, the exact assumption that
erases the tail signal. **Anyone tuning on projection error makes the
predictions worse.**

### 4.4 The slope is stable and symmetric, but heterogeneous by regularity
Pooled within-person over 1,872 person-weeks: **r = −0.737, slope = −0.754**.
Stable across weeks (−0.695 to −0.829, no trend). Symmetric (below mean −0.684,
above −0.714). But **not symmetric across people**:

| weekly-total CV quartile | slope | SD of weekly total |
|---|---|---|
| most regular | −0.931 | 2.25h |
| 2 | −0.851 | 4.02h |
| 3 | −0.723 | 5.39h |
| most irregular | −0.601 | 7.60h |

The per-person slope tries to capture this but with 4–8 weeks is too noisy:
pooled-no-cap 0.426 > shrink-0.7 0.417 > current 0.415 > raw-personal 0.400 >
CV-bucket 0.394. Good 15 seconds of video: *"the structure is real, I found it,
and with 9 weeks using it makes predictions worse — so I use the pooled number."*

### 4.5 Group features are all noise
χ² on 1,248 rows: role p = 0.134, site p = 0.334, shift_pattern p = 0.683,
employment_type p = 0.581. Supervisor 8.1% vs Driver 2.6% is not significant.

### 4.6 The shift-count signal is the ghost IDs in disguise
`hist_nsh_mean > 6` → 72.7% breach is **22 rows from 4 people — E1090, E1097,
E1126, E1193 — all consolidated records** (~10 shifts/week). Same for
`n_shifts_wed = 4` (32%, n=25). No independent signal.

### 4.7 Two code issues
- **`features.py:126`:** `float(feats["rem_std"].replace(0, np.nan).median()
  or 6.0)` — `nan` is truthy, so this returns `nan`, not `6.0`. The fallback
  never fires. Harmless today; a landmine for a thin future export.
- **`population_priors` first-fold path:** with < ~6 people at `n_weeks >= 4`
  the pooled slope silently becomes `−0.5`. A fresh client with 3 weeks of
  history runs the whole projection at the wrong reversion. The §3 fix removes
  both.

## 5. Recommendation

**Make one change, or make none. Do not add a model.**

1. Estimate the pooled slope as a **pooled within-person OLS** of remaining on
   observed over history weeks — not the median of per-person `corr·σ/σ`.
2. **Use it for everyone.** Delete the per-person branch and `MAX_SLOPE`.
3. Use the **pooled correlation** in `cond_sd`; drop `SIGMA_MULT` to 1.15.
4. **Move `DEFAULT_THRESHOLD` to 0.20** (recall-leaning, 77 flags) or **0.25**
   (same recall as today, better precision, 51 flags). Do not ship 1–3 without
   4 — at 0.35 the new scale halves the flag list and drops E1099.

**What it buys:** PR-AUC 0.414 → 0.433, best-F1 0.444 → 0.451 — both inside the
noise band. What is defensible: consistently positive across every split and
stratum; better 0.1–0.5 calibration; a fixed estimator bias; less code.
**Frame it as a simplification that also scores slightly better, not as an
improvement** — that framing is the stronger interview answer.

**What not to do:** per-weekday projection, recency weighting, GBDT/logistic,
isotonic calibration, Student-t tails, `hist_max` features, site-stress or
note-text features.

**On the ceiling:** yes, this is it. 40% of breaches have no Wednesday footprint
and survived a deliberate attempt across 45 features. The remaining headroom is
in the **data** — the 184 open shifts recorded as 0h, the 13.5h cap, no-shows
creating no row. Closing open shifts before the export would move the numbers
more than any modelling change measured here.
