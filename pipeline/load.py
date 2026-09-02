"""Load and validate a client export directory.

The client sends the same seven CSVs every week: same names, same columns, a
later week, different rows (README requirement 4). This module is the front
door: it checks the shape of what arrived and fails loudly with a readable
message if something is off, so loading a new week never needs a developer.

The newest week in an export may be **partial** -- data through Wednesday,
Friday, whatever. That is expected and fine; the prediction reads how far the
week runs (`hours.latest_cutoff_dow`) and fits to that day. Nothing here needs
to know the cutoff -- it just loads the rows.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd

# filename -> columns we require to be present (extra columns are tolerated)
REQUIRED_COLUMNS: dict[str, set[str]] = {
    "employees": {
        "employee_id", "full_name", "id_number", "role",
        "primary_site_id", "shift_pattern", "contract_ordinary_hours",
        "employment_type",
    },
    "shifts": {
        "shift_id", "employee_id", "site_id", "shift_date",
        "clock_in_time", "clock_out_time",
    },
    "sites": {"site_id", "site_name", "province"},
    "shift_notes": {"shift_id", "logged_by", "note"},
    "public_holidays": {"date", "name"},
    "weekly_summary": {
        "employee_id", "week_starting", "total_hours",
        "overtime_hours", "breached",
    },
    "payroll_details": {
        "employee_id", "full_name", "id_number", "bank_name", "branch_code",
        "account_number", "account_type", "tax_number", "hourly_rate",
        "pay_frequency",
    },
}

# weekly_summary is a convenience export from the client's system; we can
# recompute everything it holds, so a fresh drop is allowed to omit it.
OPTIONAL_FILES = {"weekly_summary"}


class ExportError(ValueError):
    """Raised when an export directory is missing files or columns."""


@dataclasses.dataclass
class Export:
    """A validated client export. Frames are raw (all-string) — parsing and
    typing happen downstream so this stays a pure I/O + shape check."""

    employees: pd.DataFrame
    shifts: pd.DataFrame
    sites: pd.DataFrame
    shift_notes: pd.DataFrame
    public_holidays: pd.DataFrame
    payroll_details: pd.DataFrame
    weekly_summary: pd.DataFrame | None
    source_dir: Path

    def summary(self) -> str:
        parts = [
            f"{len(self.employees)} employees",
            f"{len(self.sites)} sites",
            f"{len(self.shifts)} shifts",
            f"{len(self.shift_notes)} notes",
            f"{len(self.public_holidays)} public holidays",
        ]
        if self.weekly_summary is not None:
            parts.append(f"{len(self.weekly_summary)} weekly-summary rows")
        return ", ".join(parts)


def _read_csv(path: Path) -> pd.DataFrame:
    # dtype=str: keep everything as text so nothing is silently coerced
    # (leading zeros in codes, blank clock-outs, etc.). Typing is downstream.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_export(directory: str | Path) -> Export:
    """Load and validate an export directory. Raises ExportError on any
    missing file or missing required column, listing every problem at once."""
    directory = Path(directory)
    if not directory.is_dir():
        raise ExportError(f"not a directory: {directory}")

    problems: list[str] = []
    frames: dict[str, pd.DataFrame | None] = {}

    for name, required in REQUIRED_COLUMNS.items():
        path = directory / f"{name}.csv"
        if not path.exists():
            if name in OPTIONAL_FILES:
                frames[name] = None
                continue
            problems.append(f"missing file: {name}.csv")
            continue
        df = _read_csv(path)
        missing = required - set(df.columns)
        if missing:
            problems.append(
                f"{name}.csv is missing column(s): {', '.join(sorted(missing))}"
            )
        frames[name] = df

    if problems:
        raise ExportError(
            "export at %s is not usable:\n  - %s"
            % (directory, "\n  - ".join(problems))
        )

    export = Export(source_dir=directory, **frames)  # type: ignore[arg-type]
    _sanity_checks(export)
    return export


def _sanity_checks(export: Export) -> None:
    """Cross-file checks that would quietly corrupt results if ignored.
    These warn rather than raise — a real export has some mess (see
    data_checks.md) and we want it to load anyway."""
    warnings: list[str] = []

    emp_ids = set(export.employees["employee_id"])
    orphan_shifts = set(export.shifts["employee_id"]) - emp_ids
    if orphan_shifts:
        warnings.append(
            f"{len(orphan_shifts)} employee_id(s) in shifts.csv not in "
            f"employees.csv (e.g. {sorted(orphan_shifts)[:3]})"
        )

    site_ids = set(export.sites["site_id"])
    orphan_sites = set(export.shifts["site_id"]) - site_ids
    if orphan_sites:
        warnings.append(
            f"{len(orphan_sites)} site_id(s) in shifts.csv not in sites.csv"
        )

    shift_ids = set(export.shifts["shift_id"])
    orphan_notes = set(export.shift_notes["shift_id"]) - shift_ids
    if orphan_notes:
        warnings.append(
            f"{len(orphan_notes)} shift_id(s) in shift_notes.csv not in shifts.csv"
        )

    if export.shifts["shift_id"].duplicated().any():
        n = int(export.shifts["shift_id"].duplicated().sum())
        warnings.append(f"{n} duplicate shift_id(s) in shifts.csv")

    for w in warnings:
        print(f"  [load] warning: {w}")


if __name__ == "__main__":
    import sys

    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    exp = load_export(d)
    print(f"loaded {exp.source_dir}: {exp.summary()}")
