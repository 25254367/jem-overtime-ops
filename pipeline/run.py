"""One command, three outputs.

    python -m pipeline.run <export_dir> [<output_dir>]

Loads and validates the export, then writes (to the repo root by default):
    predictions.csv           the deliverable — employee_id, will_breach, risk_score
    note_classifications.csv  the deliverable — shift_id, category, note
    dashboard_data.json       feeds the dashboard (git-ignored; rebuilt on demand)

This is what "load next week's data" runs. Nothing else needs to change.
"""
from __future__ import annotations

import sys
from pathlib import Path

from .aggregate import write as write_dashboard
from .classify import note_classifications_csv
from .features import person_week_hours
from .load import load_export
from .predict import predictions_csv


def run(export_dir: str, output_dir: str = ".") -> dict:
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    export = load_export(export_dir)
    print(f"loaded {export.summary()}")

    weeks = sorted(person_week_hours(export)["week_start"].unique())
    target, history = weeks[-1], weeks[:-1]

    preds = predictions_csv(export, target, history)
    preds.to_csv(out / "predictions.csv", index=False)
    print(f"  predictions.csv       {len(preds)} rows, "
          f"{int(preds['will_breach'].sum())} flagged")

    notes = note_classifications_csv(export)
    notes.to_csv(out / "note_classifications.csv", index=False)
    print(f"  note_classifications.csv  {len(notes)} rows")

    data = write_dashboard(export, path=str(out / "dashboard_data.json"),
                           target_week=target, history_weeks=history)
    h = data["headline"]
    print(f"  dashboard_data.json   {h['n_breach_likely']} breach-likely, "
          f"{h['n_elevated']} elevated, ~R{h['projected_ot_cost_rand']:.0f} OT cost")
    return data


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ".")
