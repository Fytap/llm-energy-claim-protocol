# Dependence-Handling Guidance

This document operationalizes the `serial_dependence_assessed` and
`dependence_compatible_interval` gates for a future claim packet. It is guidance
for planning and audit retention; it does not modify the registry or engine.

## Required precollection declaration

The designated measurement/statistical owner must record:

1. The experimental unit, the block unit, planned number of independent units,
   and expected dependence class.
2. The interval method, its assumptions, and tuning choices such as HAC lag,
   bootstrap block length, clustering unit, or model specification.
3. A design simulation showing that the selected block/cluster count reaches the
   owner-selected supported-classification probability at the decision-relevant
   effect under a conservative variance/dependence model.
4. The randomization, session-reset, allocation, or clustering plan; the
   functional unit; the SESOI; and the responsible owners.

## Compatibility decision table

| Design condition | Acceptable registered approach | Evidence that must be retained |
|---|---|---|
| Randomized crossover with reset sessions and no planned carry-over | Paired randomization or paired interval, subject to design checks | Allocation schedule, reset/session records, block manifest, planning analysis, committed source |
| Ordered blocks, continuous runs, or plausible drift | Predeclared HAC, model-based interval, or block bootstrap with justified lag/block length | Ordered time series, diagnostic outputs, tuning rule, planning sensitivity, committed source |
| Shared devices, nodes, or repeated service clusters | Cluster-robust or hierarchical method with adequate independent clusters | Cluster IDs, assignment map, cluster-count calculation, model/code |
| Insufficient evidence to distinguish dependence structures | No support path at the requested level | Limitation record; classification must be inconclusive until additional independent units or a narrower claim are available |

A non-significant autocorrelation diagnostic alone does not establish
independence. If the registered method cannot be supported by the available
record, `dependence_compatible_interval` must not be marked pass.
