# CI second and third round — verified failures and resolutions

Reference runs:
- https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41919314064
- https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41919844216
- https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41919844295

On the second and third Analyzer CI runs, Python/schema compile and synthetic exporter self-test passed. Pytest stopped after five further local-only historical ZIP fixture errors, reporting **1,358 passed, 5 failed, 1 deselected**. The same five failures were reproducible. No application regression was proven by those errors.

Missing baseline-remote files: `src/tests/fixtures/historical_evidence/CHATGPT_REVIEW.zip` and `SECOND_CURATION_READY.zip`. Both remain required for exact historical provenance acceptance; they are not present as tracked Git objects and were never reconstructed artificially.

CI now conditionally deselects only seven EXACT test cases requiring these ZIPs (one in `test_historical_fixture_provenance`, one in `test_stage13_explainability`, three in `test_stage17_editorial_replay`, one in `test_stage18_handoff_audit`, one in `test_stage19_uncertain_words`). The other tests from those modules still run. When both files are physically available, all seven automatically re-enter the suite. This creates a portable offline CI result but does NOT establish historical-fixture acceptance or Windows homology.

The first synthetic ZIP workflow run failed at shell line 1 with `import: command not found` / exit 127 due to missing Python heredoc invocation. This was a workflow-script wrapper defect, not a packaging-engine failure. It is corrected to `python - <<'PY' ... PY` and requires a new run.

Promotion remains BLOCKED on Windows validation and missing fixture provenance. Subsequent CI results are tracked separately; no PASS claimed here.
