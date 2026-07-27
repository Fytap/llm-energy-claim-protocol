# Reviewer Quick Start

From the repository root, run:

```powershell
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

The entry point verifies `MANIFEST.sha256` before running any analysis. A
successful run completes without an exception and writes
`results/reproduction_report.json` with `"status": "pass"`.

The report covers 57 direct, state-transition, and metamorphic tests; 2,000
malformed-record fuzz inputs; 15 source mutations; a structured JSON Schema
contrast; synthetic operating-characteristic studies; and a model-matched AR(1)
positive control. Generated tables, machine-readable reports, and two PDF figures
are written under `results/`.

The command intentionally verifies executable structural behavior only. It does
not authenticate evidence providers or validate physical energy, meter,
whole-system, carbon, or lifecycle claims.

The package is self-contained after dependency installation and requires no
accelerator, model checkpoint, private infrastructure, or network service.
