# Second-curation export — verified entry points and open work

Status: SYNTHETIC-ONLY ZIP WORKFLOW PASS / REAL-MEDIA WORKFLOW NOT IMPLEMENTED.

Update, 2026-11-04: `.github/workflows/second-curation-synthetic.yml` executed successfully on the integration branch. See https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41922061535 and earlier ZIP artifact https://github.com/leoneldornelesporto2026/LDPORTO_VIDEO_ANALYZER/actions/runs/41920627409/artifacts/13366272755. The test package was PARTIAL (expected with the synthetic fixture), ZIP integrity PASS and independent core reader VALID. It proves no real YouTube/video ingestion, user-machine integration or publication approval.

The Windows-baseline `exportar_ldporto.py` is a compatibility wrapper that dispatches to `scripts/export/exportar_ldporto.py`. This exporter uses the Python standard library and documents separate project and analysis modes.

Existing Windows-baseline commands (must be verified in a live local checkout):

```bat
.venv\Scripts\python.exe exportar_ldporto.py --help
.venv\Scripts\python.exe exportar_ldporto.py --mode analysis --analysis analysis\EXISTING_ANALYSIS
.venv\Scripts\python.exe exportar_ldporto.py --inspect-zip "PACKAGE.zip"
```

An existing analysis is required. No remote inference, download of video/model, or automatic second-curator publication is authorized. Readiness states are NOT interchangeable: integrity of a ZIP is not human approval of its content.

### Future real-input GitHub Actions workflow (pending security design and approval)

1. Manual `workflow_dispatch` with explicit, approved input source.
2. Verify analysis provenance and safety, file paths, IDs, SHA-256 and required schemas.
3. Reuse the existing exporter/reader; do not replace it with a parallel engine.
4. Write a sanitised technical manifest and retain exact source SHA.
5. Verify package with independent ZIP reader and contract tests (R6/R6.2/R6.3).
6. Report READY, PARTIAL, BLOCKED or FAILED according to the actual exporter contract.
7. Publish outputs *only* when privacy review and access controls allow.

The GitHub repository was PUBLIC when inspected; do not upload private video, faces, speech, transcripts, analysis archives or personally identifying evidence as repository files or public Actions artifacts. For input that only exists on Windows, first approve a self-hosted runner and its access boundary, or a reviewed secure transfer with private artifact retention. A GitHub-hosted runner cannot read the user's local Windows folder by itself.

The synthetic-only Actions ZIP run was executed and validated independently; real-input orchestration, protected runner design, the original Windows installation and human editorial acceptance are NOT tested.
