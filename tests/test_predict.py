"""predictions.csv must match the README spec exactly."""
from pipeline.features import person_week_hours
from pipeline.load import load_export
from pipeline.predict import predictions_csv, project

DATA = "data"


def _target_and_history():
    exp = load_export(DATA)
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    return exp, weeks[-1], weeks[:-1]


def test_predictions_csv_shape_and_columns():
    exp, target, history = _target_and_history()
    pc = predictions_csv(exp, target, history)

    assert list(pc.columns) == ["employee_id", "will_breach", "risk_score"]
    # one row per employee_id in employees.csv, same set, no dups
    assert set(pc["employee_id"]) == set(exp.employees["employee_id"])
    assert len(pc) == len(exp.employees)
    assert not pc["employee_id"].duplicated().any()

    assert pc["will_breach"].isin([0, 1]).all()
    assert pc["risk_score"].between(0.0, 1.0).all()
    # will_breach must be consistent with the cutoff's threshold on risk_score
    from pipeline.predict import THRESHOLD_BY_CUTOFF, resolve_cutoff
    t = THRESHOLD_BY_CUTOFF[resolve_cutoff(exp, target, None)]
    assert (pc["will_breach"] == (pc["risk_score"] >= t).astype(int)).all()


def test_consolidated_pairs_get_the_same_prediction():
    exp, target, history = _target_and_history()
    pc = predictions_csv(exp, target, history).set_index("employee_id")
    for a, b in [("E1035", "E1036"), ("E1090", "E1091"), ("E1097", "E1098"),
                 ("E1126", "E1127"), ("E1193", "E1194")]:
        assert pc.loc[a, "will_breach"] == pc.loc[b, "will_breach"]
        assert pc.loc[a, "risk_score"] == pc.loc[b, "risk_score"]


def test_no_lookahead_in_projection():
    """History weeks strictly before the target must not include it."""
    exp, target, history = _target_and_history()
    assert target not in history
    proj = project(exp, target, history)
    assert (proj["observed"] >= 0).all()
    # observed is Mon-Wed only, so must be well under a full week
    assert proj["observed"].max() < 55.0


def test_cutoff_is_configurable():
    """Same mechanics at any cutoff; earlier in the week = flatter slope,
    lower threshold, and the projection leans more on history."""
    exp, target, history = _target_and_history()
    from pipeline.features import pooled_slope

    s_mon = pooled_slope(exp, history, 0)
    s_fri = pooled_slope(exp, history, 4)
    assert s_mon < s_fri < 0  # Monday slope is steeper (more negative)

    p_mon = project(exp, target, history, cutoff_dow=0)
    p_wed = project(exp, target, history, cutoff_dow=2)
    assert (p_mon["cutoff_dow"] == 0).all()
    assert p_mon["observed"].sum() < p_wed["observed"].sum()  # fewer days seen
