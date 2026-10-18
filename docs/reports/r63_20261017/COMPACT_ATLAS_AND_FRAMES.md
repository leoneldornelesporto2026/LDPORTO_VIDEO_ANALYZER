# R6.3 — atlas pesquisável e imagens compartilhadas

Implementação incremental em `src/ldporto/compact_atlas.py` e `src/ldporto/compact_frames.py`. O arquivo `visual_review_atlas.py`, com alterações anteriores do usuário, foi preservado. Não houve inferência, download, processamento integral do show ou alteração de mídia original nestes módulos.

## PDF

`build_compact_atlas(...)` recebe os índices completos de cenas, Reels, Stories, séries e atlas; lê uma vez a transcrição canônica e as decisões de câmera. Gera `08_REPORTS/VISUAL_ATLAS.pdf` com panorama, todas as cenas, contatos globais, candidatos, partes/séries e lacunas.

O escritor continua sendo `EditorialPDF`. Uma adaptação reutiliza o mesmo objeto JPEG dentro do PDF quando uma folha de contato aparece na visão global e em diferentes candidatos. A mesma imagem não é embutida novamente por ocorrência. Frames sem contato associado permanecem disponíveis por referência e podem ser embutidos individualmente.

Pessoas nos candidatos usam o índice de observações filtrado pelos intervalos da peça. Quando esse índice não foi fornecido, a listagem de pessoas das cenas é explicitamente contextual, sem afirmar presença no corte. Modos/alvos de câmera são propostas; áreas protegidas desconhecidas, ausência de ação comprovada, alinhamento e continuidade pendentes continuam declarados. O PDF não concede aprovação.

## Frames e cache

O coletor verifica a identidade da análise pelo `manifest.video_sha256` antes de reutilizar imagens persistidas. Também verifica checksums de imagens quando registrados. Sem checksum original, distingue vínculo documental à análise de prova de integridade histórica da imagem. O provider da mídia é aberto somente se uma imagem precisar ser decodificada; exportação integralmente atendida por cache não abre o vídeo.

Corrigido o timestamp de caches: a implementação anterior usava `scene.start`, embora o produtor canônico salve a imagem como `SCENE_ID_{sample_time:.3f}.jpg`. O novo código recupera o tempo persistido desse contrato, mantém a precisão arredondada explícita e não o apresenta como verificação independente do decoder.

Também foram corrigidos: falta de fallback após cache de aspecto inválido; gravação de JPEG antes de validar timestamp; perda de referências de peças quando duas solicitações resultavam no mesmo frame; set de IDs reconstruído a cada captura; amostra final a 1 ms da fronteira que podia decodificar fora do intervalo. Pedidos não atendidos e cenas sem imagem são contabilizados; nenhuma cena é removida do índice para reduzir tamanho.

O perfil padrão é navegação até 320 px, análise até 640 px, JPEG qualidade 62 com `optimize=True`. Não há upscale obrigatório. Contatos têm 640 px de largura, JPEG qualidade 50 otimizado, 16 quadros em grade 4×4. Não são criadas bordas dentro do frame fonte.

## Reperfilamento sem nova leitura do vídeo

`reprofile_shared_atlas(cache, destination, metadata, scenes, ..., analysis_folder=...)` abre apenas os JSONs/JPEGs já colhidos. Verifica hashes e identidade, grava exclusivamente em uma revisão nova e mantém o cache original imutável. Corrige os tempos dos caches somente quando o manifest da análise e o SHA256 da imagem original correspondem ao registro persistido.

A função gera novos IDs/hashes e `source_frame_id_map`, preservando o vínculo de todos os IDs anteriores, inclusive quando há deduplicação. As folhas de contato são reconstruídas com os IDs e tempos reconciliados. Arquivos órfãos antigos não são copiados. Sem prova para reconciliar um tempo, o estado permanece `UNVERIFIED`, em vez de completar a informação.

## Testes executados

Comando:

```text
.\.venv\Scripts\python.exe -m pytest -q src/tests/test_r63_compact_frames.py src/tests/test_r63_compact_atlas.py src/tests/test_r63_compact_handoff.py
```

Resultado real: **27 passed in 18.79s**. As fixtures usam AVI MJPEG pequeno e pixels explicitamente sintéticos, sem abrir mídia do show. Cobrem fonte estrangeira, cache inválido, timestamps/limites, ausência de órfãos, 379 solicitações com todas as cenas preservadas e uma única imagem física para conteúdo idêntico, reconciliação do timestamp legado, cache imutável, PDF pesquisável, reutilização de bitmap, referências ausentes, câmera/observações por peça e integração do ZIP.

Esses testes não homologam a legibilidade do show real. A inspeção visual e a abertura independente pelo leitor PDF do Windows devem constar no relatório de validação real; PDFs e capturas ficam exclusivamente no diretório externo em Vídeos. Este relatório é leve e não contém os artefatos pesados.
