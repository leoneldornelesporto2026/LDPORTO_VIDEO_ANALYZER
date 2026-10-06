# V4.3 Real Benchmark Status

## Official V4.2 baseline

Source duration ~8245 s, 1920x1080 at 30 fps. The official review baseline records severe track fragmentation (8603 raw tracks, 5998 micro-tracks, median ~0.166 s), 2213 persistent identities, zero speaker-person/active-speaker resolved coverage, ~11606 s semantic runtime, 329 question candidates with only 10 answered, source-preserving camera fallback and a degraded/partial overall status.

## V4.3 evidence available so far

A downstream replay against the official exported artifacts successfully exercised understanding, planner, Director and reporting without rerunning Whisper, Pyannote, vision or Qwen. It produced a validated compact core package (~1.56 MB in the developer run) with 188 candidates including alternates, checksums and zero dangling references. It remained PARTIAL because the review ZIP did not contain the source media required for real contact sheets/previews and because upstream person/speaker focus was not re-executed.

This replay is evidence for deterministic downstream compatibility, not proof of full-video accuracy or runtime improvement.

## Acceptance still required

Run the complete V4.3 pipeline on the same source video in the canonical Windows/Python 3.11 environment. Compare tracking fragmentation, Re-ID, speaker-person/active-speaker coverage, commercial shortlist contamination, semantic calls/repairs/cache/runtime, camera resolved focus/Smart Zoom and preview validation against V4.2. Runtime deltas must not compare a downstream replay to a full run.
