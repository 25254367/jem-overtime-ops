"""Breach projection: risk_score and will_breach for a target week.

Approach (data_checks.md §5, SUMMARY.md "Prediction approach"):

  observed  = person's actual hours in the target week so far (dow <= cutoff)
  remaining ~ Normal(mu, sigma)
      mu    = rem_mean + slope * (observed - obs_mean)     # regress to the mean
      slope = pooled within-person OLS for this cutoff (features.pooled_slope);
              same value for everyone -- per-person slopes are too noisy on
              4-8 weeks (see ANALYSIS_opus.md §3)
      sigma = conditional sd from the pooled correlation, widened for people
              with a history of un-clocked-out ("open") shifts
  projected_total = observed + mu
  risk_score      = P(observed + remaining > 55.0)         # overtime > 10.0
  will_breach     = risk_score >= threshold                # tuned per cutoff

The cutoff is how much of the week the export covers -- 2 = through Wednesday,
4 = through Friday. If not given it is read from the data. Everything is per
person_id, then mapped out to every employee_id.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from .features import build_features, person_week_hours, population_priors
from .hours import (
    BREACH_TOTAL_HOURS,
    add_person_id,
    identity_map,
    latest_cutoff_dow,
    shift_frame,
)
from .load import Export

# risk_score threshold for will_breach = 1, by cutoff weekday (0=Mon).
# Tuned on the expanding-window backtest for a recall-leaning operating point
# (a missed breach costs more than a false alarm): each holds backtest recall
# ~0.46-0.49 at the best precision available there. The full week (Sun) is
# already known, so its threshold just splits actual breaches.
THRESHOLD_BY_CUTOFF = {0: 0.16, 1: 0.22, 2: 0.24, 3: 0.22, 4: 0.23, 5: 0.42, 6: 0.99}
DEFAULT_THRESHOLD = THRESHOLD_BY_CUTOFF[2]  # Wednesday

SIGMA_FLOOR = 3.0            # never claim more certainty than this
SIGMA_MULT = 1.15           # conditional sd slightly underestimates out-of-sample
OPEN_SHIFT_SIGMA_ADD = 2.0  # per historical open shift/week: widen the tail


def resolve_cutoff(export: Export, target_week, cutoff_dow: int | None) -> int:
    if cutoff_dow is not None:
        return cutoff_dow
    s = shift_frame(export)
    return latest_cutoff_dow(s, target_week)


def _observed_this_week(export: Export, target_week, cutoff_dow: int) -> pd.Series:
    """Person's actual hours in the target week, dow <= cutoff."""
    s = add_person_id(shift_frame(export), export)
    cur = s[(s["week_start"] == target_week) & (s["dow"] <= cutoff_dow)]
    return cur.groupby("person_id")["duration_h"].sum()


def project(
    export: Export,
    target_week,
    history_weeks: list,
    cutoff_dow: int | None = None,
    threshold: float | None = None,
) -> pd.DataFrame:
    """Per-person projection for `target_week`.

    Returns: person_id, n_weeks, observed, mu_remaining, sigma,
             projected_total, prior_breaches, risk_score, will_breach,
             cutoff_dow.
    """
    cutoff_dow = resolve_cutoff(export, target_week, cutoff_dow)
    if threshold is None:
        threshold = THRESHOLD_BY_CUTOFF.get(cutoff_dow, DEFAULT_THRESHOLD)

    feats = build_features(export, history_weeks, cutoff_dow)
    pri = population_priors(export, history_weeks, cutoff_dow)
    slope = pri["slope"]           # one pooled slope, everyone
    pooled_corr = pri["corr"]
    observed = _observed_this_week(export, target_week, cutoff_dow)

    fmap = feats.set_index("person_id")
    rows = []
    for pid in set(feats["person_id"]) | set(observed.index):
        obs = float(observed.get(pid, 0.0))
        if pid in fmap.index:
            f = fmap.loc[pid]
            n = int(f["n_weeks"])
            obs_mean = f["obs_mean"] if n >= 2 else pri["obs_mean"]
            rem_mean = f["rem_mean"] if n >= 2 else pri["rem_mean"]
            base_sd = (
                f["rem_std"] if (n >= 3 and f["rem_std"] > 1e-6) else pri["rem_sd"]
            )
            open_per_wk = float(f["open_per_wk"])
            prior_breaches = int(f["prior_breaches"])
        else:  # brand-new person, no history
            n = 0
            obs_mean, rem_mean = pri["obs_mean"], pri["rem_mean"]
            base_sd = pri["rem_sd"]
            open_per_wk = 0.0
            prior_breaches = 0

        cond_sd = base_sd * np.sqrt(max(1e-3, 1 - pooled_corr**2))
        sigma = (
            max(SIGMA_FLOOR, cond_sd) * SIGMA_MULT
            + OPEN_SHIFT_SIGMA_ADD * open_per_wk
        )

        mu_rem = max(0.0, rem_mean + slope * (obs - obs_mean))
        projected = obs + mu_rem
        # P(observed + remaining > 55.0), remaining ~ Normal(mu_rem, sigma)
        risk = float(norm.sf(BREACH_TOTAL_HOURS - projected, loc=0.0, scale=sigma))

        # defensive: a projection far past what a week can physically hold
        # means the inputs are broken, not that someone will work 90 hours.
        if projected > obs + 5 * 13.5:
            print(f"  [predict] warning: {pid} projected {projected:.0f}h "
                  f"(observed {obs:.0f}h) — check the export")

        rows.append(
            dict(
                person_id=pid,
                n_weeks=n,
                observed=round(obs, 2),
                mu_remaining=round(mu_rem, 2),
                sigma=round(sigma, 2),
                projected_total=round(projected, 2),
                prior_breaches=prior_breaches,
                risk_score=round(risk, 4),
                will_breach=int(risk >= threshold),
                cutoff_dow=cutoff_dow,
            )
        )
    return pd.DataFrame(rows).sort_values("risk_score", ascending=False)


def predictions_csv(
    export: Export,
    target_week,
    history_weeks: list,
    cutoff_dow: int | None = None,
    threshold: float | None = None,
) -> pd.DataFrame:
    """One row per employee_id in employees.csv: employee_id, will_breach,
    risk_score. Person-level results are stamped onto every employee_id that
    shares the person (the duplicate-identity pairs)."""
    proj = project(export, target_week, history_weeks, cutoff_dow, threshold)
    idm = identity_map(export)
    out = idm.merge(
        proj[["person_id", "will_breach", "risk_score"]], on="person_id", how="left"
    )
    order = export.employees[["employee_id"]]
    out = order.merge(out, on="employee_id", how="left")
    out["will_breach"] = out["will_breach"].fillna(0).astype(int)
    out["risk_score"] = out["risk_score"].fillna(0.0).round(4)
    return out[["employee_id", "will_breach", "risk_score"]]


if __name__ == "__main__":
    import sys

    from .load import load_export

    exp = load_export(sys.argv[1] if len(sys.argv) > 1 else "data")
    weeks = sorted(person_week_hours(exp)["week_start"].unique())
    target, history = weeks[-1], weeks[:-1]
    cutoff = resolve_cutoff(exp, target, None)
    dow_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][cutoff]
    print(f"target week {target} | data through {dow_name} (cutoff dow {cutoff}) | "
          f"{len(history)} history weeks")

    proj = project(exp, target, history)
    print("\ntop 15 by risk_score:")
    print(
        proj.head(15)[
            ["person_id", "observed", "mu_remaining", "sigma",
             "projected_total", "prior_breaches", "risk_score", "will_breach"]
        ].to_string(index=False)
    )
    pc = predictions_csv(exp, target, history)
    print(f"\npredictions.csv: {len(pc)} rows | "
          f"will_breach=1: {int(pc['will_breach'].sum())}")
