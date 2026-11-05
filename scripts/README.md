# Ferramentas do projeto

A raiz conserva oito atalhos `.bat` publicos para compatibilidade. Cinco
delegam para scripts reais em `scripts/windows/`; o launcher da GUI
`ABRIR_ANALYZER.bat` verifica o Python 3.11. Os diagnosticos apontavam
para scripts inexistentes em `scripts/windows/diagnostics/` e foram
corrigidos sem criar uma nova camada de arquivos batch.

- `DIAGNOSTICO_WINDOWS.bat`: `analyze.py --doctor --offline` (preflight).
- `DIAGNOSTICO_GPU_WINDOWS.bat`: `scripts/test_gpu.py --check-only` (CUDA).
- `windows/CHECK_RUNTIME.bat`: Python 3.11 e `.venv`.
- `windows/install/`: instalacao base/avancada, por comando explicito.
- `windows/gpu/`: reparo NVIDIA, sem encerrar sessoes Ollama externas.
- `windows/ollama/`: configuracao Ollama local.
- `windows/testing/`: testes pytest; instala requirements/dev.
- `windows/TESTAR_FLUXO_REAL_WINDOWS.bat`: canario de midia real, opt-in.
- `dev/`: ferramentas de auditoria, benchmark e replay.
- `export/`: geracao de pacote/ZIP.

Os scripts Windows operam relativos a seu diretorio e nao ao CWD do caller.
Pacotes gerados ficam em `pacotes_para_enviar/` ou `exports/`, fora do fonte.
O instalador base agora repassa o status de erro do `install.py`.

## Sessoes 9-11: teste real

`python scripts/dev/start_real_test_s11.py --package SECOND_CURATION_READY.zip --source video_original.mp4 --output pasta_teste`
valida prontidao e hash da fonte e gera um canario MP4. A aprovacao/revisao
e separada do teste e nao autoriza publicacao. Leia `docs/S9_S11_REAL_TEST.md`.
