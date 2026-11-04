# Project Tools

Public commands remain available through the root compatibility wrappers.

- windows/install/: base and optional Windows installation.
- windows/diagnostics/: readiness and GPU diagnostics.
- windows/gpu/: NVIDIA runtime repair; never stops unrelated Ollama models.
- windows/ollama/: local serial Ollama configuration.
- windows/testing/: canonical Python 3.11 pytest entrypoint.
- dev/compare_runs.py: artifact comparison and replay editorial audit.
- export/exportar_ldporto.py: source/forensic exporter; generated files live inside ZIPs.

All moved Windows implementations resolve the project root from their own location,
not the caller's working directory. Export/package outputs belong to ignored
pacotes_para_enviar/ or exports/, never the source root.
## Sessões 9–11: primeiro teste real

`python scripts/dev/start_real_test_s11.py --package SECOND_CURATION_READY.zip --source video_original.mp4 --output pasta_teste` valida prontidão e hash da fonte e renderiza um único MP4 1080×1920. `scripts/dev/curator_s9.py` faz aprovação do canário, lote e gate final; `scripts/dev/performance_s10.py` audita A/B; `scripts/dev/homologation_s11.py` gera o relatório final. Leia `docs/S9_S11_REAL_TEST.md` antes de marcar qualquer aprovação.
