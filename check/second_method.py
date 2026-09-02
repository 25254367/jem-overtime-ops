"""Second, independent classifier for the note-sorting check.

TF-IDF over character 3-5-grams + k-nearest-neighbour vote against the
hand-labelled gold set. A completely different mechanism from the keyword
rules -- fuzzy similarity to labelled examples rather than hand-written
patterns -- so its errors are uncorrelated with the rules'.

Character n-grams (not words) make it typo-robust for free: "sikc" and "sick"
share most of their features.

No new dependencies (scikit-learn is already required), deterministic, runs in
a couple of seconds. See CLASSIFICATION.md §3 for why the *primary* classifier
is still the rules.

Outputs, both committed so the comparison reproduces without re-running:
  check/second_method_labels.csv   -- category per note (all 2,117)
  check/method_comparison.csv      -- rules vs this, side by side + agreement
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import adjusted_rand_score, confusion_matrix
from sklearn.metrics.pairwise import cosine_similarity

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.classify import CATEGORIES, classify_export  # noqa: E402
from pipeline.load import load_export  # noqa: E402

GOLD = "outputs/gold_sample_labelled.csv"
K = 5           # neighbours to vote
SEED = 20260902


_FILLER = {"", "-", "--", ".", "..", "...", "n/a", "na", "nil", "none", "ntr",
           "ok", "okay", "k", "sharp", "fine", "good", "noted", "x"}


def _is_blank(t: str) -> bool:
    s = (t or "").strip().lower().rstrip(".!,~- ")
    return s in _FILLER or s == "" or all(not c.isalnum() for c in s)


def knn_labels(notes: pd.Series, gold_text: pd.Series,
               gold_label: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Category per note: distance-weighted vote of its K nearest gold notes,
    with the vote divided by each class's frequency in the reference set (so a
    48%-of-gold class doesn't win by default). Empty / punctuation-only /
    bare-token notes are 'blank' -- not a semantic decision, and the method
    can't represent a zero vector anyway.
    Returns (labels, confidence = winning share of the weighted vote)."""
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2)
    vec.fit(pd.concat([gold_text, notes]))
    G = vec.transform(gold_text)
    N = vec.transform(notes)
    sims = cosine_similarity(N, G)
    gl = gold_label.to_numpy()
    prior = gold_label.value_counts(normalize=True).to_dict()

    labels, conf = [], []
    for i, note in enumerate(notes):
        if _is_blank(note):
            labels.append("blank")
            conf.append(1.0)
            continue
        order = np.argsort(-sims[i])[:K]
        weighted: dict[str, float] = {}
        for j in order:
            w = sims[i, j] / max(prior.get(gl[j], 1e-6), 1e-6)
            weighted[gl[j]] = weighted.get(gl[j], 0.0) + w
        total = sum(weighted.values()) or 1.0
        best = max(weighted, key=weighted.get)
        labels.append(best)
        conf.append(round(weighted[best] / total, 2))
    return pd.Series(labels, index=notes.index), pd.Series(conf, index=notes.index)


def run(data_dir: str = "data") -> pd.DataFrame:
    exp = load_export(data_dir)
    rules = classify_export(exp)[["shift_id", "note", "category"]].rename(
        columns={"category": "rules"}
    )
    gold = pd.read_csv(GOLD).fillna("")
    gold_text = exp.shift_notes.set_index("shift_id")["note"].reindex(
        gold["shift_id"]
    ).fillna("").reset_index(drop=True)

    m2, m2_conf = knn_labels(rules["note"].fillna(""), gold_text, gold["label"])
    rules["tfidf_knn"] = m2.values
    rules["tfidf_conf"] = m2_conf.values
    rules["agree"] = rules["rules"] == rules["tfidf_knn"]
    return rules


def cluster_alignment(data_dir: str = "data") -> dict:
    """k-means over the notes; how well do the clusters line up with the rule
    categories? (Does the taxonomy reflect real structure, or is it a human
    overlay?) Swept over k -- with ~50 templates, more clusters -> each
    template becomes its own, and purity should climb toward 1 if templates
    map cleanly to categories."""
    exp = load_export(data_dir)
    rules = classify_export(exp)
    text = rules["note"].fillna("")
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3)
    X = vec.fit_transform(text)

    sweep = {}
    ct7 = None
    for k in (7, 10, 15, 25, 40):
        km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
        cl = km.fit_predict(X)
        ct = pd.crosstab(cl, rules["category"])
        sweep[k] = dict(
            adjusted_rand=round(adjusted_rand_score(rules["category"], cl), 3),
            purity=round(ct.max(axis=1).sum() / ct.values.sum(), 3),
        )
        if k == 7:
            ct7 = ct
    return dict(sweep=sweep, crosstab_k7=ct7)


def report(df: pd.DataFrame) -> None:
    n = len(df)
    agree = df["agree"].mean()
    print("=" * 66)
    print("SECOND METHOD — TF-IDF char-ngram + kNN vs the RULES  (all 2,117)")
    print("=" * 66)
    print(f"\nagreement: {df['agree'].sum()}/{n} = {agree:.1%}")

    print("\nper-category agreement (where the rules assigned that category):")
    for c in CATEGORIES:
        sub = df[df["rules"] == c]
        if len(sub):
            print(f"  {c:18} n={len(sub):4}  agree={sub['agree'].mean():.1%}")

    print("\nconfusion — rules (rows) vs tfidf_knn (cols):")
    present = sorted(set(df["rules"]) | set(df["tfidf_knn"]))
    cm = confusion_matrix(df["rules"], df["tfidf_knn"], labels=present)
    print(pd.DataFrame(cm, index=present, columns=present).to_string())

    dis = df[~df["agree"]]
    print(f"\n{len(dis)} disagreements. by (rules -> tfidf_knn):")
    print(dis.groupby(["rules", "tfidf_knn"]).size()
          .sort_values(ascending=False).head(15).to_string())

    # the 11 the rules couldn't parse -- did TF-IDF rescue them?
    unc = df[df["rules"] == "unclassified"]
    if len(unc):
        print(f"\nrules 'unclassified' ({len(unc)}): tfidf_knn says")
        print(unc["tfidf_knn"].value_counts().to_string())

    print("\nsample disagreements (inspect these for rule errors):")
    for _, r in dis.sample(min(25, len(dis)), random_state=SEED).iterrows():
        print(f"  {r['shift_id']}  rules={r['rules']:17} knn={r['tfidf_knn']:17} "
              f"(conf {r['tfidf_conf']:.1f}) | {r['note'][:55]}")


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    df = run(d)
    report(df)

    outdir = Path(__file__).parent
    df[["shift_id", "note", "tfidf_knn"]].rename(
        columns={"tfidf_knn": "category"}
    ).to_csv(outdir / "second_method_labels.csv", index=False)
    df.to_csv(outdir / "method_comparison.csv", index=False)

    print("\n" + "=" * 66)
    print("CLUSTER ALIGNMENT — do the notes fall into taxonomy-shaped groups?")
    print("=" * 66)
    ca = cluster_alignment(d)
    print(f"{'k':>4}  {'adj. Rand':>10}  {'purity':>8}")
    for k, v in ca["sweep"].items():
        print(f"{k:>4}  {v['adjusted_rand']:>10}  {v['purity']:>8.1%}")
    print("\nk=7 cluster (rows) x rule category (cols):")
    print(ca["crosstab_k7"].to_string())
    print(f"\nwrote second_method_labels.csv, method_comparison.csv -> {outdir}")
