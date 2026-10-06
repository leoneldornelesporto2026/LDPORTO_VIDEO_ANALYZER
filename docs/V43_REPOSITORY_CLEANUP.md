# V4.3 Repository Cleanup

All existing runtime changes were preserved. Tracked-file moves used git mv;
rename staging does not authorize a commit. No reset, clean, checkout, commit or
push was used. New Windows implementations created earlier in this session were
relocated without copying or discarding their edits.

| Old Path | New Path | Action | Reason / Compatibility |
| --- | --- | --- | --- |
| analyze.py, app.py, install.py, ABRIR_ANALYZER.bat | unchanged | KEPT | Public GUI/CLI/install entrypoints |
| compare_runs.py | scripts/dev/compare_runs.py | MOVED + WRAPPER | Canonical developer tool; old CLI/imports retained |
| exportar_ldporto.py | scripts/export/exportar_ldporto.py | MOVED + WRAPPER | Canonical exporter; old CLI/imports retained |
| requirements-*.txt | requirements/<group>.txt | MOVED | Eight 100% renames; groups not merged/upgraded |
| CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat | scripts/windows/ollama/ | WRAPPER | Public entrypoint; source preserved |
| CORRIGIR_GPU_WINDOWS.bat | scripts/windows/gpu/ | WRAPPER | Public entrypoint; source preserved |
| DIAGNOSTICO*.bat | scripts/windows/diagnostics/ | WRAPPER | Public diagnostics, paths with spaces |
| INSTALAR*.bat | scripts/windows/install/ | WRAPPER | Public install interface; Python 3.11 required |
| TESTAR_WINDOWS.bat | scripts/windows/testing/ | WRAPPER | Canonical pytest command |
| LEIA_PRIMEIRO.md | docs/setup/LEIA_PRIMEIRO.md | MOVED | Specialized setup retained; README is primary |
| PATCH_OLLAMA_MAXIMO.md | docs/setup/OLLAMA_MAXIMO.md | MOVED | Local model setup guide |
| GPU_FIX_NOTES.md | docs/troubleshooting/GPU_FIX_NOTES.md | MOVED | GPU operation guide |
| WORKER_FINAL_REPORT.md | docs/reports/WORKER_FINAL_REPORT_V42.md | MOVED | Historical V4.2 evidence |
| DELIVERY_MANIFEST.json | docs/releases/DELIVERY_MANIFEST_V3.json | MOVED | Declares camera-director-3.0; not current inventory |
| DELIVERY_MANIFEST_V4.json | docs/releases/DELIVERY_MANIFEST_V4.json | MOVED | Declares analyzer 4.0.0; historical snapshot |
| PROJECT_EXPORT_MANIFEST/README/TREE | none | REMOVED_GENERATED | Exporter produces these inside ZIP, excludes old derived files |
| WORK_PACKAGE_MANIFEST/PROJECT_TREE/README | none | REMOVED_GENERATED | Previous generated worker input, no runtime consumer |

## Audit Decisions

- No runtime Python module was deleted based solely on missing text references.
- CLI scripts, dynamic imports and optional engines remain intentionally available.
- paths.py centralizes project-owned paths; media_runtime.py distinguishes CLI
  discovery from Shared DLL registration and optional waveform decoding.
- Demucs remains a separate environment. OCR/YOLO/audio events remain opt-in.
- /export/ and /exports/ ignores are root-scoped, so scripts/export stays visible.
- Source media, models, .venv, extracted benchmark and packages remain ignored.
- Root wrappers explicitly name their canonical implementation and forward arguments.
- Legacy test path assertions were updated only for requirements relocation; safety
  assertions were retained. Other intentional V4.3 expectation changes are listed
  in WORKER_DISCOVERY_AUDIT_V43.md.