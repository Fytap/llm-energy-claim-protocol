#!/usr/bin/env python3
"""Run documented source mutations against the Protocol v1.2.0 test suite."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "protocol_engine.py"
TEST = ROOT / "scripts" / "test_protocol_engine.py"
BUILDER = ROOT / "scripts" / "build_provenance_fixture.py"

MUTATIONS = {
    "schema_errors_bypass": ("if schema_errors:", "if False:"),
    "manifest_identity_bypass": ('if claim["evidence_manifest_id"] != manifest.get("manifest_id"):', "if False:"),
    "manifest_digest_bypass": ('if claim["evidence_manifest_sha256"] != _sha256_path(Path(manifest_path)):', "if False:"),
    "manifest_version_bypass": ('if claim["evidence_manifest_version"] != manifest.get("manifest_version"):', "if False:"),
    "sequence_rollback_bypass": ('manifest.get("sequence", -1) < claim["minimum_manifest_sequence"]', "False"),
    "integrity_token_bypass": ("if token_tags:", "if False:"),
    "declared_gate_mismatch_bypass": ("if declaration_tags:", "if False:"),
    "provenance_failure_bypass": ("if provenance_tags:", "if False:"),
    "validity_failure_bypass": ("if invalid_validity:", "if False:"),
    "missing_substantive_bypass": ("if missing_substantive:", "if False:"),
    "substantive_failure_bypass": ("if failed_substantive:", "if False:"),
    "precision_failure_bypass": ("if nonpass_precision:", "if False:"),
    "copied_digest_bypass": ("if prior_id is not None and prior_id != evidence_id:", "if False:"),
    "self_review_bypass": ('if reviewer_id == claim["claim_owner_id"]:', "if False:"),
    "wrong_role_bypass": ('if raw.get("reviewer_role") != required_role:', "if False:"),
}


def main() -> None:
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        for name, (needle, replacement) in MUTATIONS.items():
            scripts = scratch / name / "scripts"
            configs = scratch / name / "configs"
            scripts.mkdir(parents=True)
            configs.mkdir()
            for source in (ENGINE, TEST, BUILDER):
                shutil.copy2(source, scripts / source.name)
            shutil.copy2(ROOT / "configs" / "required_gates.json", configs / "required_gates.json")
            shutil.copy2(ROOT / "configs" / "claim_object_schema.json", configs / "claim_object_schema.json")
            engine_path = scripts / ENGINE.name
            original = engine_path.read_text(encoding="utf-8")
            if original.count(needle) != 1:
                raise RuntimeError(f"Mutation token not unique for {name}: {needle!r}")
            engine_path.write_text(original.replace(needle, replacement, 1), encoding="utf-8")
            run = subprocess.run(
                ["python", "-m", "unittest", "-q", TEST.name], cwd=scripts,
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            rows.append({"mutation": name, "operator": f"{needle} -> {replacement}", "killed": run.returncode != 0, "returncode": run.returncode})
    report = {
        "scope": "Deterministic source mutations of parser, state-priority, and local-provenance branches; not a formal mutation-certification claim.",
        "mutants": rows,
        "killed": sum(row["killed"] for row in rows),
        "total": len(rows),
        "equivalent_mutants_identified": [],
        "mutation_score": sum(row["killed"] for row in rows) / len(rows),
    }
    output = ROOT / "results" / "program_mutation_score.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
