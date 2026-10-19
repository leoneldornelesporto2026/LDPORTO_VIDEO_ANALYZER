# Verificação independente do export visual completo

Escopo: somente exportação visual, testes sintéticos e inspeção dos resultados persistidos. Nenhum modelo, áudio, download, render de Reels/Stories ou pipeline foi executado por esta auditoria.

## Causa reproduzida e confirmada

`preview_renderer.build_contact_sheet` gerava as frações `[0, .25, .5, .75, .99]` e acrescentava novamente o ponto médio quando não existia janela de zoom. A sequência resultante repetia o ponto médio depois da captura final.

Uma chamada real dessa função sobre AVI **sintético** de 45 s, 80×60, 10 fps, candidato `[39.65, 41.19)`, produziu:

```json
[39.65, 40.035, 40.42, 40.805, 41.1746, 40.42]
```

O ZIP anterior `SECOND_CURATION_PARTIAL_pc6SR_Fvdt0_20261019_032257_115420_b77577.zip`, SHA-256 `23100dce16ca1f1fb9b8e6a8210884d714aa2fc292f794f68b5a7dedf50b51fb`, preserva exatamente essa sequência em `candidates/MOMENT_00000_0003.json`. Os quatro candidatos tinham um timestamp repetido no último item e ordem incorreta. Essa inspeção não abriu nem modificou a mídia original.

O catálogo `analysis/video_d96cd4328fd5/scenes.json` contém 40 cenas, `SCENE_00000` a `SCENE_00039`, concatenando `[0, 66.194)` sem lacunas ou sobreposições. Existem 40 keyframes persistidos, todos com imagem presente e timestamp arredondado do nome dentro da cena; essa proveniência de cache não certifica PTS independente. A subdivisão de cada cena em janelas de até 3 s requer no mínimo 46 microjanelas.

## Testes e descobertas

Arquivo de testes: `src/tests/test_visual_scenes_export.py`. Fixtures usam pixels e recibos de decodificação explicitamente sintéticos; não homologam imagens reais.

Comando principal:

```powershell
./.venv/Scripts/python.exe -m pytest src/tests/test_visual_scenes_export.py -q --junitxml=docs/reports/visual_all_20261019/visual_scenes_unit.junit.xml
```

Execução inicial: **26 passaram em 3,10 s**. Cobriu microjanelas, cenas descartadas pela curadoria, estado editorial degradado, lacunas representadas, limites em microssegundos, cortes internos, ordenação e deduplicação por PTS absoluto, limites `[start,end)`, timestamp desconhecido, estados COMPLETE/PARTIAL/FAILED e retomada sem novas capturas nem alterações de imagens válidas.

Após testes adicionais: **27 passaram e 3 falharam em 1,11 s**. As falhas expuseram:

1. Retomada aceitava cobertura antiga quando a duração persistida da fonte mudava de 6 para 7 s.
2. Validação aceitava `scene.contact_sheet` apontando para arquivo ausente.
3. Validação aceitava `frame.contact_sheet` apontando para arquivo ausente.

O teste de hash adulterado no cache passou: somente a captura com SHA inválido foi refeita, preservando os demais recibos.

Uma execução adicional de dois testes resultou em **1 passado e 1 falha em 0,47 s**. A falha demonstrou que um recibo com imagem válida e PTS desconhecido era reutilizado na retomada, impedindo uma nova tentativa com decodificador válido. O outro teste confirmou exportação completa das lacunas de fallback.

As quatro falhas foram corrigidas no módulo. A nova execução integral do comando principal resultou em **34 testes aprovados em 1,32 s**; o JUnit indicado acima contém o resultado final. Os testes comprovam a correção de cada falha reproduzida.

Também passaram os testes de associação de segmentos e palavras às cenas por sobreposição `[start,end)`, preservação literal de descrição existente e ausência de descrição inventada. Um teste utilizou o decodificador CPU real sobre AVI **sintético** de 2 s (20 frames, 160×90, 10 fps): as duas capturas possuíam PTS correspondente ao índice de frame, a fonte permaneceu idêntica em bytes e uma identidade SHA divergente foi rejeitada. Esse teste não usa a mídia do projeto nem representa homologação visual do vídeo real.

## Auditoria independente do pacote real

Resultado: **PASS**, registrado em `INDEPENDENT_REAL_ZIP_AUDIT.json`.

Pacote: `pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/DELIVERY_20261019T034553970556Z_ce0887/00_INICIAR_POR_AQUI.zip`.

SHA-256: `b7176f0789a6faa782e45ec6f5c81e4d9fc62d5abadf138f02badd9d9b82d589`; 2.190.634 bytes; 142 membros. A reabertura verificou CRC, inventário e bytes/SHA dos 141 arquivos listados no manifesto, além dos validadores do contrato vigente e do índice visual. Nenhuma referência visual, de segmento ou de palavra ficou pendente.

- As 40 cenas originais mantêm IDs e limites. As 46 microjanelas cobrem `[0, 66194)` ms, sem lacunas, com 92 capturas de PTS conhecido e nenhuma captura obrigatória ausente. São amostras representativas, sem alegação de análise contínua de todos os frames.
- Os quatro candidatos conservam IDs, caminhos e todos os campos editoriais; apenas `visual_metadata` e os quatro JPEGs derivados foram corrigidos na nova revisão. Cada um agora possui seis PTS distintos, ordenados e dentro do intervalo original. O ZIP anterior mantém o SHA original intacto.
- Os quatro JSONs de câmera permanecem idênticos em bytes. As 13 referências de segmentos e as 63 de palavras estão disponíveis; a palavra canônica `WORD_0000005`, ausente na seleção anterior, está incluída.
- O hash medido da mídia original permanece `c264fbfd714743f2f716f3b84a9416b8e0b6a2f48a350f5375fa224208565592`, igual à identidade declarada no pacote anterior e no novo.
- `VISUAL_SCENES_ATLAS.pdf`: 22 páginas, 1.318.353 bytes, SHA-256 `410ccbe48aec6e7cc96248dbe44ff1fcdd21bb84fdeafe3b5b45595f41aaf29c`.
- A exportação visual é `COMPLETE`; o estado editorial continua `partial`, e as aprovações permanecem falsas.

A inspeção com `view_image` cobriu as sheets reais `SCENE_00000`, `SCENE_00032`, `SCENE_00039` e o candidato corrigido `MOMENT_00000_0003`. As imagens mantêm proporção e rótulos legíveis em ordem. No candidato que apresentava `40.420` duplicado, os novos rótulos são `39.667`, `39.833`, `40.033`, `40.433`, `40.800` e `41.167` segundos. A revisão visual não atribuiu identidades nem acontecimentos novos ao conteúdo.
