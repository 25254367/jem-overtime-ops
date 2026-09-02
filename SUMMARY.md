# Project summary — Jem Applied AI assessment

Master reference. Consolidates the ideation so far. Detail lives in
`ASSUMPTIONS.md` (locked decisions + BCEA) and `data_checks.md` (evidence,
findings, open questions).

---

## The problem

It is **Wednesday 12 August 2026**; the week is not over. Data runs to end of
that Wednesday. Weeks are Monday–Sunday.

**Target week = Monday 10 Aug → Sunday 16 Aug 2026.** We have actual clock data
for Mon–Wed only; Thu–Sun is what we predict.

> Who will breach the 10-hour overtime cap by Sunday, and what should the
> contract manager do about it today?

Client: a national facilities-management company, 6 sites, 213 shift workers
(guards, cleaners, kitchen, drivers). Overtime is a compliance breach (BCEA:
45 ordinary + 10 overtime hours/week max) and a cost (1.5× OT, 2× Sunday /
public holiday).

---

## What we send (3 links)

| Link | Contents |
|---|---|
| **Dashboard** | Deployed URL. Ops-room view for the contract manager: who breaches, why, what to do. Must accept next week's export with no developer. |
| **Repo** | Public or invite `southafricanrob`. Must contain `predictions.csv`, `note_classifications.csv`, `NOTES.md`, + the code. |
| **Video** | 5 min, camera + screen. Think aloud: unexpected finding, baseline & metric choice, where we don't trust it, next steps, and explain one number end-to-end. |

### The four required files
- **`predictions.csv`** — `employee_id, will_breach, risk_score` — one row per
  `employee_id` in `employees.csv` (213 rows).
- **`note_classifications.csv`** — `shift_id, category, note` — one row per note
  in `shift_notes.csv` (2,117 rows).
- **`NOTES.md`** — ≤ ~½ page. Assumptions; how we checked the note-sorting and
  what it found; what a trained model would learn that our approach doesn't (or
  what ours learned) + how to test it on hundreds of people without fooling
  ourselves.
- The dashboard code / pipeline.

---

## Locked decisions

1. **Target week** = Mon 10 – Sun 16 Aug 2026. Public holiday **Mon 10 Aug**
   (Women's Day observed) falls inside it; those hours are already banked.
2. **Hours rule** (reproduces `weekly_summary.total_hours` exactly, all 2,122
   rows): `Σ(clock_out − clock_in)` per employee-week; blank `clock_out` → 0h;
   `clock_out ≤ clock_in` → +24h; no break deduction, no rounding.
3. **Breach** ⟺ `overtime_hours > 10.0` ⟺ **`total_hours > 55.0`** (strict).
   `> 55.0` and `≥ 55.25` are identical on this data (0.25h grid) but `> 55.0`
   is the real rule and future-proof. Code: `hours.is_breach()`.
4. **Predict against the recorded-hours definition** — Jem's ground truth is
   almost certainly built from the same data. Match it.
5. **Duplicate `id_number` people** (5 of them, §"Findings"): compute
   `will_breach` and `risk_score` per **`person_id`** (consolidated by shared
   id_number / tax / bank, union-find), then stamp onto every `employee_id`
   sharing it. No-op for the other 203.
6. **`will_breach`** on recorded hours. **`risk_score`** recorded-consistent
   **plus** the deterministic open-shift adjustment only (impute an open shift
   we can *see* in the partial week). Historical "open-shift drag" is a
   dashboard flag + `NOTES.md` caveat, **not** a `risk_score` input.
7. **`risk_score` = P(projected weekly hours > 55.0)** from a distributional
   projection (see "Prediction approach"). Still open: whether a tail / expected
   -overtime measure beats plain P(breach).
8b. **Any cutoff, not just Wednesday.** The pipeline reads how far the newest
   week runs (`hours.latest_cutoff_dow`) and re-fits the slope + threshold to
   that day. Backtest PR-AUC by cutoff: Mon 0.36 → Wed 0.43 → Fri 0.49 →
   Sat 0.65.
8. Every `employee_id` gets a row; default `will_breach = 0` only for
   no-signal employees (don't blanket-zero the 6 with no target-week shift yet).

---

## Findings, by deliverable

### → feeds `predictions.csv`

- **No fixed rosters.** Week-to-week cosine similarity of the daily-hours
  vector: median 0.60, **max 0.83**. Roster-forward projection is dead.
- **Stable weekly totals.** Per-employee CV ≈ 0.11 around a mean ~42h. Breach
  zone (≥ 55.25) is the soft right tail — 3.4% of recorded employee-weeks.
- **Mon–Wed and Thu–Sun hours are negatively correlated** (within-employee
  r = −0.73). The week is actively balanced toward a personal target. A hot
  first half predicts a cooler second half — so "hours so far" alone is a weak
  signal, and the projection must **regress Thu–Sun toward the mean**.
- **Thu–Sun projection error ≈ Normal(0, 8.0h)**, unimodal (GMM prefers k=1 —
  no "doubles" bump). Conditioning on Mon–Wed → σ ≈ 5.5h.
- **Prediction is genuinely hard.** Breaches mostly aren't visible by
  Wednesday: 13 of 55 historical breach weeks had < 20h logged by Wed. Best
  simple projection: P ≈ 0.14, R ≈ 0.33. Small GBDT: PR-AUC 0.175 (≈ 5×
  prevalence). To catch half the breaches you flag ~5× as many people.
- **Two tiers:** 110 employees with historical max < 50h (≈ hard-zero);
  **68 with mean + 2·SD ≥ 55.25** — that's where the model earns its keep.
- **Irregularity is a risk feature.** The high-hours-CV employees (E1099,
  E1212, E1201, E1190, E1009…) overlap with the repeat coverers and repeat
  breachers.
- **Target-week standouts now:** E1099 Portia Fourie (40h in 3 days, risk 0.88,
  the near-certain breach); E1122 (risk 0.61); E1042, E1087 (~0.5). 26
  `employee_id`s project ≥ 55.25h but only ~5 carry model risk ≥ 0.5.

### → feeds `note_classifications.csv`

- 2,117 notes. Rough first-pass mix: **~35% nothing useful**, **absence/cover
  ~35%** (the biggest real category once multilingual + non-keyword phrasings
  are caught), client-requested ~22%, late handover ~7%, double-post /
  short-staffed ~5%, equipment ~4%.
- **Multilingual:** isiZulu ("uNkosi akezanga namhlanje"), Afrikaans ("gedek
  vir X, siek gemeld"). English-only keywords miss a real slice.
- **"Notes that lie":** *"client signed for the extra hrs but real reason is
  relief no show again"* — filed as billable, caused by an operational failure.
  These are the key cases for the "where your sorting is wrong" check (Req 3)
  and the asked-for-vs-failure split (Req 2b).
- Notes are a **weak breach predictor** (r ≈ 0.10) but the primary signal for
  Requirement 3 (why) and Requirement 2b (which overtime is fixable).

### → feeds `NOTES.md` (and the video's "unexpected finding")

- **Headline: 5 people are registered twice and breach invisibly.** Five
  `id_number`s each map to two `employee_id`s — same person, abbreviated name
  on the second record, different site, **same tax number and bank account**.
  E1193/E1194, E1126/E1127, E1090/E1091, E1035/E1036, E1097/E1098. Combined
  hours breach the cap most weeks (Motaung E1126/27: 7 of 10 weeks, max
  71.75h); each individual id maxes ~32–39h so the client's Monday report
  **cannot see any of them**. Also 9–16 time-overlapping shift pairs each (one
  person clocked in at two sites at once). Raw-sum reading → they breach;
  de-overlapped reading → mostly don't. We use raw-sum (compliance exposure)
  and state the ambiguity.
- **Hours are systematically under-recorded around operational failure:**
  - Shifts are **hard-capped at 13.5h** (366 pinned at exactly 13.5).
  - **184 open shifts** (no clock-out) counted as **0h**; they skew to night
    shifts and carry "relief never arrived, stayed on" notes.
  - A **no-show creates no row at all** — their hours vanish, not even a zero.
  - Net: a no-show *removes* recorded hours for that site-day even though the
    same coverage was delivered. Operational-failure overtime is under-counted;
    breach risk is **biased low for habitual coverers** (E1099 ≈ −8h/week).
  - Recorded breach rate 3.4%; **estimated true 4–5%**.
- **19 impossible double-site shifts** (same employee, same start, two sites);
  **5 shared-`id_number` employee pairs**; **2 employee-weeks missing** from
  `weekly_summary`. Referential integrity otherwise clean.

### → feeds the dashboard

- **Who** — employees ranked by `risk_score`, with a softer **45h** warning
  tier below the breach tier.
- **Why** — the dominant note category for each at-risk person's recent extra
  hours (from `note_classifications.csv`).
- **What to do:**
  - **Shift-swap suggestion** — for an at-risk person, find role-matching,
    under-hours, same-`shift_pattern` employees at the same site with headroom;
    propose a specific move with the receiver's resulting projected total;
    guardrail: never push the receiver over 45h. Cost framing: 1.5×/2× → 1×.
  - **Double-booking alert** — "E1126 and E1127 are the same person; combined
    Xh this week; consolidate the records; stop cross-site rostering."
  - **Open-shift flag** — "N shifts this week have no clock-out; real hours
    likely higher; close them and recheck."
  - **Two numbers** per person — recorded projection + open-shift-adjusted.
- **Reload** — the whole thing rebuilds from a fresh 7-CSV drop, no code
  changes.

### → feeds the video

- Unexpected: the 5 ghost IDs; the −0.73 Mon–Wed/Thu–Sun correlation; the
  under-recording mechanics.
- Baseline & metric: naive baselines are all-zero (R 0), historical-mean
  (R 0), linear ×7/3 (P 0.08). We optimise recall-leaning (F-β, β > 1, or
  recall at a precision floor) because a missed breach is the expensive error —
  **state why not plain accuracy or F1**.
- Where we don't trust it: post-Wednesday events; under-recorded coverer hours;
  the de-overlap ambiguity on the ghost IDs.
- Explain one number: walk through E1099's `risk_score` — 40h now, usually +X
  more Thu–Sun, adjusted down for being ahead of pace, ±σ, P(≥ 55.25).

---

## Prediction approach (implemented in `pipeline/`)

1. **Consolidate** by `person_id` (union-find on shared id_number / tax / bank).
2. Read the **cutoff** from the export (latest weekday with a shift in the
   target week). Compute `observed` = that person's hours through the cutoff.
3. **Fit the pooled slope for this cutoff** — one within-person OLS of
   remaining-hours on observed-hours across all history person-weeks
   (`features.pooled_slope`). ≈ −0.75 at a Wednesday cutoff, −0.82 Monday,
   −0.47 Saturday. Same slope for everyone — per-person slopes are too noisy
   on 4–8 weeks (`ANALYSIS_opus.md` §3).
4. Project remaining as `Normal(μ, σ)`:
   `μ = rem_mean + slope·(observed − obs_mean)`;
   `σ = rem_std·√(1−corr²)·1.15 + 2.0·(historical open-shift rate)`.
5. `risk_score = P(observed + remaining > 55.0)`.
6. `will_breach = risk_score ≥ THRESHOLD_BY_CUTOFF[cutoff]` — tuned per cutoff
   on the expanding-window backtest for a recall-leaning point (~0.46–0.49
   recall). Wednesday = 0.24.
7. Stamp the `person_id` result onto every `employee_id`.

**Backtest** (expanding window, Wednesday cutoff, 1,248 person-weeks, 65
breaches): PR-AUC **0.432** overall / **0.238** on the 203 ordinary employees
(vs 0.153 naive — the 5 consolidated people are 28% of breaches and easy).
Well calibrated. Beats every naive baseline on recall at usable precision.

**Ceiling:** ~40% of breaches score ≤ 0.10 — indistinguishable from
non-breachers on Wednesday, confirmed by a 45-feature attack
(`ANALYSIS_opus.md` §2.6). The missing input is the roster.

**Still open:** pure P(breach) vs expected-overtime-above-cap for `risk_score`;
whether to adopt any of the remaining `ANALYSIS_opus.md` items.

---

## Next steps (agreed order)

1. **Classification task** — build the note taxonomy + the asked-for-vs-failure
   split + design and run the check on our own labelling. Produce
   `note_classifications.csv`.
2. **Dashboard deep-dive** — decide the panels, the build stack, the host, and
   how the reload works.
3. Then: finalise `predictions.csv`, write `NOTES.md`, record the video.

---

## Cross-references
- `ASSUMPTIONS.md` — §1 target week, §2 BCEA + earnings threshold, §3 the
  hours/breach definition.
- `data_checks.md` — §1 reconciliation, §2 threshold, §3 data-quality
  (open shifts, double-site, ghost IDs), §4 target-week state, §5 modelling
  (schedule structure, simulate-Wednesday, distributions, open model questions),
  §6 notes taxonomy, §7 dataset at a glance, §8 Requirement-2 design.
