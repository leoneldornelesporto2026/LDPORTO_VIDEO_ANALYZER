# V4.3 Changelog

## Scope

V4.3 hardens the existing analyzer instead of replacing its architecture. The main changes are evidence-preserving tracking/Re-ID, global speaker-person affinity, commercial gating, editorial boundary/Q&A/story fixes, structured semantic caching/repair, Smart Zoom, rendered preview verification, weighted progress/ETA, replay, causal status, repository cleanup and automatic second-curation export.

## Notable changes

- Tracking: shot-aware continuity, Hungarian assignment, embedding memory and explicit conflict safeguards.
- Re-ID / participants: robust templates, simultaneous-conflict rejection and separation of visual catalog from editorial participants.
- Speaker-person: global affinity over independent evidence windows; ambiguity remains null.
- Editorial: stronger commercial detection, 30-90 s default duration contract, cleaner openings/endings, better Q&A and story/topic hierarchy.
- Semantic: structured output, targeted repair, deterministic cache keys, grounded quote refs and partial Global Review preservation.
- Camera: Smart Zoom state machine, dwell/hysteresis, source-close suppression, upscale/crop safety and source-preserving fallback.
- Preview: rendered canaries, zoom/jitter/pumping/target-loss verification and bounded repair.
- UX: structured progress events, weighted overall progress, ETA and completion screen.
- Handoff: automatic SECOND_CURATION_READY/PARTIAL core ZIP, optional media ZIP, contact sheets, checksums/readiness and SECOND_CURATOR_BRIEF.json.
- Replay/compare: downstream replay with provenance and runtime-comparison guard across different execution scopes.
- Windows/runtime: Python 3.11 contract, FFmpeg/FFprobe discovery, TorchCodec shared-DLL bootstrap and reorganized scripts/requirements.
- Repository: generated PROJECT_EXPORT/WORK_PACKAGE files removed; historical manifests/docs relocated; root wrappers kept for compatibility.

## Audit fixes after commit 39d2193

- Restored the missing canonical `scripts/windows/diagnostics/DIAGNOSTICO_WINDOWS.bat` and `DIAGNOSTICO_GPU_WINDOWS.bat` implementations referenced by root wrappers.
- Added `SECOND_CURATOR_BRIEF.json` to the compact handoff contract and validator.
- Added regression coverage proving `compare_runs` surfaces V4.3 Smart Zoom/readiness/handoff metrics while preserving scope-aware runtime comparisons.
- Made the Windows-wrapper path regression portable without weakening its Windows contract.

## Remaining acceptance work

- Targeted ASR re-review/prioritization remains unfinished.
- A new full-video V4.3 run is required to prove real tracking/active-speaker/camera and runtime improvements.
- Final full-suite homologation must still be rerun on Windows/Python 3.11 after these last audit fixes.
