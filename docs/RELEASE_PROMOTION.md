# Controlled release and rollback

Status: POLICY DRAFT. Neither Windows acceptance nor production promotion has occurred.

## Intended route

`feature/*` (when needed) or changes in `develop` -> reviewed `develop` -> approved `release` -> explicitly authorised `main`.

A version is not called equalized until the selected `develop`, `release` and `main` trees are compared for the same intended release and both automated regression and local Windows acceptance have evidence. After that snapshot, `develop` may advance independently.

## Pre-release checklist

- Recover local baseline SHA and uncommitted/ignored-file inventory on Windows.
- Confirm canonical module matrix and no lost GUI, ASR, diarization, OCR, tracking, visual/editorial, Ollama or second-curation features.
- Check Python 3.11.9, startup BAT, GUI, config loading, offline pytest, schemas, exporter, ZIP reader, Analyzer -> Curator handoff.
- Separate synthetic checks from real video/GPU/model inference. Label each with exact run/date/SHA.
- Review secrets, data privacy, large artifacts, file cleanup report and complete diff.
- Confirm Actions status and external integrations before changing branch default or enabling automated triggers.
- Confirm approved source/target SHAs and snapshot/tag, with rollback owner.

## Branch security / configuration

Require PR reviews and status checks for `release` and `main` (and `develop` when available), disallow force pushes/deletions, and restrict deployment secrets to reviewed environments. These rules were NOT applied by this audit. Confirm GitHub's available ruleset permissions separately.

## Rollback

Do not `git reset --hard` or rewrite public branch history. Keep the previous tagged production SHA and recover via reviewed revert/promoted known-good commit. Preserve local datasets and deployment configuration. Log affected SHAs, artifacts, approvals and results.

## Current fact

New `develop` and `release` branches initially point to the original `main` commit `e8d3b94c5686df76ee354367f940111352053c03`. They are not certified as Windows-baseline equivalent. No production release is authorised.
