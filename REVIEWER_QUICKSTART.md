# Reviewer Quick Start

From the repository root, install the declared dependencies and run:

```powershell
python -m pip install -r requirements.txt
python scripts/reproduce.py
```

Expected outcome: the command completes without an exception and writes
`results/reproduction_report.json` with `"status": "pass"`.

The artifact is self-contained after dependency installation and does not require
network access, an accelerator, a model checkpoint, private infrastructure, or
external services.
