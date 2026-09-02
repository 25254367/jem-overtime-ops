"""The second method must genuinely agree with the rules on the clear cases
and stay independent (a different mechanism), so the comparison is meaningful.
"""
from check.second_method import run


def test_agreement_and_independence():
    df = run("data")
    agree = df["agree"].mean()
    # high enough that the taxonomy is validated, not so high the methods are
    # the same thing
    assert 0.85 <= agree <= 0.99, agree

    # the substantive categories should agree strongly
    for cat, floor in [("client_requested", 0.95), ("late_handover", 0.95),
                       ("equipment_failure", 0.90), ("absence_cover", 0.85)]:
        sub = df[df["rules"] == cat]
        assert sub["agree"].mean() >= floor, (cat, sub["agree"].mean())


def test_outputs_written():
    from pathlib import Path
    d = Path("check")
    assert (d / "second_method_labels.csv").exists()
    assert (d / "method_comparison.csv").exists()
