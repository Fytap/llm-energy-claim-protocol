# LLM Energy-Claim Protocol Artifact

This repository contains the public computational artifact accompanying a
registry-driven protocol for assessing the structural sufficiency of LLM
energy-claim records. It includes anonymized telemetry examples, machine-readable
claim objects, an executable gate engine, deterministic synthetic controls, and
the scripts needed to reproduce the reported computational checks.

The artifact is deliberately bounded. It does not contain credentials, host
identifiers, absolute paths, model weights, author identities, personal data, or
external meter records. Its outputs assess the completeness and internal
consistency of declared evidence records; they do not independently validate
physical energy, carbon, organizational, or environmental claims.

## Reproduce

```powershell
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

The command runs unit and mutation checks, recomputes the anonymized telemetry
audits, evaluates every public claim object, generates dependence and decision
rule simulations, and writes the regenerated files under `results/`.

## Layout

- `claims/`: machine-readable, anonymized claim objects.
- `configs/`: gate registry, JSON schema, and dependence-handling guidance.
- `data/`: anonymized telemetry and request-outcome records used by the examples.
- `scripts/`: evaluator, analyses, simulations, plotting, tests, and entry point.

Dependency pins are retained in `requirements.txt` so that the computational
environment can be recreated. They are software dependencies, not internal
project or infrastructure identifiers.
