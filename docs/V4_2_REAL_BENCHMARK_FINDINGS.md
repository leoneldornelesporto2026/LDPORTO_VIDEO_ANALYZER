# Evidencia Real Do Benchmark V4.2

Data: 2026-10-05. Este documento resume o run ANTERIOR fornecido, nao um rerun V4.2.
Nenhuma fala longa do benchmark foi copiada para documentacao permanente.

## Proveniencia

- Projeto original: LDPORTO_PROJETO_ATUAL_20261005_102723_538067.zip.
  SHA256: 2798def44e14da77364e165d5b6c06b4f0adec66faea28b79791429da2f080eb.
- Benchmark original: CHATGPT_REVIEW_video_31329be78ca4_20261005_102723_538067.zip.
  SHA256: 03da3735412c24ba1ef47056eb3328521812bdf49a0ae8a4fdbe2afcbd1d9be4.
- Briefing: ldporto_worker_v42.py; SHA256
  f881f783c836c4e887a27d0c3330879e1425dc692c717fa1640004db32edbbef.
- Copia de trabalho: project_v42. Evidencia extraida: .worker_v42/benchmark,
  usada somente para leitura. O worker nao foi executado para chamar Codex.

## Fatos Observados

| Sinal | Valor | Fonte |
|---|---:|---|
| Estado / causa | partial / 05_diarization unavailable | run_manifest.json |
| Palavras | 19462 | words.json |
| Palavras de baixa probabilidade | 1177 | low_confidence_words.json |
| Alternativas / substituicoes automaticas | 100 / 0 | transcription_alternatives.json |
| Tracks brutos / IDs persistentes antigos | 8692 / 7793 | analysis_quality.json |
| Mediana da duracao de track | 0.166 s | analysis_quality.json |
| Fracao de tracks curtos | 0.6934 | analysis_quality.json |
| Sem evidencia de embedding (metrica antiga) | 0.8966 | analysis_quality.json |
| "Participantes" antigos / com fala | 7793 / 0 | participants.json |
| Perguntas / respostas associadas | 330 / 0 | questions_answers.json |
| Topicos / arcos / candidatos | 121 / 1 / 176 | contratos respectivos |
| Extras de intervalos ideais identicos | 12 | main_moments.json |
| Pares com temporal IoU >=0.8 | 34 | main_moments.json; sinal, nao equivalencia editorial |
| Scenes / shots com mesmos limites | 556 / 556; fracao 1 | scenes.json, shots.json |
| Cobertura temporal / foco nao resolvido | aproximadamente 1 / 1 | analysis_quality.json |
| Blocos semanticos em fallback | 6 de 46 | avisos de analysis_quality.json |
| Preview verificado | nao | preview_validation.json |

MediaPipe faltou em people tracking. Active speaker ficou indisponivel. O manifesto
antigo listava camera/descendentes degradados entre modules_still_valid. O overview
global estava em ingles; context_required tinha 54 representacoes distintas.
Entidades incluam falsos positivos lexicais comuns, nao evidencia de nomes civis.

## Omissao Pelo Review Exporter

O manifesto registra file_too_large para analysis.json (592628771 bytes),
CHATGPT_ANALYSIS_HANDOFF.json (180635048), people_observations.json (229546417),
person_motion.json (98044719), master_timeline.json (60175051), camera_plan.json
(35821739), camera_timeline.json (38949970), video_analysis.json (44024972) e
llm_insights.json (56232435).

Isso significa missing_in_review_package, NAO missing_in_original_run. Sem esses
raw artifacts nao e possivel medir novamente Re-ID, RAM/VRAM ou foco do mesmo video.

## Interpretacao

Contagens nao sao ground truth de acuracia. A melhora de runtime/modelos exige uma
nova analise do mesmo video em Windows/Python 3.11 com dependencias/modelos prontos.
O reprocessamento deterministico dos candidatos existentes e descrito separadamente
em V4_2_BENCHMARK_COMPARISON.md.