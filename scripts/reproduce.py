#!/usr/bin/env python3
"""One-command reproduction entry point for Protocol 1.2.0."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
RESULTS = ROOT / "results"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=SCRIPTS)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    run("verify_manifest.py")
    run("build_provenance_fixture.py")
    run("quality_audit.py")
    run("schema_contrast.py")
    run("create_content_templates.py")
    run("statistical_stress.py")
    run("simulate_composite_null.py", "--output-dir", str(RESULTS))
    run("simulate_attestation_error.py", "--output-dir", str(RESULTS))
    run("simulate_direction_guard.py", "--output-dir", str(RESULTS))
    run(
        "simulate_model_based_ar1.py", "--output-dir", str(RESULTS),
        "--iterations", "100000", "--seed", "20260720",
    )
    run(
        "plot_protocol_evidence.py", "--results-dir", str(RESULTS),
        "--output", str(RESULTS / "figure2_protocol_evidence.pdf"),
    )
    run(
        "plot_execution_summary.py", "--results-dir", str(RESULTS),
        "--output", str(RESULTS / "figure3_execution_summary.pdf"),
    )
    quality = json.loads((RESULTS / "quality_audit_summary.json").read_text(encoding="utf-8"))
    report = {
        "status": "pass",
        "protocol": "1.2.0",
        "entry_point": "python scripts/reproduce.py",
        "quality_audit": quality,
        "interpretation": (
            "The run reproduces local-record structural checks, a constructed schema baseline, "
            "and synthetic planning studies. It does not independently validate scientific evidence, "
            "people, meters, signatures, or physical energy and carbon claims."
        ),
    }
    (RESULTS / "reproduction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
