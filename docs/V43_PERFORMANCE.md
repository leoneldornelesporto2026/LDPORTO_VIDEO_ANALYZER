# V4.3 Performance

Atualização: o full run local V4.3 já foi executado. Tracking medido 2670.282s,
semântica 6053.453s e Global Review 454.406s, concluído. A afirmação “não executado”
abaixo é histórica. [Reconciliação e limites](V44_BASELINE_RECONCILIATION.md).

## V4.2 baseline hotspots

- Semantic: ~11606 s (~3 h 13 min)
- People tracking: ~3211 s
- Scene detection: ~974 s
- Transcription: ~767 s
- Diarization: ~134 s

V4.3 adds profilers for semantic calls, visual subphases, serialization and process memory; deterministic semantic cache keys; selective cache invalidation; adaptive visual sampling hooks; and downstream replay.

## What is proven

- Downstream replay can execute without rerunning expensive ASR/diarization/vision/LLM stages.
- `compare_runs` marks runtime/call deltas as `not_comparable_execution_scope` when execution scopes differ.
- Semantic cache/structured-output/targeted-repair behavior and visual/camera optimizations are covered by regression fixtures.

## What is not yet proven

No new complete source-video run has been executed after all V4.3 changes. Therefore no claim is made yet that semantic runtime, visual runtime or total runtime improved by a specific percentage. Those claims require the same source, compatible configuration and full execution.
