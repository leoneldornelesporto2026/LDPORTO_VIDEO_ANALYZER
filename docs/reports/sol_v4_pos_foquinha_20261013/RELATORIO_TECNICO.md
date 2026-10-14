# SOL V4 — pós-homologação Foquinha

13/10/2026. Continuação do V3 e do V4 de percepção já concluídos. **Pacote P0 implementado e verificado: 1.936 passed, três skipped, zero falhas; 44 testes novos. Novo ZIP de curadoria validado, 77 entradas acionáveis e três prévias locais sem aprovação.** Não foi reexecutado o episódio completo, nem Whisper, diarização, YOLO ou Qwen.

## Estado inicial e preservação

Branch `baseline/ldporto-20261012-prompt01`, HEAD `2f4634f202f976c135c4bd28db590e289ce72156`. Os 478 fontes conferiam com o freeze V4 anterior ao iniciar esta rodada. Dirty tree, exclusões históricas da automação, `.venv`, modelos, mídia, `.package/PROJECT_EXPORT_*`, análises e backups preservados. Não houve commit, reset, limpeza, instalação, download, serviço pago ou publicação.

Snapshot inicial dos fontes atuais em [sources_before.zip](sources_before.zip), SHA-256 `a2a93f52fc9499a16bf0eb9faea2adbfda293775215b052ff6968826e6c6b22c`, CRC e hashes internos verificados. Não extrair sobre o projeto. [initial_state.json](initial_state.json) e [git_before.txt](git_before.txt) registram estado e arquivos. A última regressão real, reutilizada como referência porque nenhum fonte havia mudado, foi **1.892 passed / três skipped / zero falhas**, 1.895 casos; o 1.792/3 do V3 é histórico.

Fonte `7laRa_F3FbA.mp4`, SHA-256 `0231c20cfd8147d92926bda4f452777f3803c38b248064e65548f0b12a5fb98b`; análise associada `analysis/video_1da839aad175`. ZIP original: SHA-256 `0c6cd22d4892fddbb23ab71e6c12997c2a47709ebd919c12b8ebeaaeaec2f4ff`, **154 membros, 153 arquivos declarados**, todos os hashes/tamanhos válidos, sem CRC, colisões ou paths inseguros. [original_zip_integrity.json](original_zip_integrity.json). O validador atual também aceita esse ZIP legado: [original_zip_compatibility.json](original_zip_compatibility.json).

**Preservação final VERIFIED às 14:18:43 locais:** os 1.041 arquivos originais (6.367.923.312 bytes, incluindo 27 checkpoints), ZIP original, mídia, peso YOLO, três exports protegidos, HEAD e 481 fontes congelados conferem por SHA; sem arquivos extras ou divergências na análise original. [final_integrity.json](final_integrity.json), [git_after.txt](git_after.txt), [sources_frozen_final.json](sources_frozen_final.json). O relatório desta rodada não expõe embeddings faciais ou credenciais.

## P0 — bloqueios dos candidatos e triagem humana

Não se comprovou bloqueio indevido por `P1_DEGRADED` ou falha ASD nos quatro candidatos prioritários. `editorial_integrity_ready=true` significa contrato editorial disponível, sem provar que cada candidato tenha hook, clareza, duração ou conversa completa. Score alto é média heurística dos componentes observados; não elimina componentes obrigatórios ausentes.

A [matriz top-10](top10_gate_matrix_before.json) registra valores, dependências, escopos, razões, IDs e referências de origem. Piso atual **0,50**; duração alvo **30–90 s**, limites **8–180 s**; exceção exige prova de unidade completa. Nenhuma dessas regras mudou.

| Candidato | Intervalo (s) | Score | Gates locais comprovados |
|---|---|---:|---|
| MOMENT_00022_0001 | 3946,52–3969,28 | 0,734 | Hook não medido; 22,76 s abaixo do alvo, sem exceção comprovada |
| MOMENT_00002_0002 | 425,02–446,00 | 0,715 | Hook não medido; 20,98 s abaixo do alvo, sem exceção comprovada |
| MOMENT_00008_0002 | 1585,20–1613,94 | 0,713 | Hook não medido; 28,74 s abaixo do alvo, sem exceção comprovada |
| MOMENT_00002_0000 | 363,10–407,76 | 0,610 | Hook e clareza independente não medidos; fronteira de tópico cruzada |
| MOMENT_00022_0002 | 3970,88–3974,56 | 0,437 | Abaixo do piso e do mínimo rígido; hook/clareza ausentes |
| MOMENT_00010_0000 | 1800,22–1807,58 | 0,432 | Abaixo do piso e do mínimo rígido; hook/clareza ausentes |
| MOMENT_00013_0000 | 2343,12–2351,06 | 0,390 | Abaixo do piso e do mínimo rígido; hook/clareza ausentes |
| MOMENT_00015_0000 | 2725,53–2794,43 | 0,286 | Abaixo do piso; resposta/conclusão e unidade Q&A incompletas |
| MOMENT_00004_0001 | 846,18–894,04 | 0,280 | Abaixo do piso; setup/desenvolvimento e payoff narrativo sem suporte |
| MOMENT_00006_0002 | 1135,30–1170,52 | 0,279 | Abaixo do piso; pergunta sem resposta completa |

Os três primeiros têm abertura/finalização registradas como limpas e revisão comercial verificada. O quarto cabe no alvo de duração, mas tem outros gates locais. Nenhum foi promovido à shortlist para satisfazer quota. No original, contagens de rejeição sobrepostas: 73 abaixo do piso, 74 sem clareza independente, 63 resposta/payoff pendente, 69 finalizações não limpas, 32 aberturas não limpas, 33 perguntas sem resposta completa e 25 fronteiras de tema.

**Bug corrigido: acionabilidade e escopo da fila.** A fila antiga continha 77 unidades, mas mostrava sobretudo razões genéricas de aprovação; candidatos fortes podiam ter `human_review_provisional=false`, `editorial_verified=true` e `default_shortlist_eligible=false` sem explicar a distinção. O booleano legado indica integridade/comercial, não aprovação do conteúdo; permanece para compatibilidade.

A fila existente ganha schema **1.1**, `review_state`, motivos locais, texto literal com proveniência, contexto anterior/posterior, áudio a ouvir, tarefas e fallback `SOURCE_PRESERVE`, sem associação facial ou crop aprovado presumidos. Ordenação usa score registrado, blockers e desempates estáveis; `priority_rank` é separado do rank original. `DISCOVERED`, `PROVISIONAL_HUMAN_REVIEW`, `ELIGIBLE_AUTOMATIC_SHORTLIST`, `HUMAN_APPROVED`, `PREVIEW_APPROVED` e `PUBLISH_READY` permanecem distintos. Nenhuma etapa humana/preview/publicação é aprovada pelo helper.

O modo explícito **1.0 reproduz exatamente o JSON e a ordem antigos**; o validador seleciona o contrato declarado e recusa versões desconhecidas. Planos são recalculados após os invariants comerciais/integração e carregam o método de redaction. `editorial_result` e a GUI agora mostram contagem da fila, shortlist automática separada, motivos locais sobrepostos e onde revisar. Não foi criada segunda fila editorial.

Replay real: **80 registros / 77 unidades / três alternates**, mesmos IDs, scores e intervalos, **shortlist oficial zero**, 77 entradas `PROVISIONAL_HUMAN_REVIEW`, publicação false. [editorial_queue_replay.json](editorial_queue_replay.json). Esse é o ganho comprovado de utilidade para o Curator; não é melhoria medida de precisão da seleção.

## P0 — perguntas, respostas e narrativa

Os 280 Q&A originais dividem-se em **98 unresolved, 181 not_expected e um linked_candidate**. Os 181 incluem 166 tag questions, 14 brincadeiras e uma saudação; não são 181 respostas perdidas. Razões dos 98: 42 intervenções com relevância pendente, 23 perguntas novas antes da resposta, 18 respostas com relevância pendente e 15 sem speaker suficiente. Há 204 de 1.520 segmentos sem speaker. Segment IDs das perguntas auditadas existem.

O produtor semântico **já aplica Q&A à transcrição inteira**, uma vez, depois dos blocos. A hipótese de que os 23 chunks, por si, impedem todos os vínculos não foi comprovada. A falha localizada tratada é segmentação de contexto complementar do mesmo perguntador e reações curtas antes de uma resposta potencial.

`recover_dialogue_links` reaproveita os gates existentes com contexto lexical canônico, speaker acústico, tempos e referências. Preserva IDs originais e só aceita pontes textuais provisórias. Não usa identidade visual ou simples adjacência como evidência. O understanding retorna todo o contrato Q&A refinado; pipeline, master timeline, revisão direcionada e export preferem esse contrato, com fallback para caches legados. Checkpoint 15 e transcrição original não são mutados.

Revisão independente fortaleceu quatro negativos: não pular turno longo/sobreposto para alcançar resposta posterior; não classificar confirmação polar ambígua como reação e transferir resposta a outro speaker; não tratar limite artificial da busca como fechamento natural; exigir texto, referências e tempos canônicos válidos, sem sobreposição, para sustentar narrativa. `narrative_supported=true` sem essa prova é rebaixado em qualquer kind, com diagnóstico da alegação recebida. Fixtures antigas só com IDs conservam formato/IDs e explicitam evidência parcial.

Dos 100 arcos: 62 discussões, 25 parciais e 13 anedotas. Apenas 38 setups, 38 desenvolvimentos e **zero payoffs** foram registrados. Os novos diagnósticos explicitam `no_setup`, `no_development`, `no_payoff`, referências faltantes e continuidade pendente. As **21 inversões de ordem dos componentes** encontradas no replay são atribuições nos arcos; não demonstram 21 overlaps da transcrição.

**Resultado real conservador:** cinco pontes elegíveis continuaram bloqueadas por relevância ou pergunta nova. Os 280 payloads/IDs Q&A ficaram iguais; 100 arcos e zero narrativas sustentadas. Não foi demonstrado aumento de respostas corretas ou histórias completas no episódio. Os positivos sintéticos demonstram capacidade do novo caminho, sem virar ground truth humano. [dialogue_real_cpu_replay_02.json](dialogue_real_cpu_replay_02.json), [notas de implementação](dialogue_implementation_notes.md).

Há [20 trechos para avaliação reproduzível](manual_review_packet_20.json): dez candidatos, seis exemplos Q&A e quatro narrativas, com texto/IDs/timecodes, razões e campos humanos pendentes. Não foram inventadas anotações. Precisão, recall, WER e acerto narrativo humano continuam **NOT_MEASURED**; completar as anotações é **PENDING**.

## Replay e novo pacote de curadoria

[replay_curator_export.py](replay_curator_export.py) lê inputs originais verificados por SHA, executa somente helpers CPU e exporta em pasta nova. Tempo observado: Q&A 0,009 s, arcos 0,112 s, export 30,910 s; não é benchmark de Qwen/percepção nem distribuição estatística. Payloads candidatos, Q&A e revisão por fonte preservados. Nenhuma inferência de modelo, media decoding no export ou alteração do episódio.

[Novo ZIP parcial](derived_export/SECOND_CURATION_PARTIAL_7laRa_F3FbA_20261013_171022_194230_e1477c.zip): SHA-256 `d703664b432b1dda128f81276418fb85ff50c145107b1a977a768873da9c509c`, 2.653.396 bytes, **142 membros / 141 arquivos declarados**, validado pelo produtor e pelo validador independente. [curator_export_replay.json](curator_export_replay.json), [derived_package_summary.json](derived_package_summary.json).

O pacote mantém 80 candidatos, 77 entradas acionáveis, três alternates e shortlist zero. `editorial_ready`/`transcript_ready`/`camera_ready` true indicam material de revisão disponível; `commercial_ready`, `visual_ready`, `speaker_person_ready` false, `preview_ready=null`, `publication_ready=false`. Câmera ready não confirma foco nem render final.

O replay não regenerou as **12 folhas de contato** do pacote original. Por isso o ZIP novo tem 12 membros a menos e visual continua degradado; não é alegação de redução equivalente de volume. As folhas originais estão preservadas no ZIP anterior. As três prévias abaixo são artefatos locais separados, sem aprovação e sem declarar visual completo.

## ASD, câmera, áudio, comercial e prévias

Não foram alterados Re-ID, Active Speaker ou Camera Director nesta rodada. Os avanços V4 anteriores permanecem: diagnóstico seed/merge/unmapped, busca grande exata, policies de janela opt-in e guards de independência. No real, 1.291 IDs são hipóteses, não pessoas; três speakers permanecem sem associação global e A/V `not_measured`. Fragmentação, ID switches e precisão audiovisual continuam pendentes de referência anotada.

As 99 decisões de câmera não são 99 vídeos. O foco resolvido original foi 3,465%, preservação96,535%, 2.019 beats sem foco e dois com speaker-focus; 2.395 switches suprimidos têm outro denominador. Zero zoom entregue permanece aceitável quando não há alvo/segurança/duração comprovados. Nenhum zoom foi fabricado nesta rodada.

Foram renderizadas **somente três prévias** dos três candidatos prioritários, com FFmpeg local, áudio original reencodado AAC, imagem completa 16:9, 480×270 e **sem crop, zoom ou instrumental**. Não são finais sociais 9:16. [Manifesto com comandos, frames e hashes](source_previews_manifest.json); [inspeção](preview_inspection.json); [streams de áudio/vídeo verificados](preview_stream_validation.json). Foram 682/629/861 frames, FPS 29,970; três frames por preview decodificados e verificados por SHA. Inspeção do assistente de um frame central de cada prévia mostrou enquadramento aberto com duas faces e dois planos próximos; não identifica pessoas nem prova falante ativo. Presença do stream AAC não é revisão de conteúdo: áudio não foi ouvido/verificado; aprovação humana false.

- [Prévia3946,52–3969,28 s](source_previews/MOMENT_00022_0001/source_preserve.mp4)
- [Prévia425,02–446,00 s](source_previews/MOMENT_00002_0002/source_preserve.mp4)
- [Prévia1585,20–1613,94 s](source_previews/MOMENT_00008_0002/source_preserve.mp4)

ASR: 710 flags originais/13.082 palavras não são WER. S7 soma condições de revisão sobrepostas: 710 incertezas ASR, 1.408 palavras com overlap, 16 fragmentos/interrupções, seis timestamps e duas suspeitas heurísticas; união1.966, acréscimo1.256. Não se comprovou piora acústica. `targeted_asr` vazio não apagou revisão por fonte: **16 janelas +254 pendências humanas** intactas, independente da shortlist. As 245 regiões multipass adiadas são outro escopo. Foram preservadas 16 chamadas acústicas/86,36 s; chamadas novas zero; budget não reiniciado. [Reconciliação de escopos](scope_reconciliation.json), [dez referências prioritárias de áudio](audio_review_priority_refs.json).

Comercial: OCR solicitou 77 candidatos, inspecionou 16 e deixou 61 sem medição. Na fila há62 revisões comerciais pendentes: 61 não inspecionados mais `MOMENT_00003_0001`, inspecionado mas com gate registrado `confirmed_commercial`, sem liberação comercial. As 65 revisões textuais não são cobertura visual total; as 12 folhas de contato também têm outro escopo. Ausência de detecção não foi transformada em comercial ausente. Audio events desativado conserva `skipped`, `events=[]` e música desconhecida, sem instalar bibliotecas. Não foi aplicado instrumental na percepção.

## Performance, cache e testes

Percepção e configurações não mudaram nesta rodada; benchmarks V4 anteriores foram preservados e não repetidos. Naquele trecho AV1 de 120,0199 s, mesmo FPS/resolução/config: Vision 98,481→85,151 s em um par; Scene-only OpenCV 47,944→PyAV 12,469/12,320 s, seis cuts equivalentes na tolerância de um frame + 0,5µs, um limite deslocado. PyAV continua opt-in. Não há nova mediana ou melhora de RAM/VRAM medida nesta rodada; tempo de preview 480×270 não é benchmark de percepção1080p.

Qwen original: 23 chunks, 32 chamadas, 398.026 tokens de prompt/32.143 gerados; geração3.653,566 s, prompt 272,373 s, load 5,893 s; revisão global 593,766 s partial. Perfil `max`, modelo 14b, budgets e `compact_prompt=false` intactos. Nenhum novo benchmark/model call nesta sessão; otimização de inferência/qualidade Qwen **PENDING**, ganho **NOT_MEASURED**.

Alteração de diálogo invalida o componente 16 e downstream pelo fingerprint existente; master timeline agora inclui o código de integração. Não se alteraram fingerprints/config/modelos de Whisper/YOLO/SceneDetect/Qwen para uma mudança de triagem. Não houve recomposição dos caches originais. Interfaces antigas continuam com fallbacks explícitos.

Arquivos: [source_changes.json](source_changes.json). **Sete fontes existentes**: `app.py`, `editorial_outcome.py`, `integrity_contracts.py`, `pipeline.py`, `second_curation.py`, `second_curation_export.py`, `understanding.py`. **Três arquivos de teste novos**: `test_sol_v4_post_editorial.py`, `test_sol_v4_post_dialogue.py`, `test_sol_v4_post_integration.py`. Os demais fontes iniciais permanecem íntegros; novas evidências somente nesta pasta.

Focos reais: **111 passed** editorial, 14 novos; **98 passed** diálogo,26 novos; **37 passed** integração/GUI/contratos, quatro novos. Focos se sobrepõem em testes existentes, portanto não somar totais. Positivos/negativos cobrem candidato completo versus incompleto, high-score sem gates, ASD indisponível com revisão textual/source-preserve, nenhuma publicação automática, dedup 80→77+3, versões legado/nova, referências, diálogos com intervenções/polar/tempo e narrativas sem prova. Os logs iniciais e correções de fixtures/revisão foram mantidos.

**Regressão final VERIFIED:** **1.936 passed, três skipped, zero failures/errors, exit code 0**, 1.939 casos. Pytest 246,90 s; wrapper 247,674 s. Todos os **1.895 casos anteriores preservados**, 44 novos aprovados (14 editorial + 26 diálogo + quatro integração); nenhum removido. Os três skips continuam dois de symlink Windows e um Tesseract opt-in. [after_full.json](after_full.json), [log](after_full.log), [JUnit](after_full.xml), [test_case_comparison.json](test_case_comparison.json). A conferência final de preservação também passou, sem drift dos fontes após testes.

## Estados e próxima homologação

| Entrega | Estado |
|---|---|
| Gates top-10 e justificativa dos quatro prioritários | VERIFIED |
| Fila única acionável/GUI/legado e replay real 80→77+3 | VERIFIED |
| Refino Q&A/narrativa, positivos sintéticos e negativos | VERIFIED no escopo de contratos |
| Melhor ligação/continuidade narrativa no episódio | NOT_MEASURED; contagens reais não melhoraram |
| Novo ZIP/refs e três prévias técnicas source-preserve | VERIFIED tecnicamente; aprovação humana PENDING |
| ASD global, sincronização e fragmentação real | PARTIAL / NOT_MEASURED |
| Ground truth humano20 trechos, precisão/recall/WER | PENDING / NOT_MEASURED |
| Qwen/performance novos e crop 9:16 homologado | PENDING |
| Regressão completa / 1.895 casos antigos / 44 novos | VERIFIED: 1.936 passed / três skips / zero falhas |
| Preservação da análise original, ZIP, mídia, peso, exports, HEAD e fontes | VERIFIED: sem divergências |

Nenhum bloqueio técnico foi usado para simular conclusão do projeto. O pacote P0 de triagem/contratos está implementado; o projeto completo e cortes publicáveis não são declarados concluídos.

Comandos offline de homologação:

```powershell
& .venv/Scripts/python.exe -m pytest -q src/tests/test_sol_v4_post_editorial.py src/tests/test_sol_v4_post_dialogue.py src/tests/test_sol_v4_post_integration.py
& .venv/Scripts/python.exe -B docs/reports/sol_v4_pos_foquinha_20261013/run_regression.py homologacao_posterior
```

Scripts e manifestos desta pasta registram comandos reais de auditoria, replay e previews. `replay_curator_export.py`/`render_source_previews.py` recusam sobrescrever suas saídas; nova repetição deve usar pasta nova. Não repetir agora operações já aprovadas. Para o Curator, abrir a fila 1.1 do ZIP novo, começar pelos quatro IDs solicitados, consultar as prévias locais e completar anotações/audio/comercial. Isso não aprova shortlist, preview ou publicação.
