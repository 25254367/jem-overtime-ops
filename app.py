"""Overtime Ops Room — the deployed dashboard.

A thin view over pipeline output. It does no modelling: it reads
`outputs/dashboard_data.json` (bundled), or re-runs the pipeline on an export
the user drops in the sidebar. One screen, phone-legible, Jem's palette.

    streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Overtime Ops Room", page_icon="⏱️", layout="centered")

ROOT = Path(__file__).parent
DEFAULT_JSON = ROOT / "outputs" / "dashboard_data.json"
EXPORT_FILES = [
    "employees.csv", "payroll_details.csv", "public_holidays.csv",
    "shift_notes.csv", "shifts.csv", "sites.csv", "weekly_summary.csv",
]
MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _d(iso: str) -> str:
    y, m, day = (int(x) for x in iso.split("-"))
    return f"{day} {MONTHS[m]}"


# ───────────────────────────── styling ─────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ground:#f7f2f3; --surface:#ffffff; --surface-2:#fbf5f6;
  --ink:#051d2e; --ink-soft:#265373; --ink-faint:#7c8b96;
  --line:#ececec; --line-strong:#dcdcdc;
  --brand:#c43759; --brand-fill:#ff697f; --brand-soft:#fff0f2;
  --accent:#265373; --accent-fill:#95afe8; --accent-soft:#f0f5ff;
  --crit:#cf2b1c; --crit-soft:#ffe4e0; --warn:#9a6a12; --warn-soft:#fdeecb;
  --ok:#227a1b; --ok-soft:#d8ffd6; --watch:#838383; --watch-soft:#eef0f2;
  --shadow:0 1px 2px rgba(5,29,46,.05), 0 8px 24px rgba(5,29,46,.06);
}

/* --- Streamlit chrome --- */
.stApp { background: var(--ground); }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], #MainMenu, footer { visibility: hidden; }
.block-container { max-width: 512px; padding: 1.4rem 1rem 4rem; }
html, body, .stApp, [class*="css"] { font-family: "Manrope", system-ui, -apple-system, sans-serif; }

.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 13.5px; color: var(--ink-faint); padding: 8px 6px; }
.stTabs [aria-selected="true"] { color: var(--ink); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--brand-fill); height: 2px; }
.stTabs [data-baseweb="tab-panel"] { padding-top: 14px; }

[data-testid="stExpander"] {
  border: 1px solid var(--line); border-radius: 12px;
  box-shadow: var(--shadow); background: var(--surface);
  margin-bottom: 7px; overflow: hidden;
}
[data-testid="stExpander"] summary { font-size: 13.5px; padding: 11px 13px; }
[data-testid="stExpander"] summary:hover { color: var(--brand); }
[data-testid="stExpander"] [data-testid="stExpanderDetails"] { padding: 0 13px 12px; }

/* --- header --- */
.apphdr { border-top: 3px solid var(--brand-fill); padding-top: 12px; margin-bottom: 4px; }
.brand { font-weight: 800; font-size: 19px; letter-spacing: -.02em; color: var(--ink); }
.brand span { color: var(--brand-fill); }
.asof { margin: 7px 0 2px; font-size: 12.5px; color: var(--ink-soft);
        display: flex; gap: 7px; align-items: flex-start; line-height: 1.45; }
.asof .dot { flex: none; margin-top: 5px; width: 7px; height: 7px; border-radius: 50%; background: var(--warn); }
.asof b { color: var(--ink); font-weight: 600; }
.src { font-size: 11px; color: var(--ink-faint); margin-bottom: 6px; }

/* --- metric tiles --- */
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 6px 0 4px; }
.metric { background: var(--surface); border: 1px solid var(--line); border-radius: 11px;
          padding: 11px 11px 10px; box-shadow: var(--shadow); }
.metric .v { font-weight: 800; font-size: 25px; line-height: 1; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }
.metric .v.crit { color: var(--crit); } .metric .v.warn { color: var(--warn); } .metric .v.brand { color: var(--brand); }
.metric .l { font-size: 10.5px; color: var(--ink-soft); margin-top: 6px; line-height: 1.3; }

/* --- cards --- */
.eyebrow { font-family: "IBM Plex Mono", monospace; font-size: 10.5px; letter-spacing: .13em;
           text-transform: uppercase; color: var(--ink-faint); margin: 20px 0 8px; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
        box-shadow: var(--shadow); overflow: hidden; }
.card.alert { border-color: var(--crit); }
.ahead { background: var(--crit-soft); color: var(--crit); font-weight: 700; font-size: 12.5px;
         padding: 9px 13px; border-bottom: 1px solid var(--line); }
.asub { padding: 11px 13px 3px; font-size: 10px; font-family: "IBM Plex Mono", monospace;
        letter-spacing: .05em; text-transform: uppercase; color: var(--ink-faint); }
.frow { padding: 7px 13px 9px; font-size: 12.5px; border-top: 1px solid var(--line); display: flex; gap: 9px; line-height: 1.5; }
.frow:first-of-type { border-top: 0; }
.frow .who { font-weight: 600; }
.frow .mt { color: var(--ink-soft); font-size: 12px; }
.frow .qt { color: var(--ink-soft); font-style: italic; }
.frow .tk { flex: none; color: var(--crit); font-weight: 700; }
.mono { font-family: "IBM Plex Mono", monospace; }

.brief { font-size: 12.5px; color: var(--ink-soft); line-height: 1.55; }
.brief b { color: var(--ink); } .brief .do { color: var(--brand); font-weight: 600; }
.badge { font-size: 10px; font-weight: 700; font-family: "IBM Plex Mono", monospace;
         letter-spacing: .04em; padding: 2px 7px; border-radius: 999px;
         background: var(--crit-soft); color: var(--crit); }
.badge.calm { background: var(--accent-soft); color: var(--accent); }

/* --- person detail --- */
.pd .sent { font-size: 12.5px; line-height: 1.55; background: var(--surface-2);
            border: 1px solid var(--line); border-radius: 8px; padding: 10px 11px; }
.pd .line { font-size: 11.5px; color: var(--ink-soft); margin-top: 8px; }
.pd .do { margin-top: 10px; padding-left: 10px; border-left: 2px solid var(--brand-fill); }
.pd .doh { font-size: 12px; line-height: 1.45; color: var(--ink); }
.pd .doh b { color: var(--brand); }
.pd .dos { margin: 5px 0 0; padding-left: 17px; }
.pd .dos li { font-size: 12px; line-height: 1.5; color: var(--ink-soft); margin-bottom: 2px; }

/* --- weekly bar chart --- */
.chart { margin-top: 11px; }
.chart .bars { display: flex; align-items: flex-end; gap: 5px; height: 88px; position: relative; }
.chart .cap { position: absolute; left: 0; right: 0; border-top: 1px dashed var(--line-strong); }
.chart .cap span { position: absolute; right: 0; top: -13px; background: var(--surface);
                   font-size: 9px; color: var(--ink-faint); font-family: "IBM Plex Mono", monospace; padding-left: 4px; }
.chart .bar { flex: 1; background: var(--accent-fill); border-radius: 2px 2px 0 0; opacity: .7; min-height: 3px; }
.chart .bar.br { background: var(--crit); opacity: 1; }
.chart .xr { display: flex; gap: 5px; margin-top: 4px; }
.chart .xr span { flex: 1; text-align: center; font-size: 8px; color: var(--ink-faint); font-family: "IBM Plex Mono", monospace; }
.chart .xr span.op { color: var(--brand); font-weight: 700; }
.chart .leg { font-size: 10px; color: var(--ink-faint); margin-top: 7px; display: flex; gap: 11px; flex-wrap: wrap; }
.chart .leg i { font-style: normal; }
.chart .leg .sw { display: inline-block; width: 8px; height: 8px; border-radius: 2px; vertical-align: middle; margin-right: 4px; }

/* --- why tab --- */
.stat-lead { font-size: 14.5px; line-height: 1.5; font-weight: 500; letter-spacing: -.01em; color: var(--ink); }
.stat-lead b { color: var(--brand); font-weight: 700; }
.splitbar { display: flex; height: 24px; border-radius: 6px; overflow: hidden; margin: 12px 0 6px; border: 1px solid var(--line); }
.splitbar i { display: block; }
.splitbar .a { background: var(--crit); } .splitbar .b { background: var(--warn); } .splitbar .c { background: var(--watch-soft); }
.splitkey { font-size: 10.5px; color: var(--ink-soft); display: flex; flex-wrap: wrap; gap: 9px; }
.splitkey i { font-style: normal; }
.splitkey .sw { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }

table.mini { width: 100%; border-collapse: collapse; font-size: 12px; }
table.mini th { text-align: left; font-weight: 500; color: var(--ink-faint); font-family: "IBM Plex Mono", monospace;
                font-size: 9.5px; letter-spacing: .07em; text-transform: uppercase;
                padding: 8px 13px; border-bottom: 1px solid var(--line); }
table.mini td { padding: 7px 13px; border-bottom: 1px solid var(--line); }
table.mini tr:last-child td { border-bottom: 0; }
table.mini td.n { text-align: right; font-family: "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; color: var(--ink-soft); }
table.mini td.nm { font-weight: 500; }

.note { font-size: 12px; line-height: 1.6; color: var(--ink-soft); padding: 12px 13px; }
.note b { color: var(--ink); font-weight: 600; }
.note .lead { color: var(--ink); font-weight: 500; }
.pts { margin: 7px 0 0; padding-left: 17px; }
.pts li { font-size: 12px; line-height: 1.5; color: var(--ink-soft); margin-bottom: 3px; }
.fix { color: var(--brand); font-weight: 600; }
.bignum { color: var(--crit); font-weight: 800; font-size: 18px; font-variant-numeric: tabular-nums; margin-right: 3px; }
.opsrow { padding: 9px 13px; border-top: 1px solid var(--line); font-size: 12px; display: flex; gap: 9px; line-height: 1.45; }
.opsrow:first-child { border-top: 0; }
.opsrow .dt { font-family: "IBM Plex Mono", monospace; font-size: 10.5px; color: var(--ink-faint); flex: none; width: 40px; }
.opsrow .bd { flex: 1; }
.opsrow .bd .t { font-weight: 600; }
.opsrow .bd .q { color: var(--ink-soft); font-style: italic; }
.opsrow .bd .p { color: var(--ink-faint); }
.foot { margin-top: 22px; padding-top: 13px; border-top: 1px solid var(--line);
        font-size: 10.5px; color: var(--ink-faint); line-height: 1.5; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ───────────────────────────── data ─────────────────────────────
@st.cache_data(show_spinner=False)
def _default_data() -> dict:
    """The bundled sample board. Uses the committed JSON if present; otherwise
    (e.g. a fresh deploy where the artifact isn't committed) rebuilds it from
    the sample export in data/."""
    if DEFAULT_JSON.exists():
        return json.loads(DEFAULT_JSON.read_text())
    from pipeline.aggregate import build
    from pipeline.features import person_week_hours
    from pipeline.load import load_export
    exp = load_export(str(ROOT / "data"))
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    return build(exp, target_week=weeks[-1], history_weeks=weeks[:-1])


def _run_pipeline(uploaded) -> tuple[dict, str, str]:
    from pipeline.aggregate import build
    from pipeline.classify import note_classifications_csv
    from pipeline.features import person_week_hours
    from pipeline.load import load_export
    from pipeline.predict import predictions_csv

    tmp = Path(tempfile.mkdtemp())
    for f in uploaded:
        (tmp / f.name).write_bytes(f.getvalue())
    exp = load_export(str(tmp))
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    target, history = weeks[-1], weeks[:-1]
    data = build(exp, target_week=target, history_weeks=history)
    preds = predictions_csv(exp, target, history).to_csv(index=False)
    notes = note_classifications_csv(exp).to_csv(index=False)
    return data, preds, notes


if "data" not in st.session_state:
    st.session_state.data = _default_data()
    st.session_state.source = "sample data bundled with the app"
    st.session_state.csvs = None


# ─────────────────────── brand + the reload (main column) ───────────────────────
st.markdown(
    '<div class="apphdr"><div class="brand">Overtime <span>Ops Room</span></div></div>',
    unsafe_allow_html=True,
)

with st.expander("Load next week's data  ·  how to read this"):
    st.caption(
        "Drop in next week's export — the 7 CSVs from the shift system — and the "
        "whole board recomputes. No spreadsheet, no developer."
    )
    up = st.file_uploader("Shift export (7 CSVs)", type="csv",
                          accept_multiple_files=True)
    if st.button("Validate & run", type="primary", disabled=not up):
        names = {f.name for f in up}
        missing = [f for f in EXPORT_FILES if f not in names]
        if missing:
            st.error("Missing file(s): " + ", ".join(missing))
        else:
            try:
                with st.spinner("Recomputing…"):
                    data, preds, notes = _run_pipeline(up)
                st.session_state.data = data
                st.session_state.source = "uploaded export"
                st.session_state.csvs = (preds, notes)
                st.success("Board updated — close this panel to see it.")
            except Exception as exc:  # noqa: BLE001 — surface any load/validation error
                st.error(f"Could not process the export:\n\n{exc}")

    if st.session_state.csvs:
        preds, notes = st.session_state.csvs
        c1, c2 = st.columns(2)
        c1.download_button("predictions.csv", preds, "predictions.csv",
                           use_container_width=True)
        c2.download_button("note classifications", notes,
                           "note_classifications.csv", use_container_width=True)

    if st.session_state.source != "sample data bundled with the app":
        if st.button("Reset to sample data"):
            st.session_state.data = _default_data()
            st.session_state.source = "sample data bundled with the app"
            st.session_state.csvs = None
            st.rerun()

    st.divider()
    st.markdown(
        "- **Breach** = more than 55h in the Mon–Sun week (45 ordinary + 10 "
        "overtime, the BCEA cap).\n"
        "- The **%** is the modelled chance of crossing 55h by Sunday, given "
        "hours so far and this person's history.\n"
        "- Accuracy rises through the week: a Monday read is a hint, a Saturday "
        "read is nearly certain.\n"
        "- Figures are illustrative assessment data."
    )


d = st.session_state.data
m = d["meta"]
asof = (dt.date.fromisoformat(m["target_week"])
        + dt.timedelta(days=m["cutoff_dow"]))
asof_str = f"{asof.strftime('%A')} {_d(asof.isoformat())}"


# ───────────────────────────── as-of banner ─────────────────────────────
st.markdown(
    f"""
    <div class="asof">
      <span class="dot"></span>
      <div>Data through <b>{asof_str}</b>. Predictions sharpen each day —
      accuracy today is <b>{m['confidence']}</b>.</div>
    </div>
    <div class="src">Source: {st.session_state.source} · {m['n_employees']} people · {m['n_sites']} sites</div>
    """,
    unsafe_allow_html=True,
)


# ───────────────────────────── helpers ─────────────────────────────
DOTS = {"breach_likely": "🔴", "elevated": "🟠", "watch": "⚪"}
STRIPE = {"breach_likely": "crit", "elevated": "warn", "watch": "watch"}


def weekly_chart(history: list[dict]) -> str:
    if not history:
        return ""
    hi = max([h["hours"] for h in history] + [60]) * 1.04
    bars, xs = "", ""
    for h in history:
        cls = "bar br" if h["breached"] else "bar"
        bars += f'<div class="{cls}" style="height:{h["hours"] / hi * 100:.0f}%"></div>'
        wk = _d(h["week"])
        xs += f'<span class="{"op" if h["open_shift"] else ""}">{wk}</span>'
    return (
        f'<div class="chart"><div class="bars">'
        f'<div class="cap" style="bottom:{55 / hi * 100:.0f}%"><span>55h cap</span></div>'
        f'{bars}</div><div class="xr">{xs}</div>'
        f'<div class="leg">'
        f'<i><span class="sw" style="background:var(--crit)"></span>breached</i>'
        f'<i><span class="sw" style="background:var(--accent-fill)"></span>under cap</i>'
        f'<i style="color:var(--brand)">▲ open-shift week</i></div></div>'
    )


def _do_block(headline: str, steps: list[str]) -> str:
    lis = "".join(f"<li>{s}</li>" for s in steps)
    return (f'<div class="do"><div class="doh"><b>Do</b> — {headline}</div>'
            f'<ul class="dos">{lis}</ul></div>')


def person_block(row: dict) -> None:
    pid = row["person_id"]
    det = d["people"].get(pid, {})
    dot = DOTS[row["tier"]]
    label = (f"{dot}  **{row['name']}** · {row['site']} · {row['role']}"
             f"  —  {int(round(row['risk_score'] * 100))}%")
    do = _do_block(
        det.get("rec_headline", row.get("action_headline", "")),
        det.get("rec_steps", row.get("action_steps", [])),
    )
    with st.expander(label):
        st.markdown(
            f"""
            <div class="pd">
              <div class="sent">{det.get('projection_sentence', '')}</div>
              <div class="line">{det.get('shift_line', '')}</div>
              {weekly_chart(det.get('history', []))}
              {do}
            </div>
            """,
            unsafe_allow_html=True,
        )


def discuss(lead: str, points: list[str], bignum: str | None = None) -> str:
    """A card that reads like the person 'Do' block: one prose lead, then bullets."""
    lis = "".join(f"<li>{p}</li>" for p in points)
    tag = f'<span class="bignum">{bignum}</span> ' if bignum else ""
    return (f'<div class="card"><div class="note">{tag}'
            f'<span class="lead">{lead}</span>'
            f'<ul class="pts">{lis}</ul></div></div>')


def mini_table(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for r in rows:
        tds = "".join(
            f'<td class="nm">{c}</td>' if i == 0 else f'<td class="n">{c}</td>'
            for i, c in enumerate(r)
        )
        body += f"<tr>{tds}</tr>"
    return f'<div class="card"><table class="mini"><tr>{head}</tr>{body}</table></div>'


# ───────────────────────────── tabs ─────────────────────────────
tab_now, tab_why, tab_ops = st.tabs(["Now", "Why", "Ops Review"])

# ============================ NOW ============================
with tab_now:
    h = d["headline"]
    cost = h["projected_ot_cost_rand"]
    cost_str = f"R{cost / 1000:.1f}k" if cost >= 1000 else f"R{cost:.0f}"
    st.markdown(
        f"""
        <div class="metrics">
          <div class="metric"><div class="v crit">{h['n_breach_likely']}</div>
            <div class="l">predicted to breach by Sun</div></div>
          <div class="metric"><div class="v warn">{h['n_elevated']}</div>
            <div class="l">at risk — watch Thu/Fri</div></div>
          <div class="metric"><div class="v brand">{cost_str}</div>
            <div class="l">projected overtime cost</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- fix these first ----
    si = d["alerts"]["split_identity"]
    dbl = {r["name"]: r for r in d["alerts"]["double_booking"]}
    opens = d["alerts"]["open_shifts_this_week"]

    ppl_rows = ""
    for p in sorted(si["by_person"], key=lambda x: -dbl.get(x["name"], {}).get("combined_projected", 0)):
        proj = dbl.get(p["name"], {}).get("combined_projected")
        proj_s = f" · {proj:.0f}h combined" if proj else ""
        ppl_rows += (
            f'<div class="frow"><span class="tk">·</span><div>'
            f'<div class="who">{p["name"]} <span class="mono mt">{" + ".join(p["employee_ids"])}</span></div>'
            f'<div class="mt">{"/".join(p["sites"])}{proj_s} · '
            f'{p["cover_shifts"]} phantom no-shows</div></div></div>'
        )
    open_rows = ""
    for o in opens:
        note = (o["note"][:70] + "…") if len(o["note"]) > 71 else o["note"]
        open_rows += (
            f'<div class="frow"><span class="tk">·</span><div>'
            f'<div class="who">{o["name"]} <span class="mono mt">{o["site"]} · {_d(o["date"])}</span></div>'
            f'<div class="qt">“{note}”</div></div></div>'
        )
    st.markdown('<div class="eyebrow">Fix these first</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="card alert">
          <div class="ahead">⚑ Certain, current, fixable</div>
          <div class="asub">{si['n_people']} people on two rosters as separate employees — neither site knows</div>
          <div class="frow"><span class="tk">·</span><div class="mt">
            On the days they're at one site, the other logs a no-show and pays a cover.
            <ul class="pts">
              <li><b>{si['cover_shifts']} phantom no-shows in {si['window_weeks']} weeks</b>
              — {si['cross_site_conflicts']} provably while the person was clocked in elsewhere.</li>
              <li>~{si['double_paid_hours']:.0f}h also sit on the books at two sites at once.</li>
              <li><span class="fix">Fix:</span> one site each; fill the other post locally.</li>
            </ul>
          </div></div>
          {ppl_rows}
          <div class="asub">{len(opens)} shifts this week clocked in, never closed — logged as 0h</div>
          {open_rows}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- site triage ----
    st.markdown('<div class="eyebrow">Where to focus today</div>', unsafe_allow_html=True)
    sites = d["sites"]
    for i, sv in enumerate(sites):
        act = sv["n_breach_likely"] > 0
        tag = "🔴 act here" if act else ("· hold" if sv["n_watch"] == 0 else "")
        head = (f"{sv['site_id']}  {sv['site_name']}  —  {sv['n_breach_likely']} breach · "
                f"{sv['n_watch']} watch · R{sv['fixable_ot_cost_rand']:.0f}")
        with st.expander(head, expanded=(i == 0)):
            here = [r for r in d["risk_list"] if r["site"] == sv["site_id"]]
            breach_names = [r["name"] for r in here if r["tier"] == "breach_likely"]
            bits = []
            if breach_names:
                bits.append(f"<b>{len(breach_names)} predicted breach</b> "
                            f"({', '.join(breach_names)})")
            if sv["n_watch"]:
                bits.append(f"{sv['n_watch']} on the watch tier")
            bits.append(f"~R{sv['fixable_ot_cost_rand']:.0f} of fixable overtime")
            do = ("consolidate the split identity first, then recheck the watch "
                  "list when Friday data lands." if breach_names
                  else "nothing this week beyond closing any open shifts.")
            st.markdown(
                f'<div class="brief">{" · ".join(bits)}.<br>'
                f'<span class="do">Do:</span> {do}</div>',
                unsafe_allow_html=True,
            )

    # ---- risk list ----
    st.markdown('<div class="eyebrow">Who to call about</div>', unsafe_allow_html=True)
    rl = d["risk_list"]
    for row in [r for r in rl if r["tier"] in ("breach_likely", "elevated")]:
        person_block(row)
    watch = [r for r in rl if r["tier"] == "watch"]
    if watch and st.toggle(f"Show {len(watch)} on the watch tier (projected 45–52h)"):
        for row in watch:
            person_block(row)

    st.markdown(
        '<div class="foot">Ranked by breach probability at the '
        f'{m["cutoff_label"]} cutoff. “Projected” is the central estimate; '
        'the % is P(total &gt; 55h).</div>',
        unsafe_allow_html=True,
    )

# ============================ WHY ============================
with tab_why:
    w = d["why_split"]
    tot = w["total_overtime_hours"]
    opf, ask = w["operational_failure_hours"], w["asked_for_hours"]
    unattr = tot - opf - ask
    st.markdown('<div class="eyebrow">Asked-for vs operational failure</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""
        <p class="stat-lead">Of <b>{tot:,.0f}</b> overtime hours in the record, a
        specific shift and note explain <b>{w['attributable_hours']:,.0f}h
        ({w['attributable_share']:.0%})</b>. Of those, <b>{w['opfail_share_of_attributable']:.0%}</b>
        trace to an operational failure — a no-show, a broken lift, a late handover —
        not a client request.</p>
        <div class="splitbar">
          <i class="a" style="flex:0 0 {opf / tot * 100:.1f}%"></i>
          <i class="b" style="flex:0 0 {ask / tot * 100:.1f}%"></i>
          <i class="c" style="flex:1"></i>
        </div>
        <div class="splitkey">
          <i><span class="sw" style="background:var(--crit)"></span>operational failure — {opf:,.0f}h</i>
          <i><span class="sw" style="background:var(--warn)"></span>client-requested — {ask:,.0f}h</i>
          <i><span class="sw" style="background:var(--line-strong)"></span>unattributed — {unattr:,.0f}h</i>
        </div>
        <p class="note" style="padding-left:0;padding-right:0">A stricter read: across
        <b>{w['n_breach_weeks']} breach-weeks</b>, <b>{w['breach_weeks_with_opfail_note']:.0%}</b>
        carry at least one operational-failure note. The true share is between these two
        numbers — most overtime has no note at all.</p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Operational-failure hours by cause</div>',
                unsafe_allow_html=True)
    st.markdown(
        mini_table(
            ["Cause", "Shifts", "Hours"],
            [[r["category"].replace("_", " ").title(), r["n_shifts"],
              f'{r["opfail_hours"]:.0f}'] for r in w["by_driver"]],
        ),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">By site</div>', unsafe_allow_html=True)
    st.markdown(
        mini_table(
            ["Site", "Shifts", "Hours"],
            [[f'{r["site_id"]} {r["site_name"]}', r["n_shifts"],
              f'{r["opfail_hours"]:.0f}'] for r in w["by_site"]],
        ),
        unsafe_allow_html=True,
    )

    si = w["split_identity"]
    st.markdown('<div class="eyebrow">Some of it is self-inflicted</div>',
                unsafe_allow_html=True)
    st.markdown(
        discuss(
            f"{si['cover_shifts']} of the operational-failure cover shifts are "
            f"absences by the {si['n_people']} split-identity people, at their own "
            f"two sites.",
            [
                "Neither roster knows it's one person, so each site keeps "
                "expecting them and logs a fresh no-show.",
                f"{si['cross_site_conflicts']} are provably the person clocked in "
                f"at their other site at the time.",
                f'<span class="fix">Fix:</span> single-site each person and '
                f"backfill the vacated post locally — this also ends the "
                f"~{si['double_paid_hours']:.0f}h booked at two sites at once.",
            ],
        ),
        unsafe_allow_html=True,
    )

    ur = w["under_recording"]
    st.markdown('<div class="eyebrow">The record understates it</div>',
                unsafe_allow_html=True)
    st.markdown(
        discuss(
            f"The recorded {ur['recorded_breach_rate']:.0%} breach rate is a floor "
            f"— real coverage happens that never reaches the hours.",
            [
                f"{ur['open_shift_count']} shifts ({ur['open_shift_share']:.1%}) "
                f"clock in but never clock out — logged as 0h, mostly cover shifts.",
                f"Shift length caps at {ur['shift_cap_hours']:g}h "
                f"({ur['shifts_at_cap']} sit exactly there), so a 20-hour double "
                f"records as {ur['shift_cap_hours']:g}h or 0h.",
                "A no-show creates no record at all — the site-day looks lighter "
                "even though the same cover was worked.",
                f"Impute one shift per open-shift week and the rate rises to "
                f"~{ur['estimated_true_breach_rate']:.0%}.",
            ],
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="foot">Attribution walks each breach week shift-by-shift; the '
        'overtime hour is charged to the shift being worked when the running total '
        'crosses 45h, and that shift\'s note is the cause. Method and error rates in NOTES.</div>',
        unsafe_allow_html=True,
    )

# ============================ OPS REVIEW ============================
with tab_ops:
    o = d["ops_review"]
    st.markdown(
        '<p class="note" style="padding:2px 0 0">Backward-looking — check this weekly, '
        'not daily. Concrete things to chase before payroll runs.</p>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Open shifts to close</div>', unsafe_allow_html=True)
    rows = ""
    for x in o["open_shifts_recent"][:8]:
        note = x["note"] or "—"
        q = f'“{note}”' if x["note"] else '<span class="p">no note</span>'
        rows += (f'<div class="opsrow"><span class="dt">{_d(x["date"])}</span>'
                 f'<span class="bd"><span class="t">{x["name"]}</span> · {x["site"]}<br>'
                 f'<span class="q">{q}</span></span></div>')
    by_site = " · ".join(f"{k} ({v})" for k, v in list(o["open_shifts_by_site"].items())[:3])
    st.markdown(
        f'<div class="card">{rows}<div class="note" style="border-top:1px solid var(--line)">'
        f'Clusters at {by_site}. An open shift on a cover shift means real hours &gt; '
        f'recorded hours — a payroll-integrity item.</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Phantom absences — split-identity people</div>',
                unsafe_allow_html=True)
    ph = [x for x in o["phantom_absence_shifts"] if x["cross_site"]][:6]
    rows = ""
    for x in ph:
        rows += (f'<div class="opsrow"><span class="dt">{_d(x["date"])}</span>'
                 f'<span class="bd"><span class="t">{x["covered_person"]}</span> · '
                 f'covered at {x["cover_site"]}<br><span class="q">“{x["note"]}”</span> '
                 f'<span class="p">— clocked in elsewhere that day</span></span></div>')
    si = d["why_split"]["split_identity"]
    st.markdown(
        f'<div class="card">{rows}<div class="note" style="border-top:1px solid var(--line)">'
        f'<b>{si["cover_shifts"]} cover shifts in {si["window_weeks"]} weeks</b> across the '
        f'{si["n_people"]} people, {si["cross_site_conflicts"]} a hard cross-site clash. '
        f'<b>Do:</b> one site each; permanently fill the vacated post locally.</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Covered for most often</div>', unsafe_allow_html=True)
    ra = o["repeat_absentees"][:6]
    st.markdown(
        mini_table(
            ["Absent person", "Times", "OT hrs"],
            [["unnamed / relief no-show" if r["absentee"] == "unnamed_relief"
              else r["absentee"], r["times"], f'{r["overtime_hours"]:.0f}'] for r in ra],
        ),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="eyebrow">Notes that contradict the booking</div>',
                unsafe_allow_html=True)
    st.markdown(
        discuss(
            "shifts are booked as client-requested overtime, but the supervisor's "
            "note says it was really a no-show or an unfilled post.",
            [
                "Billing risk — the client may be invoiced for what was an "
                "internal staffing failure.",
                "Accountability risk — the real cause is hidden from whoever "
                "manages that absentee.",
                '<span class="fix">Do:</span> pull these shifts and audit them '
                "against the invoices before month-end.",
            ],
            bignum=str(o["notes_that_lie"]),
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="foot">Absentee names are canonicalised from free-text supervisor '
        'notes (surname match against the staff list).</div>',
        unsafe_allow_html=True,
    )
