# Diagnóstico de pessoas e identidades — show 9UCGZia2p1k

Data local: 2026-10-16. Escopo: leitura dos fontes atuais e dos JSON do ZIP real citado em `DIAGNOSTICO_CAMERA_SHOW.md`, seguida de adaptação incremental de contratos. Não houve nova detecção, Re-ID, diarização, ASD, visualização de mídia ou inferência nominal.

## Evidências reais do pacote

`summary/quality_summary.json → quality` registra:

| Medida | Valor |
|---|---:|
| Tracklets brutos | 10458 |
| Tracklets qualificados | 3654 |
| Micro-tracklets | 6804 / 65,0602% |
| Duração mediana do tracklet | 0,5 s |
| Micros sem embedding | 4669 |
| Micros com embedding | 2135 |
| Micros anexados por Re-ID | 36 |
| Micros anexados / micros com embedding | 1,68618% |
| Identidades persistentes anônimas | 3580 |
| Identidades com presença significativa | 726 |
| Fração de tracks sem embedding facial | 60,9486% |
| Merges Re-ID aceitos | 110 |
| Cobertura speaker↔person | 0% |
| Cobertura active speaker | 0% |

`people/person_identities.json` contém 3580 linhas. Exemplo: `PERSON_001`, `TRACK_00001`, observado entre **0,958 e 2,125 s**, `identity_status=within_track_only`, `reid_confidence=null`. É uma hipótese visual dentro de um rastreamento, não identidade civil ou pessoa única comprovada.

`reid_abstained_track_count=10348` não significa 10348 erros humanos medidos: inclui seeds que originam identidades e tracks não fundidos. O código atual já distingue seeds, merges e realmente não mapeados em `reid_outcome_diagnostics`; essa melhoria anterior não foi reexecutada sobre o show aqui. Não se deve relatar "taxa de acerto Re-ID" a partir desses contadores.

## Por que não há locutor associado

`people/speaker_person_summary.json` contém sete locutores acústicos, todos `association_status=UNRESOLVED`, sem `person_id`. `audio_video_sync.status=not_measured` em todos.

| Locutor | Janelas de áudio | Janelas com candidatos | Positivas qualificadas |
|---|---:|---:|---:|
| SPEAKER_00 | 820 | 3 | 0 |
| SPEAKER_01 | 1926 | 32 | 0 |
| SPEAKER_02 | 307 | 17 | 0 |
| SPEAKER_03 | 64 | 1 | 0 |
| SPEAKER_04 | 128 | 0 | 0 |
| SPEAKER_05 | 200 | 1 | 0 |
| SPEAKER_06 | 274 | 13 | 1 |

SPEAKER_06 tem uma janela positiva (`ASD_WINDOW_003434`), suporte de 2,792 s e score boca/áudio registrado de 0,7977022. Há conflito com outra hipótese e falta de consenso independente suficiente. O sumário não oferece timestamp dessa janela; não foi inventado. Esse score não confirma pessoa ou identidade nominal.

`active_speaker.build_global_affinity` (`src/ldporto/active_speaker.py:94`) requer ao menos duas janelas positivas independentes, participação suficiente do melhor candidato, suporte positivo e ausência de empate. A presença visual sozinha não cria associação. A associação global ainda precisa de disponibilidade visual e sincronismo contemporâneo na construção de intervalos locais. O resultado `UNRESOLVED` do pacote é compatível com esses dados, não um status a contornar.

## Gargalos e implementações já existentes

- `person_reid.build_person_identities`, em `src/ldporto/person_reid.py:189`, já consolida tracklets por template facial robusto, margem entre concorrentes, consistência de cluster e veto temporal. O código atual já faz busca exata limitada em blocos para galerias grandes e retorno facial estrito de micros. Não é necessário um segundo motor.
- Micros com apenas uma observação de embedding têm limiar mais forte (`person_reid.py:364`). Posição na tela, proximidade temporal e título do vídeo não autorizam associação. Uma face parcialmente visível sem embedding adequado continua evidência insuficiente.
- `apply_person_identities` (`person_reid.py:494`) mantém os tracklets crus, mas envia aos consumidores apenas observações mapeadas. Isso protege crops/ASD de identidades frágeis; também explica por que tracklets brutos não equivalem à cobertura visual utilizável. Diminuir essa proteção para aumentar percentual seria inadequado.
- `vision.py` possui corpo/rosto, qualidade facial, tracking, amostragem adaptativa, recuperação limitada de faces e embeddings. O detector YOLO local é validado como detecção de pessoas. Não foi encontrado classificador integrado de instrumentos/papéis de palco equivalente ao solicitado. Nenhum instrumento foi inventado a partir do título ou do fato de ser show.
- `understanding.build_participants` (`understanding.py:546`) usa relevância observada, fala e perguntas. No pacote, `SPEAKER_01` e `SPEAKER_04` recebem `likely_host` por perguntas repetidas. É uma hipótese editorial de lógica conversacional; não prova de apresentador, guitarrista, cantor ou civilidade. O novo contrato a rotula explicitamente como hipótese.

`people/participants.json` contém sete participantes editoriais sem pessoa visual nem nome. O status legado `confirmed_editorial_participant` confirma relevância editorial, não rosto, papel de palco ou nome. Thiago Castanho/Marcão Britto no título não permitem preencher esses vínculos.

## Evolução implementada

`src/ldporto/performer_evidence.py::build_performer_evidence` produz contratos aditivos para:

- `participants`: campos de confirmação nominal separados do status editorial legado;
- `person_tracks`: cópia dos tracklets atuais, com associação ou abstenção original;
- `person_appearances`: observações pontuais com timestamp, track/person IDs, cena, caixas, qualidade, confiança e origem;
- `instrument_observations`: somente observações já fornecidas, com intervalo e proveniência explícitos;
- `speaker_person_mapping`: preserva o sumário e explicita `CONFIRMED / PROBABLE / UNRESOLVED / CONFLICTING` como estado de revisão;
- `performer_review_queue`: proposta de nome/papel e referências para confirmação humana, sem auto-merge.

Quando Re-ID abstém num track, o identificador online bruto permanece em `raw_person_id`, nunca é promovido a `person_id` persistente. Observações pontuais não ganham intervalos fictícios de visibilidade contínua.

Uma confirmação nominal só é preservada quando há pessoa associada e `identity_confirmation` com `method=user_verified`, nome confirmado e `evidence_refs`. Caso contrário, `confirmed_name=null`; possíveis nomes existentes continuam hipóteses revisáveis. As estruturas retêm a origem, não alteram os merges originais e não inferem instrumentos/canto/papéis.

Esta entrega cria o caminho de revisão e a preservação da evidência. Ela não melhora a acurácia real por si só, não confirma os artistas e não executa uma nova coleta de observações. Reconhecimento de instrumentos, reamostragem dirigida e validação audiovisual do show continuam trabalhos dependentes de evidência e homologação.

## Comandos e validação

Foram usados `Get-Content`, `rg`, leitura em memória com `zipfile/json`, `Get-FileHash` do pacote e testes no `.venv` existente. Não foram instaladas dependências. O comando `python -m pytest` do Python global falhou por ausência de pytest; a invocação correta está no relatório de câmera.

O conjunto focado de câmera/pessoas/Stories passou: **116 passed in 3.41s**. Cobre preservação de abstenção raw→persistente, ausência de nomes derivados de título, manutenção de hipóteses de papel, confirmação humana com referência, fallback instrumental, intervalos descontínuos e ausência de promoção a publicação. As fixtures são sintéticas; não comprovam identidade ou ASD no show. A verificação de schema/replay adicional e a regressão descoberta no índice master do pacote semântico estão registradas no relatório de câmera.

Homologação pendente no Windows: pares faciais anotados pelo usuário, correspondência de reentrada através de cortes, rosto parcialmente visível, músicos com microfone cobrindo boca, instrumento/mãos preservados e voz fora de quadro/público cantando. Manter associação nominal e speaker↔person não resolvida até confirmação sustentada.
