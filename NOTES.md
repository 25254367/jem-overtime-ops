# NOTES

Draft — to be tightened in my own words before submission.

## Assumptions about the data

- **Hours follow the client's definition, not a textbook one.** `total = Σ(clock_out − clock_in)`,
  blank clock-out = 0h, clock-out ≤ clock-in = +24h, no break deduction.
  Reverse-engineered from all 2,122 `weekly_summary` rows — exact match. Ground
  truth is the client's system, so I match it and flag the gross-hours issue
  separately.
- **Breach = more than 55.0h in the week** (45 ordinary + 10 overtime). The
  client's history shows the cap is a strict `>` — the largest non-breach
  overtime is exactly 10.0h.
- **Overtime is per person.** Five people are in the register twice (shared ID
  number, bank account, tax number), one record per site, each staying just
  under 45h. BCEA counts overtime per employee, so their hours are merged
  before the breach test — otherwise the breach is invisible.
- **All 213 employees are in scope** — the highest rate is ~R139k/year, well
  under the earnings threshold.
- **There is no roster.** Week-to-week schedules don't repeat (daily-hours
  similarity maxes at 0.83), so remaining-week shifts are inferred from each
  person's own weekday habits. This is the model's biggest limitation.
- **Recorded hours understate reality** — 184 shifts (2.1%) are clocked in but
  never out and logged as 0h, shift length caps at 13.5h, and a no-show leaves
  no row. So operational-failure overtime is a floor.

## Checking the note-sorting

Seven categories: four reasons for extra hours (client-requested, absence
cover, late handover, equipment failure) and three "nothing useful" buckets
(routine, blank, unclassified). Classified by **rules** — the notes are ~50
phrase templates with injected typos and a fixed isiZulu/Afrikaans vocabulary,
not free prose, so a deterministic rule set is inspectable, free, and re-runs
on next week's data with no developer.

Three checks. **(1)** 180 notes hand-labelled before seeing the classifier
output (100 random + 80 aimed at the rare categories): 100% category accuracy
on the random 100, κ = 1.00, zero category disagreements in 180. **(2)** An
independent classifier built a different way — TF-IDF character n-grams +
nearest neighbour — agrees on 95.1% of all 2,117 notes; I read every one of the
104 disagreements and none was a rule error. **(3)** Clustering the notes: at 7
clusters they group by vocabulary, but as the cluster count approaches ~50 each
template becomes its own cluster and maps to one category — the taxonomy is a
real grouping of the templates, not an overlay.

Where it's wrong: the rules were silently dropping ~11 garbled notes; the
second method caught them and I hardened the typo handling, so `unclassified`
is now 0 — a limitation dressed as a success, since a genuinely novel phrasing
now gets forced into a category instead of flagged. Four sub-field rules were
fixed against the gold set, so those numbers are slightly optimistic. And 100%
is 100% *for this data only* — ~50 templates, one rule each; not evidence it
survives a new supervisor.

The split: attributing each overtime hour to the shift being worked when the
weekly total crosses 45h, ~21% of overtime hours carry a note that explains
them, and 78% of those are an operational failure (no-show, cover, late
handover, broken equipment), not something the client asked for. Note coverage
is ~24%, so that's a floor.

## What a trained model would add, and how I'd test it

**Notes.** An LLM reads meaning, so it would generalise to a supervisor who
writes "my partner didn't rock up so I held the fort" instead of "relief no
show again" — my rules only recognise the ~50 sentences that are actually in
this data. For one client with a stable set of supervisors the rules are the
right call: deterministic, every label traces to a named pattern, and a wrong
rule flags itself where a wrong LLM label looks exactly like a right one.
Across many clients that flips, and an LLM (or rules as a pre-filter with an
LLM for the residual) wins.

**Breach.** I fit a deliberately small model — one pooled slope for how a
person's mid-week pace carries to the weekend. A 45-feature gradient-boosted
classifier did not beat it: nine weeks and 65 breaches is too little, and the
ceiling here isn't the model. About 40% of breaches score under 0.10 on
Wednesday because the hours that cause them are added Thursday–Sunday, and
nothing in Wednesday's data sees that. The missing piece is an input, not an
algorithm — the roster. With it, a model could also learn which posts are
chronically short and who the regular cover is.

**Testing it honestly.** Expanding-window backtest: for each past week, pretend
it's Wednesday, fit only on earlier weeks, never touch the week you score.
Judge on PR-AUC and recall, not accuracy — the base rate is ~5%, so "nobody
breaches" scores 95%. Check calibration by bucket. Pull the five split-identity
people out of the headline number; they lift PR-AUC from 0.24 to 0.43 on their
own. With only 65 breaches, quote the recall/precision trade-off, not one F1.
For the notes, re-check on a fresh labelled sample from next week's data, not
the gold set the rules were tuned against.
