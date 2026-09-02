# Overtime Ops Room

A weekly early-warning tool for a national facilities-management company: six
sites, ~213 shift workers, raw clock-in/out data every week. It answers one
question, mid-week, before payroll runs:

> **Who is going to breach the 10-hour overtime cap by Sunday, and what should
> somebody do about it today?**

The assessment brief is in [`BRIEF.md`](BRIEF.md). A short account of the
approach, the checks, and what I'd do next is in [`NOTES.md`](NOTES.md).

### Start here

| If you want to… | Look at |
|---|---|
| see it running | the deployed URL, or `streamlit run app.py` |
| read the ½-page summary | [`NOTES.md`](NOTES.md) |
| check the prediction | [`docs/prediction-model.md`](docs/prediction-model.md), `backtest/simulate_wednesday.py` |
| check the note classifier | [`docs/CLASSIFICATION.md`](docs/CLASSIFICATION.md), `check/` |
| see the two required CSVs | `outputs/predictions.csv`, `outputs/note_classifications.csv` |
| regenerate everything | `python -m pipeline.run data` |

---

## The dashboard

A phone-legible board for the contract manager, three tabs:

- **Now** — who breaches by Sunday (ranked, with a plain-English projection and
  a 9-week history), where to focus (site triage), and the certain-and-fixable
  items to clear first.
- **Why** — the asked-for vs operational-failure split of the overtime, from the
  supervisor notes, plus where the recorded hours understate the real picture.
- **Ops Review** — backward-looking follow-ups: open shifts to close, repeat
  absentees, split-identity "phantom" absences, notes that contradict the booking.

**Loading next week's data needs no developer:** the "Load next week's data"
panel takes the seven CSVs, validates them, and recomputes the whole board. The
pipeline reads how far the week runs from the data itself, so a Tuesday export
and a Friday export both just work — only the confidence language and the flag
count change. `data_next_week/` is a synthetic next-week export (see
`scripts/make_next_week.py`) you can drop straight in to see this; the
`data_next_week/broken/` copy shows the loud validation failure.

### Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Deploy (Streamlit Community Cloud, free)

Push this repo to GitHub, then at [share.streamlit.io](https://share.streamlit.io)
create an app from the repo with main file `app.py`. The theme
(`.streamlit/config.toml`) and dependencies are picked up automatically.

---

## The pipeline

One command produces the three required artefacts from one pass over the export:

```bash
python -m pipeline.run data
# -> outputs/predictions.csv            (213 rows: employee_id, will_breach, risk_score)
# -> outputs/note_classifications.csv   (2,117 rows: shift_id, category, note)
# -> outputs/dashboard_data.json        (everything the dashboard renders)
```

### How the prediction works

- **Hours** reconcile exactly with the client's `weekly_summary.csv`. Breach ⟺
  `total_hours > 55.0` (45 ordinary + 10 overtime).
- **Identity is consolidated first.** Five people hold two `employee_id`s each
  (shared ID number, bank account, tax number). BCEA overtime is per person, so
  their records are merged before the breach is computed — otherwise the breach
  is invisible (two records, each under 45h).
- **Projection is distributional.** For each person the remaining hours are
  modelled as `Normal(µ, σ)`, µ tilted by how far ahead/behind pace they are
  (one pooled within-person slope, re-fit to the cutoff day), σ widened for
  open shifts. `risk_score = P(observed + remaining > 55)`.
- **No roster in the data**, so "likely remaining shifts" come from each
  person's own weekday pattern. This is the main limitation — see `NOTES.md`.

### How it does (expanding-window backtest, "it's Wednesday" on each past week)

| | precision | recall | notes |
|---|---|---|---|
| all-zero baseline | – | 0.00 | base rate is ~5% |
| naive: history mean > 55 | 0.63 | 0.19 | |
| naive: linear extrapolation ×7 | 0.11 | 0.62 | |
| **risk_score ≥ 0.24 (default)** | **0.46** | **0.46** | recall-leaning: a missed breach is the costly error |

`risk_score` PR-AUC 0.43 overall, **0.24 for ordinary employees** (the five
split-identity people carry much of the headline number — stated honestly).
The score is calibrated: the 0.5–0.75 bucket breaches 50% of the time.
About 40% of breaches still score ≤ 0.10 on Wednesday — genuinely
unpredictable without the roster.

### How the notes are classified

Rules-first (deterministic, ~50 templates, multilingual lexicon for isiZulu /
Afrikaans terms), into seven categories. Checked two ways: against 180
hand-labelled notes (100% on the random sample, κ = 1.00) and against an
independent TF-IDF + kNN model (95% agreement, zero rule errors it could
confirm). The classifier is effectively supervisor-specific — see
[`docs/CLASSIFICATION.md`](docs/CLASSIFICATION.md) and `NOTES.md`.

---

## Repo layout

```
app.py                  the Streamlit dashboard (thin view over pipeline output)
requirements.txt        .streamlit/config.toml  (Jem palette)
pipeline/               load · hours · features · predict · classify · attribute · actions · aggregate · run
backtest/               expanding-window simulation ("it's Wednesday")
check/                  classifier checks vs hand labels + a second method
  check/gold/           the 180 hand-labelled notes + labelling guide
scripts/                make_next_week.py — builds the synthetic reload export
tests/                  31 tests
data/                   the sample export (7 CSVs)
data_next_week/         synthetic next-week export for the reload demo
  data_next_week/broken/  same export with a column dropped (validation demo)
outputs/                the deliverables: predictions.csv · note_classifications.csv · dashboard_data.json
NOTES.md                assumptions · how the checks went · what a trained model would add
BRIEF.md                the original assessment brief
docs/                   assumptions · data_checks · prediction-model · CLASSIFICATION · DASHBOARD
```

```bash
python -m pytest -q          # 31 tests
python -m pipeline.run data  # regenerate the three artefacts
python backtest/simulate_wednesday.py data 2   # the backtest
python check/classify_check.py                 # classifier vs the gold set
```
