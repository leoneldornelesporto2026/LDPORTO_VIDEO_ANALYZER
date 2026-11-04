# Integration staging checkpoint — 2026-11-04

## Status and ancestry

- Base parent on `develop`: `e8d3b94c5686df76ee354367f940111352053c03` (original main; no history rewrite).
- Source baseline: `baseline/ldporto-20261012-prompt01` at `b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d`.
- Staged commit: `759ffc8e05959fc4f1fde0ce79d126fd65be18f3` on `feature/ldporto-baseline-integration-20261104`.
- 580 *source-selected* Git blobs, 5,321,002 bytes, copied from the baseline Git tree by SHA without modifying the original baseline.
- Included: entrypoints, Windows BAT launchers, runtime engines, schemas, config, requirements, scripts, tests/fixtures, examples, current docs.
- Excluded from new branch: 1,022 baseline files in `docs/reports/`, 13 historical files in `docs/archive/` besides its index, and three `.package/` metadata files. All remain fully available in the original baseline branch and its history.
- Git's baseline and main histories have no common ancestor; this was a **copy by blob identity**, not an unrelated-history merge.
- The old `main` had `docs/reports/WORKER_FINAL_REPORT_V42.md`, which was retained rather than deleted. No deletion occurred.

## Verification limits

- File inventory/selection and Git tree ancestry: PASS.
- Offline regression and artifact tests: NOT_RUN until this branch's GitHub Actions run reports.
- Windows 11 Python 3.11.9 / GUI / media / GPU / Ollama: NOT_RUN; local files and uncommitted state inaccessible.
- Functional parity with the actual local Windows installation: BLOCKED until local SHA and working-tree diff have been inspected.
- Privacy inspection of newly selected historical fixture contents: REVIEW_REQUIRED; only remote-published files were referenced.
- Nothing was merged to develop, release or main. No new release tag or ZIP has been declared accepted.

## Important historic-report caveat

The baseline `README.md` and some tests refer to `docs/reports/` historical evidence. Those links were not automatically copied into this working branch to avoid bringing 240 MB of historical runtime artifacts forward. Review any failing tests or broken links and selectively preserve *necessary, proven* evidence or add a source-baseline link; do not silently rewrite provenance.

## CI introduced with this checkpoint

`.github/workflows/analyzer-offline-validation.yml` checks Python 3.11 syntax, JSON parsing, synthetic exporter self-test and the offline pytest suite; JUnit only is kept as short-lived artifact. No model downloads, real video or external deploy. The workflow must pass before considering promotion, and its success does not imply Windows acceptance.

## Next

1. Inspect CI result and fix only proven compatibility/test problems on this feature branch.
2. Validate code imports, tests, exporter/reader integration, R6/R6.2/R6.3 handoff, privacy and generated-file hygiene.
3. Obtain local Windows SHA/status with safe read-only commands, reconcile any local-only changes.
4. Review full diff & approvals, merge to develop, then release; main only with explicit user approval.
