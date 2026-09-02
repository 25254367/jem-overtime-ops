"""Per-person features from historical weeks.

Everything is computed per *person_id* (identity-consolidated), from a given
set of complete history weeks and a **cutoff weekday** -- how much of the week
the export covers. 2 = data through Wednesday (observe Mon/Tue/Wed, project
Thu-Sun); 4 = through Friday; the mechanics are identical at any cutoff, only
`observed` and the fitted slope change.

Design rationale in data_checks.md §5:
  - no fixed rosters -> can't roster-forward; use weekday propensities
  - weekly totals are stable (CV ~0.11)
  - within-person corr(observed-so-far, remaining) is negative: a hot first
    half predicts a cooler second half, so the projection regresses to the
    personal mean. The slope steepens the earlier in the week you are
    (~-0.79 at a Monday cutoff, ~-0.75 Wednesday, ~-0.46 Saturday) so it is
    re-fitted per cutoff by pooled_slope().
  - remaining-hours error is ~Normal
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .hours import BREACH_TOTAL_HOURS, shift_frame, add_person_id
from .load import Export

CUTOFF_DOW = 2  # default cutoff = Wednesday; pass the real one from the data


def _person_meta(export: Export) -> pd.DataFrame:
    """One row per person_id with role/site/pattern (from the canonical
    employee record — the lowest employee_id in the group)."""
    from .hours import identity_map

    idm = identity_map(export)
    emp = export.employees.merge(idm, on="employee_id", how="left")
    # canonical row = the person_id itself
    canon = emp[emp["employee_id"] == emp["person_id"]]
    return canon[
        ["person_id", "role", "primary_site_id", "shift_pattern", "employment_type"]
    ].reset_index(drop=True)


def person_week_hours(
    export: Export, cutoff_dow: int = CUTOFF_DOW
) -> pd.DataFrame:
    """Per person_id x week: total, observed (<=cutoff), remaining (>cutoff),
    n_open. One tidy frame the rest of the module builds on."""
    s = add_person_id(shift_frame(export), export)
    s["seg"] = np.where(s["dow"] <= cutoff_dow, "observed", "remaining")
    wide = (
        s.pivot_table(
            index=["person_id", "week_start"],
            columns="seg",
            values="duration_h",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )
    for col in ("observed", "remaining"):
        if col not in wide:
            wide[col] = 0.0
    wide["total"] = wide["observed"] + wide["remaining"]
    opens = (
        s.groupby(["person_id", "week_start"])["is_open"].sum().rename("n_open")
    )
    wide = wide.merge(opens, on=["person_id", "week_start"], how="left")
    wide["n_open"] = wide["n_open"].fillna(0)
    return wide


def build_features(
    export: Export,
    history_weeks: list,
    cutoff_dow: int = CUTOFF_DOW,
) -> pd.DataFrame:
    """Per-person features from `history_weeks`.

    Returns one row per person_id:
      n_weeks, wk_mean, wk_std, wk_max, obs_mean, obs_std, rem_mean, rem_std,
      corr_obs_rem, prior_breaches, open_per_wk, + role/site/pattern.
    """
    pw = person_week_hours(export, cutoff_dow)
    hist = pw[pw["week_start"].isin(set(history_weeks))]

    def _agg(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        obs, rem, tot = g["observed"], g["remaining"], g["total"]
        if n >= 3 and obs.std(ddof=0) > 1e-6 and rem.std(ddof=0) > 1e-6:
            corr = float(np.corrcoef(obs, rem)[0, 1])
        else:
            corr = np.nan
        return pd.Series(
            dict(
                n_weeks=n,
                wk_mean=tot.mean(),
                wk_std=tot.std(ddof=0) if n > 1 else 0.0,
                wk_max=tot.max(),
                obs_mean=obs.mean(),
                obs_std=obs.std(ddof=0) if n > 1 else 0.0,
                rem_mean=rem.mean(),
                rem_std=rem.std(ddof=0) if n > 1 else 0.0,
                corr_obs_rem=corr,
                prior_breaches=int((tot > BREACH_TOTAL_HOURS).sum()),
                open_per_wk=g["n_open"].mean(),
            )
        )

    feats = hist.groupby("person_id").apply(_agg, include_groups=False).reset_index()
    feats = feats.merge(_person_meta(export), on="person_id", how="left")
    return feats


def pooled_slope(export: Export, history_weeks: list, cutoff_dow: int) -> float:
    """One pooled within-person OLS of remaining-hours on observed-hours.

    Each history person-week contributes (observed - person_obs_mean,
    remaining - person_rem_mean); the slope of remaining on observed across
    all of them is the regression-to-mean coefficient. Computed this way (not
    as the median of per-person correlations, which is upward-biased on 4-8
    weeks) it is stable and unbiased. Falls back to -0.75 if there is not
    enough history to fit.
    """
    pw = person_week_hours(export, cutoff_dow)
    hist = pw[pw["week_start"].isin(set(history_weeks))]
    if len(hist) < 20 or hist["person_id"].nunique() < 5:
        return -0.75
    means = hist.groupby("person_id")[["observed", "remaining"]].transform("mean")
    x = (hist["observed"] - means["observed"]).to_numpy()
    y = (hist["remaining"] - means["remaining"]).to_numpy()
    denom = float((x * x).sum())
    if denom < 1e-6:
        return -0.75
    return float(np.clip((x * y).sum() / denom, -1.2, 0.0))


def pooled_corr(export: Export, history_weeks: list, cutoff_dow: int) -> float:
    """Pooled within-person correlation of remaining on observed (for the
    conditional SD). Same de-meaning as pooled_slope."""
    pw = person_week_hours(export, cutoff_dow)
    hist = pw[pw["week_start"].isin(set(history_weeks))]
    if len(hist) < 20:
        return -0.75
    means = hist.groupby("person_id")[["observed", "remaining"]].transform("mean")
    x = hist["observed"] - means["observed"]
    y = hist["remaining"] - means["remaining"]
    if x.std() < 1e-6 or y.std() < 1e-6:
        return -0.75
    return float(np.clip(np.corrcoef(x, y)[0, 1], -0.99, 0.0))


def population_priors(
    export: Export, history_weeks: list, cutoff_dow: int
) -> dict:
    """Cutoff-specific constants: the pooled slope + correlation, and global
    medians used as fallbacks for people with thin / no history."""
    feats = build_features(export, history_weeks, cutoff_dow)
    rem_sd = feats["rem_std"].replace(0, np.nan).median()
    return dict(
        slope=pooled_slope(export, history_weeks, cutoff_dow),
        corr=pooled_corr(export, history_weeks, cutoff_dow),
        rem_sd=float(rem_sd) if pd.notna(rem_sd) else 6.0,
        wk_mean=float(feats["wk_mean"].median()),
        obs_mean=float(feats["obs_mean"].median()),
        rem_mean=float(feats["rem_mean"].median()),
    )


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    pw = person_week_hours(exp)
    weeks = sorted(w for w in pw["week_start"].unique())
    hist = weeks[:-1]  # all but the partial target week
    f = build_features(exp, hist)
    print(f"{len(f)} people | median n_weeks {f['n_weeks'].median():.0f}")
    for cd in (0, 2, 4, 5):
        pri = population_priors(exp, hist, cd)
        print(f"  cutoff dow {cd}: slope {pri['slope']:+.3f}  corr {pri['corr']:+.3f}  "
              f"rem_sd {pri['rem_sd']:.1f}")
    print(
        f.sort_values("wk_mean", ascending=False)
        .head(8)[
            ["person_id", "n_weeks", "wk_mean", "wk_std", "wk_max",
             "obs_mean", "rem_mean", "corr_obs_rem", "prior_breaches"]
        ]
        .round(2)
        .to_string(index=False)
    )
