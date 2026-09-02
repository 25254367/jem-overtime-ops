"""Worked hours, weekly totals, identity consolidation, overtime attribution.

The hours rule reproduces the client's `weekly_summary.total_hours` exactly
(verified 2,122/2,122 rows). See ASSUMPTIONS.md §3:

    total_hours = sum(clock_out - clock_in) per employee-week
      - blank clock_out          -> shift contributes 0 hours
      - clock_out <= clock_in     -> add 24h (shift crossed midnight)
      - no break deduction, no rounding

Breach: overtime_hours > 10.0  <=>  total_hours > 55.0 (strict).
(The client's history uses > 10.0: min overtime among breached rows is 10.25,
max among non-breached is exactly 10.0. In this dataset every hour lands on a
0.25h grid so > 55.0 and >= 55.25 are identical, but > 55.0 is the actual rule
and stays correct if a future export has, say, 55.1h.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .load import Export

ORDINARY_CAP = 45.0        # BCEA s9 ordinary-hours ceiling (flat for everyone here)
OVERTIME_CAP = 10.0        # BCEA s10 weekly overtime ceiling
BREACH_TOTAL_HOURS = ORDINARY_CAP + OVERTIME_CAP  # 55.0; breach iff total_hours > this
_EPS = 1e-9               # float-safety on the strict inequality


def is_breach(total_hours):
    """Breach test: strictly more than 45 ordinary + 10 overtime hours."""
    return total_hours > BREACH_TOTAL_HOURS + _EPS


def _parse_hhmm(series: pd.Series) -> pd.Series:
    """'HH:MM' -> minutes past midnight; '' / bad -> NaN."""
    s = series.fillna("").str.strip()
    parts = s.str.split(":", n=1, expand=True)
    with pd.option_context("mode.chained_assignment", None):
        h = pd.to_numeric(parts[0], errors="coerce")
        m = pd.to_numeric(parts[1], errors="coerce") if parts.shape[1] > 1 else np.nan
    return h * 60 + m


def shift_frame(export: Export) -> pd.DataFrame:
    """One row per shift with parsed date, duration, week_start, and flags.

    Columns added: date, clock_in_min, clock_out_min, is_open (no clock-out),
    crossed_midnight, duration_h, dow (0=Mon), week_start (date), start_dt.
    """
    s = export.shifts.copy()
    s["date"] = pd.to_datetime(s["shift_date"], errors="coerce")
    s["clock_in_min"] = _parse_hhmm(s["clock_in_time"])
    s["clock_out_min"] = _parse_hhmm(s["clock_out_time"])
    s["is_open"] = s["clock_out_time"].fillna("").str.strip().eq("")

    raw = s["clock_out_min"] - s["clock_in_min"]
    s["crossed_midnight"] = raw.le(0) & s["clock_out_min"].notna()
    adj = np.where(s["crossed_midnight"], raw + 24 * 60, raw)
    # open shift -> 0h (client rule); otherwise minutes -> hours
    s["duration_h"] = np.where(s["is_open"], 0.0, adj / 60.0)
    s["duration_h"] = s["duration_h"].fillna(0.0)

    s["dow"] = s["date"].dt.weekday
    s["week_start"] = (s["date"] - pd.to_timedelta(s["dow"], unit="D")).dt.date
    s["start_dt"] = s["date"] + pd.to_timedelta(s["clock_in_min"].fillna(0), unit="m")
    return s


# --------------------------------------------------------------------------
# identity consolidation
# --------------------------------------------------------------------------
def identity_map(export: Export) -> pd.DataFrame:
    """Map each employee_id to a person_id.

    A 'person' is a natural human. Normally person_id == employee_id, but the
    data contains records that share an id_number (and bank account and tax
    number) across two employee_ids at different sites -- one person, two
    payroll records. BCEA overtime is per person per employer, so we group
    these before computing breach. See docs/data_checks.md §3c.

    Match on any of id_number / tax_number / account_number agreeing, to stay
    robust to a single mistyped field in a future export.
    """
    emp = export.employees[["employee_id", "id_number"]].copy()
    pay = export.payroll_details[["employee_id", "tax_number", "account_number"]]
    m = emp.merge(pay, on="employee_id", how="left")

    # union-find over employee_ids linked by a shared identifier
    parent: dict[str, str] = {e: e for e in m["employee_id"]}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        parent[find(a)] = find(b)

    for key in ("id_number", "tax_number", "account_number"):
        if key not in m:
            continue
        vals = m[key].fillna("").str.strip()
        for _, grp in m[vals.ne("")].groupby(vals[vals.ne("")]):
            ids = grp["employee_id"].tolist()
            for other in ids[1:]:
                union(ids[0], other)

    out = pd.DataFrame({"employee_id": list(parent)})
    out["person_id"] = out["employee_id"].map(find)
    # give each person a stable label: the lowest employee_id in the group
    canon = out.groupby("person_id")["employee_id"].min().rename("person_label")
    out = out.merge(canon, on="person_id", how="left")
    out["person_id"] = out["person_label"]
    return out.drop(columns="person_label")


# --------------------------------------------------------------------------
# weekly totals
# --------------------------------------------------------------------------
def weekly_hours(shifts: pd.DataFrame, by: str = "employee_id") -> pd.DataFrame:
    """Weekly totals per `by` (employee_id or person_id).

    Returns: <by>, week_start, total_hours, overtime_hours, breached,
             n_shifts, n_open_shifts.
    """
    g = (
        shifts.groupby([by, "week_start"])
        .agg(
            total_hours=("duration_h", "sum"),
            n_shifts=("shift_id", "size"),
            n_open_shifts=("is_open", "sum"),
        )
        .reset_index()
    )
    g["overtime_hours"] = (g["total_hours"] - ORDINARY_CAP).clip(lower=0)
    g["breached"] = is_breach(g["total_hours"]).astype(int)
    return g


def add_person_id(shifts: pd.DataFrame, export: Export) -> pd.DataFrame:
    """Attach person_id to a shift frame."""
    return shifts.merge(identity_map(export), on="employee_id", how="left")


def latest_cutoff_dow(shifts: pd.DataFrame, week_start) -> int:
    """The last weekday (0=Mon) that has a shift in `week_start`'s week.

    This is how much of the week the export actually covers -- 2 = data runs
    through Wednesday, 4 = through Friday, 6 = the week is complete. The
    prediction observes days <= this and projects the rest.
    """
    wk = shifts[shifts["week_start"] == week_start]
    if wk.empty:
        return 2  # nothing to go on; assume a Wednesday-style cut
    return int(wk["dow"].max())


# --------------------------------------------------------------------------
# chronological overtime attribution (docs/CLASSIFICATION.md §4.1)
# --------------------------------------------------------------------------
def overtime_by_shift(shifts: pd.DataFrame, by: str = "person_id") -> pd.DataFrame:
    """Locate each overtime hour in the shift it was worked in.

    Order a person's shifts within the week by clock-in; accumulate; once the
    running total passes 45h, the remainder of that shift and every later
    shift is overtime. Returns one row per shift with `overtime_h` (0 for
    shifts entirely within ordinary time).
    """
    s = shifts.sort_values([by, "week_start", "start_dt"]).copy()
    cum = s.groupby([by, "week_start"])["duration_h"].cumsum()
    prior = cum - s["duration_h"]                       # hours before this shift
    ordinary_room = (ORDINARY_CAP - prior).clip(lower=0)
    s["overtime_h"] = (s["duration_h"] - ordinary_room).clip(lower=0)
    return s


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    sf = add_person_id(shift_frame(exp), exp)
    wk = weekly_hours(sf, by="employee_id")
    print(f"{len(wk)} employee-weeks | breaches: {int(wk['breached'].sum())}")
    latest = max(sf["week_start"])
    print(f"latest week {latest}: data through {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][latest_cutoff_dow(sf, latest)]}")
    idm = identity_map(exp)
    multi = idm.groupby("person_id").filter(lambda g: len(g) > 1)
    print(f"{multi['person_id'].nunique()} people hold >1 employee_id:")
    for pid, grp in multi.groupby("person_id"):
        print(f"  {pid}: {sorted(grp['employee_id'])}")
