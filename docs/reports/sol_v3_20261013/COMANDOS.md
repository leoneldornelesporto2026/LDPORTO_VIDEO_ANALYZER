# Comandos e evidências — SOL V3

Executados no projeto atual, usando `.venv\Scripts\python.exe` Python 3.11. O inventário e backup antecederam os edits. Leituras com `rg`, `Get-Content`, `git status`, `git branch --show-current` e `git rev-parse HEAD` não executaram conteúdo dos ZIPs.

| Ação executada | Resultado registrado |
|---|---|
| `python -m pytest -q -rs --junitxml=.../before.xml` | 1711 passed / 3 skipped / exit 0; `before_run.json` |
| Backup verificável fora do projeto | 529 arquivos / CRC e SHA / `backup.json` |
| Instalação autorizada de wheels locais com `pip --isolated install --no-deps --no-index` | Exit 0; argv/URLs/hashes/versões em `yolo_installation.json` |
| `smoke_body_detector.py --video input/youtube/jNQXAC9IVRw/jNQXAC9IVRw.mp4 --output docs/reports/sol_v3_20261013/yolo_cpu --device cpu` | 4 inferências CPU / exit 0 |
| Mesmo CLI, `--output .../yolo_cuda --device cuda` | 4 inferências cuda:0 / exit 0 |
| `smoke_source_asr.py input/youtube/jNQXAC9IVRw/jNQXAC9IVRw.mp4 --output .../asr_real_smoke.json --model large-v3 --device cuda --expect-text "long trunks" --forbid-text "frutas"` | Exit 1 antes de inferência: helper/wrapper; artifact preservado |
| Mesmo CLI corrigido, `--output .../asr_real_smoke_retry.json` | Passou CUDA/int8_float16 / exit 0 |
| `benchmark_semantic_sol_v3.py --analysis analysis/video_4b0f48e4f4ae --output docs/reports/sol_v3_20261013/qwen_ab` | 12 chamadas / 3 repetições por modo / exit 0; `qwen_ab_run.log` |
| `sample_local_resources.py --output docs/reports/sol_v3_20261013/qwen_resource_samples.jsonl --seconds 900` | Sampler passivo finito / exit 0 |
| POST local `/api/generate` com `{model:qwen3:14b,keep_alive:0}`, depois GET `/api/ps` | `done_reason=unload`, `models=[]`; servidor preservado |
| Smoke corporal com `--output .../yolo_cuda_final --device cuda` | 4 inferências finais / hashes de código / exit 0 |
| Smoke ASR com `--output .../asr_real_final.json` | Inferência final 1,610 s / exit 0 |
| `python -m pytest -q src/tests/test_sol_v3_integration.py src/tests/test_sol_v3_runtime_editorial.py` | 37 passed / 15,91 s, antes da regressão integral |
| `python docs/reports/sol_v3_20261013/run_final_regression.py` | Invocou pytest integral exato de `after_full_run.json`; 1792 passed / 3 skipped / exit 0 / nenhum drift |
| `python -m compileall -q src/ldporto app.py scripts/dev/benchmark_semantic_sol_v3.py scripts/dev/smoke_body_detector.py scripts/dev/smoke_source_asr.py` | Exit 0 |
| `git diff --check` | Exit 0; apenas avisos existentes de futura conversão LF→CRLF |
| `python docs/reports/sol_v3_20261013/consolidate_evidence.py` | Hashes preservados, branch/HEAD iguais, arquivos removidos 0, drift 0 |

Os comandos abreviados com `.../` acima identificam artifacts desta pasta; o argv real está nos JSONs dos smokes, na aquisição e nos wrappers. Comandos pytest detalhados dos agentes ASR, Vision, Runtime e GUI estão em seus relatórios e logs adjacentes. Na integração inicial, dois testes novos falharam por fixture sem palavras; a fixture foi corrigida e os oito modos de export/sidecar foram verificados. Nenhuma falha foi ocultada por remover teste.

Os smokes novos e o benchmark executaram componentes isolados sobre mídia local. A regressão completa usa fixtures/model mocks e integrações sintéticas locais, não uma nova análise completa da mídia original. Não houve commit automático, orquestrador, instalação adicional fora do consentimento, serviço pago, reset/clean ou limpeza destrutiva.
