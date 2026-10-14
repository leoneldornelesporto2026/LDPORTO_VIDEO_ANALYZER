# R5.1 — Story Visual Handoff: implementação e foco

Fontes congelados antes das chamadas reais de títulos pela raiz. Nenhuma mídia ou inferência audiovisual foi executada por este agente.

`build_story_visual_handoff(legacy, semantic_artifacts, infer)` recebe documentos decodificados por caminho (JSONL como listas) e devolve quatro documentos novos:

- `social/narrative_editorial_title_proposals.json`: `pieces`, com `piece_type=STORY|REEL`, títulos, payload validado, evidências, abstenção e proveniência.
- `social/story_visual_handoff.json`: `series[].stories[]`, com títulos, speech_subtitles, highlights, partes N/M, caption, CTA, conceito de capa e restrições.
- `editorial/story_visual_completeness_report.json`: contagens e pendências por Story.
- `schemas/story_visual_handoff.schema.json`: contrato 1.0, dialeto JSON Schema 2020-12 completo.

`validate_story_visual_handoff(artifacts, legacy, semantic_artifacts)` retorna `status=valid|invalid`, `errors` e `publication_ready=false`. Verifica o schema versionado inteiro, referências cruzadas, intervalos, transcrição, projeções do payload, hashes de contexto, títulos, partes, highlights e gates.

O único executor de modelo é o callback injetado `infer(task_id, context, schema) -> (payload, provenance)`. Contexto contém `instruction`, `data`, `prompt_version`; tarefas de Story usam `titles:<story_id>`. Reels relevantes são somente os IDs da shortlist canônica, com tarefas `titles:reel:<candidate_id>`; nenhum candidato novo é selecionado. Limites parciais de Reel exigem revisão antes de inferir título. Dados legados permanecem imutáveis.

Cada Story recebe um título principal e duas alternativas distintas quando a resposta passa nos guards; falha ou insuficiência produz abstenção explícita e mantém os demais metadados. As verificações incluem citações literais, referências, números, vocabulário, negação por predicado e guard compartilhado de contrafactual. Elas **não comprovam entailment semântico ou qualidade humana**. Paráfrases podem sofrer abstenção conservadora. `factual_review_required=true` permanece obrigatório.

Palavras preservam seus timestamps existentes quando IDs, ordem, bounds e texto são coerentes com o segmento. Na ausência de método original registrado, a origem declara `persisted_asr_word_timestamps_not_independently_verified`. Ausência, suspeita ou inconsistência gera fallback por segmento, sem interpolar palavras. ASR e falantes acústicos permanecem hipóteses de origem; nenhuma identidade visual é criada. Cada intervalo mantém seu próprio `edit_mapping`, com tempos relativos nulos e `CURATOR_EDIT_REQUIRED`.

Regiões de sujeitos permanecem `UNKNOWN`, sem coordenadas inventadas. Layout, safe areas, marca, direitos, áudio, câmera e previews dependem da configuração e revisão do Curator. Não são produzidos MP4, PNG, ASS ou SRT. Todos os estados de publicação e aprovação permanecem falsos.

Foco final: **55 canários C + 41 P0 = 96 testes aprovados em 2,50 s**, sem chamadas reais de modelo. Comando, stdout e JUnit: `freeze.command.json`, `freeze.stdout.txt`, `freeze.junit.xml`. O comando registra SHA-256 dos três fontes. A execução real e a regressão completa são responsabilidades da raiz e não são inferidas destes testes.

Limites explícitos: suporte literal não garante verdade; alinhamento ASR não é escuta humana; metadados completos para revisão não significam vídeo renderizado, layout validado ou publicação autorizada. A homologação VARIG e o consumo do novo pacote devem ser apresentados separadamente pela raiz.
