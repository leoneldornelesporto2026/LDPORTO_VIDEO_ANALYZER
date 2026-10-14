# SOL V4.1 — continuidade editorial e integridade

Estado: **VERIFIED**. Replay em CPU; zero chamadas de modelos, renders ou reprocessamento do episódio.
Git preservado: `baseline/ldporto-20261012-prompt01`, HEAD `2f4634f202f976c135c4bd28db590e289ce72156`. Nenhum commit.

## Recuperação e correções

A sessão interrompida deixou o helper editorial e partes da fila 1.2. Os agentes de armazenamento e identidade terminaram em erro por limite de uso; não havia resultado final de testes, helper de mídia ou proveniência de replay salvo. Foram reaproveitados o código parcial, os cinco contextos já extraídos, o snapshot de 481 fontes e todos os relatórios V4. Nenhum agente ou benchmark foi reiniciado.

Causa do ranking: a fila 1.1 usava score histórico decrescente. No CTA, a média dos componentes observados era 0.765542, com cobertura 0.600 e penalidade de incerteza 0.032, resultando em 0.734. Abertura/fechamento tinham nota 1; gancho, payoff, narrativa, humor e áudio não tinham medição. Nota alta não comprova potencial narrativo. A ausência de hook e os demais gates continuam bloqueando seleção automática.

A fila 1.2 prioriza indícios literais de relato/experiência/contraste, depois casos sem classificação, depois CTA de manutenção. Um CTA dentro de relato, negação ou conteúdo misto recebe tratamento separado. Categorias como storytelling não provam história. Cada indício traz trecho, offsets e origem; os offsets permanecem verificáveis após a redação de dados privados. Não foi criado nem alterado score.

No catálogo: 11 CONTENT_REVIEW, 1 MIXED_CTA_CONTENT, 67 UNRESOLVED e 1 CTA_HOUSEKEEPING. A ordem dentro das classes continua usando os números históricos. Isso melhora a triagem explicável, sem alegar medir qualidade humana ou classificar semanticamente todas as histórias.

O CTA MOMENT_00022_0001 passou de prioridade 1 para 77, mantendo 0.734. Foram preservados os 80 IDs, limites históricos, segmentos, ranks, componentes, penalidades, gates, scores e as 77 unidades de revisão. Três alternates continuam nas unidades existentes; não foram descartados nem transformados em entradas adicionais. Shortlist oficial: **0**; aprovações humanas e publicações: **0**.

Propostas automáticas de limites usam apenas bordas de segmentos canônicos e contexto adjacente com tópico conhecido, sem sobreposição, intervalo solto ou duração fora dos limites rígidos. Nenhuma proposta altera o candidato ou certifica conclusão. Casos de outro tópico, lacuna, contradição de escopo e duração têm testes negativos.

## Cinco candidatos para inspeção humana

Os títulos e avaliações abaixo são hipóteses editoriais baseadas em transcrição não escutada. Os cinco permanecem elegíveis apenas à revisão provisória, sem elegibilidade automática ou aprovação. Todas as propostas respeitam o alvo de 30–90s e o limite rígido de 8–180s; a validação de conteúdo continua pendente.

| Candidato / título | Original | Proposta para inspeção | Score preservado / fila antes→depois |
|---|---|---|---|
| MOMENT_00002_0000 — A ideia de podcast que a rádio recusou | 00:06:03.10–00:06:47.76 | [00:06:00.36–00:06:47.76](review_players/MOMENT_00002_0000_inspection.html) (47.40s) | 0.610 / 4→2 |
| MOMENT_00006_0002 — A Live dos Anjos confundida com live religiosa | 00:18:55.30–00:19:30.52 | [00:18:29.68–00:19:30.52](review_players/MOMENT_00006_0002_inspection.html) (60.84s) | 0.279 / 10→3 |
| MOMENT_00008_0002 — Reconhecendo o primeiro vídeo do canal | 00:26:25.20–00:26:53.94 | [00:26:25.20–00:26:57.20](review_players/MOMENT_00008_0002_inspection.html) (32.00s) | 0.713 / 3→1 |
| MOMENT_00018_0002 — Ser outra pessoa ao entrevistar em espanhol | 00:55:33.08–00:56:10.88 | [00:55:33.08–00:56:13.72](review_players/MOMENT_00018_0002_inspection.html) (40.64s) | 0.238 / 20→5 |
| MOMENT_00020_0000 — O perrengue que o glamour do evento esconde | 01:01:28.94–01:02:09.80 | [01:01:28.94–01:02:24.38](review_players/MOMENT_00020_0000_inspection.html) (55.44s) | 0.230 / 22→6 |

**A ideia de podcast que a rádio recusou**

Promissor: causa, tentativa, obstáculo e autoavaliação final aparecem no texto; humor e surpresa não medidos.
Gancho: Antecipou um formato inspirado em Grace Helbig e ouviu uma recusa. Contexto: Incluir a pergunta sobre criadores de referência (SEG_00177–00178). Desenvolvimento: SEG_00179–00182: referência, proposta à rádio e recusa.
Conclusão observada/limite: SEG_00183–00184: comentário sobre estar à frente do tempo; termina antes da mudança em 407.96.
Riscos: topic_boundary_crossed permanece; conferir se a fronteira é uma mudança real de assunto; Grace Helbig e atribuição das intervenções precisam de escuta.
Revisões humanas: Ouvir pergunta e resposta juntas; Conferir pronúncia e locutores sem atribuir identidade visual; Reavaliar a fronteira temática com evidência, sem remover gate por conveniência.

**A Live dos Anjos confundida com live religiosa**

Promissor: há setup do nome, equívoco e consequência social explícita. A versão curta perde antecedentes.
Gancho: SEG_00497: “Gente, achei que era uma live bíblica.” Contexto: Começar na apresentação do projeto com João (SEG_00481–00483); o nome composto está incerto na transcrição. Desenvolvimento: SEG_00492–00495 explicam o nome ligado ao BBB; SEG_00496–00502 relatam a confusão.
Conclusão observada/limite: SEG_00509–00513: formação de comunidade e “Então, isso foi muito legal.”
Riscos: “João, o Luiz Pedrosa” e a frase sobre porcentagem dos evangélicos precisam de revisão acústica; Q_0104 trata fala iniciada por “Porque” como pergunta; o trecho é discurso relatado, obrigação de resposta requer revisão.
Revisões humanas: Confirmar nome e sentido da referência religiosa; Ouvir sem suprimir o contexto do BBB; Revisar Q_0104 sem alterar retroativamente o gate ou marcar resposta como confirmada.

**Reconhecendo o primeiro vídeo do canal**

Condicional: útil como reação nostálgica se o mural for legível. A posição alta na triagem não comprova história completa.
Gancho: Reconhecimento do primeiro vídeo diante de um mural de arquivos. Contexto: SEG_00664–00665 apresentam a retrospectiva; a reação depende das imagens realmente exibidas. Desenvolvimento: SEG_00666–00671: reação, reconhecimento e descrição de um teaser.
Conclusão observada/limite: SEG_00672 explica o teaser: lançou o canal querendo ir para a TV. É uma unidade de reação; a trajetória continua depois.
Riscos: Original tem 28.74s e está abaixo do alvo de 30s; Extensão a 32s só faz sentido pela explicação do teaser, nunca como preenchimento de duração; Não encerrar a história da carreira em SEG_00672; SEG_00673 em diante continuam outro desenvolvimento.
Revisões humanas: Ver o mural e ouvir a reação sincronizada; Decidir se a unidade é reação ou início de narrativa maior; A prévia existente cobre somente 1585.2–1613.94; inspecionar o restante no original.

**Ser outra pessoa ao entrevistar em espanhol**

Promissor para identificação e autodepreciação. Desfecho da resposta melhora com a continuação literal; não há risada confirmada.
Gancho: O nervosismo vem de perder a própria personalidade em outro idioma. Contexto: SEG_01206 inicia a pergunta sobre entrevistas internacionais; manter as intervenções breves. Desenvolvimento: SEG_01207–01222: idioma, personalidade e autodescrição tímida em espanhol.
Conclusão observada/limite: Original termina em “Eu fico meio, tipo...”. SEG_01224–01226 completam com “Eu sou básica” e “muito básica em espanhol”.
Riscos: ASR “esmui ratatá” e fragmentação das intervenções exigem escuta; A anedota de La Casa de Papel começa em SEG_01236 (3377.5), fora da proposta.
Revisões humanas: Confirmar palavras em espanhol sem normalização inventada; Conferir turnos de fala; Validar fim após a autodescrição antes da próxima anedota.

**O perrengue que o glamour do evento esconde**

Promissor como relato e contraste com glamour, mas sensível e dependente do tom; humor não verificado.
Gancho: O resultado constrangedor é dito na abertura; não depende de inventar um clímax posterior. Contexto: SEG_01372 inicia o relato. Se usar o contraste “glamour”, ouvir também SEG_01369–01371 em 3681.62–3688.74. Desenvolvimento: SEG_01373–01399: segurar a vontade, roupa, show, chuva, tentativa de banheiro e caminho ao hotel.
Conclusão observada/limite: SEG_01400 comenta “foi perrengue chique”. Proposta para inspeção, não fechamento semanticamente confirmado. SEG_01401 termina em handoff; não anexar como conclusão limpa.
Riscos: Original termina antes da continuação do hotel; ASR “rock rico” e outras falas coloquiais precisam de escuta; Constrangimento pessoal exige cuidado editorial; não ampliar a exposição por sensacionalismo; O autoquestionamento dentro do relato não prova pergunta externa nem resposta independente.
Revisões humanas: Confirmar o evento e a fala inicial pelo áudio; Rever o término em 3744.38 e o comentário seguinte; Avaliar tom, dignidade e necessidade do contexto sobre glamour.

A comparação estruturada, textos literais, IDs dos segmentos, gates individuais e referências de mídia estão em [priority_candidates.json](priority_candidates.json). Os players de inspeção usam o arquivo original por hash e os limites propostos, sem render. Os players *_video e *_audio preservam os limites históricos.

Q&A: a transcrição permite inspecionar respostas que o contrato automático deixou inconclusivas. Q_0104 e os casos iniciados por “Porque” em torno da retrospectiva exigem revisão da classificação interrogativa. O autoquestionamento na história do evento pode ser retórico. Esses achados não foram convertidos em respostas confirmadas: o replay reutiliza o refinamento V4 e preserva os gates históricos. O resultado comprovado nesta rodada é a proposta de contexto e fechamento, não uma nova inferência de narrativa completa.

## Fila, mídia e estados

A fila 1.2 inclui vínculos por SHA-256, ID e intervalo exato. O botão **Ouvir/ver fila** abre um seletor de candidato e permite vídeo original, áudio do próprio vídeo ou prévia existente. O arquivo escolhido precisa ter o hash correto; prévias precisam também estar dentro da raiz indicada e corresponder ao ID, fonte, intervalo, tamanho e hash. O player faz seek inicial e pausa ao final. Não há autoplay nem gravação de aprovação. Os formatos 1.0 e 1.1 continuam legíveis e os dois ZIPs históricos validaram.

Os estados são dimensões separadas: INTERESTING_CANDIDATE é hipótese de interesse; ELIGIBLE_FOR_REVIEW deriva do contrato atual; HUMAN_REVIEW_PENDING permanece até revisão explícita. HUMAN_REVIEW_COMPLETED, PREVIEW_APPROVED e PUBLISH_READY não são atribuídos pelo player ou pela classificação. O campo legado publication_eligible significa elegibilidade à curadoria; publication_ready continua falso. Identidade visual/ASD desconhecida permite examinar a câmera original, sem autorizar crop ou zoom.

As três prévias antigas foram vinculadas e tiveram seus hashes reconferidos. A validação técnica anterior por ffprobe foi reaproveitada porque os bytes são idênticos: H.264 480×270, 16:9, AAC estéreo 48kHz; durações de vídeo 22.756067s, 20.987633s e 28.728700s. Áudio presente e diferenças de duração inferiores a 12ms não comprovam sincronismo labial ou fidelidade de transcrição. Não houve nova escuta nem nova aprovação.

Entre os cinco, somente MOMENT_00008_0002 possui prévia antiga (1585.20–1613.94); ela não cobre a proposta até 1617.20. As outras duas prévias são MOMENT_00022_0001 e MOMENT_00002_0002, e não foram associadas a trechos vizinhos por nome. As cinco propostas completas podem ser examinadas no original local.

## Proveniência e pacote

Novo handoff: [ZIP final](derived_export_final/SECOND_CURATION_PARTIAL_7laRa_F3FbA_20261013_220433_901930_611d76.zip), 2,774,008 bytes, 142 hashes declarados válidos (143 membros incluindo o manifesto).
SHA-256: `efa01b273f3cd00311b205ed3060c0ec90d1d4e5c5a45f36b1095e96c633f2e6`.
Fonte original: `0231c20cfd8147d92926bda4f452777f3803c38b248064e65548f0b12a5fb98b`.
Código da análise original: `2661770914e1712b1cdcfccab15865b121794907579b1adece79f1275cb24888`; código do replay/exportador: `f7d078b94aec8a458bcf96be3bff87ff41cc2abe14b6b8c339c0bc7026970cd6`.

`provenance/editorial_replay.json` registra 27 checkpoints, 26 entradas reutilizadas e hashes dos módulos executados. Componentes realmente executados: classificação de interesse, propostas de limites, vínculo de mídia e exportação/validação. Nenhuma execução de ASR, diarização, YOLO, Active Speaker ou Qwen. O build_mismatch e o estado de execução parcial permanecem; o replay não gera atestado de percepção nova. O ZIP é portátil por referências e não inclui mídia ou caminhos privados. Os HTMLs locais referenciam a mídia desta máquina.

O pacote intermediário desta sessão também foi preservado. O final incorpora a correção dos offsets após redação de privacidade; nenhum ZIP histórico foi sobrescrito.

## Validação e pendências

Testes direcionados finais: **54 aprovados**. Regressão completa: **1972 aprovados, 3 skips, 0 falhas e 0 erros**. Baseline: 1936 aprovados e 3 skips; 36 casos adicionados, todos os casos anteriores preservados.

Os testes cobrem CTA, relato/negação, interesse versus aprovação, deduplicação, continuidade e limites, hash incorreto, travessia de diretórios, vínculo de prévias, player, privacidade e proveniência. Também rejeitam timestamps/aprovações/declaração de inferência adulterados mesmo com hashes do manifesto recalculados. O único teste existente ajustado passou a esperar a versão 1.2; o teste de contrato legado permanece.

Integridade final: 1041 arquivos originais (6,367,923,312 bytes), 27 checkpoints, 3 arquivos .package, modelo YOLO e três prévias preservados. 485 fontes congelados durante a regressão; HEAD e branch preservados.

Fontes alterados nesta rodada:

- `app.py`
- `src/ldporto/build_provenance.py`
- `src/ldporto/integrity_contracts.py`
- `src/ldporto/second_curation.py`
- `src/ldporto/second_curation_export.py`
- `src/tests/test_sol_v4_post_integration.py`
- `src/ldporto/editorial_review.py` (novo)
- `src/ldporto/review_media.py` (novo)
- `src/tests/test_sol_v4_editorial_quality.py` (novo)
- `src/tests/test_sol_v4_review_provenance.py` (novo)

Comandos e evidências: [focused_complete.log](focused_complete.log), [after_full.json](after_full.json), [replay final](editorial_replay_final.json), [integridade](final_integrity.json). O primeiro teste focado revelou um erro na busca de despedida dentro do próprio trecho; foi corrigido. O teste de redação de privacidade comprovou e protegeu a correção dos offsets.

**Próximo passo exato:** abrir os cinco links de inspeção acima, ouvir os nomes/expressões sinalizados e confirmar abertura/fechamento. Homologar também os controles do player no navegador Windows: o seek e as proteções foram testados por contrato, mas a navegação GUI e a reprodução real não foram simuladas como aprovação humana. Registrar revisão humana separada e, se necessário, renderizar apenas um canário com câmera original para o intervalo confirmado. Aprimorar perguntas iniciadas por “Porque” e a classificação semântica dos 67 casos não resolvidos pode partir dos checkpoints; corrigir associação visual/ASD exige nova inferência apenas em janelas escolhidas. Nenhuma dessas pendências autoriza shortlist, crop ou publicação.
