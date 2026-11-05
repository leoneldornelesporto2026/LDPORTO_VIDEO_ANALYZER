# Baseline versus feature — structural reconciliation matrix

Snapshot: remote tree comparison on 2026-11-04. This is a path/blob inventory only, NOT a code review or proof of runtime feature equivalence.

Refs:
- Windows candidate `baseline/ldporto-20261012-prompt01`: `b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d`
- Prior `feature/v4.4-evidence-driven-editor`: `34797e164377f05e64ae628daf499cda2fb8bf55`
- Stable pre-reconciliation `main`: `e8d3b94c5686df76ee354367f940111352053c03`

## Git tree path intersection

| Measure | Result |
| --- | ---: |
| Baseline tracked files | 1,618 |
| Feature tracked files | 513 |
| Paths present in both | 349 |
| Identical Git blob SHAs among common paths | 258 |
| Same paths with different blobs | 91 |
| Baseline-only paths | 1,269 |
| Feature-only paths | 164 |
| Baseline-only Python paths in `src/ldporto/` | 49 |
| Baseline-only files in `src/tests/` | 139 |

Among the 164 feature-only paths, 160 are in `automacao/`; the remaining four are `FINAL_HOMOLOGACAO.md`, `orquestrador.py`, `scripts/dev/baseline_etapa01.py`, and `src/tests/test_autopilot_orquestrador.py`. Do NOT reintroduce old automation automatically; confirm actual runtime consumers before excluding any source file.

## High-priority functional area review

The matrix below counts matching remote file paths by a narrow name/prefix heuristic. It does **not** measure implementation quality. A count of zero does not prove that the functionality is missing: it may have another module name.

| Area | Main | Feature | Baseline | Follow-up |
| --- | ---: | ---: | ---: | --- |
| GUI `app.py` | 1 | 1 | 1 | Blob differs between feature and baseline; verify startup/UI |
| CLI `analyze.py` | 1 | 1 | 1 | Blob differs; verify flags and compat |
| `ABRIR_ANALYZER.bat` | 1 | 1 | 1 | Same blob across feature/baseline |
| Core analysis exporter implementation | 1 | 1 | 1 | Blob differs; test ZIP/readers and privacy |
| ASR path containing `transcription` | 1 | 1 | 1 | Changed; review fidelity |
| Diarization path containing `diariz` | 1 | 1 | 1 | Changed; review speaker alignment |
| OCR-named `src/ldporto` paths | 1 | 1 | 4 | 3 extra baseline modules |
| Semantic-named `src/ldporto` paths | 1 | 2 | 6 | 4 extra baseline modules |
| Camera-named `src/ldporto` paths | 4 | 6 | 7 | Extra camera handoff |
| Editorial-named `src/ldporto` paths | 1 | 3 | 6 | 3 extra baseline modules |
| Curation-named `src/ldporto` paths | 0 | 2 | 5 | 3 extra baseline modules |
| `src/tests/` tracked files | 23 | 100 | 238 | Preserve fixtures and historical tests |

Selected baseline-only modules to review: `compact_handoff_reader.py`, `curation_recovery.py`, `curator_camera_adapter.py`, `export_privacy.py`, `r62_delivery.py`, `semantic_runtime.py`, `ocr_runtime.py`, `editorial_review.py`, `speaker_windows.py`, `camera_handoff.py`, `visual_review.py`, and `zoom_delivery.py`.

Selected changed shared modules to diff: `active_speaker.py`, `camera_director.py`, `commercial_gate.py`, `diarization.py`, `editorial_intelligence.py`, `person_reid.py`, `pipeline.py`, `preflight.py`, `ollama_local.py`, `exportar_ldporto.py`, `app.py`, and `analyze.py`.

## Next execution: safe technical sequence

1. Read Windows `git status`, all refs and exact local SHA; capture untracked/ignored state and local snapshot without destructive commands.
2. Inspect the 91 same-path differences and the 49 baseline-only core modules for imports, entrypoints, contracts and real consumers. Review the four non-automation feature-only paths before considering them obsolete.
3. Check secrets/privacy and fixture references; classify exact file candidates and compare SHA-256, not just Git blob identity.
4. On an isolated branch based on `develop`, implement a controlled source reconciliation preserving main ancestry; no unrelated-history merge or forced ref.
5. Run offline Python 3.11 tests, contracts, exporter/ZIP inspection. Then review on Windows and only then promote to `release` and (after explicit approval) `main`.

No functional source changes, deletions or tests were executed during this matrix audit.
