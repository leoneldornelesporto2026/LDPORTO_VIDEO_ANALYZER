# R6.2 — causa raiz de foco visual e Smart Zoom

Data da execução: 16/10/2026. Este diagnóstico usa o pacote mais recente e o código do workspace após o checkpoint A. As métricas do pacote são o baseline, não testes do código modificado. Nenhum pipeline de inferência, download, modelo, GPU, Ollama, aprovação ou publicação foi executado por esta investigação.

## Identidade da evidência

- Branch/head verificados pelo checkpoint A: `baseline/ldporto-20261012-prompt01`, `d508c1e4a04f78d5ddbe2ebd14c6a52b5f6cff59`; workspace limpo antes das alterações. Sem commit/reset/checkout.
- Pacote: `pacotes_para_enviar/SECOND_CURATION_READY_9UCGZia2p1k_20261016_200541_367803_f6b214.zip`.
- SHA256 do pacote: `d090841905222237b282af8b25caa02aa8b2bfcb946baae1a6f4ae0f3ab3779c`; 173 membros, 114.719.289 bytes descompactados; resultado do verificador: `valid`. Evidência: `BASELINE.json`.
- Fonte: `input/youtube/9UCGZia2p1k/9UCGZia2p1k.mp4`; SHA256 confirmado no checkpoint A: `5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea`, 2.663.231.970 bytes, 1920×1080, duração 5.840,094 s. Original preservado.
- Reutilizados: `analysis/video_8adc6609911a/`, `video_analysis.json`, `people_observations.json`, `tracklet_observations.json`, `shots.json`, `active_speaker.json`, `person_motion.json`, `main_moments.json`, `story_arcs.json`, `camera_plan.json` e configuração existente do cache `19_camera_director.json`.

## O que o baseline efetivamente contém

| Medida | Resultado medido |
|---|---:|
| Tracklets brutos | 10.458 |
| Micro-tracklets não qualificados | 6.804 |
| Tracklets sem embedding facial | 6.374 |
| Observações brutas | 63.989 |
| Observações projetadas após Re-ID | 46.326 |
| Observações excluídas da projeção | 17.663 |
| Faces brutas / faces na projeção | 33.116 / 23.924 |
| Faces excluídas junto com tracks não mapeados | 9.192 |
| IDs visuais | 3.580 |
| IDs com evidência entre tracks | 79 |
| IDs somente dentro do track | 3.501 |
| Associações pessoa/locutor | 7 `UNRESOLVED`; zero confirmadas |
| Instrumentos estruturados | 0; capacidade não medida neste snapshot |
| Shots | 2.045; mediana 2,083 s |
| Shots com duração <2 s / <3 s | 953 / 1.396 |
| Janelas de avaliação do Director | 84.713 |
| Janelas com pelo menos uma face | 44.928; 2.791,861219 s |
| Janelas com pelo menos um crop geometricamente seguro | 40.097; 2.463,538906 s |
| Dominância temporal qualificada | 1.185 janelas; 75,967438 s |
| Dominância qualificada + crop seguro | 1.176 janelas; 75,217938 s |
| Dominância + crop seguro ainda preservados no aberto | 472 janelas; 30,089188 s |
| Foco final recomendado | 1.023 janelas; 62,084750 s; **1,063078%** da fonte |
| Segmentos compartilhados | 3.986: 3.930 `SOURCE_FIT_BLUR`, 56 `FOCUS_PERSON_9X16` |
| Zoom proposto / evento na timeline / entregue | 1 / 0 / 0 |

Os 79 IDs com suporte facial entre tracks não constituem 79 pessoas identificadas com acurácia medida: não há goldset humano, medição nominal nem autorização para inferir os artistas pelo título. Re-ID e associações acústicas permaneceram conservadores.

O funil exclusivo antigo atribui 18.500 janelas a ausência de observações, 21.285 a ausência de face, 44.704 a ausência de alvo audiovisual confirmado e 224 a overlap. Esse funil é acústico; não mede elegibilidade de um alvo puramente visual. O novo diagnóstico adiciona estados paralelos, preservando o funil legado por compatibilidade.

## Cadeia causal e correções

| Problema | Evidência | Causa | Módulo | Correção incremental | Teste / resultado |
|---|---|---|---|---|---|
| Muitos tracks não chegam à câmera | 17.663 observações, incluindo 9.192 faces, fora da projeção persistente | `apply_person_identities` projeta somente tracks mapeados; 6.804 microtracks e 6.374 sem embedding | `person_reid.py` | Não fundir IDs nem afrouxar limiares. Manter evidência bruta no FULL_AUDIT e explicitar a perda de cobertura | Contagens diretas de JSON atual e pacote; sem afirmar acurácia de identidade |
| Foco depende excessivamente de entrada estável em shots curtos | Shots mediana 2,083 s; entrada exige 2 s, pelo menos 3 incrementos entre amostras e `min_hold_seconds=3` | Pouco tempo restante por shot; confiança deve ser reobtida após cortes | `camera_evidence.py`, `camera_director.py` | Preservar limiares e reset por shot/track; evitar apagar histórico após uma amostra fraca transitória; nunca enquadrar face ausente | Testes de dropout, troca de track e corte de origem |
| Uma medição rápida invalida o resto do track | `max_velocity` acumulava máximo vitalício | Outlier de posição mantém alvo permanentemente instável mesmo após estabilizar | `camera_evidence.py` | Medir máximo em janela recente de 2 s, mantendo o mesmo limite 0,10/s; histórico limitado ao shot e track | Teste de outlier/reestabilização sem transportar identidade entre tracks |
| Close seguro não pode ser alvo visual | Fallback excluía `close_up` e `medium_close_up` antes da geometria | Exclusão semântica precedia verificação geométrica | `camera_director.py` | Permitir foco baseline somente quando a geometria real é segura; Smart Zoom continua bloqueado se a fonte já é close | Teste de foco visual em close com todos os zooms iguais a 1 |
| Incumbent visual seguro perde para fallback do planner | `KEEP_CURRENT` usa score acústico zero quando locutor está unresolved; fallback recebe bônus global 0,28 | Evidência visual do mesmo alvo não participava da pontuação de continuidade | `camera_director.py` | Usar confiança detectora atual do incumbent visual, mesma chave shot/track, face presente e crop seguro; não aplicar o bônus diante de outro alvo acústico confirmado | Teste com fallback global e instabilidade transitória mantendo o mesmo rosto seguro |
| Zoom aceito vira movimento imperceptível | Proposta 1143,5–1149,5 s de 1→1,125; timeline só chega a 1,0003315143 antes de abortar em 1144,25 s | Preflight de 0,75 s não demonstrava os 6 s da transição; falta de face segura no futuro. O bypass de dead-zone já existia e não era causa principal deste pacote | `camera_director.py`, `camera_preflight.py`, `camera_motion.py` | Antes da aceitação, exigir caminho observado para toda a transição; fallback seguro para falta de suporte. Nenhum cap/upscale afrouxado | Teste que impede aceitar zoom quando a face some durante os 6 s |
| Transição cancela mesmo quando incumbent continua observado | Reavaliação V1: target mantido e crop seguro, mas `person=None` fazia Smart Zoom receber confiança zero | Variável do novo alvo dominante confundida com evidência do alvo já enquadrado; `used_beats` impedia retomada | `camera_director.py` | Continuar medindo o incumbent visual pela face atual, sem inventar vínculo acústico; conservar limites e preflight | Teste de curva contínua acima de 1,02 sem declarar entrega/render |
| Log de zoom afirma speaker sem associação | Proposta original contém `ACTIVE_SPEAKER_FOCUS` embora pessoa `PERSON_1981` seja apenas `DOMINANT_FACE` | Reason code fixo para qualquer alvo | `camera_motion.py` | Registrar `target_evidence_role`; visual-only usa `VISUAL_TARGET_FOCUS` | Teste que proíbe speaker code no evento visual |
| Proposta não é executável no Curator sem adaptação | Analyzer admite 1,125; API real inspecionada do Curator aceita 1…1,05 | Faixas diferentes entre plano e renderizador | Adapter de integração do Curator | Não truncar silenciosamente. Perfil compatível explícito com `max_zoom_factor=1.04` ou fallback, com proveniência | Homologação real e recibos de consumo constam em `CAMERA_VISUAL_VALIDATION.md` |
| Instrumento/mãos não estão protegidos por rosto seguro | `instrument_observations.json=[]`; amostras reais de guitarra têm headstock fora de crops verticais | Snapshot contém pessoa/face, sem observações espaciais instrumentais | `performer_evidence.py`, handoff/verificador | `instrument_linked=null`, status desconhecido; plano aberto para guitarra sem geometria verificável | Amostras MP4 separadas, avaliadas visualmente; não promover foco de instrumento por título ou rosto |

## Invariantes da implementação

`target_seen`, `face_seen`, `target_stable`, `speaker_linked`, `instrument_linked`, `crop_safe` e `identity_confirmed` são independentes em `focus_window_audit[*].target_states`. As contagens/durações em `metrics.independent_target_evidence` são paralelas e não devem ser somadas. Instrumento ausente é desconhecido, não falso negativo medido. Identidade nominal só é confirmada por registro humano explícito com evidência.

Confiança permanece score detector/editorial heurístico. Não há conjunto anotado para calibração probabilística ou acurácia de identidade. O código declara isso; a entrega não usa o termo probabilidade calibrada como resultado.

Não foram reduzidos `minimum_target_confidence=.85`, `minimum_face_duration=2`, margem de dominância `.35`, visibilidade `.8`, velocidade `.10/s`, limites de crop, sharpness, upscale ou limite de movimento. A histerese retém apenas histórico limitado do mesmo track/shot. A amostra atual fraca não qualifica um novo alvo e a ausência de face/crop mantém a saída segura. Proposta, timeline, render e aprovação seguem estados separados.

## Execução e reprodução

Comando de reavaliação: `.venv\Scripts\python.exe -B docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/replay_camera_snapshot.py`. Reexecuta apenas Camera Director sobre o snapshot, sem mídia/modelos. A API reutilizável é `camera_director.replan_camera_from_snapshot(snapshot, cfg=None)`; tempos absolutos e coordenadas normalizadas são preservados. A seleção por candidato/Story usa `camera_handoff.build_camera_handoff(..., intervals=[...])`.

A V1 intermediária foi preservada em `camera_replay_r62/`: 4.042 segmentos, 124,684250 s focados, 2,134970%, quatro propostas e zero entregas. A V1 identificou a falha adicional de continuidade do zoom; **não é o resultado final da engine**.

A revisão final da câmera, seus hashes de inputs/código e auditoria compactada ficam em `camera_replay_r62_v2/`: `timeline.json`, `metrics.json`, `zoom_events.json`, `config.json`, `focus_window_audit.json.gz`, `provenance.json` e `artifact_integrity.json`. As provas visuais e limitações de consumo estão em `CAMERA_VISUAL_VALIDATION.md`, não são inferidas da contagem de eventos JSON.

Resultado medido da V2: **139,324594 s de foco recomendado / 5.840,094 s = 2,385657%**, contra 62,084750 s / 1,063078% no baseline. São 4.042 segmentos: 3.910 em `full_frame` e 132 em `single_person`. Restam 5.700,769406 s em fallback; não se apresenta essa melhora modesta como solução completa do show. Os estados paralelos mediram 229,943375 s de alvo estável, 2.463,538906 s com algum crop seguro, zero locutor ligado, zero instrumento ligado medido e zero identidade nominal confirmada.

O preflight de toda a transição rejeitou 424 janelas antes de aceitar um movimento sem suporte suficiente. Restaram **duas propostas**: 1147,25–1153,25 s (`PERSON_1981`) e 1601,792–1607,792 s (`PERSON_2629`), ambas `DOMINANT_FACE` / `VISUAL_TARGET_FOCUS`. A primeira curva vai de 1 a aproximadamente 1,0991 dentro da proposta; a segunda chega a aproximadamente 1,1014 na extensão da linha e a 1,1235 depois. São curvas verificadas em JSON, **ainda não prova de movimento em MP4**. O contador legado `zoom_timeline_event_count=6` conta segmentos compactados com movimento, não seis propostas independentes. A execução final do replay durou 25,015 s, sem inferência nem render. Contador de entrega desta engine offline: **0**, verificação de entrega `null`.

Testes focados reais: 137 passaram em 1,79 s, usando o Python da `.venv` e os módulos `test_r62_camera_target_states`, `test_v44_camera`, `test_stage31_focus_audit`, `test_stage32_safe_camera`, `test_r6_camera_performer_handoff`, `test_s6_camera_director_smart_zoom`, `test_camera_director`, `test_v43_camera`, `test_v42_camera`, `test_v46_r3_camera_perception`. A primeira tentativa com Python global falhou com `No module named pytest`; nenhuma dependência foi instalada. A execução da regressão geral e homologação visual da equipe têm seus relatórios próprios.

Regressão adicional de Re-ID e integridade: `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_stage27_conservative_reid.py src/tests/test_vision_decision_integrity.py src/tests/test_sol_v3_visual_diagnostics.py` — **38 passaram em 2,47 s**. Nenhum código de Re-ID foi alterado.

Reabertura da V2: seis artefatos conferidos byte a byte contra SHA256; timeline contígua de 0 a 5.840,094 s; todo segmento individual executável mantém `crop.safe=true`; auditoria gzip reaberta com 84.713 janelas e duração correta. `timeline.json` SHA256: `cf5a90042e8980992b21de8e191123aa65ed90b7c6d0dbdea0d6a786795d83ce`. A auditoria compactada tem 2.466.939 bytes; os seis arquivos listados no manifest somam 20.577.813 bytes. Isso valida integridade e representação temporal, não preservação real de rosto/mãos/instrumento no render.

## Perfil compatível explícito para o renderizador real

Comando: `.venv\Scripts\python.exe -B docs/reports/r6_20261016/R6_2_FINAL_HANDOFF/replay_camera_snapshot.py --curator-compatible`. Resultado independente em `camera_replay_r62_curator_compat/`, sem substituir a V2 geral. Único ajuste de comportamento: `smart_zoom.max_zoom_factor` de 1,20 para **1,04**, registrado em `provenance.json.explicit_config_overrides` com razão de compatibilidade, preservando todos os limiares e preflight. O debug foi desabilitado somente para tamanho em ambas as revisões.

Replay compatível: 28,107 s, 4.040 segmentos, mesmos 139,324594 s de foco / 2,385657%, duas propostas 1→1,04, máximo observado na timeline 1,0395106265. Integridade dos seis artefatos reaberta e conferida por SHA256. `timeline.json`: `ff2d32e97e10ba825d186eb639b6a33a10838feffd8ccb2635589e21e1505b4b`; `config.json`: `6e19cb6d37392343b65cb8e5fc267e46789a1b2d8327f456d0cd74f52751f8ff`.

Teste de consumo do adapter canônico atual `curator_camera_adapter.build_curator_camera_plan(timeline, 1602, 1606, metadata)` produziu 69 segmentos nativos `crop`, 69 com movimento, zero rejeições; não houve render nesse teste. Alvo `PERSON_2629`, centro de fonte `[0.5175078153610229, 0.5]`, zoom interpolado de aproximadamente 1,000000083 a 1,0176573595 no intervalo extraído. Os dados foram entregues ao ensaio MP4 real; a verificação dos frames finais continua sendo evidência separada. A execução do adapter com metadata sem `duration` foi inicialmente rejeitada com `KeyError`, corrigida no comando de validação incluindo a duração canônica; não foi interpretada como render executado.
