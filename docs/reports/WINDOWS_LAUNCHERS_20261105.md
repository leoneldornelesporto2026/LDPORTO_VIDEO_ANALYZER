# Auditoria conservadora Windows .bat — 2026-11-05

Branch alvo: `develop`. Baseline inicial:
`b28c78cc4c6f8b91196ebecfc7f36ac5dbea2e0d`.

## Inventario e decisoes

- Baseline: 15 scripts batch (8 na raiz, 7 em `scripts/windows/`).
- Dois atalhos de diagnostico estavam quebrados por referencias a
  `scripts/windows/diagnostics/`, diretorio ausente.
- Cinco outros atalhos de raiz encaminham a scripts canonicos existentes.
  `ABRIR_ANALYZER.bat` abre a GUI e valida o runtime.
- Nenhum `.bat` apagado ou movido: todos os nomes publicos sao
  documentados e a exclusao poderia quebrar instrucao/atalho de usuario.

## Correcoes sem alterar o motor

- Diagnostico geral usa `CHECK_RUNTIME.bat` seguido de
  `analyze.py --doctor --offline`.
- Diagnostico GPU usa `CHECK_RUNTIME.bat` seguido de
  `scripts/test_gpu.py --check-only`: sem inferencia nem download de pesos.
- Instalador base preserva o codigo de retorno de `install.py` mesmo apos pause.
- Acrescentado teste estatico `src/tests/test_windows_batch_paths.py`;
  README principal, scripts/README e documento estrutural revisados.

## Validacao e limitacoes

Nao foram executados instaladores, GUI, CUDA/Ollama real, midias ou
testes integrados Windows nesta alteracao. No Windows, conferir:

```powershell
python -m unittest discover -s src/tests -p test_windows_batch_paths.py
.\DIAGNOSTICO_WINDOWS.bat
.\DIAGNOSTICO_GPU_WINDOWS.bat
.\TESTAR_WINDOWS.bat
```

Os diagnosticos exigem `.venv` Python 3.11 pronta. O script de teste geral
instala dependencias dev; nao executa-lo como checagem somente leitura.
A verificacao de caminhos nao homologa processamento de midia real.

## Correcao P0-01 (2026-11-05)

Para compatibilidade com o teste legado test_v43_runtime.py, os dois wrappers
da raiz voltam a usar call "%~dp0...diagnostics..." %* e a propagar exit code.
Os scripts canonicos foram efetivamente criados em scripts/windows/diagnostics/.
Mantiveram os comandos read-only de preflight e CUDA check e o CHECK_RUNTIME.
A nova alteracao exige validacao Windows, que ainda nao foi executada.
