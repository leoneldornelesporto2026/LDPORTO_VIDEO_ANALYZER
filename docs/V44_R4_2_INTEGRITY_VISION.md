# V4.4 R4.2 — Integrity + Vision Hardening

Build: `R4.2-INTEGRITY-VISION`  
Logical/cache version: `4.4.0`

## Why this build exists

A real 2h17 benchmark exposed a critical control-plane failure: `16_understanding` could receive a nested list where a mapping was expected, fail with `list object has no attribute get`, and downstream still emit provisional candidates/Stories. The same benchmark also showed commercial promotions leaking into Stories and ~70% micro-tracklets being discarded even when some carried usable face evidence.

## Round 1 — editorial integrity (implemented)

- Deep semantic-contract normalization with path-level diagnostics.
- `understanding_contract_diagnostics.json` artifact.
- Fail-closed second-curation/social state when Understanding is failed/blocked/unavailable.
- Provisional diagnostic candidates are explicitly non-publication-eligible.
- Canonical commercial invariant: `eligibility=excluded` => shortlist/Story ineligible.
- Commercial block propagation with bounded context and precursor-signal requirement.
- Extra PT-BR commercial cues for installments, poltrona/cadeira/móveis/sofá-cama.
- Readiness explains Understanding failure rather than masking it as visual incompleteness.

## Round 2 — visual identity (implemented conservatively)

- Micro-tracklets are still retained as raw evidence.
- A micro-tracklet may attach only to an already-established identity when it has a face embedding, passes a stricter threshold/margin than ordinary Re-ID, and has no temporal conflict.
- No screen-position merge. No new identity is created from a micro-tracklet.
- Metrics: `micro_reid_attachment_count`, `micro_track_mapped_fraction`, `unmapped_micro_track_count`.

This is not an accuracy claim. The benchmark must measure whether mapping/active-speaker coverage improves without conflicts.

## Round 3 preparation — camera diagnostics (implemented)

Smart Zoom now reports:

- `zoom_opportunity_window_count`
- `zoom_request_window_count`
- `zoom_accepted_event_count`
- `zoom_delivered_event_count`
- `zoom_aborted_window_count`
- `zoom_block_reason_counts`
- `zoom_delivery_fraction`

No zoom threshold was relaxed. These metrics exist to show the next causal bottleneck before changing camera behavior.

## Validation in audit environment

- `423 passed, 2 skipped`
- skipped tests are environment-dependent Tk display / Git metadata checks
- Python container validation is regression-only; official runtime remains Windows/Python 3.11.x

## Next benchmark questions

1. Does `16_understanding` complete on the real semantic output?
2. Do Broadcast Graphics / Commercial Visual / Targeted ASR run downstream?
3. Are commercial leaks into Stories zero?
4. How many micro-tracklets are safely attached and does speaker/person coverage rise above ~15.05% without conflict?
5. What exact reasons block Smart Zoom opportunities?
6. Only after those answers: optimize camera behavior and runtime/concurrency.
