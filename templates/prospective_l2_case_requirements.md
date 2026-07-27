# Prospective L2 Case: Minimum Collection Requirements

This is the smallest real case that can address the reviewer's L2 request.

## Before collection

- Freeze a claim object, registry digest, comparison, functional unit, quality
  task, non-inferiority margin, SLA, SESOI, direction rule, inference method,
  randomization schedule, stopping rule, and multiplicity family.
- Record an immutable timestamp or public/private repository commit before the
  first measurement.
- Specify an externally calibrated PDU, wall meter, or board meter, its model,
  calibration date, sampling interval, clock/timezone, synchronization method,
  power boundary, and uncertainty budget.
- Freeze runtime/container image digest, CUDA/driver/firmware, power cap,
  clock policy, GPU mapping, temperature policy, model/checkpoint digest,
  quantization provenance, and all serving flags.

## Design and records

- Use a randomized or balanced cross-over design with documented reset/warm-up
  sessions and independent block identifiers.
- Capture synchronized NVML and external-meter traces, request timestamps,
  input/output token counts, task outputs, completion/success outcomes, quality
  scores, SLA outcomes, temperatures, and background-load log.
- Use paired task evaluation and report energy/request, energy/output token,
  energy/total token, tokens/J, completion rate, and quality/SLA status.
- Have a non-author reviewer check the claim, meter metadata, runtime digest,
  randomization record, and analysis output before unblinding the comparison.

## Decision boundary

An L2 result is externally calibrated device-side service energy under a
declared task and boundary. It is not whole-server, facility, lifecycle, or
carbon-reduction evidence unless those boundaries and measurements are added.
