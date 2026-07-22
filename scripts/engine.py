#!/usr/bin/env python3
"""Schema- and registry-driven validity-first claim-conformance engine.

current release classifies a machine-readable claim object rather than three caller-supplied
gate dictionaries. The required gate set is derived from the registered L0--L4
evidence profile; a caller cannot obtain a positive state by omitting a required
gate.  A malformed object, an unknown level, an empty boundary, a mismatched
declared gate set, or an unsubmitted required gate is classified as ``not
assessable with available evidence`` and retained in the audit trail. For claims
using block-level inference, the registry also requires a serial-dependence
assessment and an interval method compatible with the declared dependence.

This is an internal, bounded classification tool. It does not certify SCI, ISO,
MLPerf, physical metering, environmental impact, or organizational assurance.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


class GateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    MISSING = "missing"
    INVALID = "invalid"


class ClaimState(str, Enum):
    NOT_ASSESSABLE = "not_assessable_with_available_evidence"
    CONTRADICTED = "contradicted_under_declared_boundary"
    INCONCLUSIVE = "inconclusive_due_to_precision_or_replication"
    SUPPORTED = "supported_under_declared_boundary"


GATE_FAMILIES = ("validity", "substantive", "precision")


@dataclass(frozen=True)
class Classification:
    claim_id: str
    state: ClaimState
    claim_level: str | None
    reason: str
    audit_tags: tuple[str, ...]
    required_gates: dict[str, tuple[str, ...]]

    @property
    def display_state(self) -> str:
        if self.state is ClaimState.SUPPORTED:
            return f"Supported-{self.claim_level} under the declared boundary"
        if self.state is ClaimState.CONTRADICTED:
            return "Contradicted under the declared boundary"
        if self.state is ClaimState.INCONCLUSIVE:
            return "Inconclusive due to precision or replication"
        return "Not assessable with available evidence"

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["state"] = self.state.value
        document["display_state"] = self.display_state
        document["required_gates"] = {name: list(values) for name, values in self.required_gates.items()}
        return document


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_gate_registry(path: str | Path) -> dict[str, dict[str, tuple[str, ...]]]:
    payload = load_json(path)
    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise ValueError("Registry lacks a levels object.")
    registry: dict[str, dict[str, tuple[str, ...]]] = {}
    for level, families in levels.items():
        if not isinstance(families, dict) or set(families) != set(GATE_FAMILIES):
            raise ValueError(f"Registry level {level!r} must declare all gate families.")
        registry[level] = {}
        for family in GATE_FAMILIES:
            gates = families[family]
            if not isinstance(gates, list) or not gates or any(not isinstance(gate, str) or not gate for gate in gates):
                raise ValueError(f"Registry level {level!r} has an invalid {family} gate list.")
            registry[level][family] = tuple(gates)
    return registry


def _not_assessable(
    claim_id: str,
    level: str | None,
    reason: str,
    tags: Iterable[str],
    required: Mapping[str, tuple[str, ...]] | None = None,
) -> Classification:
    return Classification(
        claim_id=claim_id,
        state=ClaimState.NOT_ASSESSABLE,
        claim_level=level,
        reason=reason,
        audit_tags=tuple(tags),
        required_gates=dict(required or {family: tuple() for family in GATE_FAMILIES}),
    )


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _schema_errors(claim: Any, registry: Mapping[str, Mapping[str, tuple[str, ...]]]) -> list[str]:
    """Small dependency-free validator for the published JSON object contract."""
    if not isinstance(claim, dict):
        return ["schema:root_not_object"]
    required_fields = (
        "id", "statement", "evidence_profile", "boundary", "functional_unit",
        "threshold_rationale", "declared_required_gates", "gates", "permitted_wording",
    )
    errors = [f"schema:missing_field={field}" for field in required_fields if field not in claim]
    for field in ("id", "statement", "functional_unit", "permitted_wording"):
        if field in claim and not _is_nonempty_string(claim[field]):
            errors.append(f"schema:empty_or_invalid={field}")
    level = claim.get("evidence_profile")
    if level not in registry:
        errors.append(f"schema:unknown_evidence_profile={level!r}")
    boundary = claim.get("boundary")
    if not isinstance(boundary, dict):
        errors.append("schema:boundary_not_object")
    else:
        for field in ("energy", "service"):
            if not _is_nonempty_string(boundary.get(field)):
                errors.append(f"schema:boundary_{field}_missing_or_empty")
        exclusions = boundary.get("exclusions")
        if not isinstance(exclusions, list) or not exclusions or any(not _is_nonempty_string(item) for item in exclusions):
            errors.append("schema:boundary_exclusions_missing_or_empty")
    rationale = claim.get("threshold_rationale")
    if not isinstance(rationale, dict) or not rationale:
        errors.append("schema:threshold_rationale_missing_or_empty")
    for field in ("declared_required_gates", "gates"):
        value = claim.get(field)
        if not isinstance(value, dict):
            errors.append(f"schema:{field}_not_object")
            continue
        for family in GATE_FAMILIES:
            if family not in value or not isinstance(value[family], (dict, list)):
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
    """Return registry requirements and audit any caller registry mismatch."""
    tags: list[str] = []
    declared = claim.get("declared_required_gates", {})
    if not isinstance(declared, Mapping):
        return dict(registry_required), ["schema:declared_required_gates_not_object"]
    for family, expected in registry_required.items():
        supplied = declared.get(family)
        if not isinstance(supplied, list):
            tags.append(f"required_gate_declaration:{family}=missing")
            continue
        supplied_set = set(supplied)
        expected_set = set(expected)
        missing = sorted(expected_set - supplied_set)
        extra = sorted(supplied_set - expected_set)
        tags.extend(f"required_gate_declaration:{family}:omitted={gate}" for gate in missing)
        tags.extend(f"required_gate_declaration:{family}:unregistered={gate}" for gate in extra)
    return dict(registry_required), tags


def classify_claim_object(
    claim: Mapping[str, Any], registry: Mapping[str, Mapping[str, tuple[str, ...]]]
) -> Classification:
    """Classify one claim object after schema and mandatory-gate enforcement."""
    claim_id = claim.get("id", "<invalid-claim-object>") if isinstance(claim, Mapping) else "<invalid-claim-object>"
    level = claim.get("evidence_profile") if isinstance(claim, Mapping) else None
    schema_errors = _schema_errors(claim, registry)
    if schema_errors:
        return _not_assessable(
            str(claim_id), level if isinstance(level, str) else None,
            "The claim object does not satisfy the executable schema and cannot be classified.", schema_errors,
        )

    assert isinstance(claim, Mapping)
    assert isinstance(level, str)
    required = registry[level]
    normalized_required, declaration_tags = _normalized_required(required, claim)
    submitted = claim["gates"]
    audit_tags = list(declaration_tags)

    # Required gates are always read from the registry. Unsubmitted gates become
    # explicit missing evidence; caller completeness is never assumed.
    statuses: dict[str, dict[str, GateResult]] = {family: {} for family in GATE_FAMILIES}
    for family, expected_names in normalized_required.items():
        actual_family = submitted.get(family, {}) if isinstance(submitted, Mapping) else {}
        if not isinstance(actual_family, Mapping):
            actual_family = {}
        for gate in expected_names:
            raw = actual_family.get(gate)
            status = _gate_status(raw)
            if raw is None:
                status = GateResult.MISSING
                audit_tags.append(f"{family}:{gate}=not_submitted")
            elif status is None:
                status = GateResult.INVALID
                audit_tags.append(f"{family}:{gate}=invalid_status")
            statuses[family][gate] = status
            if status is not GateResult.PASS:
                audit_tags.append(f"{family}:{gate}={status.value}")
        if isinstance(actual_family, Mapping):
            extras = sorted(set(actual_family) - set(expected_names))
            audit_tags.extend(f"{family}:unregistered_gate={gate}" for gate in extras)

    if declaration_tags:
        return _not_assessable(
            str(claim_id), level,
            "The caller-declared gate list does not match the registry-derived minimum set.", audit_tags, normalized_required,
        )

    invalid_validity = [gate for gate, status in statuses["validity"].items() if status is not GateResult.PASS]
    if invalid_validity:
        return _not_assessable(
            str(claim_id), level,
            "A required validity dependency is missing or invalid; the evidence cannot substantively support or contradict the claim.",
            audit_tags, normalized_required,
        )

    substantive_invalid = [
        gate for gate, status in statuses["substantive"].items() if status in (GateResult.MISSING, GateResult.INVALID)
    ]
    if substantive_invalid:
        return _not_assessable(
            str(claim_id), level,
            "A required substantive datum is unavailable under the declared boundary.", audit_tags, normalized_required,
        )

    substantive_fail = [gate for gate, status in statuses["substantive"].items() if status is GateResult.FAIL]
    if substantive_fail:
        return Classification(
            str(claim_id), ClaimState.CONTRADICTED, level,
            "Valid evidence contradicts the declared direction, threshold, or another substantive requirement.",
            tuple(audit_tags), normalized_required,
        )

    precision_nonpass = [gate for gate, status in statuses["precision"].items() if status is not GateResult.PASS]
    if precision_nonpass:
        return Classification(
            str(claim_id), ClaimState.INCONCLUSIVE, level,
            "Evidence is valid and no substantive contradiction is observed, but precision or replication is insufficient.",
            tuple(audit_tags), normalized_required,
        )

    return Classification(
        str(claim_id), ClaimState.SUPPORTED, level,
        "All registry-derived validity, substantive, and precision gates pass under the declared boundary.",
        tuple(audit_tags), normalized_required,
    )


def classify_claim_file(claim_path: str | Path, registry_path: str | Path) -> Classification:
    return classify_claim_object(load_json(claim_path), load_gate_registry(registry_path))
