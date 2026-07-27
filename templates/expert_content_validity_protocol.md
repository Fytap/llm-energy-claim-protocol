# Independent Content-Validity Review Protocol

## Purpose

This review evaluates the proposed L0-L4 claim-profile registry for relevance,
clarity, necessity, and profile assignment. It does not evaluate the authors,
the reported energy effects, or any confidential operational data.

## Panel and independence

Recruit 5-10 reviewers who are not manuscript authors and did not design the
registry. Aim to cover metrology/energy measurement, LLM serving, sustainable
computing or carbon accounting, assurance/conformity assessment, and service
operations. Record expertise category and years of relevant experience, not
names, in the analysis file. Do not include a reviewer with a material conflict
that cannot be managed.

## Ethics and consent gate

Before recruitment, obtain the institution's written determination of whether
this professional expert-review activity requires ethics approval or exemption.
Do not claim an exemption without that determination. Give each reviewer the
following consent text before collecting a score:

> Participation is voluntary. You will review a proposed technical registry and
> may skip any item. The study will retain an anonymous reviewer code, expertise
> category, and ratings/comments; it will not publish names. You may withdraw
> before the analysis freeze date by quoting your reviewer code.

Record the determination reference, consent procedure, recruitment date,
analysis-freeze date, and any registry amendment in `PANEL_AUDIT_LOG.csv`.

## Materials to send each reviewer

1. `REGISTRY_GATE_SCORECARD.csv`.
2. The human-readable registry inventory from Supplementary Table 2.
3. A one-page claim-profile definition sheet.
4. This protocol.

Do not send manuscript results, author identities, or a preferred answer key.
Ask reviewers to complete their scorecard independently before discussion.

## Ratings

For each row, enter:

- `relevance_1_to_4`: 1 not relevant, 2 somewhat relevant, 3 quite relevant,
  4 highly relevant.
- `clarity_1_to_4`: 1 not clear, 2 needs major revision, 3 clear with minor
  revision, 4 clear.
- `necessity`: `essential`, `useful_not_essential`, or `not_necessary`.
- `profile_assignment`: `correct`, `too_low`, `too_high`, or `not_applicable`.
- An optional concise comment.

## Prespecified analysis

For every gate-profile row with at least five ratings, report:

- I-CVI relevance and clarity: fraction of ratings >=3.
- CVR necessity: `(n_essential - N/2)/(N/2)`.
- Profile-assignment agreement: fraction marked `correct`.
- All comments and a structured amendment disposition.

The final report must label these as panel responses, not scientific proof of
gate sufficiency. Retain the raw, de-identified scorecards, analysis script,
and the registry version used for review.

## Amendment rule

No registry change may be made after examining energy results. After scoring,
each proposed amendment must record: gate/profile, panel evidence, author
decision, rationale, old/new registry digest, and whether it requires a new
round of review. Publish unchanged, revised, deferred, and rejected suggestions.
