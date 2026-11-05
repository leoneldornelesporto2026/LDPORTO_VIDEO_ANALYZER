# GitHub Actions Windows 11–related smoke test

Scope: GitHub-hosted `windows-latest` runner with Python 3.11 x64. It does **not** validate the owner's physical Windows 11 installation, GPU drivers or local models.

New workflow: `.github/workflows/analyzer-windows-smoke.yml`.

Operations:
- Create ephemeral venv on Windows; execute real `scripts/windows/CHECK_RUNTIME.bat` and confirm Python 3.11.
- Check CRLF on the root and internal Windows BAT scripts; verify diagnostic wrappers resolve to real files.
- Parse schemas and compile all Python sources.
- Install declared non-GPU runtime requirements and selected test dependency Pillow.
- Run targeted contract tests: `test_v43_runtime`, `test_r6_project_export`, `test_r63_compact_handoff_reader`, `test_r62_delivery_integrity`, and the actual Windows BAT contract test.
- Upload only JUnit XML, with no media, secrets or video analysis results.

This is a **new** CI scope not covered by the prior Linux pytest: it must execute and pass before it may be called verified. Windows full-suite testing, GUI interactive testing, real media, Ollama, GPU, FFmpeg integration, original historical ZIPs and promotion remain independent gates.

Any failure must be diagnosed. Do not skip tests or change production contracts solely to make the runner green. Keep the PR draft until evidence is complete and approved.
