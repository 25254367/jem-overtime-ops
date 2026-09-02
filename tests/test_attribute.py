"""Overtime attribution: hours must reconcile, and the split must be sane."""
from pipeline.attribute import overtime_attribution, split_summary
from pipeline.hours import add_person_id, shift_frame, weekly_hours
from pipeline.load import load_export

DATA = "data"


def test_attributed_overtime_matches_weekly_overtime():
    exp = load_export(DATA)
    ot = overtime_attribution(exp)
    per_week = ot.groupby(["person_id", "week_start"])["overtime_h"].sum()

    wk = weekly_hours(add_person_id(shift_frame(exp), exp), by="person_id")
    wk = wk[wk["overtime_hours"] > 1e-9].set_index(["person_id", "week_start"])

    joined = wk.join(per_week.rename("attributed"), how="left").fillna(0)
    diff = (joined["overtime_hours"] - joined["attributed"]).abs()
    assert diff.max() < 1e-6, f"attribution doesn't sum to weekly OT ({diff.max()})"


def test_split_summary_shape():
    exp = load_export(DATA)
    s = split_summary(exp)
    assert 0 < s["attributable_share"] < 1
    assert (
        abs(s["asked_for_hours"] + s["operational_failure_hours"]
            - s["attributable_hours"]) < 0.1
    )
    # operational failure should dominate the attributable overtime
    assert s["opfail_share_of_attributable"] > 0.5
    assert s["n_breach_weeks"] > 0


def test_every_overtime_shift_has_a_driver():
    exp = load_export(DATA)
    ot = overtime_attribution(exp)
    assert ot["overtime_driver"].isin(
        ["asked_for", "operational_failure", "undetermined"]
    ).all()
    # note-less shifts must be 'undetermined', not silently attributed
    assert (ot.loc[~ot["has_note"], "overtime_driver"] == "undetermined").all()
