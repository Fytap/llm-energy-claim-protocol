#!/usr/bin/env python3
"""Produce executable-quality records for Protocol v1.2.0."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUTPUT = ROOT / "results"


def execute(command: list[str]) -> str:
    result = subprocess.run(command, cwd=SCRIPTS, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout)
    return result.stdout


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    coverage_file = OUTPUT / ".coverage"
    test_output = execute([sys.executable, "-m", "coverage", "run", "--branch", f"--data-file={coverage_file}", "-m", "unittest", "-q", "test_protocol_engine.py", "test_decision_policy.py"])
    execute([sys.executable, "-m", "coverage", "json", f"--data-file={coverage_file}", "-o", str(OUTPUT / "coverage.json")])
    execute([sys.executable, "fuzz_records.py"])
    execute([sys.executable, "mutation_score.py"])
    coverage = json.loads((OUTPUT / "coverage.json").read_text(encoding="utf-8"))
    engine_key = next(key for key in coverage["files"] if key.endswith("protocol_engine.py"))
    engine = coverage["files"][engine_key]["summary"]
    report = {
        "scope": "Executable quality audit of parser, state-transition, metamorphic, local-provenance, and malformed-input branches.",
        "unit_test_output": test_output.strip(),
        "statement_coverage_percent": engine["percent_statements_covered"],
        "branch_coverage_percent": engine["percent_branches_covered"],
        "branch_coverage_enabled": True,
        "input_mutation": "property_fuzz.json",
        "program_mutation": "program_mutation_score.json",
        "limit": "Coverage and mutation scores do not validate scientific evidence, people, meters, signatures, or external provenance.",
    }
    (OUTPUT / "quality_audit_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
