# V4.4.0

Runtime oficial: Windows/Python 3.11.x; implementação e testes locais em 3.11.9.

- Contadores reais V4.3 reconciliados: 5755 hipóteses online no último log,
  5758 finais; 6085 tracklets finais, dos quais 1818 válidos e 4267 micro.
- Evidência acústica com lag/variância; consenso e conflitos preservados;
  estados confirmado/provável/incerto/offscreen e diagnóstico por speaker.
- Fallback dominante separado da identidade acústica, estados de câmera,
  geometria de cabeça, dwell, controle de movimento e gráficos persistentes.
- Commercial Gate V3 cobre Havan/Openbox com spans e OCR opcional localizado.
- Repair semântico por item mantém fatos válidos; story recovery preserva
  segmentos literais; ASR dirigido gera alternativas sem reescrever a fonte.
- Contrato SECOND_CURATION_DECISIONS V4.4 e interface de providers locais;
  visuais promovidos sob demanda conservam o catálogo e o ZIP original.
- Curator: import direto, micropercepção por corte, GC único em crop/split,
  verifier sobre frames renderizados e aprovação vinculada ao MP4/plano.
- ETA com histórico local compatível; cleanup por preview/confirmacão e
  leases de mídia; seleção/download explícito de fonte; UX de modelos.

O schema semântico de extração e seu prompt continuam 4.3.0, porque o contrato
de fatos não mudou. A implementação de repair e os fingerprints de módulos
mudaram; caches downstream são invalidados sem invalidar ASR/visão por decisões.
O schema compacto segue 2.0; o novo schema de decisões é 4.4.0.

Limites e evidências por bloco constam no Implementation Ledger.
