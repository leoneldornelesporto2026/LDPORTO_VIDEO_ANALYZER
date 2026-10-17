# Visual Frame Handoff R6.2

Contrato aditivo implementado em `src/ldporto/visual_frame_handoff.py`, com JSON Schema em `schemas/visual_frame_handoff.schema.json`. Esta entrega adapta `camera_handoff.build_camera_handoff` e a interpolação de `preview_renderer._interpolate_keyframes`. Não executa detector, Re-ID, ASR, Camera Director novo, aprovação ou publicação.

## Identidade e revisão

Cada diretório novo contém um Reel ou uma parte de Story. `candidate_id` permanece o ID original para Reels; para partes é o `story_id` fornecido, mantendo `parent_candidate_id`. A revisão é explícita. SHA256 da fonte deve coincidir com os metadados; SHA256 do pacote de entrada tem campo separado, evitando ciclo de hash com um pacote de saída que conterá o handoff.

`SparseFrameProvider` verifica o SHA256 do arquivo uma vez ao abrir o decoder compartilhado. Quando há SHA esperado nos metadados, uma fonte diferente é rejeitada. Resolução decodificada incompatível com os metadados também é rejeitada. Um provider externo é uma fronteira de confiança do chamador; o integrador deve fornecer a identidade já verificada e capturas reais. Nenhuma imagem é marcada como capturada somente porque foi pedida.

Destinos existentes são rejeitados. Uma revisão é escrita em diretório temporário próprio, reaberta e validada antes da promoção para o destino final. Falha de schema, integridade, limite ou geometria não sobrescreve revisão anterior. O chamador mantém o manifest externo e as referências de rollback do pacote.

## Arquivos e adaptação aos contratos existentes

| Artefato | Conteúdo e origem |
| --- | --- |
| `frame_index.json` | Frames realmente gravados, SHA256, tempo absoluto/relativo, índice quando reportado pelo decoder, motivo de amostragem, resolução, proveniência e pedidos não atendidos. |
| `visual_tracks.json` | Observações selecionadas por intervalo em `people/person_appearances.json`, tracks separados por track/scene e referências ao FULL_AUDIT. Sem embeddings ou nomes inferidos. Instrumentos existentes com proveniência são preservados; ausência permanece `NOT_MEASURED`. |
| `safe_areas.json` | Pessoa/face e outras regiões efetivamente presentes nas observações, com projeção para o crop/saída propostos. Cada observação é uma amostra, sem interpolar presença. Zonas livres para título/legenda/CTA permanecem `unknown`. |
| `camera_keyframes.json` | Adaptação do camera handoff compartilhado, IDs de shot/diretor, intervalo, modo, alvos, crops, câmera fonte executável e keyframes derivados pelo interpolador existente. Render permanece `UNVERIFIED`. |
| `scene_transitions.json` | Fronteiras de shot da timeline canônica; iluminação, escala e oclusão não observadas não são inferidas. |
| `thumbnail_candidates.json` | Referências a imagens capturadas, hashes e tempos; score nulo e seleção `UNVERIFIED` até revisar blur, legibilidade e região de texto. |
| `contact_sheets/index.json` e `timeline.jpg` | JPEG real com miniaturas, tempos, IDs de shot e crop proposto em laranja. Sem frame disponível, índice informa `unavailable` e não cria contato fictício. |
| `selected_frames/*.jpg` | JPEGs esparsos reais, nomes determinísticos e hashes. Os originais não são alterados. |
| `storyboard.json` | Blocos por shot/intervalo, links de frames/keyframes e transcrição literal já existente no candidato. Ação não analisada, emoção e overlay não comprovados ficam nulos. |
| `visual_handoff_manifest.json` | Versão, revisão, identidades, coordenadas, fonte/alvo, arquivos/hashes, tamanho, cobertura de amostras, lacunas, dependências e gates. |

`person_id` e `track_id` são referências anônimas existentes. `visual_track_id` inclui fonte, revisão, track e cena; não afirma identidade civil, continuidade entre cortes ou que dois tracks pertencem à mesma pessoa. Cabeça completa/cabelo, boca, mãos, instrumentos e microfone não são derivados de uma face ou body box.

## Tempo e geometria

- A fonte usa segundos absolutos do original; intervalos são `end-exclusive`.
- Para spans descontínuos ordenados, `clip_time = soma(durações anteriores) + source_time - span.start`. Lacunas do original não viram mídia contínua nem observações intermediárias.
- Keyframes na fronteira final têm `at_end_exclusive_boundary=true`; não representam um frame capturado no instante excluído.
- Bboxes usam `x/y/width/height` normalizados em `[0,1]`, origem superior esquerda, referidos à fonte orientada. Resolução e rotação declaradas nos metadados; a orientação não é certificada por inferência deste módulo.
- Pixel fonte: `(x*W, y*H, width*W, height*H)`.
- Fonte para crop: `(source_xy-crop_xy)/crop_wh`; crop para saída: resize para `1080x1920`.
- Fonte preservada: escala uniforme `min(target_W/source_W, target_H/source_H)` e centralização. Esta é a geometria do foreground; fundo desfocado não cria evidência de área livre.
- A projeção usa exatamente o interpolador existente com center/zoom originais, inclusive clamp; não cria outro motor de movimento. Região cortada recebe estado `clipped_by_proposed_crop`/`outside_proposed_crop` e recomendação de fallback.
- Margens de plataforma, quando fornecidas pelo chamador, são configuração e não certificação. Na ausência permanecem desconhecidas. Não se concede uma safe zone com base em ausência de detecção.

O timestamp e o índice de frame do OpenCV são rotulados `opencv_decoder_reported`; `timestamp_independently_verified=false`. Se o decoder não reportar tempo plausível, há `seek_request_decode_timestamp_unavailable` e índice nulo. Estes frames servem à inspeção editorial e não homologam precisão frame a frame ou movimento no MP4 final.

## Amostragem e limites

O índice pesado de aparições é ordenado uma vez, acessado por `bisect`, e cada candidato recebe apenas suas observações. A timeline também é indexada; seu SHA é calculado uma vez por índice. Não se replica o arquivo de 61 MB em cada Reel.

Há propostas nas fronteiras dos intervalos/shots, mudanças de alvo, movimento/risco de crop e pontos de cobertura temporal. Primeiro/último anchor permanecem idênticos quando o orçamento aumenta. Extras são distribuídos no tempo e priorizados por risco. Eventos não escolhidos continuam descritos temporalmente em JSON; o manifest contabiliza amostragem omitida, sem fingir cobertura visual contínua.

Perfis padrão: `EDITORIAL_HANDOFF`: até 12 frames e 2 MiB por peça; `FULL_AUDIT`: até 48 frames e 12 MiB. Ambos podem ser limitados pelo integrador. O provider compartilhado limita 384 imagens distintas/40 MiB de JPEG em cache por padrão; uma captura em cache pode servir vários candidatos. O orçamento global esgotado vira pedido não atendido, sem fabricar frame. O integrador deve aquecer pelo menos os anchors de todas as peças antes de alocar extras. Este módulo não aumenta os limites de membros/bytes do ZIP canônico.

## API para o exportador

```python
index = VisualEvidenceIndex(analysis)
with SparseFrameProvider(media_path, metadata=analysis['metadata']) as provider:
    for piece in pieces:
        plan = plan_frame_times(analysis, piece, evidence_index=index, max_frames=2)
        for request in plan['requests']:
            provider.get(request['requested_source_time_s'])
    for piece in pieces:
        manifest = build_visual_frame_handoff(
            analysis, piece, destination_for(piece),
            source_sha256=source_sha256, package_sha256=input_package_sha256,
            revision=package_revision, evidence_index=index,
            frame_provider=provider, max_frames=6,
        )
        validation = validate_visual_frame_handoff(destination_for(piece))
```

Para Stories descontínuos, o chamador passa `intervals=[{'start': ..., 'end': ...}, ...]` tanto no prepass quanto no builder. Para uma parte contínua, `start/end` originais bastam. `media_path=` é conveniência para uma peça; batches devem compartilhar provider/índice. Os campos aceitam a análise em memória ou as chaves canônicas achatadas de um pacote, por exemplo `source/metadata.json` e `camera/camera_director_timeline.json`.

## Validação executada nesta implementação

Comando do conjunto focado/adjacente: `.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r62_visual_frame_handoff.py src/tests/test_r6_camera_performer_handoff.py src/tests/test_r51_story_visual_handoff.py`: **77 passed in 2.67s**, sendo 14 testes novos. Além de distinguir início recortado de corte real, os testes preservam `literal_text/source_segment_ids` de UNITs e a referência explícita à timeline R6.2. Estes testes usam fixtures sintéticas, incluindo AVI MJPEG pequeno criado exclusivamente no diretório temporário do teste; não alegam homologação do show.

O conjunto integrado `.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r62_visual_frame_handoff.py src/tests/test_r62_delivery_profiles.py src/tests/test_r62_project_export.py src/tests/test_r6_project_export.py src/tests/test_r6_camera_performer_handoff.py src/tests/test_r51_story_visual_handoff.py` passou com **99 passed in 29.64s**. Inclui dois ZIPs reais gerados a partir de dois Reels/um Story de fixture, integridade da cópia, schema, referência à câmera ativa, imagens JPEG nos PDFs, ausência de aprovação e rejeição de adulteração de JPEG/FULL. Os pixels desses testes são explicitamente sintéticos. Os sete testes negativos do verificador FULL inicialmente expuseram aceitação de flags/perfil/schema inválidos, ledger duplicado e `files=None`; o integrador corrigiu o verificador antes deste resultado.

`project_export.py` passou a copiar o EDITORIAL e o FULL uma única vez ao diretório da segunda curadoria, validar o irmão FULL por hash, copiar `MEDIA_REFERENCE.json` e cada VFH completo aos diretórios de Reels/Stories, incorporar os contatos aos PDFs e consumir a câmera ativa em vez do plano legado. Diagnósticos e recibos de validação acompanham o dossiê. O verificador conserva o nome legado e valida também o novo perfil e todas as árvores VFH. A aceitação R6.2 `PARTIAL` impede promover o dossiê a `READY_FOR_REVIEW` com base apenas nos gates legados.

A primeira execução dos testes novos teve 7 falhas/4 passes porque o contexto passado ao interpolador canônico não incluía `start`. A adaptação foi corrigida para fornecer esse campo; os resultados acima são posteriores à correção. Nenhum teste histórico foi apresentado como execução atual.

O smoke final do pacote mais recente percorreu os 70 candidatos originais: 70/70 contratos válidos, nenhum frame capturado (provider deliberadamente ausente), soma 25.850.763 bytes e máximo 1.455.845 bytes antes de JPEGs. Escopo, identidades SHA256, contagens e falhas constam em `VISUAL_HANDOFF_BASELINE_CONTRACT_SMOKE.json`. Foi uma validação estrutural dos dados reutilizados, não reprocessamento, homologação de MP4 ou declaração de que safe areas estão aprovadas.

O validador reabre JSONs, valida schema, identidade, SHA256/tamanho de cada arquivo, membros declarados, caminhos relativos sem traversal/symlink, tempos absolutos/relativos, intervalos e caixas normalizadas. Todos os manifests permanecem `PARTIAL`, com `review_required=true`, `preview_approved=false`, `publish_ready=false`. Integridade e testes não substituem revisão humana ou evidência de frames finais de um render.
