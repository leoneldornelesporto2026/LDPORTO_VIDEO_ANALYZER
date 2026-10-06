# Preview Renderer + Verifier V4

O preview é técnico, curto e não é o render social final. Ele consome a timeline real do Camera Director e interpola todos os keyframes internos disponíveis. Suporta full-frame com padding, crop/pan/zoom, two-shot/split conforme contrato, orientação e target aspect.

Canários são selecionados pelos casos de maior risco para evitar renderizar horas apenas para homologação. O Verifier lê frames do MP4 renderizado e verifica dimensões, duração, bordas inesperadas, faces/cabeças próximas às bordas, zoom excessivo, fluxo/movimento anormal e diferença de duração A/V quando ffprobe está disponível.

Existe repair loop limitado. A classe implementada de correção automática é clipping severo de face/cabeça: o sistema pode abrir para source/full-frame e renderizar/validar novamente. Se não existir reparo seguro, o comportamento deve permanecer conservador.

Limitação: preview técnico usa CFR baseado no FPS de saída/entrada; ele não substitui o renderizador social final nem promete preservar uma cadência VFR de distribuição.
