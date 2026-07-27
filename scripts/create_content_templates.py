#!/usr/bin/env python3
"""Generate blank independent content-validity materials from the proposed registry.

The generated files contain no ratings and do not constitute a content-validity
study. They are intended for a separately administered 5-10 reviewer exercise.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "required_gates.json"


def run(output_dir: Path) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for profile, families in registry["levels"].items():
        for family, gates in families.items():
            for gate in gates:
                rows.append({
                    "reviewer_code": "",
                    "expertise_category": "",
                    "years_relevant_experience": "",
                    "registry_version": registry["protocol_version"],
                    "profile": profile,
                    "family": family,
                    "gate": gate,
                    "relevance_1_to_4": "",
                    "clarity_1_to_4": "",
                    "necessity": "",
                    "profile_assignment": "",
                    "comment": "",
                })
    with (output_dir / "REGISTRY_GATE_SCORECARD.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output_dir / "PANEL_AUDIT_LOG.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "event", "date_utc", "responsible_role", "reference_or_digest", "notes",
        ])
        writer.writeheader()
        writer.writerows([
            {"event": "institutional_ethics_or_nonhuman_determination", "date_utc": "", "responsible_role": "", "reference_or_digest": "", "notes": ""},
            {"event": "recruitment_opened", "date_utc": "", "responsible_role": "", "reference_or_digest": "", "notes": ""},
            {"event": "registry_digest_frozen", "date_utc": "", "responsible_role": "", "reference_or_digest": "", "notes": ""},
            {"event": "analysis_frozen", "date_utc": "", "responsible_role": "", "reference_or_digest": "", "notes": ""},
        ])
    with (output_dir / "REGISTRY_AMENDMENT_LOG.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "gate_profile", "panel_evidence", "proposed_change", "author_disposition", "rationale", "old_registry_digest", "new_registry_digest", "new_panel_round_required",
        ])
        writer.writeheader()


if __name__ == "__main__":
    run(ROOT / "templates" / "generated")
