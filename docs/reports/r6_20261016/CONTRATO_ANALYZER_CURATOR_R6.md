# Contrato Analyzer → Curator R6 — 2026-10-16

Evolução aditiva do pacote compacto existente. O Analyzer entrega evidências e propostas; o Curator mantém edição, renderização, revisão e aprovação. `PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED` e `PUBLISH_READY` permanecem etapas distintas.

## Artefatos e compatibilidade

| Arquivo | Responsabilidade |
| --- | --- |
| `CURATION_INDEX.json` | Índice legado com novas referências `handoff_master_ref` e `caption_preflight_ref`. |
| `SECOND_CURATOR_BRIEF.json` | Briefing legado; `HANDOFF_MASTER.json` adicionado aos pontos de entrada. |
| `HANDOFF_MASTER.json` | Índice de arquivos, bytes, SHA256, run ID, hash da fonte, IDs de candidatos/Stories e estado de legenda. Não duplica transcrição ou câmera. |
| `subtitles/caption_preflight_r6.json` | Triagem de todos os intervalos exportados, seis estados, motivos, IDs e lacunas. |
| `subtitles/semantic_caption_preflight_r6.json` | Na derivação semântica: triagem de cada `source_interval` dos Stories existentes e revisão explícita de transições. |
| `subtitles/subtitle_review_s7.json` | Revisão selecionada original, preservada. |
| `transcript/relevant_words.jsonl` | Palavras canônicas existentes, com flags de alinhamento/escuta preservadas quando disponíveis. |
| `camera/candidate_camera_plans.json` | Lista legada preservada; cada item recebe `camera_handoff` do mesmo Director usado por Reels/Stories. |
| `camera/camera_director_timeline.json` | Timeline existente sem novo processamento. |
| `camera/shared_camera_handoff.json` | Contrato global compartilhado de câmera, com fallback e verificação pendente. |
| `people/participants.json` | IDs legados preservados; confirmação nominal/papel tornam-se explícitos. |
| `people/person_tracks.json`, `people/person_appearances.json` | Tracks e observações disponíveis; não provam visibilidade contínua. |
| `people/instrument_observations.json` | Somente observações fornecidas com origem e referências, pendentes de revisão. |
| `people/speaker_person_mapping.json`, `people/performer_review_queue.json` | Associação existente e pendências humanas. |
| `people/performer_evidence.json` | Métricas e política dos contratos de participantes. |

Os schemas `schemas/caption_preflight_r6.schema.json` e `schemas/handoff_master_r6.schema.json` acompanham o pacote. O formato do catálogo, a lista de planos de câmera e os arquivos legados permanecem legíveis. Nenhuma mudança de ID, ranking ou elegibilidade foi usada para promover candidatos.

## Referências e integridade

`HANDOFF_MASTER.artifacts` indexa os arquivos presentes com tamanho e SHA256. O manifesto externo inclui o próprio master e seu hash; master e manifesto não referenciam os hashes um do outro em ciclo. Uma derivação de visuais reconstrói o master após alterar artefatos e continua invalidando a aprovação de preview existente.

`canonical_id_sources` indica os arquivos que definem `candidate_id`, `story_id`, `segment_id`, `word_id`, `participant_id`, `person_id`, `speaker_id`, `track_id`, `appearance_id` e `director_id`. IDs ausentes continuam ausentes. A mídia não é copiada nem procurada por semelhança de nome; seu vínculo é o SHA256 da fonte.

O validador R6 verifica schemas, catálogo/master, referências, hashes, campos falsos de aprovação e coerência do preflight com as palavras, segmentos, eventos e intervalos efetivamente incluídos no ZIP. Também compara o resumo de cada candidato/Story com o relatório de preflight e rederiva os handoffs de câmera da timeline efetivamente exportada. Pacotes legados sem a extensão continuam sendo lidos pelo caminho anterior.

Uma derivação `export_semantic_package` preserva o master original, com bytes exatos, em `provenance/parent_handoff_master_<hash>.json`; registra os hashes do master e pacote pai; e reconstrói o índice da revisão derivada. Os demais artefatos de dados legados permanecem iguais. Essa atualização de índice não aprova legendas ou câmera. O master derivado referencia `semantic_caption_preflight_ref` e `semantic_stories`, com IDs e intervalos canônicos. O preflight semântico tem schema próprio e é rederivado pelo validador a partir de `editorial/story_series_proposals.json`; múltiplos intervalos não recebem início/fim contínuos artificiais nem herdam aprovação da montagem.

O relatório expõe classificação de evidência; não aprova publicação. Motivos e modalidades são documentados em `DIAGNOSTICO_AUDIO_LEGENDAS.md`. `status_counts` soma entradas de candidatos e Stories; contagem exclusivamente de candidatos deve percorrer `candidates`.

## Integração real testada

O código do Curator adjacente foi somente lido. Foram chamados os importadores reais:

- `ldporto_curator.second_curation_import.read_package`.
- `ldporto_curator.import_smoke.smoke_import`.

Comando executado:

```powershell
.venv/Scripts/python.exe -B docs/reports/r6_20261016/verify_caption_curator.py
```

Resultado: ambos passaram com **três candidatos sintéticos**, pacote inalterado, `models_executed=false`, `render_executed=false` e validação Analyzer `valid`. O script gera `caption_curator_import_r6.json` com hashes antes/depois dos módulos Curator observados e o relatório completo. O ZIP de teste foi temporário; nenhuma fonte audiovisual do usuário foi acessada.

**Limite comprovado:** isso testa aceitação dos arquivos e campos adicionais pelos importadores instalados. Não testa aplicação automática dos seis estados R6, consumo de `HANDOFF_MASTER`, montagem de Stories, câmera final ou render de legendas. O consumidor instalado ainda ignora os novos campos; portanto a triagem não constitui um novo gate obrigatório no Curator independente. O master declara `curator_import_test=not_attested_by_export`: um export futuro não herda a evidência desta sessão.

Também se executou o teste com o **ZIP real reconstruído do show**, preservando os 70 IDs/intervalos existentes:

```powershell
.venv/Scripts/python.exe -B docs/reports/r6_20261016/verify_show_curator_r6.py
```

`read_package` e `smoke_import` passaram com 70 candidatos, sem mídia selecionada, modelos ou render. O pacote e os módulos Curator observados conservaram seus hashes. Evidência: `show_curator_import_r6.json`. Esse ensaio adicional prova aceitação do pacote do show pelos importadores reais; os limites de consumo/render/aprovação acima continuam válidos.

## Homologação necessária

O operador deve selecionar a fonte pelo hash, revisar o preflight por candidato/Story, manter áudio/canto originais, resolver pendências e consumir o plano de câmera como proposta. Após a montagem, o Curator deve validar tipografia e safe areas com a fonte real, gerar preview, registrar revisão por hash e aplicar seu gate separado de publicação. Até essa etapa, aprovações humanas, previews e publicação permanecem pendentes.
