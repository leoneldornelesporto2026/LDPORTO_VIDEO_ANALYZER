# R6.3 — baseline real e geometria compacta

Data: 17/10/2026. Inspeção por leitura dos artefatos e execução da simplificação matemática em RAM. Sem pipeline, inferência, download, decoder ou gravação de artefato volumoso neste escopo.

## Identidade e fontes

Pacote solicitado: `pacotes_para_enviar/SECOND_CURATION_READY_5d089e1825b3_20261017_020701_253736_8b80a1.zip`. SHA256 medido: `5e5af9a17897eb424972c4d722a818ce29ca1d75dfff5e2e96b525932872f0cb`. Tamanho 12.613.051 bytes = 12,028743 MiB; 173 membros; 116.119.475 bytes descompactados.

`source/metadata.json` informa fonte **local**, `original.mp4`, sem ID YouTube/título: SHA256 completo `5d089e1825b396dafd6b5918274f3a785eb2d8be2f622497cb7d06fdd7b3b7ea`, 5.840,094 s, 1920×1080, FPS 24,000001369843545. A análise atual correspondente é `analysis/video_da9542291a6b`; seu `second_curation_export.json` aponta exatamente ao pacote e SHA acima. O dossiê externo solicitado possui o mesmo hash de pacote e fonte, com `video_id=null` e título genérico `Projeto audiovisual`.

O manifesto existente `C:/Users/leone/Videos/LDPORTO_MEDIA_LIBRARY/9UCGZia2p1k/media_manifest.json` registra explicitamente `video_id=9UCGZia2p1k` ligado ao mesmo SHA256 completo, 2.663.231.970 bytes, VP9/Opus, 1920×1080 e duração 5.840,094 s. A análise anterior `video_8adc6609911a` também liga esse ID ao mesmo hash. Esses registros fornecem proveniência para o vínculo; o prefixo no nome do ZIP não é prova de identidade. Não se usa o título para nomear artistas/rostos.

## Contagens e lacunas medidas

| Item | Medida |
|---|---:|
| Cenas / IDs únicos | 2.045 / 2.045 |
| Shots / IDs únicos | 2.045 / 2.045 |
| União temporal das cenas e shots | 5.840,094 s, 100% da fonte |
| Tipos de shot | unknown 672; medium 295; group 465; two_shot 498; wide 51; medium_close_up 40; close_up 24 |
| Observações brutas projetadas no pacote | 63.989 |
| Faces / corpos espacialmente observados | 33.116 / 56.408 |
| Tracklets / micro-tracklets / sem embedding | 10.458 / 6.804 / 6.374 |
| IDs persistentes | 3.580: 3.501 somente dentro de track; 79 com suporte entre tracks |
| Observações com `person_id=null` | 17.663; tracks mantidos anônimos |
| Instrumentos estruturados | 0; ausência de medição, não instrumentos ausentes do show |
| Segmentos canônicos / palavras canônicas locais | 386 / 2.614 |
| Segmentos / palavras no ZIP anterior | 386 / 2.382 |
| Palavras canônicas fora de `relevant_words.jsonl` | **232**, precisam ser recuperadas de `words.json` na R6.3 |
| União temporal dos segmentos | 988,010 s = 16,917707% da fonte |
| União temporal das palavras locais / palavras no ZIP | 958,460 s / 881,180 s |
| Palavras com `alignment_verified=true` / `audio_verified=true` | 0 / 0 |
| Candidatos Reel | 70 IDs únicos |
| Estados de legenda | 68 `ALIGNMENT_REVIEW_REQUIRED`; 2 `AUDIO_REVIEW_REQUIRED` |
| Unidades narrativas / propostas de sequência | 86 / 49 |
| Sequências `complete_supported=true` | 0 |
| Story independente do manifesto social | 1 |
| Grafo narrativo | 151 nós / 124 arestas |
| Timeline do Camera Director | 4.042 segmentos, 8.407 keyframes; 3.910 full_frame / 132 single_person |
| Imagens no ZIP anterior | 12 folhas de contato JPEG; não é um atlas global de 2.045 cenas |

Contagem de cenas cobre o domínio temporal do índice. Ela não significa que há uma imagem ou medição espacial para cada instante. Acurácia nominal e calibração probabilística de identidade não foram medidas.

## Implementação

Novo módulo `src/ldporto/compact_geometry.py`, API:

```python
simplify_visual_trajectories(observations, shots, *,
    source_width, source_height, max_error_px=2., max_gap_s=1.)
```

A API consome o contrato existente de `people/person_appearances.json`. Produz `trajectories`, `statistics`, `coordinate_contract`, `gaps` e observações sem geometria/timestamp válidos explicitadas. Cada face e corpo conserva um alvo espacial independente, inclusive quando o Director escolheu preservar a fonte. Nenhum motor de câmera, identidade, instrumento ou rosto é executado.

A simplificação temporal usa interpolação linear de bbox e RDP em pixel de fonte. O erro L∞ é conferido contra **todas** as amostras originais nas coordenadas x, y, width, height e também nas bordas direita/inferior; assim a soma de erros de x+width não excede silenciosamente o limite. Preserva início/fim, extremos que ultrapassam o envelope dos endpoints por mais que o erro configurado e excursões rápidas que excedem o limite.

Precisamente, para cada timestamp original `t`, `b=(x,y,w,h)` é o bbox original e `b̂` é a interpolação linear em tempo dos keyframes retidos adjacentes. Com fonte `W×H`, o erro é o máximo de `W·|x−x̂|`, `H·|y−ŷ|`, `W·|w−ŵ|`, `H·|h−ĥ|`, `W·|(x+w)−(x̂+ŵ)|` e `H·|(y+h)−(ŷ+ĥ)|`. O maior valor em todas as amostras de cada trajetória é registrado em `max_measured_error_px`; o máximo global está em `statistics.measured_max_error_px`. Trata-se de erro matemático de representação dos bboxes observados, sem medir a acurácia do detector ou provar segurança de crop entre observações.

Partições incluem pessoa persistente, track, posição do shot e classe. Pessoa desconhecida permanece `person_id=null`, separada por track. Mudanças de track, cortes, falta de referência de shot e gaps maiores que a configuração não são interpolados. A posição do shot também impede fusão se rótulos upstream estiverem repetidos ou ausentes. Timestamps simultâneos contraditórios são separados e sinalizados.

Um singleton tem `start=end` no instante observado. O campo `end` é o último timestamp observado, inclusivo; não é uma declaração de visibilidade contínua nem de duração de um frame. Os intervalos dos shots são end-exclusive. Ocultação e identidade nominal sem evidência permanecem desconhecidas. Flags de aprovação/publicação são falsas.

## Ensaio real em RAM

As 63.989 aparições geraram 89.524 amostras espaciais em 16.720 trajetórias: 9.768 de corpo/pessoa, 6.952 de face, 4.990 singletons e 510 gaps. Todos os 10.458 track IDs e 3.580 person IDs foram preservados. Não houve bbox inválida, amostra sem shot, divergência de scene label ou correção numérica de borda neste snapshot. Todas as amostras espaciais foram contabilizadas e nenhum span atravessou um corte.

| Limite configurado | Keyframes retidos | Remoção de amostras | Maior erro medido | JSON compacto | Deflate nível 6, em RAM |
|---|---:|---:|---:|---:|---:|
| 2 px | 88.490 | 1,154998% | 1,999924485 px | 36.878.216 bytes | 6.618.128 bytes |
| 4 px | 85.062 | 4,984138% | 3,999634752 px | 36.039.878 bytes | 6.434.340 bytes |
| 8 px | 76.470 | 14,581565% | 7,999328613 px | 33.917.191 bytes | 5.951.731 bytes |

O default permanece **2 px**. Os valores 4 e 8 px foram apenas comparações matemáticas explícitas, não novos perfis aprovados. A redução temporal modesta é uma limitação real de tracks curtos/jitter; não se removem movimentos essenciais para simular compactação. A estrutura menor usa campos focados, não omissão de alvos. A etapa principal controla deduplicação de frames e tamanho final do ZIP.

Comando de testes: `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_r63_compact_geometry.py src/tests/test_r62_camera_target_states.py src/tests/test_r62_curator_adapter.py` — **32 passaram em 0,16 s**, incluindo 17 casos novos de geometria compacta. Testes cobrem erro temporal com tempos irregulares, cortes, gaps, alvos desconhecidos, fontes sem IDs, bordas do bbox, dados inválidos, singleton, imutabilidade e nenhuma aprovação. Esses testes não homologam crops ou zoom em MP4.

## Export e leitura independente — escopo dos testes

`src/tests/test_r63_compact_handoff.py` executa o exporter e o reader reais sobre um parent ZIP íntegro e artefatos canônicos locais sintéticos. Os JPEGs reais da fixture contêm o rótulo `SYNTHETIC TEST`; não são frames do show. O PDF é produzido pelo writer real e seu texto é extraído para verificar Unicode, IDs e trechos literais. A fixture contém quatro cenas, um Reel, unidades narrativas e um Story independente, além de palavras e segmentos canônicos que estavam fora do subset relevante do parent ZIP.

A execução dos nove casos integrais, já com armazenamento em shards, passou em **16,40 s**. O teste força shards com até duas trajetórias, reconstrói todos os índices e toda a transcrição canônica, e resolve a geometria de uma única peça lendo seu `camera_geometry_ref` e `trajectory_shard_refs`, sem abrir o arquivo global de coordenadas. Verifica também que uma pessoa vista aos 25 s e outra vista exatamente aos 90 s não aparecem na presença medida de um Reel `[30,90)`, embora permaneçam nos índices das cenas correspondentes. Um mesmo track observado a 59,999 s e exatamente no corte de 60 s conserva dois singletons em shots diferentes.

Na revisão foram acrescentadas regressões para o limite exato de bytes do shard (incluindo o envelope JSON e a exceção explícita de uma trajetória individual grande) e para conflito de dimensões entre metadata persistida e parent ZIP. Antes das correções, uma fixture configurada com 270 bytes produzia shard de 314 bytes contendo duas trajetórias; outra fixture com metadata persistida em 1280 pixels e parent em 1920 pixels era exportada sem rejeição. O producer passou a contabilizar o envelope JSON e a comparar dimensões, rotação e FPS entre as fontes. Nenhum teste foi alterado para aceitar o resultado incorreto.

Validação consolidada após as correções: `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_r63_compact_geometry.py src/tests/test_r63_compact_handoff.py src/tests/test_r62_camera_target_states.py src/tests/test_r62_curator_adapter.py` — **43 passaram em 15,41 s**: 17 de geometria, 11 de export/ZIP/PDF e 15 de estados de alvo/adaptação Curator. O resultado valida os contratos e fixtures locais descritos, sem atribuir esses resultados sintéticos à inspeção visual de MP4 do show.

Uma cena representada por still mantém o intervalo no índice, mas a imagem prova somente um timestamp. A proporção de duração dos intervalos com ao menos um still, a proporção de cenas com imagem, a proporção de Reels com geometria e o erro de simplificação são medidas diferentes. Percentuais como 95% ou 100% de indexação/representação por still não demonstram visibilidade contínua, integridade de mãos/instrumentos nem homologação do enquadramento de cada peça. A completude real deve ser reportada pelos denominadores próprios: 2.045 cenas, 70 Reels e 87 partes de Story esperadas neste snapshot (86 unidades narrativas e uma parte independente).
