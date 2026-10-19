# Correção cirúrgica do export visual — entrega de 19/10/2026

A exportação visual agora usa o catálogo completo de cenas, independentemente de candidatos, shortlist ou score editorial. O caso real `pc6SR_Fvdt0` foi reexportado a partir da análise existente, com **40 de 40 cenas**, **46 microjanelas**, **92 capturas válidas em `visuals_all`** e representação temporal de **[0, 66.194 s)**. O ZIP derivado foi reaberto e validado, e as 22 páginas do PDF foram renderizadas pelo leitor nativo do Windows.

O estado visual é **COMPLETE**. A análise editorial continua **partial / P1_DEGRADED**; preview e publicação continuam sem aprovação. A cobertura representa cenas e amostras dentro de cada microjanela; não constitui análise de todos os frames.

## Causa comprovada

`second_curation_export.build_core_package()` escolhia `selected_visuals` a partir de `shortlist[:visual_limit]`, completando a seleção até `min(12, len(candidates), visual_limit)`. O único loop que produzia imagens percorria candidatos. O catálogo completo de `scenes.json` não entrava nesse caminho. Assim, o caso tinha 40 cenas persistidas, mas somente quatro contact sheets no pacote.

Em `preview_renderer.build_contact_sheet()`, cinco posições incluíam o ponto médio, e uma sexta posição acrescentava novamente esse ponto ou o centro do Smart Zoom. A lista não era ordenada nem deduplicada. A imagem conhecida tinha `40.420` repetido após `41.1746`. Os rótulos usavam o tempo solicitado ao seek, sem conferir o tempo efetivo reportado pelo decoder.

O relatório [CAUSE.md](CAUSE.md) registra as linhas e os dados observados antes da mudança. Seu escopo é a investigação inicial; as capturas novas e validações posteriores estão registradas neste relatório.

## Código efetivamente alterado

| Arquivo | Alteração |
|---|---|
| `analyze.py` | Rota `--reexport-all-scenes`, executada antes da configuração do pipeline. |
| `src/ldporto/second_curation_export.py` | Acrescenta o catálogo visual completo ao fluxo atual; inclui palavras fora de candidatos e valida referências globais, imagens e hashes no ZIP. |
| `src/ldporto/preview_renderer.py` | Confere timestamps reportados pelo decoder, ordena e deduplica capturas, respeita limites exclusivos e declara timestamp indisponível/repetição de conteúdo. O renderizador de previews não foi alterado. |
| `src/ldporto/visual_scenes_export.py` (novo) | Planeja microjanelas, representa lacunas como `FALLBACK_INTERVAL`, captura amostras ausentes, valida recibos/cache, gera índice, reexporta sem análise e mantém manifesto e partes cronológicas. |
| `src/ldporto/visual_scenes_atlas.py` (novo) | Gera atlas pesquisável a partir das imagens existentes, com transcrição literal disponível, hashes, retomada e divisão cronológica em dez minutos. |

Novos testes: `test_visual_scenes_export.py`, `test_visual_scenes_atlas.py`, `test_contact_sheet_chronology.py` e `test_visual_scenes_package_integration.py`, todos em `src/tests/`. Este diretório de relatório contém as evidências textuais, JUnit e o verificador de retomada real. O inventário com SHA256 dos fontes/testes está em [ARTIFACT_INDEX.json](ARTIFACT_INDEX.json).

As microjanelas preservam a identidade e os limites originais das cenas, incorporam limites internos de shots já persistidos e têm até três segundos. Cada uma precisa de pelo menos uma captura válida para cobertura integral; neste caso todas receberam duas. Os contact sheets mantêm o layout 960×412, com proporção preservada e páginas adicionais quando necessárias. Nenhum filtro editorial atua em `visuals_all`.

Descrições inexistentes continuam `null / NOT_ANALYZED`. Transcrições e palavras são referenciadas por IDs canônicos, sem nova análise de áudio. Timestamps absolutos mantêm precisão de microssegundos no JSON; o rótulo JPEG arredonda ao milissegundo. A origem temporal é `opencv_decoder_reported`, sem substituir PTS ausente por solicitação de seek ou frame/FPS.

## Caso real e resultado

| Medida verificada | Resultado |
|---|---:|
| Duração da fonte persistida e catálogo real | 66.194 s |
| Cenas originais / exportadas | 40 / 40 |
| Shots existentes reutilizados | 40 |
| Microjanelas / sem captura obrigatória | 46 / 0 |
| Capturas válidas em `visuals_all` | 92 |
| Contact sheets de cenas | 40 |
| Lacunas e sobreposições do catálogo | 0 / 0 |
| Intervalos fallback necessários neste caso | 0 |
| Intervalo representado | [0, 66194 ms) |
| Momentos anteriores preservados | 4 |
| Capturas nos quatro contact sheets corrigidos | 24, seis por momento |
| Segmentos / palavras entregues | 13 / 63 |
| Referências pendentes de segmento ou palavra | 0 |
| PDF | 22 páginas; 1.318.353 bytes |
| ZIP principal | 142 membros; 2.190.634 bytes |

A transcrição antiga tinha 62 palavras relacionadas aos candidatos. A palavra canônica `WORD_0000005`, já disponível na análise e fora desses intervalos, foi incluída para resolver a referência global. As 62 projeções antigas foram preservadas; nenhuma fala foi sintetizada.

Os quatro IDs e caminhos em `visuals/` foram preservados. As imagens foram corrigidas em uma nova revisão; campos editoriais, ranking, scores e os quatro artefatos de câmera permaneceram inalterados. O momento `MOMENT_00000_0003` agora apresenta os PTS **39.667, 39.833, 40.033, 40.433, 40.800 e 41.167 s**, em ordem e dentro de [39.65, 41.19). A auditoria independente registra os hashes anteriores e posteriores de cada imagem.

## Artefatos validados desta entrega

Raiz relativa ao projeto:

`pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/DELIVERY_20261019T034553970556Z_ce0887/`

- ZIP para enviar: `00_INICIAR_POR_AQUI.zip`.
- Índice: `SECOND_CURATION/VISUAL_SCENES_INDEX.json`.
- Atlas: `SECOND_CURATION/VISUAL_SCENES_ATLAS.pdf`.
- Imagens: `SECOND_CURATION/visuals_all/SCENE_00000/` até `SCENE_00039/`.
- Manifestos: `VISUAL_EXPORT_MANIFEST.json` e `SECOND_CURATION/SECOND_CURATION_MANIFEST.json`.

SHA256 do ZIP: `b7176f0789a6faa782e45ec6f5c81e4d9fc62d5abadf138f02badd9d9b82d589`.

SHA256 do PDF: `410ccbe48aec6e7cc96248dbe44ff1fcdd21bb84fdeafe3b5b45595f41aaf29c`.

O vídeo tem menos de dez minutos; um ZIP e um PDF bastam. Para vídeos maiores, o reexportador produz ZIPs acompanhantes e PDFs em intervalos de dez minutos, com manifesto, hashes e IDs de cenas preservados ao cruzar fronteiras. O ZIP principal continua completo; os limites de integridade do core existente continuam ativos e produzem erro explícito ao serem excedidos, sem corte silencioso de cenas. A divisão foi verificada com assets sintéticos, não com novo processamento de vídeo longo.

## Testes e evidência visual

Comando final executado:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  src/tests/test_visual_scenes_export.py `
  src/tests/test_visual_scenes_atlas.py `
  src/tests/test_contact_sheet_chronology.py `
  src/tests/test_visual_scenes_package_integration.py `
  src/tests/test_v43_handoff.py `
  src/tests/test_v44_second_curation.py `
  --junitxml=docs/reports/visual_all_20261019/final_regression.junit.xml
```

Resultado: **76 passed in 17.91s**, sem skips ou falhas nessa execução. Registro: [final_regression.log](final_regression.log) e [JUnit](final_regression.junit.xml). São regressões focadas, não a suíte integral do repositório. Fixtures sintéticas verificam limites editoriais zero, falhas explícitas, fallback, PTS desconhecido, corrupção de cache, compatibilidade do core sem cenas, preservação editorial, retomada e cena atravessando fronteira de dois ZIPs/PDFs.

A primeira exportação real capturou 92 amostras, mas o PDF rejeitou uma comparação binária exata de duração (`733.333` versus `733.3330000000001 ms`). A comparação passou a tolerar somente `1e-6 ms`, com regressão que continua rejeitando discrepância real de `0.001 ms`. A execução seguinte reutilizou os 92 recibos, sem novas capturas, e concluiu o PDF e o ZIP. Os dois comandos e resultados estão em `real_export.log` e `real_export_resumed.log`; a falha inicial não foi contabilizada como sucesso.

[INDEPENDENT_REAL_ZIP_AUDIT.json](INDEPENDENT_REAL_ZIP_AUDIT.json) comprova CRC, hashes dos 141 itens do manifesto, todos os 40 IDs/limites originais, 46 microjanelas, referências de transcrição e preservação da câmera/editorial. [INDEPENDENT_TEST_REVIEW.md](INDEPENDENT_TEST_REVIEW.md) contém a revisão independente.

[PDF_ATLAS_VALIDATION.md](PDF_ATLAS_VALIDATION.md) registra abertura e renderização de **22/22 páginas** com `Windows.Data.Pdf`. As páginas 1, 3, 11, 21 e 22 foram inspecionadas visualmente. Todos os 40 IDs e 13 textos canônicos referenciados foram encontrados como texto pesquisável; os bytes dos 40 JPEGs estão embutidos no PDF. As imagens PNG de verificação e o recibo nativo estão em `pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/pdf_validation/actual_20261019T034553/`. A inspeção visual de páginas foi amostral, enquanto a renderização nativa cobriu todas elas.

## Retomada comprovada na mídia real

Comando executado após a auditoria:

```powershell
.\.venv\Scripts\python.exe docs/reports/visual_all_20261019/verify_real_resume.py
```

Resultado **PASS**, com `_Capture` e `build_contact_sheet` substituídos por bloqueios que falhariam se acionados: **zero chamadas**, **zero novas capturas**, `reused_complete_export=true`. Os **242 arquivos** da fonte, pacote original, cinco JSONs canônicos, assets e caches mantiveram bytes, tamanho e data de modificação. A nova revisão de retomada também foi reaberta com validação `valid`. Evidência: [REAL_RESUME_PROOF.json](REAL_RESUME_PROOF.json).

Essa prova gerou a revisão adicional `DELIVERY_20261019T035100348706Z_4d0d82/00_INICIAR_POR_AQUI.zip`, SHA256 `c665a949c9877762803f1d14772f0ae002c891717e36258c826aa27cce8db489`. O ZIP indicado como entrega principal acima permanece o que recebeu a auditoria visual independente. A diferença entre revisões inclui o recibo de execução; as imagens e o PDF são os mesmos.

As 40 thumbnails antigas não continham, por imagem, recibo verificável de SHA256 e procedência temporal. Foram preservadas. As amostras esparsas novas forneceram essa evidência; desde então a retomada reutiliza os recibos válidos. Não houve inferência, diarização, reconhecimento facial, semântica, detecção nova de cenas, direção de câmera, download ou renderização de MP4/preview. Nenhuma dependência foi instalada.

## Reexportar pelo PowerShell

Executar na raiz atual do projeto. A mesma pasta de destino permite reaproveitar os assets e caches íntegros; cada entrega recebe uma pasta nova.

```powershell
.\.venv\Scripts\python.exe analyze.py --reexport-all-scenes `
  --analysis analysis/video_d96cd4328fd5 `
  --package pacotes_para_enviar/SECOND_CURATION_PARTIAL_pc6SR_Fvdt0_20261019_032257_115420_b77577.zip `
  --media input/youtube/pc6SR_Fvdt0/pc6SR_Fvdt0.mp4 `
  --destination pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019
```

Fonte preservada: SHA256 `c264fbfd714743f2f716f3b84a9416b8e0b6a2f48a350f5375fa224208565592`. ZIP original preservado: SHA256 `23100dce16ca1f1fb9b8e6a8210884d714aa2fc292f794f68b5a7dedf50b51fb`.

HEAD permanece `fb78b717ebf45134e1c9a94a27abcd1a579cc090`. Não houve commit, push, publicação ou operação destrutiva. `git diff --check` passou. `.env`, credenciais, modelos, original de mídia e análise persistida foram preservados.
