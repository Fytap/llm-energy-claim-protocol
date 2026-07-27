# LLM Energy Claim-Protocol Artifact

This repository accompanies *A Registry-Relative Claim-Conformance Engine for
GPU-Side LLM Energy Reporting*. It contains the machine-readable registry and
claim-record schema, a deterministic conformance engine, synthetic controls,
redacted historical serving records, and the scripts needed to reproduce the
reported computational checks.

The artifact checks the declared structural completeness and local consistency
of evidence records. It does not independently validate physical energy,
carbon, organizational, or environmental claims. The retained telemetry examples
are not externally calibrated power measurements and do not support claims about
whole-server, facility, or lifecycle impacts.

## Quick start

The package was checked with Python 3.12. Install the exact dependencies and run
the documented entry point from the repository root:

```powershell
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

The command first verifies the SHA-256 manifest. It then runs 57 direct,
state-transition, and metamorphic tests; 2,000 malformed-record fuzz inputs;
15 deterministic source mutations; a structured JSON Schema contrast; synthetic
operating-characteristic studies; and two figure-generation workflows. A
successful run writes `results/reproduction_report.json` with `"status": "pass"`.

For a compact reviewer workflow and expected outputs, see
[`REVIEWER_QUICKSTART.md`](REVIEWER_QUICKSTART.md). The source-and-input
integrity manifest is [`MANIFEST.sha256`](MANIFEST.sha256); it is verified by
`scripts/verify_manifest.py` before computation begins.

## Repository layout

- `claims/`: bounded machine-readable claim records for the retained examples.
- `configs/`: gate registry, JSON Schema, and dependence-handling guidance.
- `data/`: redacted telemetry and request-outcome examples; see `data/README.md`.
- `scripts/`: evaluator, analyses, simulations, plotting, tests, and entry point.
- `templates/`: blank materials for future, separately administered evaluations.
- `MANIFEST.sha256`: SHA-256 hashes for the shipped source and input payload.

## Privacy and scope boundary

The repository contains no credentials, host identifiers, absolute paths, model
weights, personal data, or external meter records. It uses relative paths only.
After dependency installation, the workflow requires neither an accelerator nor
access to private infrastructure or network services.
