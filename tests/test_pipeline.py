"""The full pipeline: one run -> three valid outputs."""
import json
from pathlib import Path

import pandas as pd

from pipeline.aggregate import build
from pipeline.classify import CATEGORIES
from pipeline.load import load_export
from pipeline.run import run

DATA = "data"


def test_run_writes_three_files(tmp_path):
    data = run(DATA, str(tmp_path))
    for f in ("predictions.csv", "note_classifications.csv", "dashboard_data.json"):
        assert (tmp_path / f).exists(), f

    preds = pd.read_csv(tmp_path / "predictions.csv")
    assert list(preds.columns) == ["employee_id", "will_breach", "risk_score"]
    assert len(preds) == 213
    assert preds["will_breach"].isin([0, 1]).all()

    notes = pd.read_csv(tmp_path / "note_classifications.csv")
    assert list(notes.columns) == ["shift_id", "category", "note"]
    assert len(notes) == 2117
    assert notes["category"].isin(CATEGORIES).all()

    assert isinstance(data, dict)


def test_dashboard_data_shape():
    exp = load_export(DATA)
    d = build(exp)
    assert set(d) == {"meta", "headline", "risk_list", "people", "sites",
                      "alerts", "why_split", "ops_review"}
    assert d["meta"]["cutoff_label"] == "Wednesday"
    assert len(d["sites"]) == 6
    assert len(d["alerts"]["double_booking"]) == 5

    # every risk-list person has a matching detail entry and a tier
    for r in d["risk_list"]:
        assert r["person_id"] in d["people"]
        assert r["tier"] in ("breach_likely", "elevated", "watch")
        assert r["risk_score"] >= 0.10

    # the split is sane
    ws = d["why_split"]
    assert 0 < ws["attributable_share"] < 1
    assert ws["opfail_share_of_attributable"] > 0.5


def test_dashboard_json_is_serialisable():
    from pipeline.aggregate import _jsonable
    exp = load_export(DATA)
    d = build(exp)
    json.dumps(d, default=_jsonable)  # must not raise
