# Biblioteca local — controles da GUI e revisão de integridade

Data: 16/10/2026. Este complemento cobre a GUI e testes sintéticos; a migração real do original e seus hashes são documentados em `MEDIA_LIBRARY_MIGRATION.md` pela execução principal.

## Implementado

- `app.py` agora mostra botão de verificação local, origem da mídia, SHA256, estado encontrado/ausente/bloqueado e mensagem de download desnecessário quando o original íntegro já existe.
- A opção **Autorizar download se o original estiver ausente** começa desmarcada em cada sessão. Alterar a fonte revoga essa escolha e limpa a referência de original escolhida para o link anterior.
- **Original local para este link** mantém a URL/ID do YouTube e permite selecionar outra localização do mesmo original. O SHA256 esperado é opcional na GUI; quando conhecido, divergência bloqueia o início mesmo com o checkbox de download marcado.
- A busca de mídia e o cálculo de SHA256 executam em uma thread de leitura. Somente a thread principal atualiza Tk. O botão não importa downloader, modelos ou pipeline. A GUI ignora resultados de uma seleção anterior e não inicia trabalho ao fechar durante o cálculo do hash.
- Flags encaminhadas à CLI: `--media-path`, `--media-sha256` e, somente com escolha explícita para uma URL, `--allow-download`. A CLI principal fixa `allow_download=bool(args.allow_download)`; uma configuração antiga não substitui o opt-in da sessão.
- O resolvedor reutiliza um arquivo íntegro independentemente da altura pedida para um download novo. ID e hash continuam preservados. Nenhum arquivo de configuração, credencial, original ou pasta histórica foi alterado por estes testes.

Hash íntegro não equivale a áudio/container homologados. O resolvedor declara validação da extensão; a inspeção de mídia da execução continua responsável por codecs, áudio e duração antes do processamento.

## Revisão e regressões adicionais

Os testes novos de `curator_camera_adapter.py`, `media_library.py` e `r62_delivery.py` encontraram defeitos reais, corrigidos pela execução principal: erro combinado centro/escala superior ao limite anunciado de 0,75 pixel; biblioteca malformada bloqueando seleção explícita válida; risco de diretório por vídeo ser junction antes de copiar; retomada de original já copiado sem manifest; verificador FULL aceitando perfil/flags incorretos e JSON malformado; limite de 60 s de Stories aplicado indevidamente a seis Reels existentes. As regressões cobrem esses casos.

O teste de integração usa um AVI MJPEG sintético de 120 s, 64×48, 2 fps, criado no diretório temporário do pytest. Seu Reel tem 70 s, verificando que o limite de Story não cria um bloqueio artificial de legenda. O pacote fonte permanece idêntico; FULL_AUDIT e EDITORIAL_HANDOFF reabrem com integridade; os estados editorial, humano, prévia e publicação permanecem separados e não aprovados. Nenhum original do usuário, download, serviço ou modelo é usado nesse caso.

A regressão existente de OCR revelou que `save_ocr_options` forçava aspas em strings YAML. Ao restaurar o caminho Tesseract original, a configuração mudava de bytes embora o valor fosse o mesmo. A correção preserva o estilo de aspas do escalar existente e mantém o dump seguro para strings ambíguas como `true`. Novos casos verificam escalar simples, aspas simples, aspas duplas, comentários e CRLF, somente em configurações temporárias.

## Comandos e resultados reais

Comando: `.venv\Scripts\python.exe -B -m pytest -q src/tests/test_r62_media_gui.py src/tests/test_r62_ocr_config_style.py src/tests/test_stage54_ocr_gui.py src/tests/test_stage63_ocr_runtime.py src/tests/test_sol_v3_gui_review.py src/tests/test_r62_curator_adapter.py src/tests/test_r62_media_library.py src/tests/test_r62_delivery_integrity.py src/tests/test_r62_camera_target_states.py src/tests/test_r6_camera_performer_handoff.py src/tests/test_stage31_focus_audit.py src/tests/test_stage32_safe_camera.py`.

Antes da correção OCR: 56 passaram, uma falhou e uma foi ignorada. A falha era o roundtrip de aspas descrito acima. Execução final, incluindo a regressão de hash divergente com checkbox marcado: **124 passaram e uma foi ignorada em 6,50 s**. O skip é criação de symlink real sem privilégio no Windows; uma regressão adicional simula a consulta de link no diretório temporário por vídeo e passou sem privilégios. Não se declara o caso real de junction homologado por essa simulação.

Pendência de homologação humana no Windows: abrir a GUI, verificar visibilidade/rolagem dos controles na resolução usada pelo operador e selecionar o original por URL/ID/SHA. Nenhuma janela Tk foi aberta nos testes. As provas MP4 e o SIFT da equipe de previews são resultados separados; estatísticas do plano recomendado e número de testes não são prova de render.
