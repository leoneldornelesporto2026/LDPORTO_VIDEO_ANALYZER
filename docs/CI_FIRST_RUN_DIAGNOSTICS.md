# CI result — first validation on Windows-baseline integration

Date: 2026-11-04.
Run: https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41918775104
Head tested: `2230b333f8f0b9dc2be830916120f43e0304e25a`.

- `syntax-and-schemas`: **PASS** (Python 3.11 compileall and parse of JSON schemas).
- Exporter built-in synthetic self-test: **PASS**.
- `pytest-offline`: **FAIL** — 678 passed, 5 failed, interrupted by `--maxfail=5`.
- Fail 1: the root Windows BAT files did not have CRLF on Ubuntu checkout. Remediation: `.gitattributes` with `*.bat text eol=crlf` so all launchers have Windows-compatible line endings at checkout.
- Fails 2–3: FFmpeg executable absent from GitHub runner during synthetic pipeline/preview tests. Remediation: install FFmpeg/FFprobe in CI; no real video or models downloaded.
- Fail 4: `src/tests/fixtures/historical_evidence/CHATGPT_REVIEW.zip` is not in Git, even on baseline, because historic ZIP is a local-only file. Remediation: only *conditionally* omit that one test from CI when absent and explicitly record BLOCKED in GitHub job summary; it remains enabled on machines where the original byte-for-byte fixture exists. Never recreate or silently substitute the historical archive.
- Fail 5: DejaVu/Arial glyph map differs for NBSP/soft-hyphen: source text and CID separation were correct; the test wrongly assumed distinct Unicode codepoints must share font glyphs everywhere. Remediation: assert that each CID maps to the actual selected font glyph, including alias reuse when the font shares it; do not change the production PDF writer.

All fixes are isolated to CI settings, test portability and Git checkout behavior. No production code, video, model, Windows data or release branch is changed.

Next run must be recorded as new evidence; do not copy the 678 count as an updated result. GUI acceptance remains NOT_RUN.
