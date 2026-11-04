# Repository cleanup inventory (audit only)

Audited 2026-11-04 via GitHub Git Trees, recursively, without modifying files. This is an initial file-level inventory, NOT proof that a path is safe to delete.

| Scope | Main | Feature v4.4 | Windows baseline |
| --- | ---: | ---: | ---: |
| Tracked blobs | 172 | 513 | 1,618 |
| Bytes summed from Git tree blobs | 1,295,708 | 11,812,383 | 242,405,828 |
| Files under `docs/reports/` | 1 | 1 | 1,022 |
| Files under `docs/archive/` | 0 | 0 | 14 |
| Other `docs/` files | 42 | 68 | 81 |
| Files under `src/tests/` | 23 | 100 | 238 |
| Files under `src/ldporto/` | 50 | 86 | 135 |
| Files under `scripts/` | 13 | 46 | 68 |
| Files under `automacao/` | 0 | 160 | 0 |
| Files under `.package/` | 0 | 3 | 3 |
| Files at least 1 MiB | 0 | 2 | 61 |
| Files at least 10 MiB | 0 | 0 | 3 |

Git blob identity groups found in baseline: 64 groups with more than one identical blob SHA; 142 *extra paths* across those groups. They are duplicate CANDIDATES, not confirmed deletion targets or SHA-256 audits. Bytewise matching/sha256, references and test provenance are required before removing any path.

### High-volume review queue

- `docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/camera_replay_r62_v2/timeline.json` (~16.57 MiB).
- `docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/camera_replay_r62_curator_compat/timeline.json` (~16.55 MiB).
- `docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/camera_replay_r62/timeline.json` (~16.29 MiB).
- `docs/reports/sol_v4_20261013/after_visual/vision.json` (~6 MiB).
- `docs/reports/sol_v4_20261013/before_visual/vision.json` (~5.83 MiB).
- `docs/reports/r51_20261014/` and `docs/reports/r5_1_20261014/` contain matching Git blobs; examine consumers/unique provenance before consolidation.
- `.package/` export metadata and `src/tests/fixtures/` remain REVIEW_REQUIRED / KEEP_TEST pending evidence.
- Prior feature branch contains 160 `automacao/` files, while Windows baseline does not. Do not bring obsolete automation back as part of source reconciliation.

### Classification policy

KEEP_RUNTIME: executable code, imports, GUI/CLI, startup .bat, config, dependencies and schemas.
KEEP_TEST: active tests, fixtures and historical contract canaries.
KEEP_DOCUMENTATION: current setup, architecture, API contract, operational steps, indexes.
ARCHIVE: unique historical technical evidence needed for traceability.
GENERATED: confirmed reproducible logs, temporary test output and package exports.
DUPLICATE: *confirmed* same-content artifacts with no unique consumer or provenance.
SENSITIVE: any file containing credentials, proprietary media, transcripts or personal identifiers.
REVIEW_REQUIRED: uncertain category, active dependency or source of truth.

### Constraints and exact outcome

Tracked files removed: **0**. Archived: **0**. Source changed: **0**. After count: **unchanged**. Actual safe cleanup is still pending.

For every proposed removal: enumerate exact path, Git blob SHA, SHA-256, size, references/imports, classification, reason, preservation/rollback location, and before/after counts. Use `git rm --cached` only if an already tracked file must become local-only, with preservation confirmed. Never erase Windows inputs, analyses, models, checkpoints, settings or historical unique evidence; never rewrite public history or expose secret contents. Change `.gitignore` for future generated artifacts as appropriate, remembering it does not untrack existing files.

Only apply removals after reviewing all affected consumers and running baseline regression tests. In a public repository, perform security review before making any newly copied local content public.
