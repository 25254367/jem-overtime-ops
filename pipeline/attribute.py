"""Attribute overtime hours to a cause via the supervisors' notes.

Method (docs/CLASSIFICATION.md §4.1 -- chronological / marginal):
  1. Order each person's shifts in the week by clock-in.
  2. Accumulate hours. Once the running total passes 45, every hour after that
     is overtime -- and each overtime hour belongs to the shift it was worked
     in (the crossing shift is split: ordinary up to 45, overtime beyond).
  3. That shift's note -> overtime_driver. Overtime on a note-less shift is
     `undetermined`.

The honest limits (measured, docs/data_checks.md §... / docs/CLASSIFICATION.md §4.2):
  - note coverage on overtime-bearing shifts is only ~26%, so only ~1/5 of
    overtime hours are attributable;
  - operational-failure overtime is further under-counted because open shifts
    are logged as 0h and the shift length caps at 13.5h.
"""
from __future__ import annotations

import pandas as pd

from .classify import classify_export
from .hours import (
    ORDINARY_CAP,
    add_person_id,
    identity_map,
    overtime_by_shift,
    shift_frame,
)
from .load import Export


def overtime_attribution(export: Export) -> pd.DataFrame:
    """One row per overtime-bearing shift, with the hours of overtime it holds
    and the cause from its note (if any).

    Columns: shift_id, person_id, employee_id, site_id, role, week_start,
             overtime_h, has_note, category, overtime_driver, absentee.
    """
    shifts = add_person_id(shift_frame(export), export)
    obs = overtime_by_shift(shifts, by="person_id")
    ot = obs[obs["overtime_h"] > 1e-9].copy()

    notes = classify_export(export).set_index("shift_id")
    ot["has_note"] = ot["shift_id"].isin(notes.index)
    ot["category"] = ot["shift_id"].map(notes["category"]).fillna("no_note")
    ot["overtime_driver"] = (
        ot["shift_id"].map(notes["overtime_driver"]).fillna("undetermined")
    )
    # routine / blank / unclassified notes tell us nothing about the cause
    ot.loc[ot["overtime_driver"] == "none", "overtime_driver"] = "undetermined"
    ot["absentee"] = ot["shift_id"].map(notes["absentee"]).fillna("")

    role = export.employees.set_index("employee_id")["role"]
    ot["role"] = ot["employee_id"].map(role)
    return ot[[
        "shift_id", "person_id", "employee_id", "site_id", "role",
        "week_start", "overtime_h", "has_note", "category",
        "overtime_driver", "absentee",
    ]]


def split_summary(export: Export) -> dict:
    """The headline asked-for vs operational-failure numbers."""
    ot = overtime_attribution(export)
    total = ot["overtime_h"].sum()
    by = ot.groupby("overtime_driver")["overtime_h"].sum()
    asked = by.get("asked_for", 0.0)
    opfail = by.get("operational_failure", 0.0)
    attributable = asked + opfail

    # loose, week-level view: fraction of breach-weeks with >=1 op-failure note
    shifts = add_person_id(shift_frame(export), export)
    wk = shifts.groupby(["person_id", "week_start"])["duration_h"].sum()
    breach_weeks = wk[wk > ORDINARY_CAP + 10.0].index
    notes = classify_export(export).set_index("shift_id")["overtime_driver"]
    sw = shifts.assign(
        drv=shifts["shift_id"].map(notes).fillna("undetermined")
    )
    opfail_weeks = set(
        map(tuple, sw[sw["drv"] == "operational_failure"][["person_id", "week_start"]].values)
    )
    loose = (
        sum(1 for k in breach_weeks if tuple(k) in opfail_weeks) / len(breach_weeks)
        if len(breach_weeks) else 0.0
    )

    return dict(
        total_overtime_hours=round(total, 1),
        attributable_hours=round(attributable, 1),
        attributable_share=round(attributable / total, 3) if total else 0.0,
        asked_for_hours=round(asked, 1),
        operational_failure_hours=round(opfail, 1),
        opfail_share_of_attributable=(
            round(opfail / attributable, 3) if attributable else 0.0
        ),
        n_breach_weeks=len(breach_weeks),
        breach_weeks_with_opfail_note=round(loose, 3),
    )


def concentration(export: Export) -> dict[str, pd.DataFrame]:
    """Where the attributable *operational-failure* overtime lands."""
    ot = overtime_attribution(export)
    opf = ot[ot["overtime_driver"] == "operational_failure"]

    def _agg(col):
        g = (
            opf.groupby(col)["overtime_h"]
            .agg(opfail_hours="sum", n_shifts="size")
            .sort_values("opfail_hours", ascending=False)
        )
        return g.round(1)

    site = _agg("site_id")
    site["site_name"] = site.index.map(
        export.sites.set_index("site_id")["site_name"]
    )
    absentees = (
        opf[opf["absentee"].str.len() > 0]
        .groupby("absentee")["overtime_h"]
        .agg(opfail_hours="sum", n_shifts="size")
        .sort_values("opfail_hours", ascending=False)
        .round(1)
    )
    return dict(
        by_site=site,
        by_role=_agg("role"),
        by_week=_agg("week_start"),
        by_absentee=absentees,
        by_category=_agg("category"),
    )


def phantom_absences(export: Export) -> dict:
    """The split-identity people, viewed as an absence problem.

    Each of them is on two sites' rosters as a separate employee, and neither
    roster knows. On the days the person is physically at one site, the other
    site logs an unplanned no-show and pays someone to cover the post. The same
    double booking also books hours at both sites at once.

    Returns totals + per-person rows + the cover-shift list (for ops review).
    Only counts cover shifts that (a) name the split person's surname and
    (b) happen at one of that person's own two sites -- so "covering Sibiya"
    at a third site, where it cannot be this person, is excluded.
    """
    idm = identity_map(export)
    ghost_pids = sorted(
        idm.groupby("person_id").filter(lambda d: len(d) > 1)["person_id"].unique()
    )

    emp = export.employees.merge(idm, on="employee_id")
    name_by_pid = emp.groupby("person_id")["full_name"].first().to_dict()
    ids_by_pid = emp.groupby("person_id")["employee_id"].apply(list).to_dict()
    sites_by_pid = {
        p: sorted(set(emp.loc[emp["person_id"] == p, "primary_site_id"]))
        for p in ghost_pids
    }

    s = add_person_id(shift_frame(export), export)
    s = s.assign(
        _date=s["start_dt"].dt.date,
        _end=s["start_dt"] + pd.to_timedelta(s["duration_h"], unit="h"),
    )
    cls = classify_export(export).set_index("shift_id")
    s["absentee"] = s["shift_id"].map(cls["absentee"]).fillna("")
    s["absence_reason"] = s["shift_id"].map(cls["absence_reason"]).fillna("")
    notes = export.shift_notes.set_index("shift_id")["note"].to_dict()

    pds = s.groupby(["person_id", "_date"])["site_id"].agg(set).to_dict()
    n_weeks = int(s["week_start"].nunique())

    def _overlap_hours(pid: str) -> float:
        d = list(
            s[s["person_id"] == pid][["start_dt", "_end", "site_id"]]
            .itertuples(index=False, name=None)
        )
        tot = 0.0
        for i in range(len(d)):
            for j in range(i + 1, len(d)):
                if d[i][2] == d[j][2]:
                    continue  # same site -- not a cross-site clash
                lo, hi = max(d[i][0], d[j][0]), min(d[i][1], d[j][1])
                if hi > lo:
                    tot += (hi - lo).total_seconds() / 3600.0
        return tot

    ac = s[(s["absentee"].str.len() > 0) & (s["absentee"] != "unnamed_relief")]

    per_person, shift_rows = [], []
    tot_cover = tot_conflict = 0
    tot_double = 0.0
    for p in ghost_pids:
        surname = name_by_pid[p].split()[-1].casefold()
        a, b = sites_by_pid[p]
        sub = ac[
            (ac["absentee"].str.split().str[-1].str.casefold() == surname)
            & (ac["site_id"].isin([a, b]))
        ]
        conflicts = 0
        for _, r in sub.iterrows():
            worked = pds.get((p, r["_date"]), set())
            elsewhere = ({a, b} - {r["site_id"]}) & worked
            cross = bool(elsewhere) and r["site_id"] not in worked
            conflicts += int(cross)
            shift_rows.append(dict(
                covered_person=name_by_pid[p],
                date=str(r["_date"]),
                cover_site=r["site_id"],
                reason=r["absence_reason"] or "unknown",
                cross_site=bool(cross),
                note=notes.get(r["shift_id"], ""),
            ))
        dbl = _overlap_hours(p)
        tot_cover += len(sub)
        tot_conflict += conflicts
        tot_double += dbl
        per_person.append(dict(
            person_id=p,
            name=name_by_pid[p],
            employee_ids=ids_by_pid[p],
            sites=[a, b],
            cover_shifts=int(len(sub)),
            cross_site_conflicts=int(conflicts),
            double_paid_hours=round(dbl, 1),
        ))

    shift_rows.sort(key=lambda x: x["date"], reverse=True)
    return dict(
        n_people=len(ghost_pids),
        window_weeks=n_weeks,
        cover_shifts=int(tot_cover),
        cross_site_conflicts=int(tot_conflict),
        double_paid_hours=round(tot_double, 0),
        by_person=per_person,
        shifts=shift_rows,
        note=(
            f"{len(ghost_pids)} people are on two sites' rosters as separate "
            f"employees, and neither site knows. On the days they are at one "
            f"site, the other logs a no-show and pays someone to cover it — "
            f"{tot_cover} times in {n_weeks} weeks, {tot_conflict} of them "
            f"provably while the person was clocked in at their other site. The "
            f"same double booking also put ~{tot_double:.0f} hours on the books "
            f"at two sites at once — hours that cannot be trusted for payroll. "
            f"Fix: make each a single-site employee, drop them from the other "
            f"site, and spread that post across the under-used same-role staff "
            f"already there."
        ),
    )


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")

    s = split_summary(exp)
    print("=== overtime split (9 full weeks + partial) ===")
    for k, v in s.items():
        print(f"  {k:32} {v}")
    print(f"\n  STRICT : {s['attributable_share']:.0%} of overtime attributable; "
          f"of that, {s['opfail_share_of_attributable']:.0%} operational failure, "
          f"{1 - s['opfail_share_of_attributable']:.0%} asked-for")
    print(f"  LOOSE  : {s['breach_weeks_with_opfail_note']:.0%} of "
          f"{s['n_breach_weeks']} breach-weeks have an operational-failure note")

    c = concentration(exp)
    print("\n=== operational-failure overtime by site ===")
    print(c["by_site"].to_string())
    print("\n=== by category ===")
    print(c["by_category"].to_string())
    print("\n=== top absentees driving cover overtime ===")
    print(c["by_absentee"].head(12).to_string())
