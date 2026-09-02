"""'What to do about it' — recommendations must be specific and consistent."""
from pipeline.actions import double_booking_alert, recommend
from pipeline.features import person_week_hours
from pipeline.load import load_export
from pipeline.predict import project

DATA = "data"


def _setup():
    exp = load_export(DATA)
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    proj = project(exp, weeks[-1], weeks[:-1])
    recs = recommend(exp, proj, weeks[-1], weeks[:-1])
    return exp, proj, recs


def test_one_rec_per_flagged_person():
    exp, proj, recs = _setup()
    flagged = set(proj[proj["will_breach"] == 1]["person_id"])
    assert set(recs["person_id"]) == flagged
    assert not recs["person_id"].duplicated().any()


def test_duplicate_identity_people_get_the_consolidate_action():
    exp, proj, recs = _setup()
    dbl = set(double_booking_alert(exp)["person_id"])
    flagged_dbl = dbl & set(recs["person_id"])
    for pid in flagged_dbl:
        assert recs.set_index("person_id").loc[pid, "action"] == \
            "consolidate payroll records"


def test_no_colleague_recommended_as_receiver_twice():
    exp, proj, recs = _setup()
    import re
    receivers = []
    for d in recs["detail"]:
        m = re.search(r"to ([A-Z][a-z]+ [A-Z][a-z]+) \(", d)
        if m:
            receivers.append(m.group(1))
    assert len(receivers) == len(set(receivers)), receivers


def test_swaps_never_push_the_receiver_past_the_55h_cap():
    """A swap that moves the breach instead of fixing it is a bug."""
    import re
    exp, proj, recs = _setup()
    swaps = recs[recs["action"].str.startswith("shift-swap")]
    for _, r in swaps.iterrows():
        # the detail reports the receiver's resulting total, e.g. "36h -> 47h"
        afters = [float(x) for x in re.findall(r"→ (\d+)h", r["detail"])]
        assert all(a <= 55.0 for a in afters), r["detail"]


def test_severity_matches_projection():
    exp, proj, recs = _setup()
    for _, r in recs.iterrows():
        if r["projected_total"] > 55.0:
            assert r["severity"] == "will breach", r.to_dict()
        else:
            assert r["severity"] == "at risk", r.to_dict()


def test_double_booking_alert_lists_the_five_pairs():
    exp = load_export(DATA)
    a = double_booking_alert(exp)
    assert len(a) == 5
    assert a["employee_ids"].str.contains(" & ").all()
