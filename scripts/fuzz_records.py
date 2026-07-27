#!/usr/bin/env python3
"""Property-fuzz malformed local records for Protocol v1.2.0.

The generator uses equal-probability selection from fifteen documented single
mutations. The oracle is deliberately structural: every deliberately malformed
record must avoid the locally-provenance-complete state and must not crash the
classifier. This test does not judge the scientific truth of any evidence.
"""

from __future__ import annotations

import copy
import json
import random
import tempfile
from pathlib import Path

from build_provenance_fixture import build
from protocol_engine import ClaimState, classify_claim_object, load_gate_registry


ROOT = Path(__file__).resolve().parents[1]
SEED = 20260721
RUNS = 2_000


def mutate(claim: dict, rng: random.Random) -> str:
    """Apply one uniformly selected invalidity mutation and return its label."""
    choice = rng.randrange(15)
    if choice == 0:
        claim["evidence_profile"] = "L99"; return "unknown_profile"
    if choice == 1:
        claim["boundary"] = {}; return "empty_boundary"
    if choice == 2:
        claim["gates"] = []; return "invalid_gates_container"
    if choice == 3:
        claim["evidence_adjudications"]["validity"]["telemetry_gap"] = {}; return "empty_attestation"
    if choice == 4:
        claim["declared_required_gates"]["precision"] = []; return "omitted_precision"
    if choice == 5:
        claim["evidence_adjudications"]["validity"]["telemetry_gap"]["evidence_id"] = "forged"; return "forged_id"
    if choice == 6:
        claim["evidence_adjudications"]["validity"]["telemetry_gap"]["reviewer_id"] = claim["claim_owner_id"]; return "self_review"
    if choice == 7:
        claim["assessment_time_utc"] = "not-a-date"; return "invalid_time"
    if choice == 8:
        claim["evidence_manifest_sha256"] = "0" * 64; return "manifest_digest"
    if choice == 9:
        claim["evidence_manifest_version"] = "0.0.0"; return "manifest_version"
    if choice == 10:
        claim["minimum_manifest_sequence"] = 2; return "manifest_rollback"
    if choice == 11:
        claim["local_integrity_token_sha256"] = "0" * 64; return "integrity_token_mismatch"
    if choice == 12:
        claim["gates"]["validity"]["continuous_duration"]["status"] = "maybe"; return "invalid_status"
    if choice == 13:
        claim["threshold_rationale"] = {}; return "empty_threshold_rationale"
    claim["declared_required_gates"]["validity"].append("unregistered_gate"); return "unregistered_gate"


def main() -> None:
    registry = load_gate_registry(ROOT / "configs" / "required_gates.json")
    outcomes: dict[str, int] = {}
    crashes, positive_malformed = 0, 0
    with tempfile.TemporaryDirectory() as directory:
        claim_path, manifest_path = build(Path(directory) / "fixture")
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rng = random.Random(SEED)
        for _ in range(RUNS):
            specimen = copy.deepcopy(claim)
            mutation = mutate(specimen, rng)
            outcomes[mutation] = outcomes.get(mutation, 0) + 1
            try:
                result = classify_claim_object(specimen, registry, manifest, manifest_path)
                if result.state is ClaimState.PROVENANCE_COMPLETE:
                    positive_malformed += 1
            except Exception:
                crashes += 1
    report = {
        "scope": "Equal-probability malformed-input structural fuzzing; it does not validate scientific evidence.",
        "runs": RUNS,
        "seed": SEED,
        "generator": "One uniformly selected single mutation from the fifteen listed labels per record.",
        "oracle": "Malformed record must not return locally_provenance_complete and must not crash.",
        "crashes": crashes,
        "positive_malformed_records": positive_malformed,
        "mutation_counts": outcomes,
    }
    output = ROOT / "results" / "property_fuzz.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
