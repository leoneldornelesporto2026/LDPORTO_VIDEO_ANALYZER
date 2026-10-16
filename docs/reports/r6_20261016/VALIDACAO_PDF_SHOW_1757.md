# Inspeção dos PDFs do dossiê real — revisão 20261016T175750222280Z

Data local da inspeção: 2026-10-16. Foi preservada a revisão `20261016T175750222280Z_12a379`, exportada para `C:/Users/leone/Videos/LDPORTO_VIDEO_ANALYZER/` no diretório do show `9UCGZia2p1k`.

Nenhum arquivo do dossiê foi alterado. Foram lidos somente dois PDFs; não houve abertura de vídeo/áudio, extração de frames da fonte, execução de ASR/modelos ou nova inferência. As imagens vistas no Reel pertencem ao JPEG já embutido no PDF.

## Leitor e resultados

O script existente `pdf_visual/render_windows_pdf.ps1` recebeu `-MaxPages 4`, salvando resultados somente no diretório deste relatório. Ele abriu os documentos com `Windows.Data.Pdf.PdfDocument` e renderizou por `RenderToStreamAsync`.

| PDF | Total de páginas informado pelo leitor | Páginas renderizadas/inspecionadas | SHA256 |
|---|---:|---:|---|
| `00_RESUMO/GUIA_EDITORIAL_COMPLETO.pdf` | 14 | 1–4 | `562e53c4401ba1665def6fa1f7b010d4a7f02077ae14f3625624a5948d6f63a0` |
| `03_REELS/REEL_001/RELATORIO_REEL.pdf` | 5 | 1–4 | `c6eb0e7b835537d664d60f74bed55221d501fd201c4215a1494dc397a7cc5377` |

Os oito PNGs foram inspecionados visualmente. Todos foram renderizados aproximadamente em 793×1123 px. Títulos, acentos, caracteres, rodapés e timestamps ficaram legíveis e dentro das margens; não houve erro de abertura, página vazia inesperada ou glifos ausentes.

Evidências:

- `pdf_visual/show_1757_guia/windows_reader_result.json` e `page_01.png` a `page_04.png`;
- `pdf_visual/show_1757_reel_001/windows_reader_result.json` e `page_01.png` a `page_04.png`.

## Achados de apresentação

O guia apresenta fonte, duração, hash e cobertura de transcrição de 16,92% de forma legível. O índice aparece na página 2. Participantes são anônimos/não confirmados; a confirmação de rosto/nome/papel permanece pendente.

Há, porém, **um despejo de JSON no resumo**: a página 1 inicia `Resumo da análise: {"text": ... "primary_sections": ...}`, continuando na página 3 com IDs, intervalos e estruturas internas. O texto é renderizado corretamente, mas cerca de duas páginas ficam ocupadas por estrutura de máquina que dificulta a leitura editorial. Deve ser apresentada como resumo em prosa e seções resumidas, mantendo a estrutura integral no JSON canônico.

O Reel 001 está associado a `MOMENT_00012_0003`. A página 1 inclui o contact sheet já embutido, com legenda indicando que não prova aprovação final. Os estados de legenda exigem revisão e nenhum render final é declarado aprovado.

A apresentação dessa revisão ainda mostra:

- duração numérica `55.199999999999982`, em vez de duração formatada;
- arrays/IDs e os objetos completos de `caption_preflight` e `generated_copy` como JSON;
- título de abertura como ID técnico porque não havia título editorial sustentado disponível;
- páginas de timestamps de palavras legíveis, com texto original e avisos de incerteza, sem confirmação auditiva nova.

O título técnico é uma abstenção aceitável; não deve ser substituído por título inventado. Já a duração e os objetos de briefing devem ser formatados para leitura humana.

## Decisão comunicada

Foi recomendado gerar **outra revisão exclusiva após estabilizar os ajustes de apresentação**, preservando este dossiê e estes PNGs. A geração desta revisão ocorreu enquanto o exportador ainda recebia melhorias de apresentação; sua validade estrutural não comprova que reflita o estado final dos fontes.

Esta inspeção verifica abertura e apresentação dos PDFs lidos. Ela não confirma acurácia de transcrição, identidade de artistas, nomes de músicas, direitos, segurança de crops finais, movimentos entregues ou aprovação de publicação. As demais páginas não foram renderizadas neste ensaio limitado.
