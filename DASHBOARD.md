# Dashboard — design note

First-pass thinking. Deeper pass (panels, layout, build) comes later; this
locks the shape and the architecture.

---

## 1. Who it's for (from the brief)

The **contract manager** who owns the 6 sites. Not an analyst. In a car
between sites or standing in a control room, **on a phone**, ~10 minutes
before the next call.

Implications:
- One screen, no scrolling for the headline. Single-column, large text.
- **Names and sites, not `employee_id`s.**
- Every risk number paired with a plain "why" and a "what to do".
- Actions executable from a phone without opening a spreadsheet.
- Money in Rand — managers think in cost.
- "Rough is fine. Ugly is fine." Do **not** spend hours on polish — the brief
  says it's the first thing to cut and "everyone can make something pretty
  with an agent now."

---

## 2. What it must do (the 4 requirements)

| # | Requirement | Panel |
|---|---|---|
| 1 | Show who goes over by Sunday | **Risk list** (ranked) |
| 2 | Say what to do about it | **Action** on each at-risk person + the special alerts |
| 3 | Say why the hours happened | **Why tag** per person + the split analysis |
| 4 | Accept next week's data without a developer | **In-UI file upload** → pipeline re-runs |

---

## 3. Panels

Two entry points onto the same at-risk people, for the two questions the
manager actually asks:
- **"Where do I focus this week?"** → **C. Site triage**
- **"Who do I need to call about?"** → **A. Risk list**

Landing view = the headline count + site triage; the person list is one tap in.

### As-of banner (top of every view)

*"Data through **Wednesday 12 Aug**. Predictions get sharper each day — today's
accuracy is ~mid; by Friday it's high."*

The tool works at **any cutoff** — the pipeline reads how far the week runs
from the export and re-fits accordingly. The banner must always say which day
the data covers and roughly how much to trust the numbers, because a Monday
prediction and a Saturday one are very different (backtest PR-AUC 0.36 → 0.65
Mon → Sat). If the manager reloads a mid-week export, the whole board updates
to that day.

### A. Headline (the 10-second glance)
- Count line: *"3 predicted breaches · 9 to watch · 6 sites · ~R14 200 projected OT cost this week"*.
- Ranked risk list: **name · site · role · hrs so far · projected · risk · why · action**.
- Three tiers: **Breach likely** (`risk ≥ threshold`) · **Watch** (projected ≥ 45h, `risk` below threshold) · everyone else hidden by default.

### B. Person detail (tap a row)
- **Projection in words:** *"40h logged Mon–Wed. Usually +24h Thu–Sun, but 8h ahead of pace → expect ~19h more → ~59h → 14h overtime. 88% likely to breach."*
- **Confidence line:** *"At 12h by Wednesday, ~1.4% of people in this position have breached historically"* (from the observed-hours-vs-breach table, `data_checks.md` Q3) — an honest anchor the manager can sanity-check against.
- **Shift count:** *"6th shift this week — normally works 4. Breaches come from extra shifts, not longer ones."*
- **Recorded vs adjusted** — if they have open shifts: *"53h recorded / ~60h adjusted for 2 unclosed shifts."*
- **Why** — dominant `overtime_driver` for their recent extra hours + the actual note text ("covering Sibiya post, no show no call").
- **Action** — the specific recommendation (see §4).
- **History** — last 9 weeks of weekly hours, breach weeks marked.

### C. Site triage (co-primary with A — the "where do I focus?" entry point)

The manager has 6 sites and one afternoon. This panel answers **"if you deal
with one site today, which one, and why"** — it sits above the person list as
the triage layer.

**Sites ranked by an intervention score**, highest first. The score is built
from things the manager can actually act on this week:

| Signal | Why it counts |
|---|---|
| # predicted breaches | the compliance exposure |
| # in the watch tier (≥ 45h) | breaches forming |
| projected **fixable** OT cost (R) — operational-failure share only | client-requested OT is billable, not a problem; don't rank on it |
| concentration on a **nameable** cause (one vacant post, one repeat no-show) | a concentrated cause has an obvious fix; scattered OT doesn't |
| swap capacity — are there under-45h, role-matching people on this site? | can the manager actually rebalance here, or is the site just thin? |
| week-over-week trend | is this site deteriorating |

Each site row expands to a one-paragraph brief:

> **ST-03 — act here first.** 4 people projected to breach, 3 of them covering
> the same vacant guard post (Ndlovu: no-showed 3× this month). ~R4 200 of
> avoidable OT this week. Two guards on site are under 40h and could absorb the
> post. **Do:** permanently fill the ST-03 night post; interim, move the
> Thu/Fri/Sat cover to Molefe and Khumalo.

> **ST-01 — no action.** 1 person over 45h, from client-authorised extra
> patrols after the break-in. Billable. Leave it.

The distinction the panel is built around: **fixable, concentrated OT** ranks a
site up; **billable or diffuse OT** does not.

### D. Special alerts (lead with these — certain, current, fixable)
- **Double-booked identities** — the 5 people: *"E1126 & E1127 are one person
  (same ID number, bank, tax). Combined 65h this week. Consolidate the records;
  stop cross-site rostering."*
  - **Phantom absences** (measured — `attribute.phantom_absences`): each of the 5
    is on two rosters as a separate employee and neither site knows. On the days
    they're at one site, the other logs an unplanned no-show and pays someone to
    cover — **39 cover shifts in 10 weeks, 14 provably while the person was
    clocked in at their other site**. Notes say "again", "3rd time this month".
    The double-booking also put **~510h** on the books at two sites at once —
    untrustworthy for payroll. Lead with the phantom-absence story (operational,
    note-backed, actionable); the 510h is the supporting number, hedged ("some
    paid twice, none trustworthy"). **Fix:** single-site each person; drop from
    the other site; redistribute that post across under-used same-role staff
    already there (headroom exists at every ghost site — checked).
- **Open shifts this week** — *"N shifts have no clock-out; hours understated;
  close them and recheck [names]."*

### E. Why analysis (Requirement 3)
- The **asked-for vs operational-failure split** — two numbers (strict 21% /
  loose 48%, per `CLASSIFICATION.md` §4.3).
- Concentration: sites, drivers, trend across weeks.

### F. Operations review (a tab — backward-looking, check weekly not daily)

Not the forecast — a **list of concrete things to follow up on** now, from the
recorded week (and a rolling 4-week view):

- **Open shifts** — every shift this week/month with a clock-in and no
  clock-out: who, site, date, the supervisor note, and the imputed "true"
  hours. Framed as *"chase a clock-out or verify the hours before payroll
  runs"* — it's a payroll-integrity + compliance item (an open shift on a
  cover shift means the person's real hours are higher than recorded, and they
  may not have been paid for them). If the list clusters — "15 of 23 this month
  are cover shifts at ST-03" — that *is* the under-recording finding, made
  actionable.
- **Repeat absentees** — who was covered for most often (canonicalised
  surnames), with the reason split (no-show vs sick vs leave). No-shows are an
  accountability conversation; sick/leave is a rostering-resilience one.
- **Chronically-covered posts** — site/slot combinations that needed cover
  repeatedly → candidates for a permanent fill.
- **"Notes that lie"** — the count of shifts booked as client-requested that
  the note says were really a no-show (billing/accountability risk).

---

## 4. "What to do" — the action logic (`pipeline/actions.py`)

One recommendation per flagged person, in strict priority order:

1. **Duplicate identity** → consolidate the payroll records; if the *combined*
   projection breaches, also "cut their roster at one site by ~Nh" and "verify
   the N overlapping-clock-in shifts". (Admin fix + hours fix — merging the
   records makes the breach visible, it doesn't reduce the hours.)
2. **Open shift this week** → "N shifts have no clock-out, logged as 0h — verify
   and close before payroll." (Their real hours are missing from the projection.)
3. **At risk but central estimate < 55h** → **monitor**: "projects Xh, Y% breach
   chance — watch; recheck when Thu–Fri data lands." *No swap* — the person
   isn't actually projected to breach.
4. **Projected breach (> 55h)** → **shift-swap**, but only if there's a
   colleague at the **same site**, **same role**, whose projection stays
   **under 45h** after taking a ~one-shift (~10h) move. Named person, resulting
   total, rand saving shown. Otherwise → **"authorise ~Nh OT (~RX) or treat the
   site as one [role] short"**.

**Why so strict on swaps:** the six sites are hundreds of km apart, so
cross-site cover isn't real; and a swap that pushes the receiver into overtime
just relocates the cost. On this data the swap **rarely fires** — the roster
runs at a ~43h mean against a 45h cap, so clean same-site capacity almost never
exists. That is itself the finding: *for most at-risk people the honest options
are "watch it" or "authorise the overtime" — there is no slack to swap.*

**Caveat carried to NOTES/video:** "likely remaining shift" is inferred from
the person's own weekday pattern — there is no roster in the data. And the
recommendations take the employer's compliance/cost view; many shift workers
want the overtime pay.

### Strategic recommendations — NOT on the dashboard

Float/relief pool per region · roster to ~40h not ~43h · move week-to-date
hours upstream to whoever assigns weekend shifts · a hard cap in the rostering
tool · rotate Sunday/holiday work · re-price the contract. These are
data-informed but they're quarterly decisions, not "act today" — they go in
`NOTES.md` and the video ("the structural picture" / "what I'd do next"). The
subset that *is* weekly-actionable (repeat-absentee accountability, the
dispatch-desk failure, Sunday rotation) surfaces on the **Operations Review
tab (panel F)**.

---

## 5. Architecture — the reload requirement drives it

**Split the system in two:**

```
pipeline/                      thin dashboard
  load(dir) → clean → hours       reads pipeline output only
  → consolidate by id_number      no heavy computation
  → project + risk_score          just renders
  → classify notes
  → aggregate
  emits:
    predictions.csv
    note_classifications.csv
    dashboard_data.(json|parquet)
```

`predictions.csv` and `note_classifications.csv` fall out of the **same run**
as the dashboard data — one pipeline, three outputs.

### Build stack — lean Streamlit
- **Streamlit** app, deployed on **Streamlit Community Cloud** (free).
- Native **file-uploader** widget → the manager (or Jem) drops the 7 CSVs →
  app validates schema → pipeline recomputes → new week shown. This is the
  best possible answer to Requirement 4: drag-and-drop, no terminal.
- Fallback: `make load DIR=path/to/export` regenerates artifacts + redeploys.
- **Hard schema validation** on upload: column names, date ranges, `employee_id`
  overlap with `employees.csv`. Fail loudly with a readable message.
- **Partial weeks are first-class.** The export's newest week can run through
  any day; the pipeline derives the cutoff (`hours.latest_cutoff_dow`), picks
  the matching slope + threshold, and the as-of banner reflects it. An export
  through Tuesday and one through Friday both "just work" — the only visible
  difference is the confidence language and the flag count.

Alternative considered: static site (build script → Netlify/Pages) or
Next.js/Vercel. Rejected — more work, prettier than the brief wants, and the
in-UI upload story is weaker.

### Not building
Auth, user accounts, editable data, real-time anything, drill-down beyond the
9 weeks, a mobile-native app (just keep the Streamlit layout phone-legible).

---

## 6. Open decisions

1. Roster signal for remaining shifts (affects the swap suggestion's framing).
2. `risk` threshold for the "Breach likely" tier — set on the
   simulate-Wednesday backtest for a stated recall target.
3. Whether the in-UI upload recomputes live (slow cold-start on free tier) or
   the pipeline runs in a GitHub Action on commit and the app just reads.
4. Cost model detail — flat 1.5× / 2× on `hourly_rate`, or something finer.
5. How much of the "why analysis" (panel E) belongs on the dashboard vs only
   in `NOTES.md`.
6. Site triage (panel C) intervention score — how to weight its signals
   (breach count vs fixable-cost vs cause-concentration). Start simple: rank on
   fixable projected OT cost, break ties on breach count; refine if it mis-ranks
   against eyeball.
