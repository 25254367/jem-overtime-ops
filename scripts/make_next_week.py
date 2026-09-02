"""Build a synthetic 'next week' export, to demo Requirement 4 (load a new week
without a developer).

There is no real next week in the assessment data — it stops on Wednesday
12 Aug. This rolls the whole export forward by one week and extends the newest
week by a day, so the reload has something genuinely different to chew on:

  - every date + 7 days  (the newest week becomes Mon 17 – Sun 23 Aug)
  - the newest week now runs through **Friday**, not Wednesday, so the
    pipeline picks a different cutoff, re-fits the slope, and the dashboard
    banner flips to "Friday · accuracy good"
  - weekly_summary is regenerated from the shifted shifts so it still
    reconciles exactly
  - employees / sites / payroll_details are unchanged (they don't move
    week to week)

    python scripts/make_next_week.py            -> writes data_next_week/
    python scripts/make_next_week.py --broken   -> also writes data_next_week/broken/
                                                   (shifts.csv missing a column,
                                                    to show the loud failure)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SRC = Path("data")
OUT = Path("data_next_week")
OUT_BROKEN = OUT / "broken"
SHIFT_DAYS = 7
PASSTHROUGH = ["employees.csv", "sites.csv", "payroll_details.csv"]
CSV_FILES = ["employees.csv", "sites.csv", "payroll_details.csv", "shifts.csv",
             "public_holidays.csv", "shift_notes.csv", "weekly_summary.csv"]


def _shift_dates(s: pd.Series, days: int) -> pd.Series:
    return (pd.to_datetime(s) + pd.Timedelta(days=days)).dt.strftime("%Y-%m-%d")


def build() -> None:
    OUT.mkdir(exist_ok=True)

    # 1. files that don't change week to week
    for f in PASSTHROUGH:
        (OUT / f).write_bytes((SRC / f).read_bytes())

    # 2. shift every dated file forward
    shifts = pd.read_csv(SRC / "shifts.csv", dtype=str)
    shifts["shift_date"] = _shift_dates(shifts["shift_date"], SHIFT_DAYS)

    hol = pd.read_csv(SRC / "public_holidays.csv", dtype=str)
    hol["date"] = _shift_dates(hol["date"], SHIFT_DAYS)

    # 3. extend the newest week through Friday by copying each person's OWN
    #    Thursday and Friday shifts from the previous week (new shift_ids,
    #    re-dated). Copying the prior week keeps each person's real weekday
    #    pattern — someone who never works Friday doesn't suddenly get one.
    d = pd.to_datetime(shifts["shift_date"])
    newest_monday = d.dt.to_period("W-SUN").dt.start_time.max()
    prev_monday = newest_monday - pd.Timedelta(days=7)
    cutoff_day = newest_monday + pd.Timedelta(days=4)  # Friday
    max_id = shifts["shift_id"].str.extract(r"(\d+)").astype(int).max().iloc[0]
    nid = max_id
    for offset in (3, 4):  # Thursday, Friday
        src_date = (prev_monday + pd.Timedelta(days=offset)).strftime("%Y-%m-%d")
        src_rows = shifts[shifts["shift_date"] == src_date].copy()
        if src_rows.empty:
            continue
        src_rows["shift_id"] = [f"S{nid + 1 + i}" for i in range(len(src_rows))]
        src_rows["shift_date"] = (
            newest_monday + pd.Timedelta(days=offset)
        ).strftime("%Y-%m-%d")
        nid += len(src_rows)
        shifts = pd.concat([shifts, src_rows], ignore_index=True)

    shifts.to_csv(OUT / "shifts.csv", index=False)
    hol.to_csv(OUT / "public_holidays.csv", index=False)

    # 4. notes: keep the ones whose shift still exists (the Thursday clones
    #    carry no notes — that's fine, note coverage is ~24% anyway)
    notes = pd.read_csv(SRC / "shift_notes.csv", dtype=str)
    notes = notes[notes["shift_id"].isin(set(shifts["shift_id"]))]
    notes.to_csv(OUT / "shift_notes.csv", index=False)

    # 5. regenerate weekly_summary from the shifted shifts, same hours rule
    from pipeline.hours import weekly_hours
    from pipeline.load import load_export

    exp = load_export(str(OUT))
    from pipeline.hours import shift_frame

    wk = weekly_hours(shift_frame(exp), by="employee_id")
    wk = wk.rename(columns={"week_start": "week_starting"})
    wk["week_starting"] = wk["week_starting"].astype(str)
    wk[["employee_id", "week_starting", "total_hours", "overtime_hours",
        "breached"]].to_csv(OUT / "weekly_summary.csv", index=False)

    print(f"wrote {OUT}/  ({len(shifts)} shifts, newest week through "
          f"{cutoff_day.strftime('%A %d %b')})")

    if "--broken" in sys.argv:
        OUT_BROKEN.mkdir(parents=True, exist_ok=True)
        for name in CSV_FILES:
            if name == "shifts.csv":
                bad = pd.read_csv(OUT / name, dtype=str).drop(columns=["clock_out_time"])
                bad.to_csv(OUT_BROKEN / name, index=False)
            else:
                (OUT_BROKEN / name).write_bytes((OUT / name).read_bytes())
        print(f"wrote {OUT_BROKEN}/  (shifts.csv missing clock_out_time — "
              f"should fail validation loudly)")


if __name__ == "__main__":
    build()
