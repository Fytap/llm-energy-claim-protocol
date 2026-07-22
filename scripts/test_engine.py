#!/usr/bin/env python3
"""Tests for schema- and registry-driven current release claim classification."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from engine import (
    ClaimState,
    classify_claim_file,
    classify_claim_object,
    load_gate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_gate_registry(ROOT / "configs" / "required_gates.json")


def load_claim(name: str) -> dict:
    return json.loads((ROOT / "claims" / name).read_text(encoding="utf-8"))


class RegistryDrivenClaimEngineTests(unittest.TestCase):
    def test_h2_complete_registered_object_is_supported(self):
        result = classify_claim_object(load_claim("simulation_case.json"), REGISTRY)
        self.assertEqual(result.state, ClaimState.SUPPORTED)
        self.assertEqual(result.display_state, "Supported-L0 under the declared boundary")
        self.assertEqual(result.to_dict()["state"], ClaimState.SUPPORTED.value)

    def test_claim_file_entry_point_matches_object_entry_point(self):
        result = classify_claim_file(ROOT / "claims" / "simulation_case.json", ROOT / "configs" / "required_gates.json")
        self.assertEqual(result.state, ClaimState.SUPPORTED)

    def test_non_object_root_is_not_assessable(self):
        result = classify_claim_object([], REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("schema:root_not_object", result.audit_tags)

    def test_unknown_level_is_not_assessable(self):
        claim = load_claim("simulation_case.json")
        claim["evidence_profile"] = "L99"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("schema:unknown_evidence_profile='L99'", result.audit_tags)

    def test_empty_gate_sets_are_not_assessable(self):
        claim = load_claim("telemetry_case_b.json")
        claim["declared_required_gates"] = {"validity": [], "substantive": [], "precision": []}
        claim["gates"] = {"validity": {}, "substantive": {}, "precision": {}}
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertTrue(any("omitted" in tag for tag in result.audit_tags))

    def test_omitted_required_validity_gate_is_not_assessable(self):
        claim = load_claim("telemetry_case_b.json")
        del claim["gates"]["validity"]["runtime_provenance_status"]
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("validity:runtime_provenance_status=not_submitted", result.audit_tags)

    def test_empty_boundary_is_not_assessable(self):
        claim = load_claim("telemetry_case_b.json")
        claim["boundary"] = {}
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertTrue(any(tag.startswith("schema:boundary") for tag in result.audit_tags))

    def test_boundary_field_and_exclusion_contracts_are_enforced(self):
        for field, value in (("energy", ""), ("service", ""), ("exclusions", [])):
            claim = load_claim("telemetry_case_b.json")
            claim["boundary"][field] = value
            result = classify_claim_object(claim, REGISTRY)
            self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)

    def test_missing_provenance_is_not_assessable_even_when_benefit_fails(self):
        result = classify_claim_object(load_claim("telemetry_case_b.json"), REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("substantive:benefit_threshold=fail", result.audit_tags)

    def test_p3_actual_claim_object_is_not_assessable(self):
        result = classify_claim_object(load_claim("telemetry_case_a.json"), REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("validity:continuous_duration=invalid", result.audit_tags)

    def test_p4_actual_claim_object_is_not_assessable_for_design_integrity(self):
        result = classify_claim_object(load_claim("telemetry_case_b.json"), REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("validity:design_integrity=invalid", result.audit_tags)
        self.assertIn("validity:mapping_period_separability=invalid", result.audit_tags)

    def test_invalid_status_is_not_assessable(self):
        claim = load_claim("telemetry_case_b.json")
        claim["gates"]["validity"]["telemetry_gap"]["status"] = "maybe"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("validity:telemetry_gap=invalid_status", result.audit_tags)

    def test_missing_schema_field_is_not_assessable(self):
        claim = load_claim("simulation_case.json")
        del claim["functional_unit"]
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("schema:missing_field=functional_unit", result.audit_tags)

    def test_empty_required_text_fields_are_not_assessable(self):
        for field in ("id", "statement", "functional_unit", "permitted_wording"):
            claim = load_claim("simulation_case.json")
            claim[field] = ""
            result = classify_claim_object(claim, REGISTRY)
            self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
            self.assertTrue(any(field in tag for tag in result.audit_tags))

    def test_invalid_declared_or_submitted_gate_container_is_not_assessable(self):
        for field, value in (("declared_required_gates", []), ("gates", [])):
            claim = load_claim("telemetry_case_b.json")
            claim[field] = value
            result = classify_claim_object(claim, REGISTRY)
            self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)

    def test_required_gate_declaration_cannot_add_unregistered_gate(self):
        claim = load_claim("simulation_case.json")
        claim["declared_required_gates"]["validity"].append("caller_defined_gate")
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("required_gate_declaration:validity:unregistered=caller_defined_gate", result.audit_tags)

    def test_submitted_unregistered_gate_is_audited_without_changing_registry_minimum(self):
        claim = load_claim("simulation_case.json")
        claim["gates"]["validity"]["caller_defined_gate"] = {"status": "pass"}
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.SUPPORTED)
        self.assertIn("validity:unregistered_gate=caller_defined_gate", result.audit_tags)

    def test_missing_substantive_data_is_not_assessable(self):
        claim = load_claim("simulation_case.json")
        claim["gates"]["substantive"]["numerical_stability_statement"]["status"] = "missing"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)

    def test_valid_substantive_failure_is_contradicted(self):
        claim = load_claim("simulation_case.json")
        claim["gates"]["substantive"]["numerical_stability_statement"]["status"] = "fail"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.CONTRADICTED)
        self.assertEqual(result.display_state, "Contradicted under the declared boundary")

    def test_precision_failure_is_inconclusive(self):
        claim = load_claim("simulation_case.json")
        claim["gates"]["precision"]["integration_sensitivity_reported"]["status"] = "fail"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.INCONCLUSIVE)
        self.assertEqual(result.display_state, "Inconclusive due to precision or replication")

    def test_validity_failure_has_priority_over_substantive_contradiction(self):
        claim = load_claim("telemetry_case_b.json")
        claim["gates"]["validity"]["runtime_provenance_status"]["status"] = "pass"
        claim["gates"]["validity"]["design_integrity"]["status"] = "pass"
        claim["gates"]["validity"]["mapping_period_separability"]["status"] = "pass"
        claim["gates"]["validity"]["continuous_duration"]["status"] = "invalid"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("substantive:benefit_threshold=fail", result.audit_tags)

    def test_inference_mismatch_is_inconclusive_after_validity_passes(self):
        claim = load_claim("telemetry_case_b.json")
        for gate in claim["gates"]["validity"].values():
            gate["status"] = "pass"
        for gate in claim["gates"]["substantive"].values():
            gate["status"] = "pass"
        for gate in claim["gates"]["precision"].values():
            gate["status"] = "pass"
        claim["gates"]["precision"]["dependence_compatible_interval"]["status"] = "invalid"
        result = classify_claim_object(claim, REGISTRY)
        self.assertEqual(result.state, ClaimState.INCONCLUSIVE)
        self.assertIn("precision:dependence_compatible_interval=invalid", result.audit_tags)


if __name__ == "__main__":
    unittest.main(verbosity=2)
