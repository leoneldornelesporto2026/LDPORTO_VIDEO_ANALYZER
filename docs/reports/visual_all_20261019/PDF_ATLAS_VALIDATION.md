# Atlas pesquisável de todas as cenas — validação do helper

Escopo de 2026-10-19: exportação visual completa por cenas, sem inferência e sem leitura do vídeo pelo gerador de PDF. O helper `src/ldporto/visual_scenes_atlas.py` consome exclusivamente o índice de cenas, transcrições canônicas fornecidas e contact sheets JPEG já exportados. Não usa a seleção de Reels/Stories para filtrar cenas.

## Contrato implementado

`build_visual_scenes_atlas(root, index, transcript_segments=(), partition_ms=600000)` retorna recibo com PDFs, SHA256, bytes, páginas, intervalos e IDs originais de cenas. Abaixo de dez minutos há um único `VISUAL_SCENES_ATLAS.pdf`; vídeos maiores são particionados em dez minutos. Uma cena que cruza a fronteira conserva seu ID e seus limites originais nos dois PDFs. As imagens de microjanelas que cruzam a fronteira conservam seus timestamps absolutos.

Descrições ausentes permanecem `NOT_ANALYZED`. Transcrições disponíveis são literais; referências sem texto são declaradas indisponíveis. A precisão de microssegundos do índice é preservada quando existe fração de milissegundo. `COMPLETE`, `PARTIAL` e `FAILED` descrevem evidência visual; o PDF mantém `preview_approved=false` e `publication_ready=false`.

O recibo permite reutilizar PDFs sem alterações. Um PDF previamente produzido e ainda íntegro pode ser atualizado atomicamente quando seus dados mudam; arquivos preexistentes sem recibo verificável são preservados. O helper não modifica o índice recebido.

## Testes executados

Comando real:

```powershell
.venv\Scripts\python.exe -m pytest src/tests/test_visual_scenes_atlas.py -q
```

Resultado inicial: **11 passed**. Todos usam pixels sintéticos rotulados, arquivos temporários e fonte TrueType local; não são evidência da mídia real.

Verificação conjunta posterior:

```powershell
.venv\Scripts\python.exe -m pytest src/tests/test_visual_scenes_atlas.py src/tests/test_visual_scenes_export.py -q
```

Resultado inicial conjunto: **45 passed in 2.37s**. Após a correção de precisão descrita abaixo, a repetição desse comando retornou **46 passed in 2.75s**, incluindo doze casos do atlas.

Os casos cobrem todas as cenas e fallback, ordem cronológica, cenas fora de seleção editorial, Unicode pesquisável e transcrição literal, imagens JPEG efetivamente embutidas, fronteira de dez minutos, precisão temporal, ausência de capturas/contact sheet, estado `FAILED` preservado, reutilização, reparo de PDF próprio, proteção de arquivo externo, timestamps inválidos e caminhos inseguros.

A primeira execução identificou uma falha na seleção de contact sheets de uma microjanela que atravessava dez minutos. A seleção passou a considerar a identidade das capturas da microjanela sobreposta, preservando seus tempos reais; a regressão está incluída no teste de fronteira e passou.

A primeira integração real chegou ao PDF depois de capturar as cenas, mas rejeitou a duração de `SCENE_00003`: a duração persistida de `733.333 ms` e a subtração binária de `4600.0 - 3866.667 = 733.3330000000001 ms` falhavam na igualdade exata. A comparação passou a `math.isclose(abs_tol=1e-6, rel_tol=0)`, mantendo os limites existentes e sem alterar capturas. O novo teste reproduz esses números e também comprova a rejeição de uma discrepância real de `0.001 ms`. O texto do PDF usa a duração normalizada persistida.

## Homologação real

Caso atual `pc6SR_Fvdt0`, duração **66.194 s**, fonte identificada no índice por `c264fbfd714743f2f716f3b84a9416b8e0b6a2f48a350f5375fa224208565592`. O índice real declara `COMPLETE`, 40 cenas originais, 46 microjanelas, 92 capturas, nenhuma microjanela sem captura e nenhuma alegação de análise contínua de todos os frames.

PDF inspecionado:

`pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/DELIVERY_20261019T034553970556Z_ce0887/SECOND_CURATION/VISUAL_SCENES_ATLAS.pdf`

SHA256 antes/depois da leitura: `410ccbe48aec6e7cc96248dbe44ff1fcdd21bb84fdeafe3b5b45595f41aaf29c`.

Comando real de abertura e renderização independente:

```powershell
& 'pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/pdf_validation/render_windows_pdf.ps1' `
  -PdfPath 'pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/DELIVERY_20261019T034553970556Z_ce0887/SECOND_CURATION/VISUAL_SCENES_ATLAS.pdf' `
  -OutputDirectory (Join-Path (Get-Location).Path 'pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/pdf_validation/actual_20261019T034553')
```

Resultado: `Windows.Data.Pdf.PdfDocument` abriu e renderizou **22 de 22 páginas**, sem erro. O helper WinRT foi copiado sem alterações do utilitário já existente; a execução acima usou exclusivamente o PDF atual deste caso.

As páginas nativas **1, 3, 11, 21 e 22** foram abertas com `view_image`. Foram conferidos início, meio e final: IDs originais, intervalos absolutos, microjanelas, timestamps das capturas, referências de fala e indicação `NOT_ANALYZED` estão legíveis. As imagens preservam conteúdo escuro da mídia e a apresentação original; não houve inferência para preencher descrições. Nenhum corte de texto foi observado nessas páginas amostradas. Essa inspeção é amostral; todas as páginas foram renderizadas pelo leitor independente.

Uma leitura independente de ToUnicode e dos operadores de texto confirmou os **40 IDs de cenas** e os **13 textos de segmentos canônicos referenciados** como pesquisáveis; todas as linhas canônicas referenciadas estão presentes no JSONL entregue. Os bytes originais dos **40 contact sheets JPEG** aparecem integralmente nos streams de imagem do PDF. O limite `00:01:06.194` aparece no texto. Os gates `preview_approved` e `publication_ready` continuam `false`.

Evidência operacional, fora de `docs/reports/`:

`pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/pdf_validation/actual_20261019T034553/windows_reader_result.json`

`pacotes_para_enviar/VISUAL_ALL_pc6SR_Fvdt0_20261019/pdf_validation/actual_20261019T034553/atlas_semantic_validation.json`

Os 22 PNGs permanecem no mesmo diretório operacional. Este relatório leve registra o resultado; não contém cópias da mídia, do PDF ou dos PNGs.
