#!/usr/bin/env python3
"""Build a deterministic local-provenance fixture for Protocol 1.2.0 tests.

The fixture is intentionally synthetic. Its purpose is to exercise file binding,
timestamp, authorization, role, revocation, and claim-binding checks; it is not
scientific energy evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from protocol_engine import GATE_FAMILIES, load_gate_registry


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def required_role(registry: dict[str, Any], family: str, gate: str) -> str:
    return registry["required_reviewer_roles"].get(
        f"{family}.{gate}", registry["required_reviewer_roles"][f"{family}.*"]
    )


def build(destination: Path, level: str = "L1") -> tuple[Path, Path]:
    """Create one complete synthetic record at the requested evidence profile."""
    registry = load_gate_registry(ROOT / "configs" / "required_gates.json")
    if level not in registry["levels"]:
        raise ValueError(f"Unknown synthetic fixture profile: {level}")
    claim_id = f"synthetic-provenance-complete-{level.lower()}"
    destination.mkdir(parents=True, exist_ok=True)
    evidence_dir = destination / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    token_path = destination / "local_integrity_token.txt"
    token_path.write_text("Synthetic locally pinned integrity token; not a cryptographic signature.\n", encoding="utf-8")
    evidence: dict[str, Any] = {}
    authorizations: dict[str, Any] = {}
    gates: dict[str, Any] = {family: {} for family in GATE_FAMILIES}
    adjudications: dict[str, Any] = {family: {} for family in GATE_FAMILIES}
    for family in GATE_FAMILIES:
        for gate in registry["levels"][level][family]:
            gate_key = f"{family}.{gate}"
            evidence_id = f"demo:{gate_key}"
            filename = f"{family}__{gate}.txt"
            evidence_path = evidence_dir / filename
            evidence_path.write_text(
                f"Synthetic local provenance fixture for {claim_id}; {gate_key}.\n",
                encoding="utf-8",
            )
            role = required_role(registry, family, gate)
            reviewer_id = f"reviewer_{role}"
            authorization_id = f"authorization:{role}"
            authorizations[authorization_id] = {
                "reviewer_id": reviewer_id, "role": role, "status": "active",
            }
            evidence[evidence_id] = {
                "path": (Path("evidence") / filename).as_posix(),
                "sha256": sha256(evidence_path),
                "version": "demo", "status": "active",
                "expires_at_utc": "2027-07-01T00:00:00Z",
                "permitted_gates": [gate_key], "permitted_claim_ids": [claim_id],
            }
            gates[family][gate] = {"status": "pass"}
            adjudications[family][gate] = {
                "disposition": "attested", "evidence_id": evidence_id,
                "evidence_version": "demo", "evidence_sha256": sha256(evidence_path),
                "reviewed_at_utc": "2026-06-01T00:00:00Z", "reviewer_id": reviewer_id,
                "reviewer_role": role, "reviewer_authorization_id": authorization_id,
                "conflict_declaration": "none",
                "claim_binding": {
                    "claim_id": claim_id, "evidence_profile": level, "gate": gate_key,
                },
            }
    manifest = {
        "manifest_id": "synthetic-provenance-demo-manifest",
        "manifest_version": "1.2.0",
        "sequence": 1,
        "created_at_utc": "2026-05-01T00:00:00Z",
        "local_integrity_token": {
            "path": "local_integrity_token.txt",
            "sha256": sha256(token_path),
        },
        "evidence": evidence, "authorized_reviewers": authorizations,
    }
    manifest_path = destination / "evidence_manifest.json"
    write_json(manifest_path, manifest)
    claim = {
        "id": claim_id,
        "statement": "Synthetic L1 provenance-completeness record; no physical energy statement.",
        "evidence_profile": level,
        "boundary": {
            "energy": "Synthetic local-provenance fixture; no physical meter claim.",
            "service": "Synthetic test record only.",
            "exclusions": [
                "scientific evidence validation", "physical energy", "deployment outcome",
            ],
        },
        "functional_unit": "synthetic fixed technical unit",
        "threshold_rationale": {"status": "test only"},
        "declared_required_gates": registry["levels"][level],
        "gates": gates, "evidence_adjudications": adjudications,
        "permitted_wording": "Locally provenance-complete only; evidence not independently validated.",
        "claim_owner_id": "claim_owner",
        "assessment_time_utc": "2026-07-01T00:00:00Z",
        "evidence_manifest_id": manifest["manifest_id"],
        "evidence_manifest_sha256": sha256(manifest_path),
        "evidence_manifest_version": manifest["manifest_version"],
        "minimum_manifest_sequence": manifest["sequence"],
        "local_integrity_token_sha256": manifest["local_integrity_token"]["sha256"],
    }
    claim_path = destination / "claim.json"
    write_json(claim_path, claim)
    return claim_path, manifest_path


if __name__ == "__main__":
    claim_file, manifest_file = build(ROOT / "examples" / "provenance_demo")
    print(json.dumps({"claim": str(claim_file), "manifest": str(manifest_file)}, indent=2))
