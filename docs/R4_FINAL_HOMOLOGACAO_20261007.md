# Rodada 4 — Homologação, segurança editorial e ponte Curator (R4.7)

## Estado real

Implementado e verificável no ambiente auxiliar Linux: integridade do ZIP de segunda curadoria, preservação de decisões comerciais anteriores, rechecagem de Stories contra o catálogo definitivo, invariantes entre manifesto/índice/briefing, visualização sob demanda, ponte compatível com o carregador **Curator V2**, auditoria técnica do preview. Não houve reexecução completa do benchmark Clóvis com CUDA/Ollama/Whisper, nem render social final 1080×1920 nesta sessão.

**READY** no ZIP de segunda curadoria significa **pronto para segunda revisão editorial**, e não pronto para publicar. `publication_ready=false`, `requires_curator_review=true` e `final_safe_area_verified=false` são explícitos nos objetos pertinentes.

## Falhas tratadas

1. A reclassificação comercial no exportador agora **não desfaz** `excluded` do gate upstream (inclusive exclusões propagadas por bloco temporal). Pode incluir nova exclusão textual, nunca remover uma exclusão anterior.
2. Shortlist e Stories são reconciliados **depois** da classificação final. Candidato comercial ou não elegível não pode ser transmitido como sugestão aprovada.
3. Pacote de curadoria é validado em integridade de arquivos, referências, contagens, elegibilidade da shortlist/Stories e consistência `manifest == index == brief` para readiness.
4. Quando `generate_visuals_on_demand` adiciona visuais, recalcula `visual_ready` e atualiza **todos** os locais onde isso é declarado.
5. Confronta contagens finais com `summary/analysis_summary.json` e `editorial/final_gate_report.json`; sem campos antigos contraditórios.
6. Stories são recomendações editoriais, não saída renderizada nem legendas revisadas. Safe area só pode ser validada **depois** do crop/render.
7. A ponte `curator_bridge.py` recusa pacotes PARTIAL/sem shortlist, não sobrescreve diretórios e não inventa dados de rosto/câmera. Legendas com palavras sinalizadas usam texto de segmento em vez de karaoke incerto.

## Rodar no Windows (PowerShell)

Preservar `.venv`, `analysis`, `.cache`, vídeos e modelos. Instalar a atualização do código por cópia de segurança, sem `--force`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/tests

# Auditar o pacote antes de mandar para a segunda curadoria
.\.venv\Scripts\python.exe scripts\dev\bridge_curator_r4.py --package "C:\CAMINHO\SECOND_CURATION_READY_....zip" --report "C:\CAMINHO\auditoria_r4.json"

# Se e SOMENTE SE os requisitos editoriais, transcrição, shortlist e visuais estiverem prontos:
.\.venv\Scripts\python.exe scripts\dev\bridge_curator_r4.py --package "C:\CAMINHO\SECOND_CURATION_READY_....zip" --output "C:\CAMINHO\CURATOR_INPUT"

# Diagnóstico complementar do preview existente e da análise original
.\.venv\Scripts\python.exe scripts\dev\homologate_r4.py --package "C:\CAMINHO\SECOND_CURATION_READY_....zip" --analysis "C:\CAMINHO\analysis.json" --preview "C:\CAMINHO\CLIP_001_PREVIEW.mp4" --report "C:\CAMINHO\R4_HOMOLOGACAO.json"
```

Depois ajustar `paths.analysis_root` no `LDPORTO_VIDEO_CURATOR/config.yaml` para o diretório `CURATOR_INPUT` (a pasta **pai** da pasta `_SECOND_CURATION_BRIDGE`). Abrir Curator, informar a URL/ID original, rodar **CURAR → TESTAR 1 CORTE → revisar manualmente → APROVAR TESTE → RENDERIZAR TODOS**.

A ponte entrega somente dados editoriais/transcrição. Não transmite a análise visual bruta. **O Curator deve preservar a câmera de origem em casos sem evidência confiável**, e precisa localizar a mídia fonte real no seu ambiente.

## Critérios obrigatórios para homologação total

- [ ] Em Windows/Python 3.11, dependências FFmpeg/CUDA/Ollama instaladas e GPU identificada.
- [ ] Benchmark do mesmo vídeo conclui `16_understanding`, Commercial Gate, Stories e `SECOND_CURATION_READY` sem falhas e sem comerciais selecionados.
- [ ] Comparar V4.6→R4.7: ASR/timestamps, micro-ReID, speaker↔person, active speaker, câmera, zoom entregue e runtime.
- [ ] Rodar A/B de prompt compacto no **Ollama real**; ativar somente se cobertura e qualidade não regredirem.
- [ ] Rodar A/B HOG/face no **Windows real**; modo paralelo segue desligado se não houver vantagem.
- [ ] Revisar pelo menos um preview real: rosto ativo correto, GC preservado/evitado, legendas legíveis e fiel ao áudio, title/hook, ausência de comercial; revisar começo e fim dos cortes.
- [ ] Confirmar edição vertical real 1080×1920, com áudio limpo, sem corte brusco no payoff.
- [ ] Aprovar um preview **do mesmo plano de decisões** antes do lote; manter publicação em redes como ação humana separada.
- [ ] Validar o fluxo completo de Story(s) no Curator: a ponte **não implementa render em lote de Stories**. Não confundir plano de Stories do Analyzer com MP4 final.

## Evidência antiga — limites

`SECOND_CURATION_PARTIAL_yZ78vCgiPZk_20261007_155330_617122_686827.zip` é válido como arquivo de diagnóstico mas **não é elegível para a ponte**: `visual_ready=false` e shortlist vazia. Preview antigo `CLIP_001_PREVIEW.mp4`: 48s, 540×960, vídeo H.264 + áudio AAC; sua existência **não comprova** qualidade editorial/câmera/legenda.

## Próximos trabalhos se a homologação descobrir gaps

1. Recuperação de embeddings na detecção de rosto da origem quando micro-tracklets não recebem face válida; usar ground truth de identidade, não thresholds arbitrários.
2. Reconciliação probabilística speaker↔person / active speaker com janelas e verificação visual.
3. Escolha real de Smart Zoom/câmera apenas após visual ground truth; simular e testar crop nos trechos finais.
4. Renderer Social/Stories Curator próprio com safe area, legendas reparadas e publicação explicitamente separada da curadoria.
5. Otimização semântica Ollama/Python 3.11/CUDA após A/B de qualidade e custo de tokens.

Estas são **pendências reais**; não foram declaradas concluídas nesta build.
