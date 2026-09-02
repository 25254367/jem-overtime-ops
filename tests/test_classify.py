"""The note classifier: taxonomy, precedence, and the submission format."""
from pipeline.classify import (
    CATEGORIES,
    canonicalise_absentee,
    classify_export,
    classify_note,
    note_classifications_csv,
)
from pipeline.load import load_export

DATA = "data"


def _cat(text):
    return classify_note(text)["category"]


def test_known_templates_each_category():
    cases = {
        "generator fault, stayed to monitor": "equipment_failure",
        "buffer machine kaput, did the floor by hand": "equipment_failure",
        "masjien is stukkend, alles met die hand gedoen": "equipment_failure",
        "next shift guard did not pitch. had to cover": "absence_cover",
        "covering Wyk post, no show no call": "absence_cover",
        "uMolefe akezanga namhlanje, ngimele yena": "absence_cover",
        "aflos het nie opgedaag nie, moes aanbly": "absence_cover",
        "took Fourie shift as well, 2 posts 1 guard": "absence_cover",
        "late handover, waiting on paperwork": "late_handover",
        "oorhandiging was laat, gewag vir sleutels": "late_handover",
        "client requested deep clean before the audit - approved": "client_requested",
        "klient het ekstra ure gevra vir stocktake": "client_requested",
        "additional cover requested by site manager, signed off": "client_requested",
        "nothing to report": "routine",
        "all quiet": "routine",
        "akukho lutho": "routine",
        "niks om te rapporteer nie": "routine",
    }
    wrong = {t: (_cat(t), want) for t, want in cases.items() if _cat(t) != want}
    assert not wrong, wrong


def test_blank_vs_routine_boundary():
    for t in ["", "-", ".", "n/a", "ntr", "ok", "sharp", "fine", "noted", "  "]:
        assert _cat(t) == "blank", (t, _cat(t))
    # "all X" states the shift was uneventful -> routine, not blank
    for t in ["all good", "all fine", "all quiet", "all clear"]:
        assert _cat(t) == "routine", (t, _cat(t))


def test_notes_that_lie_route_to_the_true_driver():
    t = "client signed for the extra hrs but real reason is relief no show agn"
    r = classify_note(t)
    assert r["category"] == "absence_cover"
    assert r["overtime_driver"] == "operational_failure"
    assert r["surface_vs_driver_conflict"] is True


def test_absence_subfields():
    r = classify_note("covering for Ngcobo - booked off sick")
    assert r["category"] == "absence_cover"
    assert r["absence_reason"] == "sick"
    assert r["absentee"] == "Ngcobo"

    r2 = classify_note("no replacement sent, ngicela sort this out")
    assert r2["category"] == "absence_cover"
    assert r2["absentee"] == "unnamed_relief"


def test_submission_csv_format():
    exp = load_export(DATA)
    pc = note_classifications_csv(exp)
    assert list(pc.columns) == ["shift_id", "category", "note"]
    assert len(pc) == len(exp.shift_notes)
    assert set(pc["shift_id"]) == set(exp.shift_notes["shift_id"])
    assert pc["category"].isin(CATEGORIES).all()
    assert not pc["category"].isna().any()


def test_unclassified_is_small():
    exp = load_export(DATA)
    df = classify_export(exp)
    share = (df["category"] == "unclassified").mean()
    assert share <= 0.05, f"unclassified {share:.1%} — rules need work"


def test_absentee_canonicalisation():
    surnames = ["Mokoena", "Motaung", "Sibiya", "Ndlovu"]
    assert canonicalise_absentee("Mokena", surnames) == "Mokoena"
    assert canonicalise_absentee("Motuang", surnames) == "Motaung"
    assert canonicalise_absentee("Sibiya", surnames) == "Sibiya"
    assert canonicalise_absentee("unnamed_relief", surnames) == "unnamed_relief"
    assert canonicalise_absentee("", surnames) == ""
    assert canonicalise_absentee("Zzyzx", surnames) == "Zzyzx"  # no close match


def test_overtime_driver_rollup():
    exp = load_export(DATA)
    df = classify_export(exp)
    m = df.groupby("category")["overtime_driver"].agg(lambda s: set(s))
    assert m["client_requested"] == {"asked_for"}
    assert m["absence_cover"] == {"operational_failure"}
    assert m["routine"] == {"none"} and m["blank"] == {"none"}
