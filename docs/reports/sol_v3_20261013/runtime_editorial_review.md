# SOL V3 — semântica, contexto editorial e handoff

## Evidência auditada

Foram inspecionados diretamente, sem extração ou execução de conteúdo, os dois ZIPs solicitados em `pacotes_para_enviar/`. Ambos passaram pelo leitor/validador atual. O AFTER possui 66 membros, 65 arquivos declarados com SHA-256 conferido, nenhum hash divergente nem caminho inseguro; SHA-256 do ZIP: `843b5c05376f5c8a63845e225ad3069bd5778efd5afe888e1135ae63ecb7ac2d`.

Os dois registram a mesma fonte SHA-256 `e25bcad888afc039e27d316da0471ea08199ed2cf0f424cffd46d05a7902c998`, duração 19,014 s, 320×240, 15 fps. O AFTER mantém cinco segmentos originais em inglês, incluindo `really, really, really long trunks`; traduções continuam separadas e vazias. Esta auditoria não executou ASR, diarização, visão nem Ollama.

| Medição registrada | BEFORE | AFTER | Interpretação |
|---|---:|---:|---|
| Semântica total | 289,360 s | 253,047 s | redução observada de 12,55% |
| Chunk | 149,187 s | 155,890 s | aumento observado de 4,49% |
| Revisão global | 140,141 s | 97,094 s | redução observada de 30,72% |
| Tokens gerados | 2113 | 1731 | contadores reais registrados nos artefatos |
| Geração | 8,3205 tokens/s | 8,3767 tokens/s | throughput observado, não benchmark repetido |
| Chamadas/cache | 2 / miss | 2 / miss | ambas usaram prompt legado com schema repetido |

O AFTER também registra 4408 tokens de prompt, carregamento de 11,8664 s, prompt de 34,2244 s e geração de 206,6437 s. VRAM/utilização da GPU não foram medidas nesses campos e permanecem `null`. O inglês original substituiu o português anterior na entrada semântica: igualdade da fonte não significa igualdade do prompt. Esses dois resultados não permitem atribuir a diferença temporal a uma otimização específica ou alegar ganho universal.

Quatro candidatos foram confirmados: 2,14 / 7,72 / 1,08 / 1,86 s, todos abaixo do mínimo rígido de 8 s; score máximo 0,404, piso 0,5, alvo 30–90 s. As quatro rejeições, shortlist zero, `video_too_short` e publicação não aprovada são resultados legítimos e foram preservados.

## Causa e implementação

| Prioridade/problema | Causa confirmada | Mudança | Evidência/status |
|---|---|---|---|
| P1: quatro seções maiores em cinco segmentos | A hierarquia anterior compara principalmente rótulos lexicais; continuidade entre `these guys` e `that's` não superou limiares de rótulo | Agrupamento de seções adjacentes baseado em referências presentes na fala, IDs consecutivos, mesmo ID acústico, tipo de conteúdo compatível, ausência de mudança explícita de assunto/degradação diferente e limites temporais | VERIFIED em replay de artefato e fixtures; quatro tópicos preservados, quatro seções tornam-se uma, sem criar história ou score |
| P1: schema redundante na revisão global | `compact_prompt` só alterava extração local/reparo local; a revisão global ainda embutia o schema no system prompt | Opção compacta também aplicada ao prompt global e seu reparo; schema continua no parâmetro nativo `format`; caches globais distinguem os modos | VERIFIED em testes de request/cache; default permanece opt-in até benchmark/qualidade coordenados pelo responsável principal |
| P1: vídeo curto sem contexto integral para revisão | Shortlist vazia é correta, mas havia apenas candidatos breves excluídos | `full_source_review` separado, intervalo real 0–duração, IDs originais, sem score e explicitamente inelegível para shortlist/publicação | VERIFIED em testes <8 s e 19 s; não cria candidato nem afrouxa 8 s / 30–90 s / 0,5 |
| P1: revisão dependia implicitamente dos candidatos exportados | Palavras relevantes eram selecionadas somente pelos candidatos | Dossiê de revisão por fonte e comparação localizada exportados independentemente da shortlist; palavras originais das janelas permanecem referenciáveis | VERIFIED sem candidatos, incluindo corrupção de IDs e texto original |
| P1: raw hypotheses externas | O hash/caminho do produtor não implica disponibilidade do arquivo no ZIP | Trilha compacta liga hipóteses a palavras/segmentos exportados; cada raw ref informa `external_producer_artifact`, `unavailable` e hash somente declarado pelo produtor | VERIFIED em testes/validação; arquivos de áudio/vídeo/cache não foram copiados |
| P1: readiness ambígua sob P1_DEGRADED | Disponibilidade para revisão textual pode coexistir com ausência de foco visual e aprovação de render | Escopo de readiness explícito em manifesto/index/brief; continua distinto de qualidade, verificação humana e publicação | VERIFIED em paridade dos documentos; gates preservados |
| P1: causas independentes perdidas no pacote | O pacote final só copiava campos tradicionais de gate | Copia `causal_diagnostics` e `root_causes` produzidos pelo módulo de qualidade, mantendo a causa raiz legada; compara paridade dos documentos | VERIFIED em fixture e rehash negativo; a dedução das causas é responsabilidade do módulo de qualidade |
| P1: métricas globais sem decomposição auditável no ZIP | Performance summary continha agregados e stage runtime | Exporta também o perfil de chamadas semânticas e os metadados da chamada global, quando registrados | Implementado; dados ausentes continuam ausentes, sem reconstruir medições antigas |

A agregação modifica somente a organização em seções. Os tópicos, referências, transcrição original e incertezas permanecem disponíveis. A indicação `contextual_continuity_requires_review` explicita que a regra ajuda a revisão e não prova uma história. Mudança real de assunto, outra voz, promoção comercial, lacuna interna de IDs, intervalo temporal excessivo e diferença de degradação preservam fronteiras.

O contrato editorial passa a versão aditiva 1.1, mantendo campos existentes e acrescentando `full_source_review`; a trilha/dossiê usa versão 1.0. O contrato de transcrição do ZIP passa a 1.1, acrescentando referências a `source_audio_review.json`, `hypothesis_comparison.json` e `raw_hypothesis_dossier.json`; leitores continuam aceitando a versão 1.0, comprovado com ambos os ZIPs históricos. O index/catálogo público mantém sua versão e seus campos existentes.

Campos de palavras de baixa confiança agora são resolvidos pela palavra canônica com o mesmo ID, preservando speaker/segment atuais após diarização em vez de recircular IDs de snapshots anteriores. Isso não altera palavras nem probabilidades. `ORIGINAL` do dossiê é validado contra palavra/raw/timestamps canônicos. Revisão acústica registrada pelo produtor, inspeção do dossiê e revisão humana continuam ações distintas; construir o dossiê não executa nem certifica áudio.

## Arquivos

- `src/ldporto/semantic.py`: modo compacto global, cache por modo, agrupamento contextual de seções.
- `src/ldporto/editorial_outcome.py`: diagnóstico integral da fonte curta, contrato aditivo 1.1.
- `src/ldporto/transcript_dossier.py`: trilha compacta, referências canônicas e validação de disponibilidade/consistência.
- `src/ldporto/second_curation_export.py`: dossiês, diagnóstico, escopos de readiness, perfil semântico, causas e validação do pacote.
- `src/tests/test_sol_v3_runtime_editorial.py`: 17 casos novos.

O responsável principal integra chaves de pipeline/report, invalidação/recibos dos módulos novos, qualidade, GUI e benchmark real. Esta atividade não alterou modelos, mídias do usuário, `.package`, configurações de perfil ou gates editoriais/comerciais.

## Comandos e resultados reais

1. Leituras com `rg`, `Get-Content -Encoding UTF8` e `.venv\Scripts\python.exe -B -`, usando `zipfile` somente para ler membros previamente nomeados, verificar hashes e inspecionar JSONs. Sem extração ou execução de conteúdo do ZIP.
2. `.venv\Scripts\python.exe -m pytest -q --tb=short src/tests/test_sol_v3_runtime_editorial.py src/tests/test_runtime_fidelity_contracts.py src/tests/test_v43_semantic.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_v47_r3b_performance.py` — **85 passed, 15,56 s**, em `runtime_editorial_focus_01.log`.
3. Acrescentado o caso que impede esconder uma lacuna interna de segmentos e os testes de recibos/coerência de relatórios: `.venv\Scripts\python.exe -m pytest -q --tb=short src/tests/test_sol_v3_runtime_editorial.py src/tests/test_runtime_fidelity_contracts.py src/tests/test_v43_semantic.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_v47_r3b_performance.py src/tests/test_stage65_execution_receipts.py src/tests/test_stage06_report_coherence.py` — **134 passed, 25,95 s**, em `runtime_editorial_focus_02.log`.
4. Replay offline por `.venv\Scripts\python.exe -B -`, chamando `validate_core_package` nos dois ZIPs e `contextual_program_sections`/`classify_editorial_outcome` sobre o AFTER. Resultado em `runtime_historical_replay.json`: leitores **valid/valid**, mesma fonte, seções **4→1**, tópicos **4 preservados**, segmentos originais **inalterados**, shortlist **0**, estado **video_too_short**.

Escopos: `unit_mocked` para API/cache e regras; `integration_local` para serialização/validação e testes existentes com mídia sintética temporária; replay de artefatos históricos para compatibilidade. Nenhuma chamada de inferência, benchmark real, medição nova de qualidade acústica/visual ou revisão humana foi realizada por este agente. A regressão integral final e os benchmarks reais ficam no relatório principal.

## Pendências

- Benchmark cold/warm Qwen com três repetições comparáveis, metadados por chamada e avaliação de qualidade: coordenado pelo responsável principal; nenhum ganho real novo declarado aqui.
- Default do modo compacto: preservado desativado até prova controlada suficiente.
- Homologação de causalidade audiovisual/ASD/câmera: exige evidência real e permanece separada desta organização textual.
- Disponibilidade dos arquivos raw externos: explicitamente inacessíveis no ZIP; metadados e trilha presentes não substituem escuta ou inspeção do artefato original.
- Revisão humana e publicação: pendentes; o diagnóstico da fonte inteira nunca abre esses gates.
