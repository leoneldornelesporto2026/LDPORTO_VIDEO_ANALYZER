# Integration milestone — GitHub checkpoint 2026-11-04

This document supersedes *status* notes in earlier historical audit snapshots without rewriting the evidence.

- Baseline candidate: `baseline/ldporto-20261012-prompt01`, SHA `b28c78c`. Unlike `main`, it has unrelated Git history.
- Integration PR: [#2](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/pull/2) (draft) targets `develop` from `feature/ldporto-baseline-integration-20261104`; audit PR #1 is being consolidated into PR #2.
- 240 core runtime/config/schema/script file paths matched baseline Git blob SHAs in a previous checkpoint. Future commits must be rechecked.
- Linux offline regression at SHA `2aec995`: [PASS, 2,607 tests passed, 5 skipped, 7 exact historical tests deselected](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41922061643). Full historical provenance remains NOT TESTED.
- Synthetic-only second-curation ZIP at the same head: [PASS](https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41922061535). Artifact tested as PARTIAL, not editorial-ready.
- Native Windows runner workflow added at SHA `a3a72f2` for Python 3.11, CHECK_RUNTIME.bat, CRLF, selected contracts. Its outcome must be separately verified; no result asserted by this document.
- Historical ZIPs `CHATGPT_REVIEW.zip` and `SECOND_CURATION_READY.zip` not present as versioned source. Local checksum/provenance acceptance remains BLOCKED.
- Windows local checkout, ignored or uncommitted files, GUI, GPU, Ollama, real media, remote workflow URL analysis and release acceptance remain NOT_RUN.
- `develop`, `release`, `main` retain initial SHA `e8d3b94`; no merges, force pushes or branch deletion have been performed. No branch rulesets configured.
- Source history, heavy reports and archive remain preserved on the original baseline branch.

## Remaining gates

1. Resolve native Windows CI findings without masking errors. Classify Linux/Windows differences.
2. Run full Windows acceptance on the user's existing installation; capture `git status`, exact SHA, untracked files and local-only data safely.
3. Independently verify missing historical ZIP SHA-256 privately; don't commit personal data to public GitHub.
4. Review PR #2 content, workflow security, and existing code path contracts; merge to `develop` only when actual source baseline is approved.
5. Promote reviewed content to `release`, then to `main` only with explicit approval. Only after homologation, remove old remote branches safely with rollback references.

`docs/RECONCILIATION_MATRIX.md`, `docs/REPOSITORY_CLEANUP_REPORT.md`, `docs/BRANCHING_STRATEGY.md`, `docs/RELEASE_PROMOTION.md` remain available as audit evidence and policies.
