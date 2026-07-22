#!/usr/bin/env python3
"""Deterministic input-mutation checks for the retained evaluator.

This is not a formal proof over all Python objects.  It exercises the published
schema/registry contract with reproducible malformed, incomplete and adversarial
claim-object mutations and asserts the safety property actually tested here:
none of these mutations may be promoted to a supported or contradicted state.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from engine import ClaimState, classify_claim_object, load_gate_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_gate_registry(ROOT / "configs" / "required_gates.json")


def load_claim() -> dict:
    return json.loads((ROOT / "claims" / "telemetry_case_b.json").read_text(encoding="utf-8"))


def mutations() -> list[tuple[str, dict]]:
    base = load_claim()
    cases: list[tuple[str, dict]] = []

    def add(name: str, transform) -> None:
        candidate = copy.deepcopy(base)
        transform(candidate)
        cases.append((name, candidate))

    add("unknown_profile", lambda item: item.__setitem__("evidence_profile", "L99"))
    add("empty_boundary", lambda item: item.__setitem__("boundary", {}))
    add("boundary_not_object", lambda item: item.__setitem__("boundary", []))
    add("empty_energy_boundary", lambda item: item["boundary"].__setitem__("energy", ""))
    add("empty_service_boundary", lambda item: item["boundary"].__setitem__("service", ""))
    add("empty_exclusions", lambda item: item["boundary"].__setitem__("exclusions", []))
    add("missing_statement", lambda item: item.pop("statement"))
    add("missing_functional_unit", lambda item: item.pop("functional_unit"))
    add("missing_permitted_wording", lambda item: item.pop("permitted_wording"))
    add("missing_threshold_rationale", lambda item: item.pop("threshold_rationale"))
    add("threshold_rationale_empty", lambda item: item.__setitem__("threshold_rationale", {}))
    add("declared_gate_families_empty", lambda item: item.__setitem__("declared_required_gates", {}))
    add("submitted_gate_families_empty", lambda item: item.__setitem__("gates", {}))
    add("declared_validity_omitted", lambda item: item["declared_required_gates"].__setitem__("validity", []))
    add("declared_substantive_omitted", lambda item: item["declared_required_gates"].__setitem__("substantive", []))
    add("declared_precision_omitted", lambda item: item["declared_required_gates"].__setitem__("precision", []))
    add("submitted_validity_omitted", lambda item: item["gates"].__setitem__("validity", {}))
    add("submitted_substantive_omitted", lambda item: item["gates"].__setitem__("substantive", {}))
    add("submitted_precision_omitted", lambda item: item["gates"].__setitem__("precision", {}))
    add("invalid_gate_status", lambda item: item["gates"]["validity"]["runtime_provenance_status"].__setitem__("status", "maybe"))
    add("missing_provenance_gate", lambda item: item["gates"]["validity"].pop("runtime_provenance_status"))
    add("unregistered_declared_gate", lambda item: item["declared_required_gates"]["validity"].append("adversarial_gate"))
    add("gates_not_object", lambda item: item.__setitem__("gates", []))
    add("declared_gates_not_object", lambda item: item.__setitem__("declared_required_gates", []))
    return cases


def main() -> None:
    results: list[dict[str, object]] = []
    states = Counter()
    for name, candidate in mutations():
        result = classify_claim_object(candidate, REGISTRY)
        states[result.state.value] += 1
        if result.state in (ClaimState.SUPPORTED, ClaimState.CONTRADICTED):
            raise AssertionError(f"Unsafe promotion for mutation {name}: {result.to_dict()}")
        results.append({"mutation": name, "state": result.state.value, "audit_tags": list(result.audit_tags)})
    output = ROOT / "results" / "input_mutations.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "scope": "Deterministic input-mutation suite; not a formal proof.",
                "mutations": len(results),
                "state_counts": dict(states),
                "results": results,
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"mutations": len(results), "state_counts": dict(states)}, indent=2))


if __name__ == "__main__":
    main()
