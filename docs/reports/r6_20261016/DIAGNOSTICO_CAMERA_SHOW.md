# Diagnóstico de câmera — show 9UCGZia2p1k

Data local: 2026-10-16. A primeira etapa desta inspeção foi somente leitura. O baseline e o rollback dos fontes pertencem a `BASELINE_R6.json` e `rollback_sources.zip`, no mesmo diretório. Não houve pipeline, inferência, acesso a GPU/Ollama, download ou leitura de frames da mídia local neste trabalho.

## Evidência consultada

Pacote: `pacotes_para_enviar/SECOND_CURATION_READY_9UCGZia2p1k_20261016_134534_055860_7b047a.zip`.

SHA256: `f5a167a7fe39da50417c765a9ff3e21d22a8dea9c0e3fa808022d49df05bffb1`.

As 160 entradas foram inspecionadas com `zipfile.ZipFile`, lendo JSON em memória, sem extração sobre fontes. O manifesto declara versão `4.4.0`, build `R4.9-S4-TRACKING-FACIAL` e fingerprint `2cf5ac760af300db6fe23f01bad1cb23e0b9030d84f80c8e09a156141d36d863`. Os números abaixo descrevem esse pacote; não são resultado de uma nova execução dos fontes R6.

Fonte declarada em `source/metadata.json`: 5840,094 s, 1920×1080, cerca de 24 fps. O SHA256 da mídia é o registrado no pacote; a mídia não foi reprocessada.

## O que ocorreu

`camera/camera_summary.json` separa corretamente vários estágios que não podem ser somados como sucesso:

| Indicador | Valor do pacote |
|---|---:|
| Decisões inteligentes | 56 |
| Oportunidades editoriais brutas | 20548 janelas |
| Oportunidades elegíveis | 12033 janelas |
| Pedidos de zoom | 157 janelas |
| Eventos propostos / aceitos | 1 / 1 |
| Eventos de zoom na timeline | 0 |
| Eventos entregues | 0 |
| Foco visual resolvido | 62,08475 s / 1,06308% |
| Preservação da fonte | 98,9369% |
| Foco em falante conhecido | 0% |

Todo o foco resolvido é classificado como `VISUAL_ONLY_FALLBACK`; não corresponde a falante ativo confirmado. A timeline preencher o vídeo inteiro representa cobertura de recomendações e fallback, não 100% de foco comprovado.

O único evento proposto é `PERSON_1981`, de **1143,5 a 1149,5 s** (19:03,5–19:09,5). Seu `render_timeline_supported` é falso e não há recibos de entrega. O relatório histórico registra `CROP_PREFLIGHT_UNSAFE`, `CROP_UNSAFE`, `INSUFFICIENT_TEMPORAL_CROP_EVIDENCE`, `UPSCALE_OR_CROP_LIMIT` e outras razões. Não se pode concluir que todas essas razões pertencem ao mesmo frame: o código anterior agregava razões das linhas sobrepostas e também falhas de outros canários. Nenhum zoom desse evento foi declarado entregue por esta auditoria.

O funil anterior à decisão registra buckets exclusivos por duração:

| Falta de evidência | Segundos | Fração do vídeo |
|---|---:|---:|
| Sem observação de pessoa | 1434,7879 | 24,5679% |
| Sem rosto visível | 1613,4449 | 27,6270% |
| Sem alvo audiovisual confirmado | 2783,2595 | 47,6578% |
| Sobreposição de áudio | 8,6017 | 0,1473% |

Os contadores paralelos de geometria registram 36197 janelas com geometria ausente/insegura, 8251 com baixa nitidez facial e 91 com sujeitos que não cabem no recorte vertical. São contadores paralelos; não devem ser somados aos buckets exclusivos nem tratados como acurácia.

## O verificador existe e foi executado no pacote

`summary/preview_validation.json` declara quatro canários, frames renderizados usados e status `partial`. Há evidências registradas de `FACE_OR_HEAD_CLIPPED`:

| Intervalo fonte | Canary | Evidência registrada |
|---|---|---|
| 356,9375–364,9375 s | CANARY_00 | frame 5, bbox `[483,332,53,53]` |
| 1139,676109375–1147,676109375 s | CANARY_01 | frame 190, bbox `[7,105,126,126]` |
| 1148,47925–1156,47925 s | CANARY_02 | frame 0, bbox `[2,183,126,126]` |

Os dois últimos também têm `BORDER_REVIEW_REQUIRED`, status geométrico `unknown`, com 39 amostras cada. Estes dados foram lidos do JSON; os frames não foram vistos nem reavaliados aqui. A limitação concreta é ausência de validação/aprovação final do produto e pendências nos canários, não ausência completa de verificador visual.

O verificador atual usa OpenCV para rostos genéricos/bordas/fluxo e FFprobe para metadados. Em `src/ldporto/preview_verifier.py:324`, ele explicita que rosto genérico não comprova identidade. A área segura social continua pendente porque a prévia técnica não contém o conjunto final de títulos/legendas. Não há medição que certifique preservação de instrumentos, boca correta ou movimento do alvo por comparação registrada `SOURCE → FINAL`.

## Causas de código e evolução incremental

1. **Acoplamento ao alvo audiovisual.** `camera_director._prepare` exige associação local válida para focar falante e permite fallback facial apenas quando habilitado e sustentado. `camera_evidence.local_speaker_supported` não promove `UNCERTAIN` a confirmado. O show não possui associação global confirmada; reduzir esse gate produziria uma afirmação falsa.
2. **Preflight real limitado.** `src/ldporto/camera_director.py:403` e `camera_preflight.preflight_target` verificam amostras do mesmo alvo na mesma cena. Uma proposta aceita não garante que o alvo permaneça seguro por todos os segundos do evento. As saídas de segurança devem continuar podendo anulá-la.
3. **Deadzone aplicado a movimento deliberado.** `CameraMotion.move` aplicava `zoom_deadzone=.035` aos pequenos incrementos iniciais da curva editorial. Uma transição segura e de pouca amplitude podia permanecer estática até ultrapassar esse limiar. A correção separa comando intencional `SMART_ZOOM_IN/OUT` de ruído de tracking. Velocidade, aceleração, jerk, geometria, cortes e preflight continuam ativos. É um defeito reproduzido em fixture sintética; não foi demonstrado que ele seja a causa exclusiva do evento histórico nem que esse show agora entregue zoom.
4. **Evidência fora do intervalo.** `zoom_delivery` antes aceitava amplitude em keyframes da linha inteira, mesmo se o movimento estivesse fora da proposta, e agregava falhas de canários que não cruzavam a proposta. Agora interpola a curva dentro da interseção e ignora canários temporalmente separados.
5. **Render técnico e Curator têm políticas distintas.** `preview_renderer._fit` preserva a fonte em canvas preto (`fit_with_padding`). Ele não executa `SOURCE_FIT_BLUR`. O novo handoff pede `contain` central + `cover_blur` de fundo ao renderizador pertencente ao Curator; a implementação do renderer técnico não foi duplicada.
6. **Stories narrativas preservavam apenas layout sem geometria.** `story_visual_handoff` recebe snapshots por caminhos de artefatos. Agora agrega o mesmo contrato `camera_handoff` usado pelas Stories normais e pelos candidatos exportados, consumindo a timeline existente quando fornecida em `camera/camera_director_timeline.json`. Snapshots antigos sem essa evidência mantêm fallback explícito. Intervalos descontínuos continuam separados, sem criar uma falsa continuidade.

## Contrato R6 aditivo

`src/ldporto/camera_handoff.py` e `schemas/camera_handoff.schema.json` expõem as seis intenções: `FOCUS_PERSON_9X16`, `SOURCE_FIT_BLUR`, `DUO_STAGE`, `INSTRUMENT_FOCUS`, `AUDIENCE_REACTION`, `SOURCE_PRESERVE`.

As recomendações de foco/dupla dependem de geometria já aprovada pelo Director. Intenção instrumental ou plateia sem geometria própria não é promovida a crop seguro; segue para `SOURCE_FIT_BLUR`, com revisão indicada. Isso não é homologação de seis novos reconhecedores ou seis renderizadores.

O contrato preserva Director IDs, cenas, crops, keyframes normalizados e timestamps absolutos. Separa foco proposto, geometria, preflight, movimento na timeline, recibo do transform renderizado, frames decodificados e confirmação em frames finais. `movement_confirmed_in_final_frames` permanece `null`; recibos técnicos não viram essa confirmação. `preview_approved=false` e `publish_ready=false` permanecem independentes da recomendação.

O contador também foi endurecido: `rendered_zoom_event_count` registra execução sustentada por recibos e checagens técnicas; `zoom_delivered_event_count` permanece zero e `zoom_delivery_verified=null` enquanto não houver medição conclusiva de movimento nos frames finais. O contrato é `r6_final_frame_motion_evidence_required`. A fixture de fonte uniforme é um contraexemplo concreto: um crop animado foi renderizado e decodificado, mas todos os pixels uniformes continuam sem movimento visual demonstrável. O teste agora espera `rendered=1` e `delivered=0`, em vez de confundir os dois.

## Verificação executada e limitações

Primeira tentativa: `python -m pytest ...` falhou antes da coleta porque o Python global não tem pytest. Nenhuma dependência foi instalada; o ambiente já existente `.venv` foi usado.

Comando focado final antes da adição do schema:

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r6_camera_performer_handoff.py src/tests/test_stage32_safe_camera.py src/tests/test_stage50_visual_review.py src/tests/test_s6_camera_director_smart_zoom.py src/tests/test_r51_story_visual_handoff.py src/tests/test_v44_social_output.py
```

Resultado final, incluindo schema compartilhado e distinção estrita de entrega: **116 passed in 3.41s**. Uma execução intermediária expôs 25 falhas no guard legado de Stories, que exige `preview_approved=false` recursivamente; o novo handoff foi ajustado para esse contrato e a mesma seleção passou integralmente. Não são testes de acurácia no show.

Verificação adicional de replay/schema: `.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r6_camera_performer_handoff.py src/tests/test_r51_semantic_replay.py src/tests/test_r51_privacy_schema.py src/tests/test_r51_embedded_schema.py` → **65 passed in 1.90s**. Segundo olhar na integração de export executou `test_r51_semantic_package.py` e `test_r6_caption_handoff.py`: **1 failed, 49 passed in 8.12s**, expondo incompatibilidade entre o índice master R6 e a derivação de pacote semântico (índice da revisão original não cobre os novos artefatos/schemas). A falha foi comunicada ao responsável por exportação e ao agente principal para correção; não foi omitida nem tratada como teste aprovado.

Pendente de homologação autorizada no Windows: render curto e inspecionado do trecho 1143,5–1149,5, comparação entre fonte/crop/render final no Curator, crop de cabeça/mãos/instrumento, blur amplo, overlays e áudio musical original. Não executar isso automaticamente nem promover `PARTIAL` para aprovação de preview/publicação.
