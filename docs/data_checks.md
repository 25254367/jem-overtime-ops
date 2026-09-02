# Data checks — findings & open questions

Checks run 2026-09-01 against `data/` (scripts in scratchpad, not committed yet).
This file is **things to talk through**, not settled decisions. Settled
decisions live in `ASSUMPTIONS.md`.

---

## 0. Open questions (the agenda)

**Q1 — Is the prediction target "overtime", yes/no?**
Working answer: the target is **binary breach** — `will_breach = 1` if projected
overtime for the target week exceeds 10.0h (i.e. projected `total_hours ≥
55.25`; see §2). "Overtime hours" itself is a useful *intermediate* we regress
or project, but the graded quantity in `predictions.csv` is the 0/1 flag plus a
`risk_score`. Open sub-question: do we also want to flag the 45h ordinary-time
line as a softer warning tier in the dashboard? (Leaning yes — it is the
earlier, more actionable signal.)

**Q2 — `risk_score`: how do we quantify risk?**
Candidates, roughly in order of preference:
1. **Calibrated probability** from a model: P(projected hours ≥ 55.25). Needs
   the projection to carry an uncertainty distribution, not a point estimate.
2. **Distance-to-threshold, squashed**: `sigmoid((projected_hours − 55.25) / s)`
   where `s` is a spread constant (e.g. the std of week-to-date → full-week
   projection error, measured on history). Simple, monotonic, no training.
3. **Historical hit rate** in a similar week-to-date state (empirical: of past
   employee-weeks that looked like this by Wednesday, what fraction breached).
Whatever we pick, it must be **calibrated around the 55.25 boundary** and
monotonic in projected hours. Decision pending — see §5.

**Q3 — Break deduction?** See §1. Current call: mirror the client (no
deduction) to match ground truth; note the "true" figure separately.

**Q4 — Duplicate `id_number` people (§3): predict per `employee_id` or per
person?** Genuine judgement call, see `ASSUMPTIONS.md` and §3 below.

**Q5 — "What to do about it" design (Requirement 2).** See §8.

---

## 1. Hours reconciliation — how the client's numbers are built

`weekly_summary.total_hours` reproduces **exactly** (2,122 / 2,122 rows, mean
diff 0.00, max diff 0.00) as:

```
total_hours = Σ (clock_out − clock_in) over the employee's shifts that week
              · blank clock_out            → shift contributes 0 hours
              · clock_out ≤ clock_in       → add 24h (crossed midnight)
              · no break deduction, no rounding
overtime_hours = max(0, total_hours − 45)
breached       = 1 if overtime_hours > 10
```

**We can reproduce the client's hours to the exact 0.25h.** The pipeline
computes hours itself and needs `weekly_summary` only for validation labels.

**Discussion points:**
- No break deduction at all. BCEA s14 expects a meal break after 5 hours; the
  client's figure is gross. Mirror the client (needed to match ground truth),
  note the "true" worked hours separately.
- Blank `clock_out` = 0 hours is the client's rule. Almost certainly wrong in
  reality (see §3) — surface it, do not silently copy.

## 2. Breach threshold

- Min overtime among `breached = 1`: **10.25h**. Max overtime among
  `breached = 0`: exactly **10.0h**.
- So breach ⟺ overtime **strictly > 10.0** ⟺ `total_hours ≥ 55.25`
  (all hours land on 0.25h increments).
- **Discussion:** predict `will_breach = 1` at ≥ 55.25 projected hours;
  calibrate `risk_score` around that boundary (Q2).

## 3. Data-quality issues

### 3a. 184 shifts (2.1%) have a blank `clock_out_time` — and they are not random

Spread across all 10 weeks, all 6 sites, 107 employees. Client counts them as
**0 hours**. But matching them to the notes (join on `shift_id`) shows they are
concentrated on the **longest, most disrupted shifts**:

| Signal | Open shifts | All shifts |
|---|---|---|
| Carries a supervisor note | **39.7%** | 23.9% |
| Night-pattern employee | **27%** | 12% |
| Evening clock-in (18:00–20:00) | **27%** | ~13% |

Of the 73 open shifts that have a note, **39 (53%) are absence/cover**, 15 (21%)
client-requested. Recurring phrasings on open shifts:
- *"no relief. stayed. someone must please sort the roster"* (verbatim ×3–4)
- *"relief never arrived, stayed on till 06:00"* / *"relief no show AGAIN"*
- *"double shift bc relief never pitched"*
- *"control room says relief coming, nobody came"*
- *"aflos het nie opgedaag nie, moes aanbly"*

**Directional bias — this is the point:**
- **0 of 171 employee-weeks that contain an open shift are recorded as a
  breach** (3.4% base rate → ~6 expected).
- Conservative counterfactual — impute one normal 9.75h shift per open record:
  **+9 breaches, ~+14%** over the 66 recorded. Impute the doubles the notes
  describe and it is more.
- So "missing clock-out = 0h" **systematically strips hours off exactly the
  shifts that ran long**, understating overtime for the people who cover
  no-shows — the people most likely to breach.

**Named specifics:**
- **E1099 Portia Fourie has 6 open shifts — the most of anyone** — and is also
  the top target-week breach suspect (40h in 3 days). Her open-shift notes:
  *"double shift bc relief never pitched"*, *"Next shift guard did not pitch.
  Had to cover"*, *"molefe absent, took her rounds as well"*. Her true hours are
  almost certainly higher than the client's system shows.
- Other repeat open-shift employees: E1190 (5), E1087 (5), E1201 (5), E1094 (4),
  E1086 (4), E1145 (4).
- The **"notes that lie"** pattern recurs: *"client signed for the extra hours
  but real reason is relief no show agn"* appears **verbatim on two open
  shifts** (E1099, E1086) — booked as billable, actually an operational failure.

**Proposal:** dashboard flags "N open shifts this week — real hours likely
higher" against affected employees, with an upper-bound estimate (impute the
employee's median shift length, or a double where the note says so). In
`predictions.csv`, anyone with a target-week open shift + a "stayed on" note is
a candidate for an understated-risk flag.

### 3b. 19 shift pairs: same employee + date + clock-in, two different sites
- e.g. E1006 on 16 Jun: ST-04 06:00–18:00 (12h) **and** ST-02 06:00–10:00 (4h).
- Physically impossible to be at both. Both are counted in `weekly_summary`.
- **Proposal:** leave as-is (matching ground truth requires it), log as a
  data-integrity smell. Could be split-post billing or double capture.

### 3c. 5 people are registered twice and breaching invisibly — headline finding

Five pairs of employee records share an `id_number`: same person, two
`employee_id`s, abbreviated name on the second ("Lucky Sibiya" / "L. Sibiya"),
**each registered to a different site**. Consecutive ids:
E1193/E1194, E1126/E1127, E1090/E1091, E1035/E1036, E1097/E1098.

They also share **bank account number, tax number, hourly rate, role, and shift
pattern** — this is unambiguously one human each. The second record is always
`Fixed-term`; the first is usually `Permanent`. Exactly 5 records in the whole
dataset have abbreviated first names — precisely these 5 "second" records.
Deliberately planted.

Combine each pair's weekly hours:

| Person | combined mean/wk | combined max/wk | weeks > 55h |
|---|---|---|---|
| Lucky Sibiya (E1193/94) | 52.8 | 66.5 | 5 of 10 |
| Lerato Motaung (E1126/27) | 56.5 | **71.75** | 7 of 10 |
| Pieter Van Wyk (E1090/91) | 54.6 | 66.75 | 5 of 10 |
| Tshepo Motaung (E1035/36) | 51.9 | 62.75 | 4 of 10 |
| Busisiwe Jacobs (E1097/98) | 56.3 | 67.0 | 6 of 10 |

Each individual id maxes ~32–39h/week, so **none ever shows as breached in
`weekly_summary`** — the client's Monday report cannot see these 5 people at
all, yet each is over 45h nearly every week and repeatedly past the 10h cap.

Each pair also has **9–16 time-overlapping shift pairs** — one human clocked in
at two sites simultaneously. That anomaly stands on its own.

**Legal reading:** BCEA s1 defines overtime as time an *employee* works in
excess of ordinary hours — per person, per employer, per week. Splitting across
`employee_id`s or sites is an accounting choice, not a compliance shield. Same
tax number = SARS already treats it as one employment. So substantively these 5
are the clearest breaches in the data.

**Notes cross-check — suggestive, NOT conclusive:** the surnames Sibiya / Wyk /
Motaung / Jacobs appear often in "covering for X" / "X no-showed" notes, and on
several dates a "X absent at site A" note coincides with a logged shift for the
double-ID person at sites B/C. BUT the notes only give a surname, and those are
among the most common surnames in the register (9–12 people each), so the notes
may refer to a different person. No first name / id in the notes and no roster
data → cannot conclude phantom-hours / fraud. Flag as "investigate with more
data", not a finding.

**Discussion points:**
- `predictions.csv` is keyed by `employee_id` and scored per-id. Options:
  (A) per-id projection → `will_breach = 0` for all 10 ids, flag loudly in
  NOTES/dashboard; (B) merge on `id_number`, set `will_breach = 1` on both ids
  when the person breaches (risk: up to 10 false positives if GT is naive
  per-id); (C) `will_breach` per A but `risk_score` ≈ 1.0 for the 10 ids.
  Current lean: **C**, plus a first-class "same ID number, multiple records"
  dashboard panel.
- This is the lead item for `NOTES.md` and the video ("a problem they cannot
  see coming").

### 3d. 2 employee-weeks in `shifts.csv` but absent from `weekly_summary.csv`
- E1094, E1182 — both in the target week, both a single open shift (0 hours).
- Client omits zero-hour employee-weeks. Pipeline must still emit a prediction
  row for **every** `employee_id` in `employees.csv` (213 rows).

---

## 4. Target-week state (as of end of Wed 12 Aug)

- 207 of 213 employees have logged ≥ 1 shift. **6 have none yet**: E1009, E1101,
  E1145, E1157, E1170, E1196 — all have full 9-week history, could still be
  rostered Thu–Sun. E1009 and E1157 each breached once before (hist max 55.5h).
- **Nobody is over 45h yet.** Highest is E1099 Portia Fourie at **40.0h in 3
  days** (breached twice historically, hist max 58.75h) → current prime suspect.
- 143 of 213 worked the Mon 10 Aug public holiday — those hours are already
  banked.
- Only ~3 open shifts in the target week so far; more may land Thu–Sun.
- **Discussion:** default `will_breach = 0` for no-signal employees, but do not
  blanket-zero the 6 no-shift employees without checking their roster pattern.

---

## 5. Modelling notes

### 5.1 The basics
- **Breach base rate 3.1%** (66 / 2,122 employee-weeks; 55 / 1,491 in the
  simulate-Wednesday panel). Severe imbalance → accuracy is meaningless
  (predict-all-zero scores 96.9%). Score on precision / recall / F-β / PR-AUC;
  a missed breach is the expensive error.
- **Naive baselines to beat** (measured on the simulate-Wednesday panel):
  - all-zero → recall 0.
  - "employee historical mean weekly hours ≥ 55.25" → **recall 0** (nobody
    averages that high).
  - linear `hours_so_far / days_elapsed × 7` → recall 0.60 but **precision
    0.08** (386 false positives); the Mon holiday front-loads the first 3 days.
- **History helps, not enough alone:** of 66 breaches, 49 were the employee's
  first in the data, 17 were repeats. 49 employees breached once, 10 twice,
  6 three times, 1 four times.
- **Weak group signals:** night 4.4% vs day 2.9%; Kitchen Assistant 4.0% vs
  Cleaner 1.9%; site range 2.7–3.8%; weekly range 1.9–5.2%. Nothing dominant.
- **Notes: weak predictor, strong explainer.** corr(overtime hours, notes that
  week) = 0.10. Use notes for Requirement 3 (why), not as a core Requirement 1
  feature.
- **Sunday = 13% of all hours, public holidays = 3.3%.** ~16% of hours carry
  premium pay and all count toward the 45+10 cap → heavy Sunday workers sit
  structurally closer to a breach.

### 5.2 Schedule structure — there are no fixed rosters

| Question | Finding |
|---|---|
| Fixed weekly roster (week N ≈ week N-1)? | **No.** Daily-hours-vector week-to-week cosine similarity: median 0.60, **max 0.83, none > 0.9**. Only 17 / 213 employees are even "semi-regular" (0.75–0.9). |
| Stable *total* weekly hours? | **Yes.** Per-employee CV ≈ 0.11 (±11%), around a mean of ~42h — well below the 55.25 line. |
| Fixed start times / shift lengths? | **No.** Start-hour std ≈ 1.1h, duration std ≈ 1.7h for everyone. No fixed "posts". |
| Recognisable core days? | Median employee: **2 core days** (worked ≥ 70% of weeks) **+ 5 flex days**. 22 employees fully rotating; only ~30% have a 3+ day core. |

Consequences:
- **Roster-forward projection is dead** — there is no roster to roll forward.
- What *is* stable and usable: total weekly hours, and per-person
  P(work | weekday) × E(hours | worked, weekday).
- **Irregularity is itself a risk feature.** The high-hours-CV employees
  (E1099, E1212, E1201, E1190, E1009, E1013) are the same people who show up as
  repeat open-shifts and repeat breaches.

### 5.3 "Scheduled" vs "cover" shifts cannot be separated by pattern

Heuristic (off-pattern weekday / 2nd shift that day / duration outlier) flagged
5.1% of shifts as "extra". Of the 843 shifts that carry a cover-type note, it
caught only **8.5%**. The schedule is too loose for a cover shift to look
different. **Notes are the only reliable "this was cover" signal, and they
cover ~24% of shifts.** `corr(extra_hrs, overtime_hours) ≈ 0.05` — breach weeks
are just *broadly heavier* (mean 57.5h total vs 41.5h), not one dramatic cover
event.

### 5.4 Simulate-Wednesday results — prediction is genuinely hard here

Rebuilt features per week from prior weeks only, projected each employee's
target-week total, scored against the known outcome:

- **Breaches are mostly not visible by Wednesday.** In real breach weeks mean
  hours-by-Wed = 25h vs 18h non-breach (weak). **13 of 55 breach weeks had
  < 20h logged by Wednesday** — the breach-causing hours land Thu–Sun.
- **Simple projection** (hours-so-far + weekday expectation for Thu–Sun):
  P ≈ 0.14, R ≈ 0.33, **MAE 6.8h** — projection error ≈ the decision margin.
- **Gradient-boosted classifier**, features {proj, hist_mean, hist_max,
  hist_std, exp_rem, pace_vs_norm, open_rate, …}, GroupKFold by week:
  **PR-AUC 0.175** (≈ 5× the 0.037 prevalence). Operating points:
  recall 0.3 → precision 0.20; recall 0.5 → precision 0.18; recall 0.7 →
  precision 0.10.
- Translation: **to catch half the breaches you flag ~5× as many people as
  actually breach.** That is the honest ceiling of the simple approaches.
- Top features: `proj`, `hist_mean`, `hist_max`, `exp_rem`, `pace_vs_norm`.

### 5.5 Target-week projection (as of Wed 12 Aug, current model)

- **E1099 Portia Fourie** — 40h in 3 days, projects ~72h, model risk **0.88**.
  The one near-certain breach (2 prior breaches, night guard, 6 open shifts
  all-time → true hours likely even higher).
- **E1122** (Kitchen Asst) — 28h so far but hist mean 52h, 3 prior breaches,
  hist max 65.75 → risk 0.61.
- **E1042, E1087** (guards) — ~36h in 3 days, project ~65h, risk ~0.5.
- 26 `employee_id`s project ≥ 55.25h; only ~5 carry model risk ≥ 0.5.
- **All 5 consolidated `id_number` people project ≥ 55h combined** (Motaung
  E1126/27 ≈ 77h) but a per-`employee_id` model scores them ~0.01 — they are
  invisible unless the pipeline consolidates. See §3c.

### 5.6 OPEN — model choice needs much more ideation

Nothing below is decided. Questions to work through:

- **Is a classifier even the right frame,** or is this a *projection +
  threshold* problem where the honest output is a calibrated `risk_score`
  ranking and `will_breach` is just a chosen cut? Leaning toward the latter
  because it is explainable to a site manager (Requirement: explain one number
  simply).
- **What to actually predict:** full-week hours (regression) then threshold, vs
  P(breach) directly (classification), vs remaining-hours only (add to the
  known Mon–Wed actual). The third isolates the thing that is genuinely
  uncertain.
- **Model family:** transparent (logistic / small GBDT / hand-built projection
  with a distance-to-threshold sigmoid) vs a heavier learner. Given PR-AUC is
  only 0.175 and the brief prizes explainability, a heavy model probably is not
  worth the opacity — but confirm by trying.
- **Uncertainty:** the projection needs a *distribution*, not a point, to make
  `risk_score` meaningful. Options: quantile regression, conformal prediction,
  empirical residual bootstrap by employee, or a simple
  `sigmoid((proj − 55.25) / s)` with `s` = historical projection-error std.
- **Feature ideas not yet tried:** trend over the 10 weeks (is this person
  ramping?), count of recent cover-notes naming this person's site (absence
  upstream → they will cover), days since last breach, headroom to 45h at
  current pace, whether they have an open shift *this* week.
- **Class imbalance handling:** class weights vs focal loss vs threshold
  tuning vs nothing (just rank by score).
- **Metric to optimise, and why that one:** F-β with β > 1? Recall at a fixed
  precision floor? Cost-weighted (rand cost of a missed breach vs a false
  alarm)? The video explicitly asks "which metric and why not another".
- **Validation:** expanding-window by week (train on weeks 1..k, test k+1) is
  the realistic protocol; simple k-fold leaks future weeks. Report the naive
  baseline on the *same* splits.
- **The floor we cannot beat:** breaches driven by post-Wednesday events and by
  hours that never entered the data (open shifts, §3a). Quantify this as the
  irreducible error and say so in `NOTES.md`.

---

## 6. Notes taxonomy — first scan (keyword rough-cut, ~2,117 notes)

Rough proportions from a keyword pass (**not** the final classifier):

| Bucket | ~share | Examples |
|---|---|---|
| nothing useful | ~35% | "nothing to report", "as per normal", "all quiet", "akukho lutho", "niks om te rapporteer nie", "-", "." |
| client requested | ~22% | "client signed for the extra hrs", "centre manager requested additional cover for stocktake", "klient het ekstra ure gevra" |
| relief no-show / absence | ~22%+ | "aflos het nie opgedaag nie", "Fourie absent, took her rounds", "covering for Ngcobo - booked off sick", "COVERED FOR NDLOVU AGAIN - 3RD TIME THIS MONTH" |
| late handover | ~7% | "oorhandiging was laat, gewag vir sleutels", "relieved late" |
| double post / short-staffed | ~5% | "2 posts 1 guard", "took Sithole shift as well" |
| equipment failure | ~4% | "macine down again", "generator fault", "scrubber broke down, had to do the floor manually" |

An absence/cover regex over the full note set matches **745 of 2,117 (35%)** —
so once the multilingual and non-keyword phrasings are captured, **absence-driven
overtime is the single biggest category**, not client-requested.

Observations that matter:
- **Multilingual confirmed:** isiZulu ("uNkosi akezanga namhlanje"), Afrikaans
  ("geddek vir wyk, siek gemeld"). A pure English keyword approach misses a real
  slice.
- The **asked-for vs operational-failure split (Requirement 2b)** is legible in
  the text — but watch for **notes that lie**: "client signed for the extra hrs
  but real reason is relief no show again" is filed as client-requested on
  paper, caused by a no-show in reality. Prime cases for the "where your sorting
  is wrong" check (Requirement 3).
- A large uncategorised bucket (~700) is mostly absence-cover phrased without my
  keywords ("stood in for Mabaso", "Zulu off sick. agn. covered.") → the real
  no-show/absence share is well above 22%.

---

## 7. Dataset at a glance

- 213 employees, 6 sites (ST-01…ST-06), 10 weeks of shifts
  (2026-06-08 → 2026-08-12, last week partial), 8,863 shift rows,
  2,117 shift notes, 2,122 weekly-summary rows.
- `contract_ordinary_hours`: 45 for all.
- `shift_pattern`: 183 day, 30 night. `employment_type`: 161 Permanent,
  52 Fixed-term. `pay_frequency`: Monthly for all.
- `hourly_rate`: R28.41 – R59.52.
- Shift duration range 3.5–13.5h (mean 9.8h), all on 0.25h increments.
- Public holidays in period: 16 Jun 2026 (Youth Day, Tue), 10 Aug 2026
  (National Women's Day observed, Mon — in the target week).
- 9 complete Mon–Sun weeks + the 3-day partial target week. All
  `weekly_summary.week_starting` values are Mondays.
- Referential integrity clean: every `employee_id` / `site_id` / `shift_id`
  reference resolves; all 213 employees are in payroll and have ≥ 1 shift.

---

## 8. Requirement 2 — "what to do about it" (design sketch)

**Idea (from MS's notes):** when an employee is predicted to breach the 10h
overtime cap — or even just cross the 45h ordinary line — surface a concrete
**shift-swap / cover suggestion** rather than a generic "watch this person".

Mechanism:
1. Identify the at-risk employee, the **site(s)** where the projected overtime
   is landing, and the specific remaining shifts driving it.
2. Scan the same site (then nearby sites) for employees who:
   - match the **role** (Security Guard ↔ Security Guard, etc.),
   - are **under** their weekly hours with enough headroom to absorb the shift
     without themselves breaching,
   - are not already rostered against that slot,
   - ideally share `shift_pattern` (day/night).
3. Rank candidates by spare capacity and propose: "Move Thu 18:00–06:00 at ST-04
   from `E1099` to `E1132` (currently 28.5h, would go to 40.25h)."

Open questions:
- Do we have enough roster signal to know the *remaining* shifts, or only
  historical actuals? If the latter, the suggestion is "based on this person's
  usual Thu/Fri/Sat/Sun pattern".
- Cost framing: a swap that just moves the hours to someone still under 45h
  converts 1.5×/2× overtime back to ordinary pay — quantify the saving.
- Guardrail: never suggest a swap that pushes the receiver over 45h (or over
  their own comfort threshold). Show the receiver's resulting projected total.
- Tie-in with §3c/§6: a chunk of the overtime is caused by chronic no-shows.
  The deeper "what to do" is naming the repeat no-show posts, not just
  reshuffling cover.
