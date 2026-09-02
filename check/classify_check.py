"""Score the rule classifier against the hand-labelled gold set.

Gold set: outputs/gold_sample_labelled.csv (180 notes, hand-labelled by MS,
blind to classifier output). Strata metadata: outputs/gold_sample_strata.csv.

The classifier runs on the ORIGINAL note text from shift_notes.csv (not the
gold sheet's note column), so this measures its performance on the real data.
Overall accuracy is reported on the RANDOM-100 subset (representative); the
targeted 80 oversample rare categories so all-180 accuracy would be biased.

See CLASSIFICATION.md §5 for the measurement strategy and success criteria.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.classify import CATEGORIES, canonicalise_absentee, classify_note  # noqa: E402
from pipeline.load import load_export  # noqa: E402

GOLD = "outputs/gold_sample_labelled.csv"
STRATA = "outputs/gold_sample_strata.csv"

# success criteria, fixed before seeing results (CLASSIFICATION.md §5)
TARGET_ACCURACY = 0.85          # on the random-100
TARGET_MIN_RECALL = 0.70        # no reason-category below this
TARGET_LIE_HIT = 0.80           # notes-that-lie routed to operational_failure


def _load():
    exp = load_export("data")
    gold = pd.read_csv(GOLD).fillna("")
    strata = pd.read_csv(STRATA)[["shift_id", "stratum", "lang", "len_bucket"]]
    notes = exp.shift_notes.set_index("shift_id")["note"].fillna("")
    surnames = sorted({n.split()[-1] for n in exp.employees["full_name"] if n.split()})

    rows = []
    for _, g in gold.iterrows():
        raw = notes.get(g["shift_id"], "")
        pred = classify_note(raw)
        rows.append(dict(
            shift_id=g["shift_id"], note=raw,
            gold=g["label"], pred=pred["category"],
            gold_reason=g["absence_reason"], pred_reason=pred["absence_reason"],
            gold_auth=g["authorised"], pred_auth=pred["authorised"],
            gold_absentee=canonicalise_absentee(str(g["absentee"]).strip(), surnames),
            pred_absentee=canonicalise_absentee(pred["absentee"], surnames),
            gold_lie=bool(re.search(r"\blie\b", g["comment"].lower())),
            pred_conflict=pred["surface_vs_driver_conflict"],
            confidence=g["confidence"] or "confident",
        ))
    df = pd.DataFrame(rows).merge(strata, on="shift_id", how="left")
    return df


def _prf(df: pd.DataFrame, label: str) -> dict:
    tp = ((df.pred == label) & (df.gold == label)).sum()
    fp = ((df.pred == label) & (df.gold != label)).sum()
    fn = ((df.pred != label) & (df.gold == label)).sum()
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return dict(category=label, support=int((df.gold == label).sum()),
               precision=round(p, 2), recall=round(r, 2), f1=round(f1, 2),
               tp=int(tp), fp=int(fp), fn=int(fn))


def report(df: pd.DataFrame) -> None:
    rnd = df[df.stratum == "random"]
    acc_rnd = (rnd.pred == rnd.gold).mean()
    acc_all = (df.pred == df.gold).mean()
    kappa = cohen_kappa_score(df.gold, df.pred)

    print("=" * 66)
    print("RULE CLASSIFIER vs GOLD  (180 notes, 100 random + 80 targeted)")
    print("=" * 66)
    print(f"\noverall accuracy — random 100 : {acc_rnd:.1%}"
          f"   {'PASS' if acc_rnd >= TARGET_ACCURACY else 'FAIL'} "
          f"(target {TARGET_ACCURACY:.0%})")
    print(f"overall accuracy — all 180     : {acc_all:.1%}  (biased high — "
          f"targeted stratum oversamples rare categories)")
    print(f"Cohen's kappa (all 180)        : {kappa:.3f}")

    print("\nper-category (all 180):")
    prf = pd.DataFrame(_prf(df, c) for c in CATEGORIES)
    print(prf.to_string(index=False))
    weak = prf[(prf.support > 0) & (prf.recall < TARGET_MIN_RECALL)
              & (prf.category.isin(["client_requested", "absence_cover",
                                    "late_handover", "equipment_failure"]))]
    if len(weak):
        print(f"\n  ⚠ reason-categories below {TARGET_MIN_RECALL:.0%} recall: "
              f"{list(weak.category)}")
    else:
        print(f"\n  all reason-categories ≥ {TARGET_MIN_RECALL:.0%} recall  PASS")

    print("\nconfusion matrix (rows = gold, cols = pred):")
    present = [c for c in CATEGORIES if c in set(df.gold) | set(df.pred)]
    cm = confusion_matrix(df.gold, df.pred, labels=present)
    print(pd.DataFrame(cm, index=present, columns=present).to_string())

    print("\naccuracy by confidence:")
    for c in ("confident", "ambiguous"):
        sub = df[df.confidence == c]
        if len(sub):
            print(f"  {c:10} n={len(sub):3}  acc={ (sub.pred == sub.gold).mean():.1%}")

    print("\naccuracy by language:")
    for lang in ("en", "af", "zu"):
        sub = df[df.lang == lang]
        if len(sub):
            print(f"  {lang}  n={len(sub):3}  acc={ (sub.pred == sub.gold).mean():.1%}")

    # ---- targeted audits ----
    print("\n" + "-" * 66)
    print("targeted audits")
    print("-" * 66)

    lies = df[df.gold_lie]
    hit = ((lies.pred == "absence_cover") & lies.pred_conflict).mean() if len(lies) else 0
    print(f"\nnotes that lie: {len(lies)} in gold | "
          f"routed to absence_cover + flagged: {hit:.0%}  "
          f"{'PASS' if hit >= TARGET_LIE_HIT else 'FAIL'} (target {TARGET_LIE_HIT:.0%})")

    ac = df[(df.gold == "absence_cover") & (df.pred == "absence_cover")]
    if len(ac):
        ra = (ac.gold_reason == ac.pred_reason).mean()
        print(f"\nabsence_reason accuracy (on {len(ac)} agreed absence_cover): {ra:.1%}")
        rc = pd.crosstab(ac.gold_reason, ac.pred_reason)
        print(rc.to_string())

    cr = df[(df.gold == "client_requested") & (df.pred == "client_requested")]
    if len(cr):
        aa = (cr.gold_auth == cr.pred_auth).mean()
        print(f"\nauthorised accuracy (on {len(cr)} agreed client_requested): {aa:.1%}")

    named = ac[ac.gold_absentee.str.len() > 0]
    if len(named):
        ab = (named.gold_absentee == named.pred_absentee).mean()
        print(f"\nabsentee accuracy (on {len(named)} named absence_cover): {ab:.1%}")
        miss = named[named.gold_absentee != named.pred_absentee]
        for _, m in miss.head(10).iterrows():
            print(f"   {m.shift_id}: gold={m.gold_absentee!r} pred={m.pred_absentee!r} "
                  f"| {m.note[:55]}")

    # ---- every disagreement ----
    print("\n" + "-" * 66)
    print("all category disagreements")
    print("-" * 66)
    dis = df[df.pred != df.gold].sort_values(["gold", "pred"])
    for _, d in dis.iterrows():
        print(f"  {d.shift_id} [{d.confidence[:4]}/{d.lang}] gold={d.gold} "
              f"pred={d.pred}  | {d.note[:60]}")
    if dis.empty:
        print("  (none)")


if __name__ == "__main__":
    df = _load()
    report(df)
    out = Path(__file__).parent / "classify_check_rows.csv"
    df.to_csv(out, index=False)
    print(f"\nrows -> {out}")
