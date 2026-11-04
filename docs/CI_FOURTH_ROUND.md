# CI validation #4 — 2,602 passing tests, 5 blockers

Run https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41920627557
SHA: `87d379ac1bed88d3a278ca90d6509626ce9a0798`

Python and schemas: PASS. Synthetic exporter: PASS. Full portable pytest: **FAIL** (2,602 passed, 5 failed, 5 skipped, 7 historical tests deselected). Exact new failures:

- 2 OCR tests use synthetic fake Tesseract executables without executable POSIX bits. The production `resolve_executable()` correctly rejects the files before the mock probes. Corrected the two *test fixtures* with chmod(0o755); no weakening the runtime check.
- 2 tests found missing `scripts/windows/diagnostics/DIAGNOSTICO_WINDOWS.bat` and `DIAGNOSTICO_GPU_WINDOWS.bat`; root .bat wrappers pointed to missing implementations in the original baseline. Added safe diagnostics that run `CHECK_RUNTIME.bat` before, and invoke existing `analyze.py --doctor --offline` or `scripts/test_gpu.py --check-only`, returning exact exit code; no model download, installation or inference.
- Root allowlist test forgot to include the newly required `.gitattributes` used for Windows BAT CRLF checkout. Added legitimate Git config to the test allowlist.

**Not yet accepted:** The next CI run must confirm these changes. Local Windows tests are still NOT_RUN and the historical ZIP provenance acceptance remains BLOCKED without original local files.
