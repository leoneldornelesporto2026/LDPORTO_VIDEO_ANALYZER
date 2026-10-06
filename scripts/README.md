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