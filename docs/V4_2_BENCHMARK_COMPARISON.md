# Comparacao V4.2 E Limites Da Evidencia

## Resultado Demonstravel

Foram aplicadas somente normalizacao, classificacao lexical comercial, ranking e
dedup aos 176 candidatos do review real anterior. Nao foram executados ASR,
diarizacao, visao, active speaker nem Ollama novamente no video.

| Medida | Antes | Regras V4.2 sobre o mesmo export |
|---|---:|---:|
| Candidatos | 176 | 163 |
| Duplicatas exatas extras | 12 | 12 consolidadas como alternativos |
| Outros merges por alta equivalencia temporal/editorial | nao avaliado | 1 |
| Alternativos preservados | nao estruturados | 13 |
| Candidatos invalidos descartados | nao avaliado | 0 |
| Comerciais detectados pelo classificador conservador | sem contrato | 6 |
| Elegiveis apos dedup/filtro comercial | sem contrato | 157 |
| Representacoes de contexto | 54 valores livres | none / required / unresolved nesta amostra |
| Overview global ingles | aceito no run anterior | rejeitado pelo detector lexical V4.2 |

Classificacao comercial e idioma sao heuristicas, nao acuracia anotada. Os 34 pares
de alta sobreposicao anteriores nao foram todos fundidos: ideias diferentes devem
permanecer separadas. Intervalos exatamente iguais guardam seus nucleos como
alternativos. A manutencao de referencia aos IDs antigos permite auditar cada merge.

Evidencia interna: .worker_v42/benchmark-reference-check/benchmark_comparison.json,
campo existing_editorial_audit. Essa pasta nao e dependencia de runtime e nao entra
no ZIP de projeto.

## Ainda Nao Demonstrado

- Diarizacao/active speaker disponiveis no mesmo video.
- Reducao segura de identidades e participantes com novos vetores de visao.
- Melhora de WER/DER, qualidade de arcos, titulos, clipping ou ranking humano.
- Reducao de tempo semantico/visao, RAM, VRAM ou disco em 2h de video.
- Rerun Windows/Python 3.11; nao havia interpretador 3.11 executavel localizado.

## Proximo Benchmark

Use uma .venv criada por Python 3.11.x real, o instalador recomendado e
`.venv\Scripts\python.exe analyze.py --doctor`. Corrija todos os recursos ENABLED
com ERROR antes do video. Forneca token HF somente na GUI/ambiente em memoria e
aceite Community-1. Carregue o modelo Ollama configurado.

Comando do mesmo video, substituindo apenas o caminho pelo arquivo real:
`.venv\Scripts\python.exe analyze.py "C:\Videos\MESMO_VIDEO_DO_BENCHMARK.mp4" --output "analysis\benchmark_v42_same_video" --device cuda --semantic ollama --preview --camera-profile natural`.

Se a maquina nao tem CUDA, escolha `--device cpu` explicitamente e registre que os
tempos nao sao comparaveis ao perfil GPU. Nao use --force em retomadas normais.

Compare com `.venv\Scripts\python.exe compare_runs.py "CAMINHO_DO_RUN_ANTERIOR_EXTRAIDO" "analysis\benchmark_v42_same_video" --output-dir "comparison_v42"`.
O comparador gera benchmark_comparison.json/md, preserva null em campos legados
ausentes e nao presume mesma fonte sem hash completo dos dois runs.