# Note classification task — scope & plan

Covers Requirement 3 (why the hours happened) and the asked-for-vs-failure
split (Requirement 2b). Feeds `note_classifications.csv`, `NOTES.md`, the
dashboard "why" panel, and the video walkthrough.

Context: `shift_notes.csv` = 2,117 notes on 2,117 distinct shifts (~24% of all
shifts). Highly templated — 103 templates (≥3 occurrences) cover 79%; ~50 base
sentences with injected typos, name-swaps, and isiZulu / Afrikaans variants.
Notes are a weak breach *predictor* (r ≈ 0.10) but the primary signal for *why*.

---

## 1. Deliverables

| Output | Form | Destination |
|---|---|---|
| `note_classifications.csv` | 2,117 rows, **exactly** `shift_id, category, note` | repo |
| Classifier code | pure fn `shift_notes.csv → note_classifications.csv`; deterministic; runs unchanged on next week's export | repo / pipeline |
| Internal enriched table | adds `overtime_driver`, `authorised`, `absentee`, `absence_reason`, `note_quality`, `surface_vs_driver_conflict` | repo (not submitted CSV) |
| Asked-for vs operational-failure split | headline %, concentration by site / role / week / absentee, + the under-count caveat | `NOTES.md`, dashboard |
| The check | frozen gold set + metrics + confusion matrix + 2-method agreement + ≥3 named failure modes + "notes that lie" count | `NOTES.md` (short), backing analysis in repo |
| `NOTES.md` paragraph | assumptions about the notes; how we checked; what it found; where the sorting is wrong | repo |
| One-note walkthrough | pick one classified note, explain step by step, simply | video |

The submitted CSV is locked to 3 columns. All richer fields live in the
internal table.

---

## 2. Taxonomy — 7 categories

**Carry a reason for extra hours:**

| Category | Definition | Example templates |
|---|---|---|
| `client_requested` | Client / centre management / site manager asked for extra cover, patrol, clean, or for staff to stay | "requested by centre management for load in, signed off"; "client requested deep clean before the audit – approved"; "stocktake ran over, client asked us to remain, they know they pay for it"; "klient het ekstra ure gevra vir stocktake" |
| `absence_cover` | Someone who should have been on post wasn't — relief no-show, named colleague absent, sick, on leave, double-post | "next shift guard did not pitch. had to cover"; "control room says relief coming, nobody came"; "covering <NAME> post, no show no call"; "<NAME> akezanga namhlanje, ngimele yena"; "covering for <NAME> – booked off sick"; "double duty today, <NAME> on family responsibility leave"; "took <NAME> shift as well, 2 posts 1 guard"; "aflos het nie opgedaag nie, moes aanbly" |
| `late_handover` | Handover delayed — waiting on paperwork, keys, OB book, or the next person just late | "late handover, waiting on paperwork"; "oorhandiging was laat, gewag vir sleutels"; "handover late again, keys missing"; "waited 25 min for handover, ob book not signed" |
| `equipment_failure` | Machine / generator / lift / gate broke; task done manually or took longer | "generator fault, stayed to monitor"; "buffer machine kaput, did the floor by hand"; "scrubber broke down, had to do the floor manually"; "lift out of order, everything carried up stairs, took long"; "masjien is stukkend, alles met die hand gedoen" |

**Do not carry a reason:**

| Category | Definition | Example |
|---|---|---|
| `routine` | Affirmative all-clear — an actual statement that nothing happened | "quiet shift", "nothing to report", "no incidents", "all quiet", "no issues on site", "as per normal", "akukho lutho", "niks om te rapporteer nie" |
| `blank` | Empty, punctuation-only, or pure filler token | "", " ", "-", ".", "n/a", "ntr", "ok", "sharp", "fine", "all good" |
| `unclassified` | Real content, no rule matched — genuinely garbled or a rare one-off. **Audited in the check.** Target ≤ ~5%. | (residual) |

### Sub-fields (internal table only)

- `overtime_driver` ∈ {`asked_for`, `operational_failure`, `none`}
  - `client_requested` → `asked_for`
  - `absence_cover`, `late_handover`, `equipment_failure` → `operational_failure`
  - `routine`, `blank`, `unclassified` → `none`
- `authorised` ∈ {`yes`, `unclear`, `n/a`} — for `client_requested` only.
  "signed off" / "approved" / "ok'd" → `yes`; "dont know if office approved" /
  "dont know if signed" → `unclear` (billing-risk flag).
- `absentee` — for `absence_cover`: the name if the note gives one, else
  `unnamed_relief`.
- `absence_reason` ∈ {`no_show`, `sick`, `leave`, `unknown`} — for
  `absence_cover`.
- `note_quality` ∈ {`substantive`, `all_clear`, `filler`, `blank`, `garbled`}
  — orthogonal descriptor; lets `NOTES.md` report blank/garbled rates without
  bloating the taxonomy.
- `surface_vs_driver_conflict` (bool) — true when the note's surface wording is
  `client_requested` but the stated real reason is operational (the "notes
  that lie", e.g. *"client signed for the extra hours but real reason is
  relief no show agn"*). Classify to the **driver** (`absence_cover`), set the
  flag.

### Precedence (when a note matches more than one reason)

1. `surface_vs_driver_conflict` → classify to the operational driver.
2. Otherwise: `equipment_failure` > `absence_cover` > `late_handover` >
   `client_requested` (equipment and absence are concrete causes; a bare
   "client asked us to stay" with no other signal is the weakest).
3. Reason category always beats `routine` / `blank`.
4. Log every multi-match for the check.

---

## 3. Method — rules-first, LLM/embeddings as auditor

**Primary classifier: curated keyword / regex rules per category.**

Rationale (for `NOTES.md`):
- The notes are ~50 templates + mild injected typos + a fixed multilingual
  vocabulary — not open-ended prose.
- A rule set is 100% inspectable, deterministic, and free — it satisfies the
  "accepts next week's data without a developer" requirement and is trivial to
  re-audit.
- Multilingual handling is a ~20-word lexicon, not translation:
  - isiZulu: `akezanga`, `namhlanje`, `ngimele yena`, `akukho lutho`,
    `ngicela`, `umsebenzi`
  - Afrikaans: `aflos`, `opgedaag`, `gedek/geddek vir`, `siek gemeld`,
    `oorhandiging`, `sleutels`, `masjien`, `stukkend`, `ekstra ure`, `niks om
    te rapporteer nie`, `gewag`
- Typo tolerance: normalise (lowercase, strip trailing punct, collapse
  whitespace), then match on stems / allow 1–2 char edits on keyword hits
  (`macine`/`machnie`, `agn`/`again`, `bc`/`because`, `sift`/`shift`).

**A well-argued "an LLM is the wrong tool here" scores as well as clever LLM
use** (brief, explicit). We use an LLM / embeddings only as the **independent
second method** for the check and to adjudicate the `unclassified` residual —
never a paid API (brief bans it); a local model or `sentence-transformers`
multilingual embeddings + nearest-labelled-neighbour.

---

## 4. Asked-for vs operational-failure split

### 4.1 Attribution rule — chronological / marginal (locked)

We attribute overtime *hours*, not note counts (the brief asks about hours).
Overtime hours physically sit in specific shifts, so:

1. Order each employee-week's shifts by clock-in time.
2. Accumulate hours shift by shift.
3. Once cumulative hours pass **45**, every hour after that is overtime — and
   each overtime hour belongs to the shift it was worked in (the crossing
   shift is split: ordinary up to 45, overtime beyond).
4. That shift's note → `overtime_driver`. Overtime on a note-less shift is
   `undetermined`.

This matches the client's flat-45 cumulative rule, needs no notes on the
early-week (ordinary-time) shifts, and makes "how much can we explain" explicit.

### 4.2 What the data actually supports (measured — `pipeline/attribute.py`)

Consolidated by `person_id`, all weeks (9 full + the partial target week),
**3,146 overtime hours**:

| | hours | % of all OT |
|---|---|---|
| attributed → **operational failure** | 519 | 16.5% |
| attributed → **asked-for** | 146 | 4.6% |
| OT on a routine/blank/unclassified-note shift | ~130 | ~4% |
| **OT on a no-note shift** | ~2,350 | **~75%** |

- **Attributable overtime ≈ 21% of the total.** Of that portion:
  **78% operational failure / 22% asked-for**.
- Note coverage on OT-bearing shifts is only ~26% — an OT-bearing shift is
  usually just a normal shift that fell after the 45h mark in a heavy week, not
  an event shift. So the chronological rule does **not** rescue coverage; the
  other ~75% is unattributable, consistent with breach weeks being *broadly
  heavier* rather than one disruption.

### 4.3 Report it as two numbers

- **Strict (shift-level, chronological):** "We can attribute ~21% of overtime
  hours to a cause; of those, **78% is operational failure** (no-shows, cover,
  equipment, handover), 22% client-requested."
- **Loose (week-level):** "**48% of the 93 breach-weeks** contain at least one
  operational-failure note" — a sense of how often a breach has a visible
  trigger.

The strict number is the defensible headline; the loose one gives context.

### 4.4 Concentration (measured)

Operational-failure overtime by driver: **absence_cover 346h**, equipment 123h,
late_handover 50h. By site: ST-03 Menlyn Park highest (137h), ST-04 Century City
lowest (53h). By `absentee`: **`unnamed_relief` 152h** (relief no-shows — the
roster gap), then named repeat-cover people — Ndlovu 23h, Maluleke 16h,
Khumalo 16h — the accountability list.

### 4.5 Caveat (from `data_checks.md` §3a)

Operational-failure overtime is **under-counted** — 13.5h shift cap, open shifts
zeroed, no-shows create no row. So the true operational-failure share is higher
than even the 78%-of-attributable figure.

---

## 5. The check ("do not cut this" — brief) — RESULTS

### 5a. Method 1 (rules) vs the 180-note hand-labelled gold
`check/classify_check.py` · gold `check/gold/gold_sample_labelled.csv`

| Metric | Result |
|---|---|
| Category accuracy — random 100 | **100%** |
| Category accuracy — all 180 | 99.4% |
| Cohen's κ | 0.99 |
| absence_reason (no_show/sick/leave/unknown) | **100%** |
| notes that lie (13 in gold) → operational driver | **100%** |
| authorised (yes/unclear) | 100% |
| absentee extraction | 98.8% |
| by language | en 99% · af 100% · **zu 95%** |

Only ~2 category misses across 180, both garbled typos.

**Honest reading:** the categories are *solved for this data* because the notes
are ~50 templates and the rules have a pattern per template — this is not
evidence the approach generalises. The sub-field rules **were** iterated
against the gold disagreements (4 bugs fixed: `ill\b` matching "st**ill**"→
sick; name-extraction missing lowercase names; a bug in the check; typo gaps),
so those numbers are optimistic — a genuinely novel phrasing still fails.

### 5b. Method 2 (TF-IDF char-ngram + kNN) vs the rules, all 2,117
`check/second_method.py` · a different mechanism (fuzzy similarity to labelled
examples, not keyword patterns), sklearn-only, deterministic, outputs committed.

- **Agreement: 95.1%** (2,013 / 2,117).
- Substantive categories: client_requested 100%, late_handover 100%,
  equipment_failure 99%, absence_cover 92%.
- **104 disagreements → 0 confirmed rule errors.** They are:
  - short `absence_cover` notes ("stood in for X", "took X shift") → method
    says `routine` (50) — method wrong, thin char signal + class-prior;
  - "no incidents" → method says `absence_cover` (23) — method wrong;
  - "waited for relief, nobody came through" → method says `late_handover`
    (18) — genuine fuzzy boundary; rules match the human gold;
  - "all fine" → method says `blank` (11) — the one systematic difference;
    we chose `routine`, similarity leans `blank`; both defensible.
- **What the method DID find:** the rules were leaving ~11 garbled notes
  `unclassified`, all `absence_cover`; the method caught them, and we hardened
  the typo normalisation → `unclassified` now **0**.

### 5c. Cluster alignment — is the taxonomy real or a human overlay?
k-means over the same vectors, swept over k:

| k | adjusted Rand | purity |
|---|---|---|
| 7 | 0.26 | 64% |
| 15 | 0.26 | 75% |
| 40 | 0.18 | **88%** |

At k=7 the clusters group by *vocabulary* more than *reason* (purity 64%). As
k grows toward the ~50 templates, purity climbs to 88% — **each template
becomes its own cluster and templates map cleanly to one category**. So the
7-category taxonomy is a sensible grouping of ~50 templates, not an arbitrary
imposition.

### 5d. Targeted audits (done, in `check/classify_check.py`)
- notes that lie: 13 in gold, 100% routed to `absence_cover` + flagged.
- absence_reason: 100% on the agreed absence_cover set (after the `ill\b` fix).
- multilingual: isiZulu 95% (one garbled note), Afrikaans 100%.

### 5e. Named failure modes (for `NOTES.md`)
1. **Garbled typos** — `"Covreed for Mabaso"`, `"still on site, reelief was
   suppose"` — needed hand-added typo patterns; a fresh export's typos will
   surface new ones.
2. **The `no_show` vs `unknown` reason boundary** — "X absent" vs "X didn't
   come" — genuinely fuzzy; MS was inconsistent on it first pass too.
3. **`late_handover` vs `absence_cover` on "waited for relief"** — the two
   methods split on it; defensible either way.
4. **`unclassified` is effectively unused on this data** (0 notes) — that's a
   *limitation dressed as a success*: it means novel phrasings will be
   mis-forced into an existing category rather than flagged.

### 5f. The headline limitation — the rules are writer-specific

The classifier is fit to **these ~24 supervisors' phrasing habits**, not to the
concept of "a shift note". It recognises 50-odd memorised sentences. Give it a
different facilities company, different supervisors, or one guard who writes
*"my partner didn't rock up so I held the fort till 6"* instead of *"relief no
show again"*, and the rules have no pattern — the note falls through (or, worse,
`unclassified` being unused means it gets force-fit).

**This is exactly what an LLM would do better.** An LLM reads *meaning*, so it
generalises across writers and unseen phrasings; the rules generalise across
*rows that repeat a template*. For a single client with a stable roster of
supervisors (this brief), the rules are the right call — deterministic, free,
inspectable, and empirically 100% on the sample. The moment this is rolled out
across multiple clients, the rules become a maintenance burden (a new pattern
per new phrasing) and an LLM (or the rules as a fast pre-filter with an LLM
fallback for the residual) is the better architecture.

→ This is the core of the `NOTES.md` "what a trained model would learn that
your approach does not" answer.

### 5g. Why rules beat an LLM *for this problem* (the brief rewards this)

1. **Deterministic** — same note → same category, forever. An LLM at temp 0 is
   only near-deterministic (drifts across model versions / quantisation /
   hardware). Matters for a compliance-adjacent tool.
2. **Auditable** — every label traces to a named pattern (`matched_rule`). A
   dispute over "why was this client-requested" points to a line of code, not
   a weight.
3. **Fails visibly** — a wrong rule → `unclassified` (a flag). A wrong LLM → a
   confident wrong label indistinguishable from a right one. No silent drift.
4. **Free, offline, instant** — no download / GPU / daemon / API key. 2,117
   notes in <1s vs minutes–hours for a local 7B model. Brief: "normal laptop,
   no paid API key".
5. **No prompt fragility** — LLM output swings with prompt wording / example
   order / category-definition phrasing. Rules don't.
6. **The check means something** — the rules are simple enough to reason about,
   so you can enumerate what they will/won't catch. 100% on the sample is
   informative; with an LLM you're guessing about note 2,118.
7. **Transparent maintenance** — new phrasing → add one readable line.
8. **The data suits it** — ~50 templates; an LLM is a sledgehammer.

**Counterweight (keep visible):** the LLM wins on generalisation to new writers
and unseen phrasings, the garbled tail, and multilingual coverage beyond the
hand-built lexicon. Right tool for *this* job (one client, stable supervisors,
templated notes); wrong tool for "classify any shift note from any company".

---

## 6. Definition of done

- [x] `note_classifications.csv`: 2,117 rows, 3 cols, every note labelled
      (`unclassified` 0 on this data — see §5e limitation).
- [x] Classifier is deterministic; re-runs on a fresh export unchanged; rules
      in one readable file (`pipeline/classify.py`).
- [x] Gold set: 180, frozen, hand-labelled (`check/gold/gold_sample_labelled.csv`).
- [x] Check: rules-vs-gold + rules-vs-second-method + cluster alignment +
      targeted audits (§5).
- [x] Split: strict 21% attributable / 78% operational failure; loose 48% of
      breach-weeks; concentration by site/driver/absentee; under-count caveat
      (§4).
- [ ] `NOTES.md` paragraph written; one note chosen for the video.

---

## 7. Open decisions

1. ~~Overtime-hour attribution~~ — **locked: chronological / marginal (§4.1).**
2. **Second method** — multilingual embeddings + kNN vs local zero-shot LLM vs
   TF-IDF + logistic. Lean embeddings + kNN (no model hosting, multilingual
   out of the box).
3. **Gold set size** — 180 vs 200; whether to oversample `ambiguous` and
   `unclassified`.
4. **Label split** — how many each of MS / model; reconciliation process for
   disagreements.
5. Whether an 8th category emerges from reading the `unclassified` pile
   (e.g. `safety_incident`, `weather`) — decide after first pass. (Gold set has
   0 `unclassified` — the labeller categorised every note — so an 8th category
   looks unlikely.)
6. ~~`all good` / `all fine` / `all quiet`~~ — **resolved: `routine`** (they
   state the shift was uneventful). Bare `ok` / `fine` / `sharp` / `noted` stay
   `blank`.
