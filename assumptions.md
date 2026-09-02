# Assumptions

Working notes. A stated assumption is never wrong; a silent one usually is.

---

## 1. The question and the target week

- Scenario: "it is Wednesday, the week is not over." Data in `shifts.csv` runs
  to the end of **Wednesday 12 August 2026**.
- Weeks run **Monday → Sunday** (every `week_starting` in `weekly_summary.csv`
  is a Monday).
- **Target week = Monday 10 Aug → Sunday 16 Aug 2026.** We have actual clock
  data for Mon 10, Tue 11, Wed 12 only. Thu 13 – Sun 16 are what we predict.
- `predictions.csv` answers: for each employee, will cumulative **overtime**
  exceed **10 hours** by Sunday 16 Aug?

---

## 2. Legal framework (BCEA)

Basic Conditions of Employment Act 75 of 1997.

| Rule | Section | Substance |
|---|---|---|
| Ordinary hours | s9 | Max **45 ordinary hours/week**. Max 9 hrs/day (≤5 days worked) or 8 hrs/day (>5 days). |
| Overtime | s10 | Overtime = time worked **in excess of ordinary hours**. Max **10 overtime hours/week**. Paid at **1.5×**. |
| Sunday work | s16 | **2×** ordinary rate if the employee does not ordinarily work Sundays; **1.5×** if they do. |
| Public holidays | s18 | If it is a normal working day and the employee works: **the greater of (a) 2× ordinary wage, or (b) ordinary wage + payment for hours worked**. If a normal working day and they do **not** work: still paid ordinary daily wage. If not a normal working day and they work: ordinary daily wage **+** wage for time worked. Shift spanning a public holiday counts wholly as public-holiday work if the greater portion falls on the holiday. Payment on the usual payday. |

Source for s18: labourguide.co.za, "Understanding Work on Public Holidays – A
Guide to Section 18 of the BCEA" (Cloudflare-gated; retrieved via reader proxy
2026-09-01).

### Earnings threshold
Sections 9, 10, 16(2) and 18(3) do not apply to employees earning above the
Minister's earnings threshold (~R261k/year, 2025). In this data the highest
hourly rate is **R59.52** → ~R139k/year at 45 hrs/week. **Every employee here is
covered.** No threshold exclusions.

### The pay multipliers (from the brief)
Overtime 1.5×; Sunday and public-holiday work 2×. These matter for **cost**
(Requirement 2), not for the breach test itself.

---

## 3. How "overtime" is defined for the breach test

**Assumption A — we predict against the client's definition, not a strict BCEA
reading.** Ground truth is checked against the client's system, so we replicate
what `weekly_summary.csv` does.

Reverse-engineered from all 2,122 historical `weekly_summary` rows (exact match,
evidence in `DATA_CHECKS.md` §1):

```
total_hours    = Σ (clock_out − clock_in) over the employee's shifts that week
                 · shifts with a blank clock_out contribute 0
                 · if clock_out ≤ clock_in, add 24h (shift crossed midnight)
                 · no break deduction, no rounding
overtime_hours = max(0, total_hours − 45)
breached       = 1 if overtime_hours > 10
```

The prediction pipeline computes hours itself with this rule and uses
`weekly_summary` only for validation labels.

Consequences of this definition, all confirmed in the data:
- **Sunday and public-holiday hours are not treated separately for the cap.**
  They are just hours in the weekly total. A person who hits 45 hrs Mon–Sat and
  then works Sunday is accumulating overtime toward the 10-hour cap.
- **No daily overtime sub-limit is applied.** Only the weekly total matters.
- Ordinary-hours threshold is a flat **45** for everyone (`contract_ordinary_hours`
  is 45 for all 213 employees).

**Assumption B — "exceed 10 hours" means strictly greater than 10.00**, i.e.
**breach ⟺ `total_hours > 55.0`** (strict). In this dataset every hour lands on
a 0.25h grid, so `> 55.0` and `≥ 55.25` pick out exactly the same rows — but
`> 55.0` is the actual rule and stays correct if a future export has, e.g.,
55.1h. The client's history confirms the strict `>`: min overtime among
`breached=1` is 10.25, max among `breached=0` is exactly 10.0 (`DATA_CHECKS.md`
§2). Code: `hours.is_breach()` / `BREACH_TOTAL_HOURS = 55.0`.

**Assumption C — a breach is about the projected full-week total**, not what is
already logged. The prediction works at **any cutoff** — data through Wednesday,
Friday, whatever — and re-fits to that day; earlier in the week means a flatter
regression slope, a lower `will_breach` threshold, and more weight on history.
The cutoff is read from the export (`hours.latest_cutoff_dow`), not assumed.

---

## 4. See `DATA_CHECKS.md`

Data-quality findings, reconciliation evidence, modelling observations, the
notes-taxonomy first scan, and open questions to discuss are in
`DATA_CHECKS.md` — kept separate because they are discussion items, not settled
assumptions.
