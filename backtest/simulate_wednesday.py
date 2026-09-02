"""Simulate 'the week is in progress' on every historical week and score.

Expanding window: for week k, history = weeks[0..k-1], observed = week k's
days up to the cutoff, truth = whether the person actually breached in week k
(total_hours > 55.0).

Default cutoff is Wednesday (dow 2). Pass another to see how the model does
earlier or later in the week -- accuracy climbs each day (see the by-cutoff
sweep at the bottom).

Answers the video's questions: what's the naive baseline, do we beat it,
which metric, and at what precision/recall does will_breach sit.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_curve

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.features import person_week_hours  # noqa: E402
from pipeline.hours import BREACH_TOTAL_HOURS, is_breach  # noqa: E402
from pipeline.load import load_export  # noqa: E402
from pipeline.predict import THRESHOLD_BY_CUTOFF, project  # noqa: E402

MIN_HISTORY = 3
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def run(data_dir: str = "data", cutoff_dow: int = 2) -> pd.DataFrame:
    exp = load_export(data_dir)
    pw = person_week_hours(exp, cutoff_dow)
    full_weeks = sorted(pw["week_start"].unique())[:-1]  # drop the partial week
    truth = pw.set_index(["person_id", "week_start"])

    frames = []
    for i, wk in enumerate(full_weeks):
        if i < MIN_HISTORY:
            continue
        history = full_weeks[:i]
        proj = project(exp, wk, history, cutoff_dow=cutoff_dow, threshold=0.0)
        proj = proj.assign(week=wk)
        proj["actual_total"] = [
            truth["total"].get((pid, wk), 0.0) for pid in proj["person_id"]
        ]
        proj["breach"] = is_breach(proj["actual_total"]).astype(int)
        hist = pw[pw["week_start"].isin(set(history))]
        hmean = hist.groupby("person_id")["total"].mean()
        days = cutoff_dow + 1
        proj["naive_histmean"] = [hmean.get(p, np.nan) for p in proj["person_id"]]
        proj["naive_linear"] = np.where(
            proj["observed"] > 0,
            proj["observed"] / days * 7,
            proj["naive_histmean"],
        )
        frames.append(proj)

    return pd.concat(frames, ignore_index=True)


def _score(name: str, y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return dict(model=name, precision=round(prec, 3), recall=round(rec, 3),
               f1=round(f1, 3), tp=tp, fp=fp, fn=fn)


def report(R: pd.DataFrame, cutoff_dow: int = 2) -> None:
    y = R["breach"].values
    b = f"> {BREACH_TOTAL_HOURS:g}"
    print(f"cutoff = through {DOW[cutoff_dow]} | simulated person-weeks: {len(R)} "
          f"| breaches: {int(y.sum())} ({y.mean():.2%})\n")

    rows = [
        _score("all-zero", y, np.zeros_like(y)),
        _score(f"naive: hist mean {b}", y,
               is_breach(R["naive_histmean"]).astype(int).values),
        _score(f"naive: linear x7 {b}", y,
               is_breach(R["naive_linear"]).astype(int).values),
        _score(f"ours: projected {b}", y,
               is_breach(R["projected_total"]).astype(int).values),
    ]
    default_t = THRESHOLD_BY_CUTOFF.get(cutoff_dow, 0.25)
    for t in sorted({0.20, 0.25, 0.30, 0.35, 0.50, default_t}):
        tag = " (default)" if abs(t - default_t) < 1e-9 else ""
        rows.append(_score(f"ours: risk_score >= {t:.2f}{tag}", y,
                           (R["risk_score"] >= t).astype(int).values))
    print(pd.DataFrame(rows).to_string(index=False))

    ap = average_precision_score(y, R["risk_score"].values)
    print(f"\nrisk_score PR-AUC: {ap:.3f}  (prevalence {y.mean():.3f})")

    # PR-AUC on the ordinary employees only (excludes the consolidated pairs,
    # which are ~28% of breaches and trivially predictable -- ANALYSIS_opus §4.1)
    from pipeline.hours import identity_map
    idm = identity_map(load_export("data"))
    multi = set(idm.groupby("person_id").filter(lambda g: len(g) > 1)["person_id"])
    ord_mask = ~R["person_id"].isin(multi)
    if ord_mask.sum() and R.loc[ord_mask, "breach"].sum():
        ap_ord = average_precision_score(
            R.loc[ord_mask, "breach"], R.loc[ord_mask, "risk_score"]
        )
        print(f"  ordinary employees only: PR-AUC {ap_ord:.3f} "
              f"(prevalence {R.loc[ord_mask, 'breach'].mean():.3f}, "
              f"n={int(ord_mask.sum())})")

    prec, rec, thr = precision_recall_curve(y, R["risk_score"].values)
    print("\noperating points on risk_score:")
    for target_r in (0.4, 0.5, 0.6, 0.7):
        idx = np.where(rec >= target_r)[0]
        if len(idx):
            i = idx[-1]
            t = thr[i - 1] if i > 0 else 0.0
            flagged = int((R["risk_score"] >= t).sum())
            print(f"  recall >= {target_r}: precision {prec[i]:.2f}  "
                  f"threshold {t:.3f}  flags {flagged}/{len(R)}")

    print("\ncalibration (risk_score bucket -> actual breach rate):")
    R2 = R.assign(bucket=pd.cut(R["risk_score"], [0, .1, .25, .5, .75, 1.0]))
    print(R2.groupby("bucket", observed=True)["breach"].agg(["mean", "size"])
          .round(3).to_string())


def by_cutoff(data_dir: str = "data") -> None:
    """How prediction quality changes with how much of the week we have."""
    print("\n" + "=" * 60)
    print("prediction quality by cutoff day")
    print("=" * 60)
    for cd in range(0, 6):
        R = run(data_dir, cutoff_dow=cd)
        y = R["breach"].values
        ap = average_precision_score(y, R["risk_score"].values)
        t = THRESHOLD_BY_CUTOFF[cd]
        pred = (R["risk_score"] >= t).astype(int).values
        s = _score("", y, pred)
        print(f"  through {DOW[cd]}: PR-AUC {ap:.3f}  |  at t={t}: "
              f"P {s['precision']:.2f} / R {s['recall']:.2f} / F1 {s['f1']:.2f}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--by-cutoff"]
    data = args[0] if args else "data"
    cutoff = int(args[1]) if len(args) > 1 else 2
    R = run(data, cutoff_dow=cutoff)
    report(R, cutoff_dow=cutoff)
    out = Path(__file__).parent / "backtest_rows.csv"
    R.to_csv(out, index=False)
    print(f"\nrows -> {out}")
    if "--by-cutoff" in sys.argv:
        by_cutoff(data)
