# Validação independente de PDF e status da GUI no Windows

Data local: 2026-10-16. Este ensaio usa somente conteúdo sintético. Nenhum frame do show, mídia local, modelo, inferência, serviço pago ou rede foi utilizado. Não houve instalação de dependências nem abertura de janela de navegador.

## Leitor PDF real

Foi usado o componente nativo **Windows.Data.Pdf.PdfDocument**, independente do escritor `EditorialPDF` do projeto. O script `pdf_visual/render_windows_pdf.ps1` carregou o PDF pelo `StorageFile`, abriu suas páginas e executou `RenderToStreamAsync`, salvando os PNGs. Não é apenas inspeção de xref ou de operadores PDF.

Comandos executados:

```powershell
.\.venv\Scripts\python.exe docs/reports/r6_20261016/pdf_visual/create_fixture.py
& .\docs\reports\r6_20261016\pdf_visual\render_windows_pdf.ps1
```

Resultado: **5 páginas abertas e renderizadas**, cada uma em aproximadamente 793×1123 px. As cinco imagens foram inspecionadas visualmente por ferramenta de imagem. Título, acentos portugueses, imagem JPEG sintética, identificador longo quebrado dentro da página, índice, seções e rodapés ficaram legíveis. As páginas não ficaram vazias ou com glifos ausentes. O índice ocupa a página 2; alguns parágrafos continuam na página seguinte, como permitido pelo paginador atual.

O PDF original de ensaio tem SHA256 `204f162dbafa5b3a62d3155d41ebf56cf1c6218ecdf8b6a99eb349f29c3774bd`. Seu manifesto, resultado do leitor e PNGs foram preservados em `pdf_visual/`.

## Defeito Unicode descoberto e corrigido

Na Arial do Windows, espaço U+0020 e espaço inseparável U+00A0 compartilham o glifo 3; hífen U+002D e soft hyphen U+00AD compartilham o glifo 16. O escritor usava o glifo como CID e sobrescrevia `used[gid]` ao encontrar outro codepoint. O visual continuava correto, porém o `ToUnicode` só podia devolver um dos caracteres. A fixture demonstrou perda do NBSP e substituição de hífen comum por soft hyphen na extração.

`editorial_pdf.py` agora atribui CID distinto a cada codepoint e inclui um stream `CIDToGIDMap` para reutilizar o glifo visual correto. A tabela `ToUnicode` fica sem colisões. Um teste usa o mapa e operadores públicos do PDF para extrair o texto independentemente de `_Font.encode`; também verifica CIDs distintos apontando ao mesmo glifo em `CIDToGIDMap`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r6_project_export.py
```

Resultado após a correção: **10 passed in 4.59s**.

A revisão corrigida foi gerada e aberta novamente no leitor nativo:

```powershell
.\.venv\Scripts\python.exe docs/reports/r6_20261016/pdf_visual/create_fixture.py after_cid_fix
& .\docs\reports\r6_20261016\pdf_visual\render_windows_pdf.ps1 -PdfPath '.\docs\reports\r6_20261016\pdf_visual\after_cid_fix\synthetic_editorial.pdf' -OutputDirectory '.\docs\reports\r6_20261016\pdf_visual\after_cid_fix'
```

O leitor novamente renderizou **5 de 5 páginas**. SHA256 do PDF corrigido: `b6176039573272a47a159a4e2b479fffa5604135b87d762385522be22f296d5e`.

`pdf_visual/cid_fix_comparison.json` registra:

- Os cinco PNGs renderizados antes/depois são idênticos byte a byte; o layout e os glifos visuais permaneceram iguais.
- NBSP: antes ausente na extração, depois preservado.
- Hífen comum: antes substituído, depois preservado.
- Soft hyphen: antes apareceu duas vezes, depois apenas na ocorrência original.

O Windows.Data.Pdf foi usado para renderização real. A extração textual citada é uma leitura independente dos mapas e operadores, sem alegar que a busca do Adobe/Edge foi operada manualmente. Os PDFs de projetos reais e seus frames não foram abertos neste ensaio.

## Status da interface nativa

```powershell
.\.venv\Scripts\python.exe docs/reports/r6_20261016/pdf_visual/check_gui_status.py
```

O script criou widgets Tk nativos com a janela principal e a central de resultados ocultas. O refresh do Ollama foi substituído por função vazia; tentativas de criar thread ou subprocesso disparariam erro. Nenhuma operação de análise, exportação ou limpeza foi invocada.

Resultado registrado em `pdf_visual/gui_status_result.json`: exportação automática inicialmente desmarcada, status inicial distinguindo PDF de vídeo final, central de resultados criada com 13 ações, estado final sem capacidades medidas e sem alegação de aprovação/publicação. Nenhum worker, processo externo ou inferência foi iniciado.

A execução de regressões existentes de GUI, com processamento/modelos simulados, foi:

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_sol_v3_gui_review.py src/tests/test_stage54_ocr_gui.py
```

Resultado naquele ponto: **3 failed, 23 passed in 0.46s**. As três falhas vêm de fixtures que constroem `App.__new__` sem inicializar o novo `auto_project_export`, acessado em `show_completion`. A aplicação real inicializou esse campo no ensaio nativo. O resultado e a necessidade de adequar a fixture/compatibilidade foram comunicados ao agente principal; esse resultado não foi apresentado como aprovado.

O segundo olhar também apontou ao responsável: o resumo legado de câmera ainda usava `zoom_event_count` sem explicitar as etapas, e o verificador de dossiê precisava restringir estados arbitrários. A verificação desta seção não homologa inferência, render social, navegação humana completa, reconhecimento de artistas ou qualidade do show.
