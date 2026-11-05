# Branching strategy — L.D.PORTO VIDEO ANALYZER

Status: DRAFT / NOT HOMOLOGATED. Last verified: 2026-11-04.

## Permanent branches

- `develop`: daily development and integration. New routine work starts here; use feature branches when isolation/review matters.
- `release`: pre-production / Windows acceptance. Advance only after validated `develop`.
- `main`: approved production. No automatic promotion.

On 2026-11-04, `develop` and `release` were created pointing to the then-current `main` SHA `e8d3b94c5686df76ee354367f940111352053c03`. This means branching infrastructure exists; it does NOT mean source parity with the Windows baseline.

## Source reconciliation — mandatory before promotion

Candidate Windows branch: `baseline/ldporto-20261012-prompt01` at `b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d`.
Another distinct implementation: `feature/v4.4-evidence-driven-editor` at `34797e164377f05e64ae628daf499cda2fb8bf55`.

GitHub comparison confirmed that `main` and the feature branch share ancestry (feature is 12 commits ahead of the initial main). GitHub returned NO COMMON ANCESTOR for `main` vs. Windows baseline and for feature vs. baseline.

DO NOT perform an unrelated-history merge, forced ref update, force push, or production reset. Reconcile files and their consumers on a dedicated branch based on `develop`, with provenance captured per component and regression checks. Keep backup branches/history intact. Local uncommitted files and ignored media must be inspected on the Windows machine separately.

## Promotion gates

1. Compare implementations: GUI/CLI, ASR, diarization, vision, tracking, Re-ID, Active Speaker, OCR, Ollama, Camera Director, Smart Zoom, curator contracts R6/R6.2/R6.3, export/reader and recovery.
2. Preserve required fixtures and historic schemas; scan security/privacy before publishing.
3. Run offline regression and exporter/schema verification; retain logs and exact SHA.
4. Merge reviewed integration into `develop`.
5. Promote reviewed commit to `release`, perform Windows 11 + Python 3.11.9 GUI/real-runtime acceptance.
6. Promote the approved release to `main` only with explicit authorization.
7. Verify content/tree equivalence at the chosen release and record rollback SHA.

Set `develop` as GitHub default branch only after inspecting external integrations, automation triggers and open PRs. Configure branch rulesets/admin protections in repository settings (not yet applied).

See `docs/ENVIRONMENT_BASELINE.md`, `docs/RELEASE_PROMOTION.md`, and `docs/REPOSITORY_CLEANUP_REPORT.md`.
