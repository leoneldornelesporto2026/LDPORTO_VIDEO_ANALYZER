# Environment baseline / reconciliation checkpoint

Snapshot date: 2026-11-04. Source: remote GitHub ref, commit, tree and root-file read-only inspection. This document is *not* a Windows test report.

| Ref | Inspected SHA | Tracked blobs | Sum of blob sizes |
| --- | --- | ---: | ---: |
| `main` | `e8d3b94c5686df76ee354367f940111352053c03` | 172 | 1,295,708 B |
| `feature/v4.4-evidence-driven-editor` | `34797e164377f05e64ae628daf499cda2fb8bf55` | 513 | 11,812,383 B |
| `baseline/ldporto-20261012-prompt01` | `b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d` | 1,618 | 242,405,828 B |

`develop` and `release` were created with the original `main` SHA `e8d3b94c5686df76ee354367f940111352053c03`. Those new refs are provisionally identical to `main` ONLY at branch creation; they do not contain the Windows baseline.

## Evidence established

- Repository visibility was PUBLIC at inspection time. Never publish local media, transcripts, person data, credentials or private analysis artifacts to repository files, workflow logs or public Actions artifacts.
- Feature branch: 12 commits ahead of `main` with shared ancestry (GitHub compare).
- Baseline: no shared Git ancestor with `main` or feature branch (GitHub compare returned 404 / No common ancestor).
- Baseline has `app.py` (GUI), `analyze.py` (CLI), `ABRIR_ANALYZER.bat`, `scripts/export/exportar_ldporto.py`, `docs/README.md`, 238 tracked files under `src/tests/` and no `automacao/` tree.
- Existing launcher calls `scripts/windows/CHECK_RUNTIME.bat` then `.venv/Scripts/python.exe app.py`.
- The Windows local path, Python 3.11.9, runtime version and branch were user-provided; NO independent local disk inspection, `git status`, functional GUI test, model/GPU/Ollama test or video test was possible from this GitHub-only session.

## Current states

- Branch scaffolding: PASS (creation of develop and release; no main rewrite).
- Canonical Windows implementation selection: PARTIAL (candidate identified, local modifications unverified).
- Environment functional parity: BLOCKED.
- Repository cleanup execution: NOT_RUN (inventory only).
- Offline Python regression / exporter and consumer tests: NOT_RUN.
- Windows GUI / real video validation: NOT_RUN.
- Actions workflows and ZIP reconstruction: NOT_RUN.
- Production promotion and release tag: NOT_RUN.

## Resumption commands — on user's existing Windows checkout (read-only)

```bat
REM Execute these commands from the existing Windows Analyzer repository folder.
REM Do not guess a local path, copy or change the working directory.
git status --short --branch
git branch -avv
git remote -v
git log -1 --format="%H %s"
git fetch origin --prune
git status --porcelain=v1 --untracked-files=all
```

Do NOT run `git reset --hard`, `git clean -fd`, destructive checkout, or `git pull` with an unresolved working tree. Record the exact local SHA and changes before copying/reconciling into a fresh workspace.

Next work unit: classify remote file candidates; inspect local `git status`; produce module-level comparison matrix; copy/reconcile safely in a separate integration branch. Follow `docs/BRANCHING_STRATEGY.md`.
