# Homologação visual real R6.2 — 16/10/2026

Estado: **PARTIAL / aguardando revisão humana**. Sete MP4s técnicos foram gerados pelo grafo real do Curator em 1080×1920, CPU libx264: cinco casos exigidos com fonte preservada, um ensaio adicional de Smart Zoom real e seu fallback após reprovação por corte de gesto. O zoom digital foi observado nos pixels; o crop desse ensaio foi reprovado. Nenhuma aprovação editorial foi criada.

## Fonte e execução

- Fonte original, somente leitura: `input/youtube/9UCGZia2p1k/9UCGZia2p1k.mp4`.
- SHA256 confirmado no checkpoint A: `5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea`.
- Fonte: VP9, 1920×1080, 24 fps, áudio Opus, duração 5840,094 s, 2.663.231.970 bytes.
- Render reutilizado: `LDPORTO_VIDEO_CURATOR/ldporto_curator/render.py::_base_cmd`, o mesmo grafo usado por `render_clip`; `validate_output` real também foi executado. O Curator não foi alterado.
- Driver: `camera_samples/build_real_previews.py`. Não cria fila, aprovação ou projeto Curator e usa uma revisão inédita por render.
- Encoder explicitamente CPU, duas threads, FFmpeg `-n`. Sem GPU, Ollama, ASR, downloads ou processamento integral do show.
- Legendas/títulos foram omitidos para isolar a câmera. Não há alegação de legenda pronta nem de safe area de overlay homologada. O áudio original dos intervalos foi reutilizado, com os filtros reais de áudio do Curator.

## Cinco casos exigidos

Todos os caminhos abaixo são relativos a `camera_samples/`; `preview_approved=false` e `publish_ready=false` em todos os recibos.

| Caso | Fonte absoluta, s [início,fim) | MP4 real | Frames | Decodificação integral | Avaliação |
|---|---|---|---:|---|---|
| Pessoa isolada | [113,75;116,75) | `01_isolated/engine_r62/TECHNICAL_PREVIEW.mp4` | 72 | PASS | Fonte preservada. Crop central fixo reprovado: pessoa e microfone saem lateralmente do crop no fim. |
| Pessoa com guitarra | [156,25;158,25) | `02_guitar/engine_r62/TECHNICAL_PREVIEW.mp4` | 48 | PASS | Guitarra, cabeça e mãos mantidas na fonte inteira. Crop vertical reprovado: corta braço/headstock do instrumento. Nenhum solo musical foi afirmado. |
| Banda completa | [139,75;144,75) | `03_full_band/engine_r62/TECHNICAL_PREVIEW.mp4` | 120 | PASS | Plano amplo preservado. Crop central excluiria músicos laterais. Zoom/cortes da câmera original não são Smart Zoom. |
| Dupla/mudança de composição | [105,75;109,75) | `04_duo/engine_r62/TECHNICAL_PREVIEW.mp4` | 96 | PASS | Dois participantes e ação compartilhada preservados. Crop central demonstrativo corta um sujeito e parte do outro. |
| Luz difícil/corte de fonte | [174,25;176,75) | `05_difficult_light/engine_r62/TECHNICAL_PREVIEW.mp4` | 60 | PASS | Close roxo do público seguido por palco amplo. O topo da cabeça já está cortado na fonte; o fallback não acrescenta corte. Crop de rosto reprovado. |

O replay real `camera_replay_r62/timeline.json` e `build_camera_handoff` produziram SOURCE_FIT_BLUR nesses cinco intervalos. O driver preservou esse resultado e não forçou um foco para aumentar contagens. Spans idênticos do fallback foram unidos na adaptação, sem alterar a composição. O JSON `analyzer_camera_handoff_r62.json` de cada caso retém todos os spans originais e sua proveniência.

## Evidência por caso

Cada pasta contém `SOURCE_EXCERPT.mp4` e seu recibo com tempos/hash/ffprobe. A subpasta `engine_r62/` contém:

- `camera_plan_consumed.json`, `clip_consumed.json` e `renderer_identity.json`;
- `render_command_original.json`, `render_command_result.json` e `render_integrity.json`;
- `source_00..02.png`, `final_00..02.png`, `rejected_center_crop_00..02.png` e `comparison_00..02.jpg`;
- `crop_proposal_review.json`, `frame_capture_commands.json` e `frame_transform_verification.json`.

As imagens de crop central são propostas geométricas **rejeitadas**, não caixas detectadas nem planos aprovados. O JSON registra essa distinção. O foreground nítido final ocupa 1080×608 px, aproximadamente y=656..1264 na tela 1080×1920; regiões de legenda e título permanecem UNVERIFIED.

Foi feita inspeção visual com `view_image` dos quinze frames de fonte, dos comparativos intermediários dos cinco renders, do frame final do caso isolado e do primeiro frame difícil. O caso isolado mostra claramente que o crop central perde o rosto no fim; o caso difícil mostra o corte de cabeça herdado da fonte. Guitarras e microfones são observações visuais destes frames; nomes de pessoas, canto, palavras e solo não foram inferidos.

## Verificação fonte → pixels finais

`camera_samples/verify_real_previews.py` compara cada frame original ao foreground nítido do frame decodificado do MP4. Usa SIFT, razão 0,72, homografia RANSAC com limiar de 2 px, mínimo de vinte inliers, erro mediano <1,5 px e escala isotrópica dentro de 2%. Não usa `motion=1`, movimentos entre frames de fonte ou o zoom comandado como prova.

- Quinze de quinze pares foram MEASURED.
- Inliers por par: 218 a 1.500.
- Erro mediano de reprojeção por par: 0,1520 a 0,4228 px.
- Escala medida próxima a 0,5625, compatível com a fonte 1920 px ajustada ao foreground de 1080 px.
- Controle negativo com frame liso: ABSTAIN / INSUFFICIENT_FEATURES. Sem textura suficiente, o verificador não inventa transformação.
- Decodificação completa dos cinco MP4s: cinco PASS, zero erros FFmpeg. Comandos e saídas reais em `camera_samples/FULL_DECODE_CHECK.json`.

Essas medições verificam geometria nos frames amostrados. Não certificam identidade, alinhamento de palavras, todas as poses/mãos ao longo do clipe ou aprovação editorial. Índices de frame foram calculados nominalmente pelos 24 fps e são identificados como não certificados por PTS original exato.

Índice dos cinco renders, hashes completos, dimensões, durações e métricas: `camera_samples/FIVE_SAMPLE_RENDER_INDEX.json`.

## Ensaio adicional: Smart Zoom real, composição reprovada

Fonte absoluta: `[1601,792;1607,792)` — evento completo de seis segundos, `PERSON_2629` apenas como ID visual, sem identidade nominal confirmada.

- Render de foco/zoom: `camera_samples/06_isolated_replanned/engine_r62_compat/TECHNICAL_PREVIEW.mp4`.
- Fallback após reprovação: `camera_samples/06_isolated_replanned/safe_fallback_review/TECHNICAL_PREVIEW.mp4`.
- Fonte curta: `camera_samples/06_isolated_replanned/SOURCE_EXCERPT.mp4`.

O plano veio de `camera_replay_r62_curator_compat/timeline.json`, replay offline do mesmo Camera Director com override explícito `smart_zoom.max_zoom_factor=1.04` para a envoltória instalada do Curator. Não houve clamp silencioso nem mudança dos gates de confiança, cabeça, crop e upscale. `curator_camera_adapter.build_curator_camera_plan` produziu onze segmentos nativos, mantendo keyframes de origem e erro de aproximação no JSON. O driver chamou o `_base_cmd` real e registrou os comandos originais/executados. O plano original permanece imutável; a confirmação de execução fica em `camera_execution_receipt.json`.

Sete pares fonte→frame final foram medidos em 0, 1, 2, 3, 4, 5 e 5,9583 s. A homografia irrestrita mediu seis e absteve-se no último por anisotropia; o resultado foi preservado. Como o render instalado faz escala uniforme/crop, foi executado também o estimador de similaridade `estimateAffinePartial2D` com SIFT e RANSAC. Esse modelo evita extrapolar perspectiva a partir de rosto/mão em movimento.

| Tempo no MP4, s | Escala fonte→MP4 medida | Inliers | Erro mediano, px |
|---:|---:|---:|---:|
| 0 | 1,777668 | 396 | 0,3493 |
| 1 | 1,779878 | 370 | 0,3782 |
| 2 | 1,783502 | 363 | 0,3374 |
| 3 | 1,792633 | 314 | 0,4111 |
| 4 | 1,807014 | 298 | 0,4103 |
| 5 | 1,821939 | 303 | 0,3706 |
| 5,9583 | 1,833197 | 107 | 1,2300 |

As sete escalas são estritamente crescentes; aumento relativo medido de **3,1237%**. Isso é evidência da transformação digital aplicada pelo FFmpeg, independente do movimento da câmera original. O último par tem suporte mais fraco e a abstenção da homografia não foi ocultada. O controle negativo liso também retorna ABSTAIN no estimador de similaridade. A janela temporal é a pedida no comando; PTS exato de cada frame original não foi certificado. Foi feita busca diagnóstica de frames vizinhos no final, preservada em `end_frame_temporal_alignment_scan.json`; ela não substituiu silenciosamente a referência usada na medida publicada.

Foram vistos com `view_image` os frames finais 0, 3 e 5,9583 s e os frames originais das bordas. Cabeça, rosto e microfone permanecem íntegros. **O gesto de mão sai lateralmente do crop em 3 s e no final; a composição foi reprovada.** O Analyzer dispõe de geometria de rosto, insuficiente para declarar mãos e tronco protegidos. O fallback de seis segundos foi então renderizado em revisão separada, visto no comparativo final e medido em três pares fonte→MP4, todos MEASURED; ele preserva a mão.

Ambos os MP4s adicionais passaram pela decodificação integral e têm 144 frames, seis segundos e hashes em `camera_samples/06_isolated_replanned/FULL_DECODE_CHECK.json`. A cadeia real fica em `engine_r62_compat/SMART_ZOOM_EXECUTION_CHAIN.json`: proposed/keyframed/serialized/consumed/FFmpeg_applied são comprovados; transformação observada; `delivered=false` porque a composição foi reprovada. `preview_approved=false` e `publish_ready=false` continuam separados dessa constatação técnica.

Todos os sete renders, hashes e status: `camera_samples/ALL_RENDER_INDEX.json`. A inspeção visual não equivale a revisão editorial humana.

## Pendências e gates

O fallback foi executado e visto nos MP4s. Foco vertical para guitarra, dupla e cena de público fica reprovado nos crops demonstrados; será necessário preservar o aberto ou fornecer evidência espacial suficiente. A preservação de instrumentos não pode ser deduzida de uma caixa de rosto.

Smart Zoom foi aplicado e observado no ensaio adicional, mas a composição permanece reprovada por corte de gesto. Não se declara DELIVERED nem homologação editorial. O fallback revisável está disponível. Aprovação editorial e gates PREVIEW_APPROVED/PUBLISH_READY permanecem humanos. Títulos, legendas, safe areas de overlays e preservação de instrumento em foco vertical continuam sem homologação nestes ensaios de câmera.
