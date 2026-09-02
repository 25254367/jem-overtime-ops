"""What to do about it (README requirement 2).

For each person the model flags, produce ONE concrete recommendation the
contract manager could act on without opening a spreadsheet, in priority
order:

  1. same person on two payroll records   -> consolidate the records
  2. open (un-clocked-out) shift this week -> chase the clock-out
  3. otherwise                             -> a specific shift-swap:
       move a named likely-remaining shift to a named role-matching colleague.
       Ranked: (a) receiver stays <= 45h (no cost), (b) receiver goes 45-55h
       (legal overtime, stops the breach, costs the OT premium), (c) a
       colleague at another site, (d) none -> authorise it, with the cost.
       Hard rule: a receiver is NEVER pushed past 55h -- that just moves the
       breach.

Each row carries a severity: "will breach" (point projection > 55h) vs
"at risk" (flagged by risk score, projection <= 55h). "Remaining shifts" are
inferred from the person's own recent weekday pattern -- there is no roster in
the data. Cost is the 0.5x overtime premium on the hours that change status.
"""
from __future__ import annotations

import pandas as pd

from .hours import (
    BREACH_TOTAL_HOURS,
    ORDINARY_CAP,
    add_person_id,
    identity_map,
    latest_cutoff_dow,
    shift_frame,
)
from .load import Export

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
OT_PREMIUM = 0.5       # an overtime hour costs 1.5x; a swap saves/adds the 0.5x
# BREACH_TOTAL_HOURS (55.0) is the hard ceiling for a receiver -- a swap that
# pushes them past it just moves the breach.


def _rate(export: Export) -> pd.Series:
    return pd.to_numeric(export.payroll_details.set_index("employee_id")["hourly_rate"])


def _weekday_profile(hist: pd.DataFrame) -> pd.DataFrame:
    """Per person_id x weekday: P(work) and mean hours when worked, from
    history."""
    nwk = hist.groupby("person_id")["week_start"].nunique()
    cnt = hist.groupby(["person_id", "dow"]).size()
    mdur = hist.groupby(["person_id", "dow"])["duration_h"].mean()
    prof = pd.concat([cnt.rename("n"), mdur.rename("mdur")], axis=1).reset_index()
    prof["p_work"] = prof.apply(lambda r: min(1.0, r["n"] / nwk.get(r["person_id"], 1)), axis=1)
    return prof


def expected_remaining_shifts(
    export: Export, target_week, history_weeks, cutoff_dow: int
) -> pd.DataFrame:
    """The shifts a person is likely still to work this week (dow > cutoff),
    from their own weekday pattern. One row per (person_id, dow) with the
    expected hours and how likely."""
    s = add_person_id(shift_frame(export), export)
    hist = s[s["week_start"].isin(set(history_weeks))]
    prof = _weekday_profile(hist)
    rem = prof[(prof["dow"] > cutoff_dow) & (prof["p_work"] >= 0.4)].copy()
    rem["expected_hours"] = rem["mdur"].fillna(hist["duration_h"].median())
    return rem[["person_id", "dow", "p_work", "expected_hours"]]


def _overlapping_shift_count(export: Export, employee_ids: list) -> int:
    """How many times this person's two records are clocked in at the same
    time (physically impossible -> the hours need verifying)."""
    s = shift_frame(export)
    s = s[s["employee_id"].isin(employee_ids) & ~s["is_open"]]
    if s["employee_id"].nunique() < 2:
        return 0
    a, b = [g for _, g in s.groupby("employee_id")][:2]
    n = 0
    for _, x in a.iterrows():
        clash = b[(b["start_dt"] < x["start_dt"] + pd.to_timedelta(x["duration_h"], "h"))
                  & (b["start_dt"] + pd.to_timedelta(b["duration_h"], "h") > x["start_dt"])]
        n += len(clash)
    return int(n)


def _site_role_pattern(export: Export) -> pd.DataFrame:
    idm = identity_map(export)
    e = export.employees.merge(idm, on="employee_id")
    canon = e[e["employee_id"] == e["person_id"]].copy()
    prov = export.sites.set_index("site_id")["province"]
    canon["province"] = canon["primary_site_id"].map(prov)
    return canon.set_index("person_id")[
        ["full_name", "primary_site_id", "province", "role", "shift_pattern"]
    ]


def recommend(
    export: Export,
    projections: pd.DataFrame,      # from predict.project(): person_id, observed, projected_total, will_breach, ...
    target_week,
    history_weeks,
    cutoff_dow: int | None = None,
) -> pd.DataFrame:
    """One recommendation row per flagged person.

    Columns: person_id, name, site, role, projected_total, severity,
             risk_score, action, headline, steps (list[str]), detail, rand_saving.

    `headline` is one short sentence (the why); `steps` are 1-3 short imperative
    bullets (the what). `detail` is the two joined, kept for text consumers.
    """
    if cutoff_dow is None:
        cutoff_dow = latest_cutoff_dow(shift_frame(export), target_week)

    idm = identity_map(export)
    grp = idm.groupby("person_id")["employee_id"].apply(list)
    meta = _site_role_pattern(export)
    rate = _rate(export)

    s = add_person_id(shift_frame(export), export)
    cur = s[s["week_start"] == target_week]
    open_now = cur[cur["is_open"]].groupby("person_id")
    exp_rem = expected_remaining_shifts(export, target_week, history_weeks, cutoff_dow)

    flagged = projections[projections["will_breach"] == 1].sort_values(
        "projected_total", ascending=False
    )
    used_receivers: set = set()   # don't recommend the same colleague twice
    rows = []
    for _, p in flagged.iterrows():
        pid = p["person_id"]
        m = meta.loc[pid] if pid in meta.index else None
        name = m["full_name"] if m is not None else pid
        site = m["primary_site_id"] if m is not None else "?"
        role = m["role"] if m is not None else "?"
        projected = float(p["projected_total"])
        certain = projected > BREACH_TOTAL_HOURS
        severity = "will breach" if certain else "at risk"
        risk_pct = int(round(float(p.get("risk_score", 0)) * 100))
        rec = dict(person_id=pid, name=name, site=site, role=role,
                   projected_total=round(projected, 1), severity=severity,
                   risk_score=round(float(p.get("risk_score", 0)), 3),
                   action="", headline="", steps=[], detail="", rand_saving=0.0)

        # 1. duplicate identity -- an admin fix (merge the records) AND, if the
        #    combined hours breach, a rostering fix (cut them at one site).
        ids = grp.get(pid, [pid])
        if len(ids) > 1:
            id_sites = sorted(set(
                add_person_id(shift_frame(export), export)
                .query("employee_id in @ids")["site_id"]
            ))
            overlap = _overlapping_shift_count(export, ids)
            cut = projected - BREACH_TOTAL_HOURS
            rec["action"] = "consolidate payroll records"
            rec["headline"] = (
                f"One person, two payroll records ({' + '.join(id_sites)}) — "
                f"the client sees two staff each under 45h."
            )
            steps = [f"Merge {' + '.join(ids)}."]
            if overlap:
                steps.append(
                    f"{overlap} shifts clock in at both sites at once — "
                    f"verify the real hours."
                )
            if certain and cut >= 1:
                steps.append(
                    f"Combined ~{projected:.0f}h. Cut the roster ~{cut:.0f}h "
                    f"at one site."
                )
            elif certain:
                steps.append(
                    f"Combined ~{projected:.0f}h — right at the cap. Hold hours flat."
                )
            else:
                steps.append(
                    f"Combined ~{projected:.0f}h — overtime, not yet a breach. "
                    f"Stop the cross-site rostering."
                )
            rec["steps"] = steps
            rows.append(rec)
            continue

        # 2. open shift this week
        if pid in open_now.groups:
            og = open_now.get_group(pid)
            days = ", ".join(sorted({DOW[d] for d in og["dow"]}))
            rec["action"] = "close the open shift(s)"
            rec["headline"] = (
                f"{len(og)} shift(s) this week ({days}) have no clock-out — "
                f"logged as 0h, so real hours are missing from the projection."
            )
            rec["steps"] = ["Verify the hours and close them before payroll."]
            rows.append(rec)
            continue

        # 3. at risk but not a projected breach -> monitor, don't act yet.
        if not certain:
            rec["action"] = "monitor"
            rec["headline"] = (
                f"Projects ~{projected:.0f}h — {risk_pct}% breach chance, "
                f"central estimate under 55h."
            )
            rec["steps"] = ["Watch. Recheck when Thu–Fri data lands."]
            rows.append(rec)
            continue

        # 4. projected breach -> a same-site, same-role shift-swap to a
        #    colleague who stays UNDER 45h (no new overtime). Nothing else:
        #    cross-site cover isn't realistic, and pushing a colleague into
        #    overtime just relocates the cost.
        overtime_h = projected - ORDINARY_CAP
        mine = exp_rem[exp_rem["person_id"] == pid].sort_values(
            "expected_hours", ascending=False
        )
        slot_h = float(mine.iloc[0]["expected_hours"]) if len(mine) else 10.0
        slot_day = DOW[int(mine.iloc[0]["dow"])] if len(mine) else "a remaining"
        pers_rate = float(rate.get(pid, 40.0))

        cand = projections[
            projections["person_id"].isin(meta[meta["role"] == role].index)
            & (projections["person_id"] != pid)
            & (projections["will_breach"] == 0)
            & ~projections["person_id"].isin(used_receivers)
        ].merge(
            meta[["full_name", "primary_site_id"]], left_on="person_id",
            right_index=True,
        )
        cand = cand[cand["primary_site_id"] == site]
        cand["after"] = cand["projected_total"] + slot_h
        clean = cand[cand["after"] <= ORDINARY_CAP].sort_values("projected_total")

        if len(clean):
            r = clean.iloc[0]
            rec["action"] = "shift-swap"
            rec["rand_saving"] = round(
                min(overtime_h, slot_h) * pers_rate * OT_PREMIUM, 0)
            rec["headline"] = (
                f"Projects ~{projected:.0f}h ({overtime_h:.0f}h overtime)."
            )
            step = (
                f"Move the ~{slot_h:.0f}h {slot_day} shift at {site} to "
                f"{r['full_name']} ({r['projected_total']:.0f}h → "
                f"{r['after']:.0f}h, still no overtime)."
            )
            rec["steps"] = [step] + (
                [f"Saves ~R{rec['rand_saving']:.0f}."] if rec["rand_saving"] else []
            )
            used_receivers.add(r["person_id"])
        else:
            cost = overtime_h * pers_rate * 1.5
            rec["action"] = "authorise OT / structural gap"
            rec["headline"] = (
                f"Projects ~{projected:.0f}h ({overtime_h:.0f}h overtime). "
                f"No {role} at {site} has slack, and cross-site cover isn't real."
            )
            rec["steps"] = [
                f"Authorise ~{overtime_h:.0f}h OT (~R{cost:.0f}), or treat "
                f"{site} as one {role} short."
            ]
        rows.append(rec)

    for rec in rows:
        rec["detail"] = " ".join([rec["headline"], *rec["steps"]]).strip()

    df = pd.DataFrame(rows)
    # portfolio note: how much of the flagged overtime is actually re-routable
    if len(df):
        structural = df["action"].str.startswith(("authorise", "no swap")).sum()
        df.attrs["summary"] = (
            f"{len(df)} people flagged. "
            f"{(df['action'] == 'consolidate payroll records').sum()} are "
            f"duplicate-identity (fix the records). "
            f"{(df['action'] == 'close the open shift(s)').sum()} have open "
            f"shifts to close. Of the rest, {structural} have no swap available "
            f"— the roster is running at capacity (workforce mean projection "
            f"~43h against a 45h cap)."
        )
    return df


def double_booking_alert(export: Export) -> pd.DataFrame:
    """The consolidated-identity people, for the dashboard's special-alerts
    panel — independent of whether they're flagged this week."""
    idm = identity_map(export)
    multi = idm.groupby("person_id").filter(lambda g: len(g) > 1)
    meta = _site_role_pattern(export)
    rows = []
    for pid, g in multi.groupby("person_id"):
        ids = sorted(g["employee_id"])
        name = meta.loc[pid, "full_name"] if pid in meta.index else pid
        rows.append(dict(person_id=pid, name=name, employee_ids=" & ".join(ids)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys

    from .features import person_week_hours
    from .load import load_export
    from .predict import project

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    target, history = weeks[-1], weeks[:-1]
    proj = project(exp, target, history)

    recs = recommend(exp, proj, target, history)
    print(recs.attrs.get("summary", ""), "\n")
    for _, r in recs.iterrows():
        print(f"  {r['name']} ({r['site']}/{r['role']}) — {r['severity']}, "
              f"projected {r['projected_total']}h  (risk {r['risk_score']})")
        print(f"    → {r['action'].upper()}: {r['detail']}\n")

    print("double-booking alert:")
    print(double_booking_alert(exp).to_string(index=False))
