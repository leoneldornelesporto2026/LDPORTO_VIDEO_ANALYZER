# Analyzer R5 — baseline antes da implementação

Data de referência: 2026-10-14. Projeto atual preservado; HEAD `2f4634f202f976c135c4bd28db590e289ce72156`. O snapshot em `docs/reports/r5_20261014/initial_state.json` confirma 485 fontes sem divergência da V4.1 e preserva hashes de 621 arquivos da análise VARIG (2.689.113.718 bytes), ZIP e `.package`. Baseline de testes reutilizado: 1.972 aprovados, 3 skips.

Fonte: `analysis/video_5198fcdaef38`; pacote localizado em `pacotes_para_enviar/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_001849_795742_c0795c.zip`. SHA-256 do ZIP: `6c5da0b276ad5330ae81f678f0856c402b41d2783841096dd99ccbfa32e1a51f`. Vídeo: zd_wjssZ7mc, duração 2234.574s, hash `b2958122415980a8afff4f77c23ead3c31c00345e5df0ab460995eb731efb00f`.

## Fluxo real e dependências

| Responsabilidade | Código e persistência | Dependências / limitação |
|---|---|---|
| Pipeline, DAG, cache | `pipeline.py`, `core.Context.step`, `run_status.py`, `execution_receipts.py`; `cache/<hash>/<stage>.json` | Cache identifica fontes, parâmetros e código; snapshot antigo não prova execução atual. Automação/orquestrador aposentados não serão recriados. |
| ASR e hipóteses | `transcription.py`, `targeted_asr.py`, `asr_comparison.py`; palavras, segmentos, revisão e alternativas persistidos | Whisper/CUDA já configurados; orçamento de reparo existe. Nenhuma execução ou instalação é necessária para começar o replay. |
| Diarização e pessoas | `diarization.py`, `vision.py`, `person_reid.py`, `active_speaker.py`, `speaker_windows.py` | Pyannote/visão/YOLO persistidos. Speaker acústico, identidade global e pessoa ativa são evidências distintas. |
| Semântica | `semantic.SemanticEngine`, `questions_answers`, `qa_contract`; stage 15 | Tópicos, seções, entidades e hipóteses Qwen já persistidos. Busca QA atual: até 32 segmentos/125s, sem atravessar vetos de contexto. |
| Entendimento | `understanding.run_understanding`, `recover_dialogue_links`, `build_story_arcs`, `story_support_diagnostics`; stage 16 | Usa transcript, tópicos, QA, falantes, shots e evidência visual. Cache stage16 lista os módulos editoriais. |
| Recuperação narrativa | `story_recovery.recover_story_arcs` | Até 360s, controle de narrador, conflito/desfecho literal e continuidade. Semelhança lexical não prova resolução ou causalidade. |
| Candidatos/S3 | `understanding.build_main_moments`, `editorial.rank_candidate`, `editorial_intelligence.select_editorial_shortlist` | Integridade, duração, contexto e scores obrigatórios; scores históricos e gates serão preservados no replay derivado. |
| Comercial | `editorial.classify_content`, `commercial_gate.refine_candidates`, `_speech_classification`; stage17c | Transcrição/OCR/cobertura têm escopos diferentes; contexto monetário isolado não deve provar anúncio. Ausência de observação não prova segurança. |
| Câmera | `camera_planner.py`, `camera_director.py`, `director_integration.py`; stages18b/19 | Alvo e crop exigem evidência audiovisual. Narrativa textual pode ser revista com enquadramento original e identidade desconhecida. |
| Social | `social_output.build_social_output`, `second_curation_export._reconcile_social_output` | Fluxo legado exige elegibilidade de Reel para Stories; não oferece unidades provisórias dependentes de outras unidades. Títulos dependem dos Stories selecionados. |
| Exportação | `reports.ReportEngine` → `build_second_curation_package` → `second_curation_export.build_core_package` | Valida referências, privacidade, gates e hashes. Fila 1.2, contratos legados e decisões por hash permanecem ativos. |
| Replay | `replay.ReplayArtifacts`, `replay_analysis`, `build_provenance.py` | Verificação de checksum e caminhos já existe. Replay geral também chama câmera/preview; R5 precisa modalidade editorial isolada, sem essa inferência. |
| Schemas/testes | `schemas/`, `integrity_contracts.py`, `editorial_handoff_audit.py`, `src/tests/` | Compatibilidade por adição de contrato versionado; validação de referência não equivale a narrativa completa ou aprovação. |

## Causas localizadas antes das alterações

O pacote contém 50 arcos: 28 discussion_segment, 14 anecdote e 8 partial_story. Não há história completa sustentada. Em `build_story_arcs`, `narrative_structure.development` é o miolo temporal da seção; para discussão, o campo narrativo `development` é intencionalmente nulo. `STORY_0000` ilustra essa diferença. Os diagnósticos verificam componentes narrativos, não simples IDs de layout. O contrato precisa explicitar os escopos, sem copiar IDs para preencher desenvolvimento.

Nas histórias parciais, o miolo usa `segments[1:-1]` e pode anteceder o setup encontrado depois. A origem deve limitar desenvolvimento à posição do setup. A busca escolhe os primeiros marcadores e se abstém quando falta continuidade. O vocabulário de desfecho é estreito; isso não autoriza ampliar positivos sem evidência.

`recover_story_arcs` testa fronteira de tópico antes da regra de interrupção curta: uma reação na fronteira pode abortar continuidade antes da retomada do narrador. A correção precisa exigir retomada sustentada, não ignorar a mudança de assunto.

QA já olha o transcript completo, mas sua janela conservadora e vetos impedem ligações de longo alcance. Propostas posteriores devem registrar entidades, pergunta literal, resposta possível, alternativas, contradição e revisão; não alterar automaticamente os registros canônicos ou contar proposta como resposta confirmada.

O exportador legado filtra Stories com gates de Reel e deriva títulos somente dos Stories restantes. A solução é um contrato paralelo de unidades/sequências para curadoria, explicitamente provisório; não enfraquecer o legado nem transformar dependência narrativa em aprovação.

O diagnóstico específico de S3, comercial, ASR e cobertura visual será preservado em `docs/reports/r5_20261014/data_diagnostic.json`. O relatório final distinguirá números confirmados de hipóteses. Fluxo de geração, persistência e exportação conhecido: implementação incremental autorizada a partir deste ponto.
