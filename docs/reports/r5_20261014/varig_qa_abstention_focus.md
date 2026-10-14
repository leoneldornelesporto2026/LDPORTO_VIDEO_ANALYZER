# VARIG — diagnóstico focado de abstenção Q&A

Fonte original somente de leitura: `analysis/video_5198fcdaef38`. Foram examinados os quatro sidecars pequenos de segmentos, Q&A, tópicos e seções. Não houve inferência, decodificação de mídia, pipeline ou leitura do JSON de análise completo. Evidência estruturada e hashes: `varig_qa_abstention_focus.json`.

Não havia incompatibilidade de shape, IDs ou propriedade na entrada: **383/383 segmentos aceitos e 34/34 perguntas canônicas válidas**. O QA original tem 29 unresolved e cinco not_expected. A nova API emitia 29 registros unresolved e nenhuma proposta com resposta. Das 29 continuações imediatas, 24 têm o mesmo speaker registrado, oito têm termos compartilhados, quatro são classificadas como nova pergunta e uma tem speaker ausente; nenhuma tinha um marcador tipado reconhecido pela regra anterior. Esses grupos se sobrepõem e não são uma taxonomia de acurácia.

Dois casos reais demonstraram lacunas estreitas de autorresposta na narração:

| Referência | Evidência literal curta | Tratamento novo |
|---|---|---|
| Q_0000 / SEG_00003, 13,96–14,86 s | “Como a gente lê?” → SEG_00004, 14,94–15,52 s: “270.” | Candidato de autorresposta numérica. SEG_00002 contém literalmente “número 0270”; mesmo speaker e gaps de 0,46/0,08 s. |
| Q_0004 / SEG_00013, 66,46–70,20 s | Pergunta começa “Ué, a gente já não contou…” → SEG_00014, 70,38–77,64 s: “Sim, a gente contou…” | Candidato de confirmação na mesma narração, com duas âncoras literais. A classificação canônica direct_question permanece intacta. |
| Q_0015 / SEG_00126, 709,46–714,72 s | Pergunta como o piloto sabe para onde está indo; a continuação cita auxílios de radionavegação. | Explicação plausível sem marcador/âncoras exigidos. Continua unresolved; não se afirma que não haja resposta real. |
| Q_0024 / SEG_00267, 1441,04–1443,62 s | “220, 230 a nós é devagar?”; a continuação é uma instrução para monitorar sinais. | Sem resposta explícita; abstenção preservada. |
| Q_0032 / SEG_00366, 2110,58–2115,84 s | Começa “Porque existe um código morse…” e não contém interrogação. | Candidato legado classificado direct_question pelo prefixo; não é evidência de pergunta real. Registro original preservado. |

A alteração ficou restrita a `narrative_relations.py` e seu teste. O cue numérico exige pergunta de leitura, número literal no segmento imediatamente anterior, equivalência inteira exata, mesmo speaker e gaps curtos; não inventa observação de tela. O cue polar exige resposta imediata do mesmo narrador com Sim/Não, forma polar sem WH e duas âncoras. Perguntas/respostas canônicas, limites, vetos temporais, fronteiras e aprovações permanecem intactos.

Comparação CPU com as novas regras desligadas em memória: zero propostas e 29 unresolved. Ligadas: **duas propostas e 27 unresolved**, exatamente Q_0000→SEG_00004 e Q_0004→SEG_00014. Todas exigem revisão, `confirmed=False`, completude/áudio não verificados. Os quatro inputs originais permaneceram byte a byte iguais. O contexto SEG_00002 é dependência explícita da proposta numérica, sem extensão automática de limites históricos.

O padrão lexical estrito de retomada de arco tem sua contagem registrada no JSON de diagnóstico. A ausência desse marcador não demonstra ausência de retomadas reais; nenhuma regra de recuperação de arcos foi ampliada.

Validação final: **134 passed em 6,57 s, exit 0**, incluindo 36 canários novos sintéticos e 98 testes existentes. Comando, stdout, JUnit e hashes em `narrative_focus_05.*`. A revisão independente acrescentou veto explícito a WH de quantidade/tipo (quantos/quantas/quanta/que), sem mudar as duas propostas reais. Os focos anteriores ficam preservados. Não foi medida precisão/recall humano e não se trata de uma nova execução completa do vídeo.

```text
narrative_relations.py 65706b51bf4e9b7a6c7682f3da4c64e65cb3fca0e2785acf3664edcf5f1065b9
test_r5_narrative_relations.py 1e39068ba246436a80abb42c43fbc7267c59b59b4dd0baaf87e2eb665d152973
```
