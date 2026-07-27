#!/usr/bin/env python3
"""Compare JSON Schema structural validation with Protocol 1.2.0.

This is not a comparison against SHACL, SACM, GSN, PROV-O, OPA, in-toto/SLSA,
or expert review. It demonstrates that a standard Draft 2020-12 JSON Schema
checks declared document shape, while the local prototype also applies its
author-proposed profile, manifest and claim/evidence-binding rules.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from build_provenance_fixture import build
from protocol_engine import classify_claim_file
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "required_gates.json"
SCHEMA = json.loads((ROOT / "configs" / "claim_object_schema.json").read_text(encoding="utf-8"))


def json_schema_check(claim: dict[str, Any]) -> bool:
    """Draft 2020-12 structural validation without registry or file semantics."""
    return not list(Draft202012Validator(SCHEMA).iter_errors(claim))


def _save_claim(path: Path, claim: dict[str, Any]) -> None:
    path.write_text(json.dumps(claim, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _save_manifest(path: Path, claim: dict[str, Any], manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    claim["evidence_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def run(output_dir: Path) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with TemporaryDirectory() as temporary:
        fixture = Path(temporary) / "fixture"
        claim_path, manifest_path = build(fixture)

        def evaluate(name: str, mutate) -> None:
            local_claim = json.loads(claim_path.read_text(encoding="utf-8"))
            local_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            local_dir = Path(temporary) / name
            local_dir.mkdir()
            copied_claim = local_dir / "claim.json"
            copied_manifest = local_dir / "manifest.json"
            for item in fixture.iterdir():
                if item.is_file():
                    (local_dir / item.name).write_bytes(item.read_bytes())
                elif item.is_dir():
                    (local_dir / item.name).mkdir()
                    for child in item.iterdir():
                        (local_dir / item.name / child.name).write_bytes(child.read_bytes())
            mutate(local_claim, local_manifest, local_dir)
            _save_manifest(copied_manifest, local_claim, local_manifest)
            _save_claim(copied_claim, local_claim)
            result = classify_claim_file(copied_claim, REGISTRY, copied_manifest)
            rows.append({
                "constructed_case": name,
                "json_schema_accepts": str(json_schema_check(local_claim)).lower(),
                "protocol_overall_state": result.state.value,
                "protocol_primary_audit_tag": result.audit_tags[0] if result.audit_tags else "",
                "interpretation": "Constructed local-record test; not a comparison with an assurance standard, policy engine, provenance framework or expert review.",
            })

        evaluate("complete_record", lambda claim, manifest, directory: None)
        evaluate(
            "caller_omits_profile_gate",
            lambda claim, manifest, directory: claim["declared_required_gates"]["validity"].remove("runtime_provenance_status"),
        )
        evaluate(
            "wrong_claim_gate_binding",
            lambda claim, manifest, directory: claim["evidence_adjudications"]["substantive"]["benefit_threshold"]["claim_binding"].update({"gate": "substantive.other"}),
        )
        evaluate(
            "path_traversal",
            lambda claim, manifest, directory: manifest["evidence"][claim["evidence_adjudications"]["validity"]["continuous_duration"]["evidence_id"]].update({"path": "../outside.txt"}),
        )
        evaluate(
            "manifest_sequence_rollback",
            lambda claim, manifest, directory: manifest.update({"sequence": 0}),
        )
    output = output_dir / "jsonschema_comparison.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "scope": "Constructed Draft 2020-12 JSON Schema comparison, not a benchmark against SHACL, SACM, GSN, PROV-O, OPA, in-toto/SLSA or expert review.",
        "json_schema_baseline": "Checks declared document shape only; does not derive author-proposed profile gates or verify local files, bindings, review roles, manifest sequence or local tokens.",
        "cases": len(rows),
        "json_schema_accepted": sum(row["json_schema_accepts"] == "true" for row in rows),
        "protocol_downgraded": sum(row["protocol_overall_state"] != "locally_provenance_complete_evidence_not_independently_validated" for row in rows),
    }
    (output_dir / "jsonschema_comparison_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return rows


if __name__ == "__main__":
    run(ROOT / "results")
