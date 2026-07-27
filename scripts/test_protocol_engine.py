#!/usr/bin/env python3
"""Unit, state-transition, metamorphic, and local-attack tests for Protocol v1.2.0."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_provenance_fixture import build
from protocol_engine import (
    Classification,
    ClaimState,
    GateResult,
    _attestation_tags,
    _component_statuses,
    _gate_status,
    _load_manifest,
    _parse_utc,
    _safe_relative_file,
    _schema_errors,
    classify_claim_file,
    classify_claim_object,
    load_gate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = load_gate_registry(ROOT / "configs" / "required_gates.json")


class LocalProvenanceEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.claim_path, self.manifest_path = build(Path(self.temp.name) / "fixture")
        self.claim = json.loads(self.claim_path.read_text(encoding="utf-8"))
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def classify(self):
        return classify_claim_file(
            self.claim_path,
            ROOT / "configs" / "required_gates.json",
            self.manifest_path,
        )

    def save_claim(self) -> None:
        self.claim_path.write_text(json.dumps(self.claim, indent=2) + "\n", encoding="utf-8")

    def save_manifest_and_update_claim_digest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        self.claim["evidence_manifest_sha256"] = hashlib.sha256(
            self.manifest_path.read_bytes()
        ).hexdigest()
        self.save_claim()

    def test_complete_local_record_is_provenance_complete(self):
        self.assertEqual(self.classify().state, ClaimState.PROVENANCE_COMPLETE)

    def test_unknown_profile_is_not_assessable(self):
        self.claim["evidence_profile"] = "L99"
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_empty_boundary_is_not_assessable(self):
        self.claim["boundary"] = {}
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_omitted_required_gate_is_not_assessable(self):
        self.claim["declared_required_gates"]["validity"].remove("runtime_provenance_status")
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_forged_evidence_id_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        row["evidence_id"] = "forged:not-in-manifest"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("evidence_id_not_in_manifest", " ".join(result.audit_tags))

    def test_stale_review_is_not_assessable(self):
        self.claim["evidence_adjudications"]["validity"]["continuous_duration"][
            "reviewed_at_utc"
        ] = "2019-01-01T00:00:00Z"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("review_timestamp_stale", " ".join(result.audit_tags))

    def test_changed_evidence_file_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        record = self.manifest["evidence"][row["evidence_id"]]
        (self.manifest_path.parent / record["path"]).write_text(
            "changed after attestation\n", encoding="utf-8"
        )
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("evidence_digest_mismatch", " ".join(result.audit_tags))

    def test_explicitly_authorized_evidence_reuse_across_two_gates_passes(self):
        source = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        target = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        target.update(copy.deepcopy(source))
        target["claim_binding"]["gate"] = "validity.telemetry_gap"
        self.manifest["evidence"][source["evidence_id"]]["permitted_gates"].append("validity.telemetry_gap")
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.PROVENANCE_COMPLETE)

    def test_self_review_is_not_assessable(self):
        self.claim["evidence_adjudications"]["validity"]["continuous_duration"][
            "reviewer_id"
        ] = "claim_owner"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("self_review_not_permitted", " ".join(result.audit_tags))

    def test_wrong_reviewer_role_is_not_assessable(self):
        self.claim["evidence_adjudications"]["precision"]["interval_rule"][
            "reviewer_role"
        ] = "service_owner_reviewer"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("wrong_reviewer_role", " ".join(result.audit_tags))

    def test_revoked_evidence_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        self.manifest["evidence"][row["evidence_id"]]["status"] = "revoked"
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("evidence_status='revoked'", " ".join(result.audit_tags))

    def test_revoked_authorization_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        self.manifest["authorized_reviewers"][row["reviewer_authorization_id"]][
            "status"
        ] = "revoked"
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("reviewer_authorization_not_active", " ".join(result.audit_tags))

    def test_binding_and_conflict_failures_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["substantive"]["benefit_threshold"]
        row["claim_binding"]["gate"] = "substantive.other"
        row["conflict_declaration"] = "unresolved"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        tags = " ".join(result.audit_tags)
        self.assertIn("claim_binding_mismatch", tags)
        self.assertIn("conflict_unresolved", tags)

    def test_valid_substantive_failure_is_attested_criterion_failure(self):
        self.claim["gates"]["substantive"]["benefit_threshold"]["status"] = "fail"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.CONTRADICTED)
        self.assertIn("Attested criterion failed", result.display_state)

    def test_precision_failure_is_inconclusive(self):
        self.claim["gates"]["precision"]["interval_rule"]["status"] = "fail"
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.INCONCLUSIVE)

    def test_validity_failure_has_priority(self):
        self.claim["gates"]["validity"]["telemetry_gap"]["status"] = "invalid"
        self.claim["gates"]["substantive"]["benefit_threshold"]["status"] = "fail"
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_missing_substantive_datum_is_not_assessable(self):
        self.claim["gates"]["substantive"]["benefit_threshold"]["status"] = "missing"
        self.save_claim()
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_non_object_claim_is_not_assessable(self):
        result = classify_claim_object([], REGISTRY, self.manifest, self.manifest_path)
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)

    def test_complete_record_exposes_component_statuses(self):
        result = self.classify()
        self.assertEqual(result.component_statuses["overall"], result.state.value)
        self.assertEqual(result.component_statuses["provenance"], "locally_consistent")
        self.assertEqual(result.component_statuses["energy_subclaim"], "submitted_gate_passes")
        self.assertEqual(result.component_statuses["service_quality"], "not_required_for_profile")

    def test_energy_failure_is_separate_from_component_state(self):
        self.claim["gates"]["substantive"]["benefit_threshold"]["status"] = "fail"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.CONTRADICTED)
        self.assertEqual(result.component_statuses["energy_subclaim"], "conflicts_with_declared_component")
        self.assertIn("locally provenance-consistent adjudication", result.reason)

    def test_l3_quality_failure_is_not_an_energy_failure(self):
        claim_path, manifest_path = build(Path(self.temp.name) / "l3", level="L3")
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        claim["gates"]["substantive"]["paired_task_quality"]["status"] = "fail"
        claim_path.write_text(json.dumps(claim, indent=2) + "\n", encoding="utf-8")
        result = classify_claim_file(claim_path, ROOT / "configs" / "required_gates.json", manifest_path)
        self.assertEqual(result.state, ClaimState.CONTRADICTED)
        self.assertEqual(result.component_statuses["energy_subclaim"], "submitted_gate_passes")
        self.assertEqual(result.component_statuses["service_quality"], "conflicts_with_declared_component")

    def test_manifest_version_mismatch_is_not_assessable(self):
        self.claim["evidence_manifest_version"] = "0.0.0"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("manifest_version_mismatch", " ".join(result.audit_tags))

    def test_manifest_sequence_rollback_is_not_assessable(self):
        self.manifest["sequence"] = 0
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("sequence_rollback_detected", " ".join(result.audit_tags))

    def test_replaced_local_integrity_token_is_not_assessable(self):
        token = self.manifest["local_integrity_token"]
        (self.manifest_path.parent / token["path"]).write_text("replaced token\n", encoding="utf-8")
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("local_integrity_token_digest_mismatch", " ".join(result.audit_tags))

    def test_missing_and_invalid_local_integrity_tokens_are_not_assessable(self):
        del self.manifest["local_integrity_token"]
        self.save_manifest_and_update_claim_digest()
        self.assertIn("local_integrity_token_missing_or_invalid", " ".join(self.classify().audit_tags))

        self.manifest["local_integrity_token"] = {
            "path": "../outside.txt",
            "sha256": self.claim["local_integrity_token_sha256"],
        }
        self.save_manifest_and_update_claim_digest()
        self.assertIn("local_integrity_token_path_not_normalized_relative", " ".join(self.classify().audit_tags))

    def test_path_traversal_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        self.manifest["evidence"][row["evidence_id"]]["path"] = "../outside.txt"
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("path_not_normalized_relative", " ".join(result.audit_tags))

    def test_duplicate_content_under_two_ids_is_not_assessable(self):
        source = self.claim["evidence_adjudications"]["validity"]["continuous_duration"]
        target = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        copied_id = "demo:duplicate-content"
        self.manifest["evidence"][copied_id] = copy.deepcopy(self.manifest["evidence"][source["evidence_id"]])
        self.manifest["evidence"][copied_id]["permitted_gates"] = ["validity.telemetry_gap"]
        target["evidence_id"] = copied_id
        target["claim_binding"]["gate"] = "validity.telemetry_gap"
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("duplicate_evidence_digest_under_distinct_ids", " ".join(result.audit_tags))

    def test_unregistered_gate_and_duplicate_declared_name_are_not_assessable(self):
        self.claim["declared_required_gates"]["validity"].append("telemetry_gap")
        self.claim["gates"]["validity"]["unregistered_gate"] = {"status": "pass"}
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        tags = " ".join(result.audit_tags)
        self.assertIn("duplicate_gate_name", tags)
        self.assertIn("unregistered=unregistered_gate", tags)

    def test_extra_top_level_key_fails_formal_json_schema(self):
        self.claim["unexpected_control"] = True
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("schema:jsonschema=root", " ".join(result.audit_tags))

    def test_declared_gate_order_is_metamorphically_invariant(self):
        baseline = self.classify().to_dict()
        for family in self.claim["declared_required_gates"]:
            self.claim["declared_required_gates"][family].reverse()
        self.save_claim()
        transformed = self.classify().to_dict()
        self.assertEqual(transformed["state"], baseline["state"])
        self.assertEqual(transformed["required_gates"], baseline["required_gates"])

    def test_every_display_state_is_explicit(self):
        self.assertIn("Locally provenance-complete", self.classify().display_state)
        self.claim["gates"]["substantive"]["benefit_threshold"]["status"] = "fail"
        self.save_claim()
        self.assertIn("Attested criterion failed", self.classify().display_state)
        self.claim["gates"]["validity"]["telemetry_gap"]["status"] = "missing"
        self.save_claim()
        self.assertEqual(self.classify().display_state, "Not assessable with available evidence")

    def test_invalid_gate_status_is_not_assessable(self):
        self.claim["gates"]["validity"]["telemetry_gap"]["status"] = "maybe"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("schema:jsonschema=gates/validity/telemetry_gap/status", " ".join(result.audit_tags))

    def test_missing_gate_object_is_not_assessable(self):
        del self.claim["gates"]["validity"]["telemetry_gap"]
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("not_submitted", " ".join(result.audit_tags))

    def test_attestation_disposition_and_missing_fields_are_not_assessable(self):
        self.claim["evidence_adjudications"]["validity"]["telemetry_gap"] = {"disposition": "pending"}
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("disposition='pending'", " ".join(result.audit_tags))

    def test_missing_attestation_fields_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        del row["reviewer_id"]
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("missing=reviewer_id", " ".join(result.audit_tags))

    def test_invalid_evidence_id_and_version_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        row["evidence_id"] = " "
        self.save_claim()
        self.assertIn("evidence_id_invalid", " ".join(self.classify().audit_tags))

    def test_evidence_version_and_claim_binding_are_checked(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        row["evidence_version"] = "bad-version"
        self.save_claim()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        self.assertIn("evidence_version_mismatch", " ".join(result.audit_tags))

    def test_missing_evidence_file_and_gate_binding_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        record = self.manifest["evidence"][row["evidence_id"]]
        (self.manifest_path.parent / record["path"]).unlink()
        record["permitted_gates"] = []
        self.save_manifest_and_update_claim_digest()
        result = self.classify()
        self.assertEqual(result.state, ClaimState.NOT_ASSESSABLE)
        tags = " ".join(result.audit_tags)
        self.assertIn("evidence_file_missing", tags)
        self.assertIn("evidence_not_bound_to_gate", tags)

    def test_evidence_not_bound_to_claim_is_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        self.manifest["evidence"][row["evidence_id"]]["permitted_claim_ids"] = []
        self.save_manifest_and_update_claim_digest()
        self.assertIn("evidence_not_bound_to_claim", " ".join(self.classify().audit_tags))

    def test_bad_timestamps_expiry_and_authorization_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        record = self.manifest["evidence"][row["evidence_id"]]
        row["reviewed_at_utc"] = "bad"
        record["expires_at_utc"] = "bad"
        authorization = self.manifest["authorized_reviewers"][row["reviewer_authorization_id"]]
        authorization["reviewer_id"] = "someone_else"
        self.save_manifest_and_update_claim_digest()
        tags = " ".join(self.classify().audit_tags)
        self.assertIn("reviewed_at_invalid", tags)
        self.assertIn("evidence_expired_or_invalid_expiry", tags)
        self.assertIn("reviewer_authorization_identity_mismatch", tags)

    def test_missing_authorization_and_role_mismatch_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        row["reviewer_authorization_id"] = "missing"
        self.save_claim()
        self.assertIn("reviewer_authorization_missing", " ".join(self.classify().audit_tags))

    def test_manifest_identity_and_digest_mismatch_are_not_assessable(self):
        self.claim["evidence_manifest_id"] = "wrong"
        self.save_claim()
        self.assertIn("claim_manifest_id_mismatch", " ".join(self.classify().audit_tags))
        self.claim["evidence_manifest_id"] = self.manifest["manifest_id"]
        self.claim["evidence_manifest_sha256"] = "0" * 64
        self.save_claim()
        self.assertIn("claim_manifest_digest_mismatch", " ".join(self.classify().audit_tags))

    def test_unreadable_and_invalid_manifest_are_not_assessable(self):
        self.manifest_path.write_text("not-json", encoding="utf-8")
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)
        self.manifest_path.write_text(json.dumps({"manifest_id": "m"}), encoding="utf-8")
        self.assertEqual(self.classify().state, ClaimState.NOT_ASSESSABLE)

    def test_non_posix_and_symlink_escape_paths_are_not_assessable(self):
        row = self.claim["evidence_adjudications"]["validity"]["telemetry_gap"]
        self.manifest["evidence"][row["evidence_id"]]["path"] = "evidence\\file.txt"
        self.save_manifest_and_update_claim_digest()
        self.assertIn("path_not_posix", " ".join(self.classify().audit_tags))

        # A syntactically valid relative path must still fail when a real link
        # resolves outside the manifest root.
        outside_root = Path(self.temp.name) / "outside_root"
        outside_root.mkdir()
        (outside_root / "outside.txt").write_text("outside manifest root\n", encoding="utf-8")
        link = self.manifest_path.parent / "linked_outside"
        try:
            link.symlink_to(outside_root, target_is_directory=True)
        except OSError as exc:
            if not self._create_windows_junction(link, outside_root):
                self.fail(f"could not create a symlink or junction for the path-escape test: {exc}")
        self.manifest["evidence"][row["evidence_id"]]["path"] = "linked_outside/outside.txt"
        self.save_manifest_and_update_claim_digest()
        self.assertIn("path_escapes_manifest_root", " ".join(self.classify().audit_tags))

    @staticmethod
    def _create_windows_junction(link: Path, target: Path) -> bool:
        """Use a Windows junction only when ordinary symlink creation is unavailable."""
        if not Path("C:/Windows/System32/cmd.exe").exists():
            return False
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0 and link.exists()

    def test_schema_rejects_bad_scalar_and_container_fields(self):
        for key, value in (
            ("id", ""),
            ("assessment_time_utc", "bad"),
            ("minimum_manifest_sequence", -1),
            ("threshold_rationale", {}),
        ):
            specimen = copy.deepcopy(self.claim)
            specimen[key] = value
            self.assertTrue(_schema_errors(specimen, REGISTRY))
        specimen = copy.deepcopy(self.claim)
        specimen["gates"] = []
        self.assertTrue(_schema_errors(specimen, REGISTRY))

    def test_schema_rejects_non_object_boundary_and_non_mapping_attestation(self):
        specimen = copy.deepcopy(self.claim)
        specimen["boundary"] = "not-an-object"
        self.assertIn("schema:boundary_not_object", _schema_errors(specimen, REGISTRY))
        self.claim["evidence_adjudications"]["validity"]["telemetry_gap"] = "not-an-attestation"
        self.save_claim()
        self.assertIn("schema:jsonschema=evidence_adjudications/validity/telemetry_gap", " ".join(self.classify().audit_tags))


class PureHelperTests(unittest.TestCase):
    def test_registry_loader_rejects_incomplete_or_invalid_registry_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            for payload in (
                {},
                {"levels": {"L1": {}}},
                {
                    "levels": {
                        "L1": {
                            "validity": ["ok"],
                            "substantive": ["ok"],
                            "precision": [""],
                        }
                    },
                    "required_reviewer_roles": {},
                },
                {
                    "levels": {
                        "L1": {
                            "validity": ["ok"],
                            "substantive": ["ok"],
                            "precision": ["ok"],
                        }
                    }
                },
            ):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_gate_registry(path)

    def test_parse_and_gate_helpers_cover_invalid_and_mapping_forms(self):
        self.assertIsNone(_parse_utc(None))
        self.assertIsNone(_parse_utc(""))
        self.assertIsNone(_parse_utc("not-a-date"))
        self.assertIsNone(_parse_utc("2026-01-01T00:00:00"))
        self.assertIsNotNone(_parse_utc("2026-01-01T00:00:00Z"))
        self.assertEqual(_gate_status({"status": "pass"}), GateResult.PASS)
        self.assertIsNone(_gate_status("unknown"))

    def test_safe_relative_file_rejects_missing_absolute_dot_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for raw in (None, "", "C:/absolute", "./dot", "../escape"):
                path, error = _safe_relative_file(root, raw)
                self.assertIsNone(path)
                self.assertIsNotNone(error)
            path, error = _safe_relative_file(root, "nested/file.txt")
            self.assertIsNone(error)
            self.assertEqual(path, root / "nested" / "file.txt")

    def test_component_statuses_handles_empty_failed_and_unknown_states(self):
        empty = _component_statuses({"validity": {}, "substantive": {}, "precision": {}}, ClaimState.PROVENANCE_COMPLETE, True)
        self.assertEqual(empty["validity"], "not_required_for_profile")
        statuses = {
            "validity": {"x": GateResult.FAIL},
            "substantive": {"functional_unit_declared": GateResult.PASS, "fixed_work_unit": GateResult.MISSING},
            "precision": {"x": GateResult.INVALID},
        }
        result = _component_statuses(statuses, ClaimState.NOT_ASSESSABLE, False)
        self.assertEqual(result["validity"], "conflicts_with_declared_component")
        self.assertEqual(result["energy_subclaim"], "not_assessable")
        self.assertEqual(result["precision"], "not_assessable")

    def test_display_state_covers_every_public_state(self):
        base = {
            "claim_id": "example",
            "claim_level": "L1",
            "reason": "test",
            "audit_tags": [],
            "required_gates": {},
            "component_statuses": {},
        }
        for state, expected in (
            (ClaimState.PROVENANCE_COMPLETE, "Locally provenance-complete--L1"),
            (ClaimState.ATTESTED_CRITERION_FAILED, "Attested criterion failed"),
            (ClaimState.INCONCLUSIVE, "Inconclusive due to precision"),
            (ClaimState.NOT_ASSESSABLE, "Not assessable with available evidence"),
        ):
            rendered = Classification(state=state, **base)
            self.assertIn(expected, rendered.display_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
