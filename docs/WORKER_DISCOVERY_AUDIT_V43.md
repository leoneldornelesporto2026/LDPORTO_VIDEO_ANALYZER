# Worker Discovery Audit V4.3

## DISC-V43-001 — High — Windows diagnostic wrappers referenced missing implementations

**Evidence:** `DIAGNOSTICO_WINDOWS.bat` and `DIAGNOSTICO_GPU_WINDOWS.bat` pointed to `scripts/windows/diagnostics/...`, but those canonical files were absent from commit 39d2193.

**Impact:** both public diagnostic commands would fail immediately on Windows.

**Fix:** restored canonical diagnostic implementations under `scripts/windows/diagnostics/`, using the shared Python 3.11 runtime check and project-root resolution.

**Tests:** wrapper-target regression plus full auxiliary suite.

**Status:** fixed.

## DISC-V43-002 — Medium — Implementation ledger lagged behind implemented/tested code

**Evidence:** many rows remained PENDING despite scoped gates reported during implementation.

**Impact:** misleading completion status and difficult handoff after credit exhaustion.

**Fix:** statuses reconciled conservatively into VERIFIED_FIXTURE / VERIFIED_REPLAY / VERIFIED_RUNTIME; unproven ASR/full-run/dead-code work stays pending.

**Status:** fixed.

## DISC-V43-003 — Medium — Second-curation package lacked a self-describing curator brief

**Impact:** a new ChatGPT/session could open the ZIP without knowing the intended task, goals, duration target or capability limitations.

**Fix:** added and validated `SECOND_CURATOR_BRIEF.json` with task, source, goals, duration target, readiness and recommended entrypoints.

**Status:** fixed.

## DISC-V43-004 — Medium — Compare-runs completion needed explicit V4.3 metric regression

**Impact:** readiness/Smart Zoom/handoff metrics could regress silently even though the collector had been extended.

**Fix:** added a regression covering Smart Zoom metrics, second-curation readiness/package metrics and existing execution-scope runtime guard.

**Status:** fixed.

## Remaining known gaps

- Targeted ASR re-review/prioritization is still pending.
- Dead-code audit is intentionally conservative and unfinished.
- Full Windows/Python 3.11 post-audit suite and full-video V4.3 benchmark remain required for release acceptance.
