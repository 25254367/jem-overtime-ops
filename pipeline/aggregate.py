"""Build dashboard_data.json — everything the dashboard renders, computed once.

The dashboard is a thin view over this; it does no modelling. One pipeline run
produces predictions.csv, note_classifications.csv, and this file.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .actions import double_booking_alert, recommend
from .attribute import (
    concentration,
    overtime_attribution,
    phantom_absences,
    split_summary,
)
from .classify import classify_export
from .features import person_week_hours
from .hours import (
    BREACH_TOTAL_HOURS,
    ORDINARY_CAP,
    add_person_id,
    identity_map,
    latest_cutoff_dow,
    shift_frame,
)
from .load import Export
from .predict import THRESHOLD_BY_CUTOFF, project

DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CONFIDENCE_BY_CUTOFF = {
    0: "very low — only Monday's data", 1: "low", 2: "moderate",
    3: "moderate", 4: "good", 5: "high", 6: "the week is complete",
}


def _rate(export: Export) -> pd.Series:
    return pd.to_numeric(
        export.payroll_details.set_index("employee_id")["hourly_rate"]
    )


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return round(float(o), 3)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (dt.date, pd.Timestamp)):
        return str(o)
    raise TypeError(type(o))


def build(export: Export, target_week=None, history_weeks=None) -> dict:
    pw = person_week_hours(export)
    weeks = sorted(pw["week_start"].unique())
    if target_week is None:
        target_week = weeks[-1]
    if history_weeks is None:
        history_weeks = [w for w in weeks if w < target_week]

    cutoff = latest_cutoff_dow(shift_frame(export), target_week)
    proj = project(export, target_week, history_weeks, cutoff_dow=cutoff)
    threshold = THRESHOLD_BY_CUTOFF[cutoff]

    idm = identity_map(export)
    ids_by_person = idm.groupby("person_id")["employee_id"].apply(list).to_dict()
    site_name = export.sites.set_index("site_id")["site_name"].to_dict()
    rate = _rate(export)

    # per-person meta (canonical record)
    e = export.employees.merge(idm, on="employee_id")
    canon = e[e["employee_id"] == e["person_id"]].set_index("person_id")

    # observed hours this week + shift count
    s = add_person_id(shift_frame(export), export)
    cur = s[s["week_start"] == target_week]
    obs_h = cur[cur["dow"] <= cutoff].groupby("person_id")["duration_h"].sum()
    obs_n = cur[cur["dow"] <= cutoff].groupby("person_id").size()
    open_cur = cur[cur["is_open"]].groupby("person_id").size()
    # historical weekly hours per person, for the sparkline
    hist_wk = (
        pw[pw["week_start"].isin(set(history_weeks))]
        .groupby(["person_id", "week_start"])["total"].sum()
    )
    typ_shifts = (
        s[s["week_start"].isin(set(history_weeks))]
        .groupby(["person_id", "week_start"]).size().groupby("person_id").mean()
    )
    # which weeks each person had an un-clocked-out shift (hours understated)
    open_wk = (
        s[s["is_open"]].groupby(["person_id", "week_start"]).size()
    )
    open_wk_by_person = {
        pid: {str(w) for (p, w) in open_wk.index if p == pid}
        for pid in {p for (p, _) in open_wk.index}
    }
    open_all_time = s.groupby("person_id")["is_open"].sum()

    recs = recommend(export, proj, target_week, history_weeks, cutoff_dow=cutoff)
    rec_by_person = recs.set_index("person_id").to_dict("index") if len(recs) else {}

    # split-identity people, framed as the phantom-absence problem they cause
    phantom = phantom_absences(export)
    phantom_by_person = {r["person_id"]: r for r in phantom["by_person"]}

    def _recommendation(pid: str, projected: float, risk: float) -> dict:
        """{headline, steps} for the dashboard — concise, bulleted."""
        rc = rec_by_person.get(pid)
        if rc:
            head, steps = rc["headline"], list(rc["steps"])
        else:  # watch-tier person, not flagged -> no action, just watch
            head = (f"Projects ~{projected:.0f}h — {int(round(risk * 100))}% "
                    f"breach chance, central estimate under 55h.")
            steps = ["Watch. Recheck when more data lands."]
        pp = phantom_by_person.get(pid)
        if pp:
            steps.append(
                f"{pp['cover_shifts']} phantom no-shows trace to this split — "
                f"put them on one site only, backfill the other locally."
            )
        return dict(headline=head, steps=steps)

    notes = classify_export(export).set_index("shift_id")
    # dominant recent overtime driver per person (last 3 weeks with overtime)
    ot = overtime_attribution(export)
    recent_weeks = set(sorted(weeks)[-4:])
    why_by_person = (
        ot[ot["week_start"].isin(recent_weeks) & (ot["overtime_driver"] != "undetermined")]
        .groupby("person_id")["category"].agg(lambda x: x.value_counts().index[0])
        .to_dict()
    )

    # ---- risk list ----
    risk_rows = []
    people_detail = {}
    for _, r in proj.iterrows():
        pid = r["person_id"]
        if pid not in canon.index:
            continue
        c = canon.loc[pid]
        projected = float(r["projected_total"])
        risk = float(r["risk_score"])
        tier = ("breach_likely" if risk >= 0.5 else
                "elevated" if risk >= threshold else
                "watch" if risk >= 0.10 else "ok")
        if tier == "ok":
            continue
        rc = rec_by_person.get(pid, {})
        obs = float(obs_h.get(pid, 0.0))
        reco = _recommendation(pid, projected, risk)
        row = dict(
            person_id=pid,
            employee_ids=ids_by_person.get(pid, [pid]),
            name=c["full_name"], site=c["primary_site_id"],
            site_name=site_name.get(c["primary_site_id"], c["primary_site_id"]),
            role=c["role"],
            hours_so_far=round(obs, 1),
            projected=round(projected, 1),
            risk_score=round(risk, 3),
            tier=tier,
            why=why_by_person.get(pid, "—"),
            open_shifts_this_week=int(open_cur.get(pid, 0)),
            hours_understated=bool(open_cur.get(pid, 0)),
            action=rc.get("action", "monitor"),
            action_headline=reco["headline"],
            action_steps=reco["steps"],
        )
        risk_rows.append(row)

        # ---- person detail ----
        rem = max(0.0, projected - obs)
        sentence = (
            f"{obs:.0f}h logged through {DOW[cutoff]}. Projection: ~{rem:.0f}h "
            f"more → ~{projected:.0f}h total"
            + (f" → {projected - ORDINARY_CAP:.0f}h overtime." if projected > ORDINARY_CAP
               else " — no overtime.")
            + f" {int(round(risk * 100))}% chance of a breach (>55h)."
        )
        nshift = int(obs_n.get(pid, 0))
        typ = float(typ_shifts.get(pid, np.nan))
        shift_line = (
            f"{nshift} shifts so far; normally ~{typ:.0f}/week."
            if not np.isnan(typ) else f"{nshift} shifts so far."
        )
        p_open_weeks = open_wk_by_person.get(pid, set())
        n_open_all = int(open_all_time.get(pid, 0))
        understated_note = ""
        if open_cur.get(pid, 0):
            understated_note = (
                f"{int(open_cur.get(pid, 0))} shift this week has no clock-out "
                f"(logged as 0h) — real hours are likely higher and the "
                f"projection understates the risk."
            )
        elif n_open_all >= 3:
            understated_note = (
                f"Had {n_open_all} un-clocked-out shifts in the data (all on "
                f"cover shifts) — this person's hours are chronically under-"
                f"recorded, so the risk here is a floor."
            )
        people_detail[pid] = dict(
            name=c["full_name"], site=c["primary_site_id"], role=c["role"],
            projection_sentence=sentence,
            shift_line=shift_line,
            open_shifts_this_week=int(open_cur.get(pid, 0)),
            open_shifts_all_time=n_open_all,
            hours_understated_note=understated_note,
            history=[
                {"week": str(w), "hours": round(float(h), 1),
                 "breached": bool(h > BREACH_TOTAL_HOURS),
                 "open_shift": str(w) in p_open_weeks}
                for (p, w), h in hist_wk.items() if p == pid
            ],
            rec_headline=reco["headline"],
            rec_steps=reco["steps"],
        )

    risk_rows.sort(key=lambda x: -x["risk_score"])

    # ---- headline ----
    n_breach = sum(r["tier"] == "breach_likely" for r in risk_rows)
    n_elevated = sum(r["tier"] == "elevated" for r in risk_rows)
    n_watch = sum(r["tier"] == "watch" for r in risk_rows)
    proj_ot_cost = 0.0
    for r in risk_rows:
        ot_h = max(0.0, r["projected"] - ORDINARY_CAP)
        eid = r["employee_ids"][0]
        proj_ot_cost += ot_h * float(rate.get(eid, 45.0)) * 1.5

    # ---- site triage ----
    site_rows = []
    for sid, sname in site_name.items():
        here = [r for r in risk_rows if r["site"] == sid]
        fixable = sum(
            max(0.0, r["projected"] - ORDINARY_CAP)
            * float(rate.get(r["employee_ids"][0], 45.0)) * 1.5
            for r in here if r["why"] != "client_requested"
        )
        site_rows.append(dict(
            site_id=sid, site_name=sname,
            n_breach_likely=sum(r["tier"] == "breach_likely" for r in here),
            n_watch=sum(r["tier"] == "watch" for r in here),
            fixable_ot_cost_rand=round(fixable, 0),
            people=[r["name"] for r in here],
        ))
    site_rows.sort(key=lambda x: (-x["n_breach_likely"], -x["fixable_ot_cost_rand"]))

    # ---- alerts ----
    dbl = double_booking_alert(export)
    dbl_rows = []
    for _, d in dbl.iterrows():
        pid = d["person_id"]
        pr = proj[proj["person_id"] == pid]
        pp = phantom_by_person.get(pid, {})
        dbl_rows.append(dict(
            name=d["name"], employee_ids=d["employee_ids"].split(" & "),
            sites=sorted(set(
                s[s["employee_id"].isin(d["employee_ids"].split(" & "))]["site_id"]
            )),
            combined_projected=round(float(pr["projected_total"].iloc[0]), 1)
            if len(pr) else None,
            phantom_no_shows=pp.get("cover_shifts", 0),
            cross_site_conflicts=pp.get("cross_site_conflicts", 0),
            double_paid_hours=pp.get("double_paid_hours", 0.0),
        ))

    open_rows = []
    for _, sh in cur[cur["is_open"]].iterrows():
        pid = sh["person_id"]
        c = canon.loc[pid] if pid in canon.index else None
        open_rows.append(dict(
            shift_id=sh["shift_id"],
            name=c["full_name"] if c is not None else pid,
            site=sh["site_id"], date=str(sh["date"].date()),
            note=notes["note"].get(sh["shift_id"], ""),
        ))

    # ---- why split ----
    split = split_summary(export)
    conc = concentration(export)

    # ---- under-recording: the operational-failure number is a floor ----
    n_open = int(s["is_open"].sum())
    dur = s.loc[~s["is_open"], "duration_h"]
    cap = float(dur.max())
    n_at_cap = int((dur >= cap - 1e-6).sum())
    full_wk = pw[pw["week_start"] < target_week]
    recorded_rate = float((full_wk["total"] > BREACH_TOTAL_HOURS).mean())
    # counterfactual: impute one median shift on each open-shift employee-week
    # (person_week_hours already carries n_open per person-week)
    med_shift = float(dur.median())
    adj_total = full_wk["total"] + full_wk["n_open"] * med_shift
    est_rate = float((adj_total > BREACH_TOTAL_HOURS).mean())
    under_recording = dict(
        open_shift_count=n_open,
        open_shift_share=round(n_open / len(s), 3),
        shift_cap_hours=cap,
        shifts_at_cap=n_at_cap,
        recorded_breach_rate=round(recorded_rate, 3),
        estimated_true_breach_rate=round(est_rate, 3),
        note=(
            f"{n_open} shifts ({n_open / len(s):.1%}) were clocked in but never "
            f"clocked out and are logged as 0h — most carry cover notes. Shift "
            f"length caps at {cap:g}h ({n_at_cap} shifts sit exactly there), so "
            f"a genuine 20-hour double is recorded as {cap:g}h or 0h. A no-show "
            f"creates no record at all. Net: a no-show removes recorded hours "
            f"for that site-day even though the same coverage was delivered — "
            f"so operational-failure overtime, and the breach risk of the "
            f"people who cover, is understated. Recorded breach rate "
            f"{recorded_rate:.1%}; imputing one shift per open-shift week puts "
            f"it at ~{est_rate:.1%}."
        ),
    )

    split_identity = {
        k: phantom[k] for k in (
            "n_people", "window_weeks", "cover_shifts", "cross_site_conflicts",
            "double_paid_hours", "by_person", "note",
        )
    }

    # ---- ops review ----
    ot_all = overtime_attribution(export)
    opf = ot_all[ot_all["overtime_driver"] == "operational_failure"]
    repeat_abs = (
        opf[opf["absentee"].str.len() > 0]
        .groupby("absentee")
        .agg(overtime_hours=("overtime_h", "sum"), times=("shift_id", "size"))
        .sort_values("overtime_hours", ascending=False).head(10)
        .reset_index().to_dict("records")
    )
    lies = int(classify_export(export)["surface_vs_driver_conflict"].sum())
    open_month = s[s["is_open"]].sort_values("date", ascending=False).head(30)
    open_month_rows = [
        dict(shift_id=x["shift_id"], site=x["site_id"], date=str(x["date"].date()),
             name=canon.loc[x["person_id"], "full_name"]
             if x["person_id"] in canon.index else x["person_id"],
             note=notes["note"].get(x["shift_id"], ""))
        for _, x in open_month.iterrows()
    ]

    return dict(
        meta=dict(
            generated_at=dt.datetime.now().isoformat(timespec="seconds"),
            target_week=str(target_week),
            cutoff_dow=cutoff, cutoff_label=DOW[cutoff],
            data_through=f"end of {DOW[cutoff]}",
            confidence=CONFIDENCE_BY_CUTOFF[cutoff],
            n_employees=len(export.employees), n_sites=len(export.sites),
            threshold=threshold,
        ),
        headline=dict(
            n_breach_likely=n_breach, n_elevated=n_elevated, n_watch=n_watch,
            n_sites=len(export.sites),
            projected_ot_cost_rand=round(proj_ot_cost, 0),
        ),
        risk_list=risk_rows,
        people=people_detail,
        sites=site_rows,
        alerts=dict(
            double_booking=dbl_rows,
            open_shifts_this_week=open_rows,
            split_identity=split_identity,
        ),
        why_split=dict(
            **split,
            by_driver=conc["by_category"].reset_index().to_dict("records"),
            by_site=conc["by_site"].reset_index().to_dict("records"),
            under_recording=under_recording,
            split_identity=split_identity,
        ),
        ops_review=dict(
            repeat_absentees=repeat_abs,
            notes_that_lie=lies,
            open_shifts_recent=open_month_rows,
            open_shifts_by_site=(
                s[s["is_open"]].groupby("site_id").size().sort_values(
                    ascending=False).to_dict()
            ),
            under_recording_note=under_recording["note"],
            phantom_absence_shifts=phantom["shifts"],
        ),
    )


def write(export: Export, path="outputs/dashboard_data.json", **kw) -> dict:
    data = build(export, **kw)
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, default=_jsonable))
    return data


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    d = write(exp)
    m, h = d["meta"], d["headline"]
    print(f"target week {m['target_week']} | data through {m['cutoff_label']} "
          f"| confidence {m['confidence']}")
    print(f"{h['n_breach_likely']} breach-likely, {h['n_watch']} to watch, "
          f"~R{h['projected_ot_cost_rand']:.0f} projected OT cost")
    print("\ntop of the risk list:")
    for r in d["risk_list"][:6]:
        print(f"  {r['name']:20} {r['site']} {r['tier']:14} risk {r['risk_score']} "
              f"→ {r['action']}")
    print(f"\nsplit: {d['why_split']['attributable_share']:.0%} attributable, "
          f"{d['why_split']['opfail_share_of_attributable']:.0%} operational failure")
    print("wrote outputs/dashboard_data.json")
