# Export visual completo — causa e baseline de leitura

Inspeção em 19/10/2026, sobre HEAD `fb78b717ebf45134e1c9a94a27abcd1a579cc090`. Escopo deste relatório: leitura de código, JSONs, nomes e hashes de imagens existentes, integridade do ZIP e identidade do original. Nenhuma inferência, análise de áudio, detecção de cenas, timeline de câmera, render ou download foi executado nesta investigação.

## Caso real e identidade

- Análise: `analysis/video_d96cd4328fd5`.
- Fonte: `pc6SR_Fvdt0`, título registrado `O OCULTO - O FILME | FREE FIRE BRASIL`.
- SHA256 completo da fonte: `c264fbfd714743f2f716f3b84a9416b8e0b6a2f48a350f5375fa224208565592`.
- Original existente: `input/youtube/pc6SR_Fvdt0/pc6SR_Fvdt0.mp4`, 8.742.196 bytes. O hash dos bytes corresponde ao `download.json`, `analysis_summary.json`, `manifest.json` da análise e `source/metadata.json` do ZIP. O arquivo foi apenas lido para calcular hash.
- Duração registrada: **66,194 s**, 1920×1080, 30 FPS, AV1/Opus, referência temporal absoluta `[start,end)`.
- Run ID: `c264fbfd714743f2`; `analysis_status=partial`; gate editorial `P1_DEGRADED`. Não há aprovação de preview/publicação.
- ZIP de referência: `pacotes_para_enviar/SECOND_CURATION_PARTIAL_pc6SR_Fvdt0_20261019_032257_115420_b77577.zip`.
- ZIP: **542.612 bytes**, 99 membros, SHA256 `23100dce16ca1f1fb9b8e6a8210884d714aa2fc292f794f68b5a7dedf50b51fb`; `ZipFile.testzip()` retornou `None`.

| Medida observada | Baseline |
|---|---:|
| Cenas em `scenes.json` | **40** |
| Shots em `shots.json` | **40** |
| Início / fim do catálogo | 0 / 66,194 s |
| União dos intervalos do catálogo | **66,194 s**, sem lacunas |
| Momentos em `main_moments.json` e candidatos no ZIP | **4** |
| Shortlist automática | **0** |
| Contact sheets em `visuals/` | **4** |
| Imagens de cena em `visuals_all/` no ZIP original | **0** |
| Catálogo de cenas/shots dentro do ZIP original | **ausente** |
| Thumbnails de cenas existentes na análise | **40** |
| Amostras já medidas em `video_analysis.frame_samples` | **506** |
| Microjanelas de até 3 s obtidas das cenas atuais | **46** |

As 46 microjanelas são uma contagem matemática de planejamento: `sum(ceil((end-start)/3))`, sem acrescentar detecção de mudanças internas. Não é uma contagem de capturas novas já produzidas.

`scenes.json` tem SHA256 `056dda1582e4239816e215adfc9a2a631217dbb3ed835fb28fd6924f613c92fb` e `shots.json`, `740af3cc5760edecf1c0ebc0fdcc3e6a009342750f64416865bf6b3b25902aac`; ambos correspondem ao ledger da análise.

## Caminho existente e filtro exato

1. `scenes.py:SceneEngine` produz o catálogo de cenas com o detector existente; conserva a cauda até `metadata.duration`.
2. `vision.py` grava `thumbnails/SCENE_....jpg` ao encontrar uma cena ainda sem thumbnail, sujeito ao limite técnico `max_thumbnails`. Esta etapa pertence à análise existente e não deve ser reexecutada para o novo export.
3. `pipeline.enrich_scenes()` liga a primeira thumbnail `reason=scene_start` ao campo `scene.keyframe`.
4. `reports.py` chama `build_core_package(isolated, ctx.video, ...)` na etapa final de exportação.
5. `second_curation_export.build_core_package()` gera imagens a partir do catálogo de **candidatos**, e não do catálogo de cenas. O bloco `selected_visuals` usa `shortlist[:second_curation_visual_candidate_limit]` (default 16) e completa a lista até `min(12, len(candidates), visual_limit)` com candidatos fora da shortlist.
6. Dentro do loop de candidatos, somente `candidate_id in selected_visuals` recebe `build_contact_sheet()` quando não há reutilização de imagem verificada. O caminho gerado é `visuals/<candidate_id>/contact_sheet.jpg`.
7. Ao final, `_write_handoff_master()`, a lista `manifest.files`, `SECOND_CURATION_MANIFEST.json` e o ZIP são montados sobre os arquivos efetivamente existentes na árvore temporária. Não existe uma varredura independente do catálogo completo de cenas para acrescentar imagens.

Portanto, **não há um Top 4 fixo**. Quatro é o número total de momentos deste caso; a shortlist vazia recebe o preenchimento visual e os quatro ganham imagem. As 40 cenas completas continuam fora do domínio desse gerador. Retirar somente o limite de candidatos não resolveria a falta de cenas que não viraram momentos.

`generate_visuals_on_demand()` também trabalha com IDs de candidatos solicitados. O export de dossiê em `project_export.py` consome essas imagens existentes. O fluxo opcional `compact_handoff.py`/`compact_frames.py` constitui outro contrato; sua presença no repositório não altera o conteúdo do `SECOND_CURATION_PARTIAL` inspecionado.

## Timestamp repetido: causa reproduzível sem decoder

`preview_renderer.build_contact_sheet()` calcula as frações `[0, .25, .5, .75, .99]` e depois acrescenta o midpoint de um zoom ou o midpoint do candidato. Não ordena nem deduplica essa lista. Sem zoom, a sexta posição repete a terceira e volta no tempo.

O próprio JSON de `MOMENT_00000_0003`, intervalo `[39.65,41.19)`, registra:

```text
39.650, 40.035, 40.420, 40.805, 41.1746, 40.420
```

Todos os quatro candidatos deste ZIP apresentam o mesmo padrão de repetição do midpoint. Isso explica precisamente o `00:00:40.420` repetido da referência. Os rótulos são construídos a partir do timestamp solicitado antes do seek; o gerador não registra PTS real do frame decodificado. Essa é uma limitação adicional de proveniência temporal, distinta da ordenação.

O layout atual é 3×2, 960×412, com tiles ajustadas preservando proporção. Quando há direção válida, tiles posteriores à primeira podem receber crop do Director. O catálogo cronológico completo precisa usar a fonte preservada; não deve depender da seleção nem de alterações na timeline de câmera.

## Reutilização de cache: evidência disponível

Todas as 40 `scene.keyframe` existem. O timestamp arredondado no nome de cada imagem encontra exatamente uma entrada de `video_analysis.frame_samples` na mesma cena, com diferença menor que 0,00051 s. Exemplo final: nome `61.867`, amostra existente `61.86666666666667`.

O ledger `manifest.artifact_checksums` tem 64 entradas de artefatos e **não registra os JPEGs de thumbnails**. Ausência de registro não significa checksum divergente nem prova de corrupção; também não equivale a integridade histórica comprovada. Para reutilizar, registrar o hash atual, a associação existente cena/amostra e a limitação de PTS; quando a política exigir PTS comprovado, extrair somente as capturas faltantes/sem prova necessária. Não assumir que o número arredondado do nome é um PTS exato.

Uma thumbnail por cena é insuficiente para todos os requisitos de microjanelas, sobretudo nas seis cenas com mais de 3 s. As capturas ausentes podem ser obtidas em export incremental, sem chamar qualquer modelo ou reconstruir a análise.

## Superfície mínima sugerida e riscos de regressão

| Arquivo/área | Mudança localizada sugerida | Risco a verificar |
|---|---|---|
| Novo helper de export visual de cenas | Percorrer todas as cenas, criar microjanelas `[start,end)`, registrar fallback para lacunas, reutilizar capturas e extrair somente faltantes | O limite técnico de memória/pacote não pode virar corte editorial ou omissão silenciosa |
| `second_curation_export.py` | Chamar o helper antes do inventário final; acrescentar índice, atlas, arquivos e referências de pacotes ao manifesto | Preservar os quatro candidatos, os caminhos `visuals/`, gates e semântica de readiness editorial; recalcular inventários/hashes na ordem correta |
| `preview_renderer.py`, somente contato | Ordenar e deduplicar tempos reais, preservar proporção e distinguir seek solicitado de PTS efetivo | Não modificar render de previews ou equações/decisões de câmera |
| Novo writer de atlas, reaproveitando PDF existente | Gerar PDF a partir das contact sheets já exportadas e dividir por intervalo quando necessário | Não abrir novamente o original; manter IDs, timestamps e leitura compacta |
| Comando de reexportação existente ou wrapper pequeno | Carregar análise persistida e fonte por SHA; retomar apenas export visual | Não chamar `Pipeline.run`, ASR, diarização, faces, semântica, câmera ou download |
| Testes de export/readiness existentes | Conservar assertions de candidatos/visuais antigos e acrescentar cenas, microjanelas, PTS, retomada e pacotes | `visual_count` legado não deve ser redefinido como número de cenas; estado `COMPLETE` visual não equivale a aprovação editorial |

Testes existentes relevantes: `test_v43_handoff.py`, `test_v44_second_curation.py`, `test_stage04_readiness.py`, `test_s2_pipeline_integrity.py` e `test_v48_r4_homologation.py`. São pontos para regressão; esta investigação não os executou nem atribui aprovação aos novos artefatos.

## Verificações executadas neste escopo

- `git rev-parse HEAD`: baseline acima.
- Leitura UTF-8 do pedido anexado, dos módulos citados e dos JSONs persistidos.
- `hashlib.sha256` do ZIP, original, `scenes.json` e `shots.json`; comparação com os registros existentes.
- `zipfile.ZipFile.testzip()` e inventário de membros, candidatos e visuais.
- Comparação aritmética dos intervalos das 40 cenas e contagem das 46 microjanelas previstas.
- Existência das 40 thumbnails e associação com as amostras já persistidas; nenhuma extração/alteração de imagem realizada.

Na fase de investigação, o único arquivo escrito foi este relatório leve. A execução e validação do novo catálogo `visuals_all` pertencem ao exportador adicional e à sua homologação.

## Correção autorizada do contact sheet legado

Após a investigação, foi autorizada a alteração localizada de `src/ldporto/preview_renderer.py`, somente em `build_contact_sheet()` e no novo helper `decode_source_frame()`, e a criação de `src/tests/test_contact_sheet_chronology.py`. A assinatura pública, o layout 960×412, as seis posições e `source_and_director_framing` permanecem. Nenhuma função de render de preview, regra de câmera ou modelo foi alterada.

O helper retorna o frame e `{source_time_s, source_frame_index, timestamp_provenance, requested_source_time_s}`. `source_time_s` vem do timestamp informado pelo decoder OpenCV; não é substituído pelo pedido de seek nem por frame/FPS. Um `POS_MSEC=0` fora do primeiro frame não comprova um timestamp. Quando o decoder não informa tempo, o valor é `null`, a proveniência é `unavailable` e o rótulo da imagem diz `PTS unavailable`.

As seis propostas normais usam frações distintas `[0,.125,.25,.5,.75,.99]`. O centro de zoom pode substituir uma proposta interna, sem acrescentar um sétimo slot. Após o decode, os frames são ordenados pelo timestamp efetivo. Frames com o mesmo índice ou PTS são deduplicados; pequenas tentativas adicionais, limitadas, preenchem somente slots ausentes. Tempos efetivos fora do intervalo da peça/fonte são rejeitados. Se não houver seis frames distintos ou faltar timestamp, o resultado é explicitamente `partial`, com motivo e espaços ausentes sinalizados; não se repete um frame para simular seis evidências.

Pixels iguais em PTS distintos podem representar fonte estática/congelada; são preservados e assinalados com `duplicate_content`, `duplicate_content_of_slot` e contagem, sem declarar cópias como imagens diferentes por acidente. No máximo seis pares pequenos de tiles fonte/Director ficam retidos em memória. Os quatro JPEGs do ZIP original não são alterados por esta implementação.

### Proveniência dos tempos do cache da análise

Em `vision.py`, após `cap.grab()`, o tempo vem de `CAP_PROP_POS_MSEC/1000`; quando esse valor é não positivo fora do início, o código usa `frame_index/fps`. A amostra grava `time`, `frame` e `scene_id`, e a thumbnail usa o mesmo frame/tempo, arredondando somente o nome para três casas. Portanto, a associação única nome→amostra recupera o tempo armazenado com mais precisão, mas o registro antigo não permite distinguir PTS de fallback por frame. A reutilização deve declarar essa proveniência limitada, sem afirmar verificação independente de PTS.

### Testes executados da correção

1. `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_contact_sheet_chronology.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py` — **24 passaram em 7,49 s**, na primeira revisão.
2. `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_contact_sheet_chronology.py src/tests/test_v43_handoff.py src/tests/test_v44_second_curation.py src/tests/test_stage04_readiness.py src/tests/test_s2_pipeline_integrity.py src/tests/test_v48_r4_homologation.py src/tests/test_stage64_curation_recovery.py` — **107 passaram, 1 pulou em 54,90 s**. O skip corresponde à ausência de privilégio de symlink no Windows (`test_stage64_curation_recovery.py`).
3. Após proteger a leitura de propriedades de timestamp não suportadas sem descartar pixels decodificados, `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_contact_sheet_chronology.py` — **14 passaram em 0,40 s**, sobre a revisão final do helper.

Os testes novos cobrem o intervalo concreto 39,65–41,19 s com decoder sintético explicitamente declarado; ordenação após decode; diferença entre tempo solicitado e informado; limite end-exclusive; falta de PTS; duplicação de frame; conteúdo estático em PTS distintos; limites da fonte; centro de zoom; intervalo inválido; propriedade não suportada; rótulos e layout. Um teste faz roundtrip real de uma mídia MJPG minúscula sintética. As suítes antigas também exercitam exportação/on-demand e os gates vigentes. Esses resultados não constituem prova de que o novo pacote completo do vídeo real já foi produzido.
