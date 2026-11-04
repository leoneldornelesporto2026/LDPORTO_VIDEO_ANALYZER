# Second Curation ZIP — GitHub workflow (synthetic proof)

Workflow: `.github/workflows/second-curation-synthetic.yml`.

**Status:** code staged in the integration PR. Its end-to-end GitHub run must be evaluated separately; adding a workflow file does not prove execution or acceptance.

## Supported scope

Only uses `src/tests/test_v43_handoff.py`'s synthetic fixture; no URL, user video, downloaded media, transcript or secret is accepted. The workflow:
1. Starts under Python 3.11, offline inference environment flags.
2. Calls the existing `build_core_package()` (no reimplementation of the Analyzer engine).
3. Uses `snapshot_core_package()` for independent byte-level validation.
4. Uses existing `inspect_package()` for ZIP integrity and secret scanning.
5. Explicitly rejects actual video/audio files and any claims of preview/publication approval.
6. Records the source commit, SHA256, ZIP size, integrity and READY/PARTIAL state.
7. Exposes ONLY the synthetic ZIP and its JSON manifest as GitHub Action artifacts.

This is the **safe initial version** of the user-requested manual ZIP workflow. It is NOT YouTube ingestion or real analyzer inference, and PARTIAL must never be marketed as READY.

## To support real analyses later

The GitHub repository was public at inspection. Do **not** add media, faces, transcripts, private analysis exports or personal data to its code or Actions artifacts. Design an approved source path, robust privacy and provenance controls, and private artifact retention (e.g., reviewed private self-hosted runner) first; verify system dependencies/models/compute and implement the handoff contract on that environment. The Windows local state is still unavailable from GitHub-only operation.
