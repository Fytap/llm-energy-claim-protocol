#!/usr/bin/env python3
"""Protocol v1.2.0 registry-relative structural classifier.

This executable checks the *record structure* around a declared L0--L4 claim.
It derives mandatory gates from a registry and, for every required gate, checks a
locally supplied evidence manifest, file digest, version, review timestamp,
reviewer-role authorization, conflict declaration, revocation status, manifest
sequence, locally pinned integrity token, and a claim/gate binding. The checks
deliberately stop at local provenance
consistency: they do not authenticate people, establish reviewer competence, or
scientifically validate an underlying meter, quality study, or statistical model.

The only positive output is therefore ``locally_provenance_complete``.  It means
that a supplied record is internally complete under the declared local policy;
it never validates the scientific truth of the submitted evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


GATE_FAMILIES = ("validity", "substantive", "precision")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
CLAIM_SCHEMA_PATH = ROOT / "configs" / "claim_object_schema.json"


class GateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"
    INVALID = "invalid"


class ClaimState(str, Enum):
    NOT_ASSESSABLE = "not_assessable_with_available_evidence"
    ATTESTED_CRITERION_FAILED = "attested_criterion_failed_under_declared_boundary"
    # Compatibility alias for callers of Protocol 1.1.0. New output never uses
    # this word because the engine does not independently establish scientific contradiction.
    CONTRADICTED = "attested_criterion_failed_under_declared_boundary"
    INCONCLUSIVE = "inconclusive_due_to_precision_or_replication"
    PROVENANCE_COMPLETE = "locally_provenance_complete_evidence_not_independently_validated"


@dataclass(frozen=True)
class Classification:
    claim_id: str
    state: ClaimState
    claim_level: str | None
    reason: str
    audit_tags: tuple[str, ...]
    required_gates: dict[str, tuple[str, ...]]
    component_statuses: dict[str, str] = field(default_factory=dict)

    @property
    def display_state(self) -> str:
        if self.state is ClaimState.PROVENANCE_COMPLETE:
            return (
                f"Locally provenance-complete--{self.claim_level}; "
                "evidence not independently validated"
            )
        if self.state is ClaimState.ATTESTED_CRITERION_FAILED:
            return "Attested criterion failed under the declared boundary"
        if self.state is ClaimState.INCONCLUSIVE:
            return "Inconclusive due to precision or replication"
        return "Not assessable with available evidence"

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["state"] = self.state.value
        document["display_state"] = self.display_state
        document["required_gates"] = {
            name: list(values) for name, values in self.required_gates.items()
        }
        return document


def _component_statuses(
    statuses: Mapping[str, Mapping[str, GateResult]] | None,
    overall: ClaimState,
    provenance_ok: bool,
) -> dict[str, str]:
    """Expose component outcomes without treating a composite failure as energy-only."""
    if statuses is None:
        return {
            "overall": overall.value,
            "provenance": "not_assessable",
            "validity": "not_assessable",
            "energy_subclaim": "not_assessable",
            "service_quality": "not_assessable",
            "sla_feasibility": "not_assessable",
            "precision": "not_assessable",
        }

    def gate_state(family: str, gates: tuple[str, ...]) -> str:
        observed = [statuses[family].get(gate, GateResult.MISSING) for gate in gates]
        if not gates:
            return "not_required_for_profile"
        if any(value in {GateResult.MISSING, GateResult.INVALID} for value in observed):
            return "not_assessable"
        if any(value is GateResult.FAIL for value in observed):
            return "conflicts_with_declared_component"
        if all(value is GateResult.PASS for value in observed):
            return "submitted_gate_passes"
        return "inconclusive"

    validity_values = tuple(statuses["validity"].keys())
    precision_values = tuple(statuses["precision"].keys())
    energy_values = tuple(
        gate for gate in ("functional_unit_declared", "fixed_work_unit", "benefit_threshold")
        if gate in statuses["substantive"]
    )
    return {
        "overall": overall.value,
        "provenance": "locally_consistent" if provenance_ok else "not_assessable",
        "validity": gate_state("validity", validity_values),
        "energy_subclaim": gate_state("substantive", energy_values),
        "service_quality": gate_state("substantive", ("paired_task_quality",))
        if "paired_task_quality" in statuses["substantive"] else "not_required_for_profile",
        "sla_feasibility": gate_state("substantive", ("sla_feasibility",))
        if "sla_feasibility" in statuses["substantive"] else "not_required_for_profile",
        "precision": gate_state("precision", precision_values),
    }


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parse_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None:
        return None
    return value.astimezone(UTC)


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_gate_registry(path: str | Path) -> dict[str, Any]:
    """Load and validate the published gate/role minimums."""
    payload = _load_json(path)
    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise ValueError("Registry lacks a levels object.")
    for level, families in levels.items():
        if not isinstance(families, dict) or set(families) != set(GATE_FAMILIES):
            raise ValueError(f"Registry level {level!r} must declare all gate families.")
        for family in GATE_FAMILIES:
            gates = families[family]
            if not isinstance(gates, list) or not gates or any(
                not _is_nonempty_string(gate) for gate in gates
            ):
                raise ValueError(f"Registry level {level!r} has invalid {family} gates.")
    roles = payload.get("required_reviewer_roles")
    if not isinstance(roles, dict):
        raise ValueError("Registry lacks required_reviewer_roles.")
    return payload


def _required(registry: Mapping[str, Any], level: str) -> dict[str, tuple[str, ...]]:
    return {
        family: tuple(registry["levels"][level][family]) for family in GATE_FAMILIES
    }


def _not_assessable(
    claim_id: str,
    level: str | None,
    reason: str,
    tags: Iterable[str],
    required: Mapping[str, tuple[str, ...]] | None = None,
    component_statuses: Mapping[str, str] | None = None,
) -> Classification:
    return Classification(
        claim_id=claim_id,
        state=ClaimState.NOT_ASSESSABLE,
        claim_level=level,
        reason=reason,
        audit_tags=tuple(tags),
        required_gates=dict(required or {family: tuple() for family in GATE_FAMILIES}),
        component_statuses=dict(component_statuses or _component_statuses(None, ClaimState.NOT_ASSESSABLE, False)),
    )


def _schema_errors(claim: Any, registry: Mapping[str, Any]) -> list[str]:
    if not isinstance(claim, dict):
        return ["schema:root_not_object"]
    try:
        schema = _load_json(CLAIM_SCHEMA_PATH)
        formal_errors = sorted(
            Draft202012Validator(schema).iter_errors(claim), key=lambda error: list(error.absolute_path)
        )
    except (OSError, json.JSONDecodeError):
        return ["schema:formal_schema_unavailable"]
    errors = [
        "schema:jsonschema=" + ("/".join(str(part) for part in error.absolute_path) or "root")
        for error in formal_errors
    ]
    required_fields = (
        "id", "statement", "evidence_profile", "boundary", "functional_unit",
        "threshold_rationale", "declared_required_gates", "gates",
        "evidence_adjudications", "permitted_wording", "claim_owner_id",
        "assessment_time_utc", "evidence_manifest_id", "evidence_manifest_sha256",
        "evidence_manifest_version", "minimum_manifest_sequence",
        "local_integrity_token_sha256",
    )
    errors.extend(
        f"schema:missing_field={field}" for field in required_fields if field not in claim
    )
    for field in (
        "id", "statement", "functional_unit", "permitted_wording", "claim_owner_id",
        "evidence_manifest_id", "evidence_manifest_sha256",
        "evidence_manifest_version", "local_integrity_token_sha256",
    ):
        if field in claim and not _is_nonempty_string(claim[field]):
            errors.append(f"schema:empty_or_invalid={field}")
    if _parse_utc(claim.get("assessment_time_utc")) is None:
        errors.append("schema:assessment_time_utc_invalid")
    if not isinstance(claim.get("minimum_manifest_sequence"), int) or claim["minimum_manifest_sequence"] < 0:
        errors.append("schema:minimum_manifest_sequence_invalid")
    level = claim.get("evidence_profile")
    if level not in registry.get("levels", {}):
        errors.append(f"schema:unknown_evidence_profile={level!r}")
    boundary = claim.get("boundary")
    if not isinstance(boundary, dict):
        errors.append("schema:boundary_not_object")
    else:
        for field in ("energy", "service"):
            if not _is_nonempty_string(boundary.get(field)):
                errors.append(f"schema:boundary_{field}_missing_or_empty")
        exclusions = boundary.get("exclusions")
        if not isinstance(exclusions, list) or not exclusions or any(
            not _is_nonempty_string(item) for item in exclusions
        ):
            errors.append("schema:boundary_exclusions_missing_or_empty")
    if not isinstance(claim.get("threshold_rationale"), dict) or not claim["threshold_rationale"]:
        errors.append("schema:threshold_rationale_missing_or_empty")
    for field in ("declared_required_gates", "gates", "evidence_adjudications"):
        value = claim.get(field)
        if not isinstance(value, dict):
            errors.append(f"schema:{field}_not_object")
            continue
        for family in GATE_FAMILIES:
            expected_type = list if field == "declared_required_gates" else dict
            if family not in value or not isinstance(value[family], expected_type):
                errors.append(f"schema:{field}_{family}_missing_or_invalid")
    return errors


def _gate_status(raw: Any) -> GateResult | None:
    if isinstance(raw, Mapping):
        raw = raw.get("status")
    try:
        return GateResult(raw)
    except (TypeError, ValueError):
        return None


def _normalized_required(
    registry_required: Mapping[str, tuple[str, ...]], claim: Mapping[str, Any]
) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    tags: list[str] = []
    declared = claim.get("declared_required_gates", {})
    for family, expected in registry_required.items():
        supplied = declared.get(family)
        if not isinstance(supplied, list):
            tags.append(f"required_gate_declaration:{family}=missing")
            continue
        supplied_set, expected_set = set(supplied), set(expected)
        if len(supplied_set) != len(supplied):
            tags.append(f"required_gate_declaration:{family}:duplicate_gate_name")
        tags.extend(
            f"required_gate_declaration:{family}:omitted={gate}"
            for gate in sorted(expected_set - supplied_set)
        )
        tags.extend(
            f"required_gate_declaration:{family}:unregistered={gate}"
            for gate in sorted(supplied_set - expected_set)
        )
        for record_name in ("gates", "evidence_adjudications"):
            records = claim.get(record_name, {}).get(family, {})
            if not isinstance(records, Mapping):
                tags.append(f"{record_name}:{family}=missing_or_invalid")
                continue
            if not records:
                tags.append(f"{record_name}:{family}=empty")
            tags.extend(
                f"{record_name}:{family}:unregistered={gate}"
                for gate in sorted(set(records) - expected_set)
            )
    return dict(registry_required), tags


def _load_manifest(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    manifest_path = Path(path)
    try:
        manifest = _load_json(manifest_path)
    except (OSError, json.JSONDecodeError) as error:
        return None, [f"manifest:unreadable={type(error).__name__}"]
    errors: list[str] = []
    if not _is_nonempty_string(manifest.get("manifest_id")):
        errors.append("manifest:manifest_id_missing_or_empty")
    if not _is_nonempty_string(manifest.get("manifest_version")):
        errors.append("manifest:manifest_version_missing_or_empty")
    if not isinstance(manifest.get("sequence"), int) or manifest["sequence"] < 0:
        errors.append("manifest:sequence_invalid")
    if _parse_utc(manifest.get("created_at_utc")) is None:
        errors.append("manifest:created_at_utc_invalid")
    if not isinstance(manifest.get("evidence"), dict):
        errors.append("manifest:evidence_not_object")
    if not isinstance(manifest.get("authorized_reviewers"), dict):
        errors.append("manifest:authorized_reviewers_not_object")
    return manifest, errors


def _safe_relative_file(root: Path, raw_path: Any) -> tuple[Path | None, str | None]:
    """Resolve a normalized relative POSIX file path without allowing escape."""
    if not _is_nonempty_string(raw_path):
        return None, "path_missing_or_invalid"
    text = str(raw_path)
    if "\\" in text:
        return None, "path_not_posix"
    candidate_relative = PurePosixPath(text)
    raw_parts = text.split("/")
    if (
        text.startswith("/")
        or PureWindowsPath(text).is_absolute()
        or any(":" in part for part in raw_parts)
        or ".." in raw_parts
        or "." in raw_parts
    ):
        return None, "path_not_normalized_relative"
    candidate = root.joinpath(*candidate_relative.parts).resolve()
    resolved_root = root.resolve()
    if resolved_root not in candidate.parents:
        return None, "path_escapes_manifest_root"
    return candidate, None


def _local_integrity_token_tags(
    claim: Mapping[str, Any], manifest: Mapping[str, Any], manifest_path: Path
) -> list[str]:
    """Check a locally pinned token; this is not cryptographic signature verification."""
    token = manifest.get("local_integrity_token")
    if not isinstance(token, Mapping):
        return ["manifest:local_integrity_token_missing_or_invalid"]
    token_path, path_error = _safe_relative_file(manifest_path.parent, token.get("path"))
    if path_error is not None:
        return [f"manifest:local_integrity_token_{path_error}"]
    assert token_path is not None
    if not token_path.is_file():
        return ["manifest:local_integrity_token_file_missing"]
    digest = _sha256_path(token_path)
    if digest != token.get("sha256") or digest != claim.get("local_integrity_token_sha256"):
        return ["manifest:local_integrity_token_digest_mismatch"]
    return []


def _attestation_tags(
    claim: Mapping[str, Any],
    registry: Mapping[str, Any],
    manifest: Mapping[str, Any],
    manifest_path: Path,
    family: str,
    gate: str,
    raw: Any,
    evidence_use: dict[str, set[str]],
    evidence_digest_use: dict[str, str],
) -> list[str]:
    """Return provenance errors for one record without judging scientific truth."""
    prefix = f"attestation:{family}:{gate}"
    if not isinstance(raw, Mapping):
        return [f"{prefix}=missing_or_invalid"]
    disposition = raw.get("disposition")
    if disposition != "attested":
        return [f"{prefix}:disposition={disposition!r}"]
    required_fields = (
        "evidence_id", "evidence_version", "evidence_sha256", "reviewed_at_utc",
        "reviewer_id", "reviewer_role", "reviewer_authorization_id",
        "conflict_declaration", "claim_binding",
    )
    tags = [f"{prefix}:missing={field}" for field in required_fields if field not in raw]
    if tags:
        return tags
    evidence_id = raw["evidence_id"]
    if not _is_nonempty_string(evidence_id):
        return [f"{prefix}:evidence_id_invalid"]
    evidence = manifest["evidence"].get(evidence_id)
    if not isinstance(evidence, Mapping):
        return [f"{prefix}:evidence_id_not_in_manifest={evidence_id}"]
    if evidence.get("status") != "active":
        return [f"{prefix}:evidence_status={evidence.get('status')!r}"]
    if raw["evidence_version"] != evidence.get("version"):
        tags.append(f"{prefix}:evidence_version_mismatch")
    try:
        evidence_path, path_error = _safe_relative_file(manifest_path.parent, evidence.get("path"))
        if path_error is not None:
            tags.append(f"{prefix}:evidence_{path_error}")
        elif evidence_path is None or not evidence_path.is_file():
            tags.append(f"{prefix}:evidence_file_missing")
        else:
            actual_digest = _sha256_path(evidence_path)
            prior_id = evidence_digest_use.get(actual_digest)
            if prior_id is not None and prior_id != evidence_id:
                tags.append(f"{prefix}:duplicate_evidence_digest_under_distinct_ids={prior_id}")
            evidence_digest_use[actual_digest] = evidence_id
            if actual_digest != evidence.get("sha256") or raw["evidence_sha256"] != actual_digest:
                tags.append(f"{prefix}:evidence_digest_mismatch")
    except (KeyError, OSError, TypeError):
        tags.append(f"{prefix}:evidence_path_invalid")
    if f"{family}.{gate}" not in evidence.get("permitted_gates", []):
        tags.append(f"{prefix}:evidence_not_bound_to_gate")
    allowed_claims = evidence.get("permitted_claim_ids", [])
    if claim["id"] not in allowed_claims:
        tags.append(f"{prefix}:evidence_not_bound_to_claim")
    binding = raw.get("claim_binding")
    expected_binding = {
        "claim_id": claim["id"],
        "evidence_profile": claim["evidence_profile"],
        "gate": f"{family}.{gate}",
    }
    if binding != expected_binding:
        tags.append(f"{prefix}:claim_binding_mismatch")
    evidence_use.setdefault(evidence_id, set()).add(f"{family}.{gate}")
    assessment_time = _parse_utc(claim["assessment_time_utc"])
    reviewed_at = _parse_utc(raw["reviewed_at_utc"])
    expires_at = _parse_utc(evidence.get("expires_at_utc"))
    max_age = registry.get("provenance_policy", {}).get("max_attestation_age_days", 365)
    if reviewed_at is None:
        tags.append(f"{prefix}:reviewed_at_invalid")
    elif assessment_time is not None and (
        reviewed_at > assessment_time or (assessment_time - reviewed_at).days > max_age
    ):
        tags.append(f"{prefix}:review_timestamp_stale_or_after_assessment")
    if expires_at is None or (assessment_time is not None and expires_at < assessment_time):
        tags.append(f"{prefix}:evidence_expired_or_invalid_expiry")
    reviewer_id = raw["reviewer_id"]
    if reviewer_id == claim["claim_owner_id"]:
        tags.append(f"{prefix}:self_review_not_permitted")
    authorization = manifest["authorized_reviewers"].get(raw["reviewer_authorization_id"])
    if not isinstance(authorization, Mapping):
        tags.append(f"{prefix}:reviewer_authorization_missing")
    else:
        if authorization.get("status") != "active":
            tags.append(f"{prefix}:reviewer_authorization_not_active")
        if authorization.get("reviewer_id") != reviewer_id:
            tags.append(f"{prefix}:reviewer_authorization_identity_mismatch")
        if raw["reviewer_role"] != authorization.get("role"):
            tags.append(f"{prefix}:reviewer_role_authorization_mismatch")
    required_role = registry["required_reviewer_roles"].get(
        f"{family}.{gate}", registry["required_reviewer_roles"].get(f"{family}.*")
    )
    if raw.get("reviewer_role") != required_role:
        tags.append(f"{prefix}:wrong_reviewer_role")
    if raw.get("conflict_declaration") not in {"none", "declared_and_managed"}:
        tags.append(f"{prefix}:conflict_unresolved_or_invalid")
    return tags


def classify_claim_object(
    claim: Mapping[str, Any], registry: Mapping[str, Any], manifest: Mapping[str, Any], manifest_path: str | Path
) -> Classification:
    """Classify one local record; no semantic evidence or identity validation occurs."""
    claim_id = claim.get("id", "<invalid-claim-object>") if isinstance(claim, Mapping) else "<invalid-claim-object>"
    level = claim.get("evidence_profile") if isinstance(claim, Mapping) else None
    schema_errors = _schema_errors(claim, registry)
    if schema_errors:
        return _not_assessable(str(claim_id), level if isinstance(level, str) else None,
                               "The claim object does not satisfy the executable schema.", schema_errors)
    assert isinstance(claim, Mapping) and isinstance(level, str)
    required = _required(registry, level)
    if claim["evidence_manifest_id"] != manifest.get("manifest_id"):
        return _not_assessable(str(claim_id), level, "The submitted manifest identity does not match the claim.",
                               ["manifest:claim_manifest_id_mismatch"], required)
    if claim["evidence_manifest_sha256"] != _sha256_path(Path(manifest_path)):
        return _not_assessable(str(claim_id), level, "The submitted manifest digest does not match the local manifest.",
                               ["manifest:claim_manifest_digest_mismatch"], required)
    if claim["evidence_manifest_version"] != manifest.get("manifest_version"):
        return _not_assessable(str(claim_id), level, "The submitted manifest version does not match the claim.",
                               ["manifest:claim_manifest_version_mismatch"], required)
    if registry.get("provenance_policy", {}).get("require_manifest_sequence", False) and (
        manifest.get("sequence", -1) < claim["minimum_manifest_sequence"]
    ):
        return _not_assessable(str(claim_id), level, "The submitted manifest sequence is older than the claim permits.",
                               ["manifest:sequence_rollback_detected"], required)
    if registry.get("provenance_policy", {}).get("require_local_integrity_token", False):
        token_tags = _local_integrity_token_tags(claim, manifest, Path(manifest_path))
        if token_tags:
            return _not_assessable(str(claim_id), level, "The local manifest-integrity token does not match the claim.",
                                   token_tags, required)
    normalized_required, declaration_tags = _normalized_required(required, claim)
    audit_tags = list(declaration_tags)
    statuses: dict[str, dict[str, GateResult]] = {family: {} for family in GATE_FAMILIES}
    evidence_use: dict[str, set[str]] = {}
    evidence_digest_use: dict[str, str] = {}
    for family, names in normalized_required.items():
        for gate in names:
            raw_gate = claim["gates"].get(family, {}).get(gate)
            status = _gate_status(raw_gate)
            if raw_gate is None:
                status = GateResult.MISSING
                audit_tags.append(f"{family}:{gate}=not_submitted")
            elif status is None:
                status = GateResult.INVALID
                audit_tags.append(f"{family}:{gate}=invalid_status")
            statuses[family][gate] = status
            if status is not GateResult.PASS:
                audit_tags.append(f"{family}:{gate}={status.value}")
            audit_tags.extend(_attestation_tags(
                claim, registry, manifest, Path(manifest_path), family, gate,
                claim["evidence_adjudications"].get(family, {}).get(gate), evidence_use, evidence_digest_use,
            ))
    if declaration_tags:
        return _not_assessable(str(claim_id), level,
                               "The caller-declared gates do not match the registry-derived minimum.", audit_tags, normalized_required,
                               _component_statuses(statuses, ClaimState.NOT_ASSESSABLE, False))
    provenance_tags = [tag for tag in audit_tags if tag.startswith("attestation:")]
    if provenance_tags:
        return _not_assessable(str(claim_id), level,
                               "A required local provenance, role, binding, or attestation check failed; scientific evidence was not assessed.", audit_tags, normalized_required,
                               _component_statuses(statuses, ClaimState.NOT_ASSESSABLE, False))
    invalid_validity = [name for name, status in statuses["validity"].items() if status is not GateResult.PASS]
    if invalid_validity:
        return _not_assessable(str(claim_id), level,
                               "A required validity dependency is missing or invalid; the claim cannot be assessed.", audit_tags, normalized_required,
                               _component_statuses(statuses, ClaimState.NOT_ASSESSABLE, True))
    missing_substantive = [name for name, status in statuses["substantive"].items() if status in {GateResult.MISSING, GateResult.INVALID}]
    if missing_substantive:
        return _not_assessable(str(claim_id), level,
                               "A required substantive datum is unavailable under the declared boundary.", audit_tags, normalized_required,
                               _component_statuses(statuses, ClaimState.NOT_ASSESSABLE, True))
    failed_substantive = [name for name, status in statuses["substantive"].items() if status is GateResult.FAIL]
    if failed_substantive:
        return Classification(str(claim_id), ClaimState.ATTESTED_CRITERION_FAILED, level,
                              "A locally provenance-consistent adjudication attests that a required criterion failed. This is not an independent scientific contradiction finding.", tuple(audit_tags), normalized_required,
                              _component_statuses(statuses, ClaimState.ATTESTED_CRITERION_FAILED, True))
    nonpass_precision = [name for name, status in statuses["precision"].items() if status is not GateResult.PASS]
    if nonpass_precision:
        return Classification(str(claim_id), ClaimState.INCONCLUSIVE, level,
                              "Submitted evidence is not precise or replicated enough under the registered rule.", tuple(audit_tags), normalized_required,
                              _component_statuses(statuses, ClaimState.INCONCLUSIVE, True))
    return Classification(str(claim_id), ClaimState.PROVENANCE_COMPLETE, level,
                          "All registry gates pass local provenance checks. Evidence is not independently validated.", tuple(audit_tags), normalized_required,
                          _component_statuses(statuses, ClaimState.PROVENANCE_COMPLETE, True))


def classify_claim_file(claim_path: str | Path, registry_path: str | Path, manifest_path: str | Path) -> Classification:
    registry = load_gate_registry(registry_path)
    manifest, manifest_errors = _load_manifest(manifest_path)
    claim = _load_json(claim_path)
    claim_id = claim.get("id", "<invalid-claim-object>") if isinstance(claim, Mapping) else "<invalid-claim-object>"
    level = claim.get("evidence_profile") if isinstance(claim, Mapping) else None
    if manifest is None or manifest_errors:
        return _not_assessable(str(claim_id), level if isinstance(level, str) else None,
                               "The local evidence manifest cannot be used.", manifest_errors)
    return classify_claim_object(claim, registry, manifest, manifest_path)
