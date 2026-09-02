"""The hours rule must reproduce the client's weekly_summary exactly.

If this ever fails on a real export, our whole overtime definition is wrong,
so it's the first test to run.
"""
import pandas as pd

from pipeline.load import load_export
from pipeline.hours import (
    BREACH_TOTAL_HOURS,
    identity_map,
    is_breach,
    latest_cutoff_dow,
    overtime_by_shift,
    shift_frame,
    weekly_hours,
)

DATA = "data"


def test_reconciles_with_weekly_summary():
    exp = load_export(DATA)
    assert exp.weekly_summary is not None, "sample export includes weekly_summary"

    ours = weekly_hours(shift_frame(exp), by="employee_id")
    theirs = exp.weekly_summary.copy()
    theirs["week_start"] = (
        pd.to_datetime(theirs["week_starting"]).dt.date
    )
    theirs["total_hours"] = pd.to_numeric(theirs["total_hours"])
    theirs["overtime_hours"] = pd.to_numeric(theirs["overtime_hours"])
    theirs["breached"] = pd.to_numeric(theirs["breached"])

    merged = theirs.merge(
        ours, on=["employee_id", "week_start"], suffixes=("_client", "_ours"),
        how="left", indicator=True,
    )
    # every client row must have a match
    assert (merged["_merge"] == "both").all(), (
        merged.loc[merged["_merge"] != "both", ["employee_id", "week_starting"]]
    )

    diff = (merged["total_hours_client"] - merged["total_hours_ours"]).abs()
    assert diff.max() < 1e-6, f"max total_hours diff {diff.max()} on {int((diff>1e-6).sum())} rows"

    ot_diff = (merged["overtime_hours_client"] - merged["overtime_hours_ours"]).abs()
    assert ot_diff.max() < 1e-6

    assert (merged["breached_client"] == merged["breached_ours"]).all()


def test_breach_rule_matches_history():
    exp = load_export(DATA)
    ws = exp.weekly_summary.copy()
    ws["total_hours"] = pd.to_numeric(ws["total_hours"])
    ws["breached"] = pd.to_numeric(ws["breached"])
    # the client's rule is overtime > 10.0  <=>  total_hours > 55.0 (strict)
    assert BREACH_TOTAL_HOURS == 55.0
    assert (is_breach(ws["total_hours"]).astype(int) == ws["breached"]).all()
    # exactly 55.0 (overtime 10.0) is NOT a breach; 55.25 is the next step up
    assert not is_breach(55.0)
    assert is_breach(55.01)
    assert ws.loc[ws["breached"] == 1, "total_hours"].min() == 55.25
    assert ws.loc[ws["breached"] == 0, "total_hours"].max() == 55.0


def test_latest_cutoff_dow():
    exp = load_export(DATA)
    sf = shift_frame(exp)
    # the sample data's last week runs through Wednesday
    target = max(sf["week_start"])
    assert latest_cutoff_dow(sf, target) == 2
    # a complete historical week runs through Sunday
    complete = sorted(sf["week_start"].unique())[0]
    assert latest_cutoff_dow(sf, complete) == 6


def test_identity_consolidation_finds_the_five_pairs():
    exp = load_export(DATA)
    idm = identity_map(exp)
    multi = idm.groupby("person_id").filter(lambda g: len(g) > 1)
    groups = {
        pid: sorted(g["employee_id"]) for pid, g in multi.groupby("person_id")
    }
    assert len(groups) == 5, groups
    assert ["E1035", "E1036"] in groups.values()
    assert ["E1126", "E1127"] in groups.values()


def test_overtime_attribution_sums_to_weekly_overtime():
    exp = load_export(DATA)
    sf = shift_frame(exp)
    sf["person_id"] = sf["employee_id"]  # test on raw employee_id
    obs = overtime_by_shift(sf, by="person_id")

    per_week_from_shifts = (
        obs.groupby(["person_id", "week_start"])["overtime_h"].sum().reset_index()
    )
    wk = weekly_hours(sf, by="person_id")
    m = wk.merge(
        per_week_from_shifts,
        left_on=["person_id", "week_start"],
        right_on=["person_id", "week_start"],
        how="left",
    )
    m["overtime_h"] = m["overtime_h"].fillna(0)
    diff = (m["overtime_hours"] - m["overtime_h"]).abs()
    assert diff.max() < 1e-9, f"attribution doesn't sum to weekly OT (max diff {diff.max()})"
