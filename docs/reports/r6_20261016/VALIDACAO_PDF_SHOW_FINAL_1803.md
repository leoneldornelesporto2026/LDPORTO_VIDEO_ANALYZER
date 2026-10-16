# Inspeção final dos PDFs do show — revisão 20261016T180302510442Z

Data local: 2026-10-16. A revisão final inspecionada é `20261016T180302510442Z_0796ac`, em `C:/Users/leone/Videos/LDPORTO_VIDEO_ANALYZER/`. A revisão anterior `20261016T175750222280Z_12a379` e os dois PDFs anteriores foram preservados, com SHA256 conferidos novamente.

O ensaio abriu somente PDFs com o leitor nativo `Windows.Data.Pdf.PdfDocument`. Os fontes estavam congelados e não foram editados. Nenhum vídeo/áudio foi aberto, e nenhum modelo, ASR, pipeline ou render social foi executado. O contact sheet visto abaixo já estava embutido no PDF.

## Leitor real e contagem

| Documento final | Páginas totais | Páginas renderizadas e vistas | SHA256 do PDF |
|---|---:|---:|---|
| Guia editorial completo | 13 | 1–4 | `15b52a86dc9f6016a1b73ce9b4ede0662ea5df5a0951330d8574c409c018c8b1` |
| Reel 001 | 5 | 1–4 | `a8629868f861486f16453a1d8d14071d392367e97179d414b37561b91b301d54` |

As oito imagens foram inspecionadas visualmente. Títulos, acentos, texto, timestamps, índice e rodapés estão legíveis e dentro das margens. Não foi observado glifo ausente, erro de leitura ou corte de texto nas páginas amostradas.

As contagens são do documento inteiro informado pelo leitor; a inspeção visual ficou limitada às quatro primeiras páginas de cada PDF. Isso não equivale a revisar todas as páginas, precisão de transcrição ou produto audiovisual final.

## Comparação com a revisão anterior

- **Guia:** passou de 14 para 13 páginas. O objeto completo de `episode_summary` que ocupava páginas 1 e 3 foi substituído por um resumo em prosa sob “Resumo editorial proposto”. A fonte da síntese e a necessidade de conferir falas, nomes, papéis e acontecimentos estão explícitas.
- **Título:** usa a referência editorial fornecida no pedido. Isso não atribui os nomes a rostos. Participantes continuam “Nome não confirmado” e `UNKNOWN_PERSON`, com papéis registrados como hipótese.
- **Reel 001:** continua com cinco páginas. O corte aparece como `00:59:57.550–01:00:52.750`, com duração `55.20 segundos`, em vez de segundos absolutos sem formatação e artefato de ponto flutuante.
- **Legenda:** apresenta `ALIGNMENT_REVIEW_REQUIRED`, modalidade permitida `none` e aviso de revisão; não despeja mais o objeto `caption_preflight` no briefing.
- **Propostas criativas:** gancho, título alternativo e CTA ausentes aparecem como não registrados, com revisão necessária. O ID `MOMENT_00012_0003` é mantido em vez de inventar título confirmado.
- **Material visual:** o contact sheet embutido está legível e mantém a advertência de que os frames não comprovam aprovação da prévia final.
- **Fonte canônica:** transcrição, timestamps por palavra e incertezas continuam visíveis. Esta inspeção não ouviu o áudio nem corrigiu palavras.

Os achados de apresentação que motivaram a nova revisão foram resolvidos nas páginas amostradas. Não foi identificado motivo de nova regeneração por falha visual nessas páginas.

## Artefatos e integridade

PNGs e recibos do leitor:

- `pdf_visual/show_1803_guia_final/windows_reader_result.json` e `page_01.png` a `page_04.png`;
- `pdf_visual/show_1803_reel_001_final/windows_reader_result.json` e `page_01.png` a `page_04.png`.

`pdf_visual/show_final_pdf_comparison_hashed.json` inclui os hashes dos PDFs, de cada PNG e de cada recibo, contagem total, páginas inspecionadas e comparação das revisões. SHA256 desse JSON: `58957d1f78c8bc7d6d735c29eb2a3d25bc6caa6dc7251c6fd16cc2191846e2b3`.

A comparação confirmou que os PDFs antigos continuam com os hashes registrados na inspeção anterior. Nenhuma revisão foi sobrescrita. Esta validação de PDF não promove `PARTIAL`, aprova preview ou autoriza publicação.
