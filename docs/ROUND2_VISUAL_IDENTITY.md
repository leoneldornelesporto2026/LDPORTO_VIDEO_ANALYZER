# Rodada 2 — Visual Identity Hardening (checkpoint)

## Implementado

- Preservado o Re-ID facial estrito de micro-tracklets introduzido na R4.2.
- Adicionada busca facial alternativa quando os buckets binários não retornam nenhum candidato. A busca usa similaridade cosseno real sobre templates existentes e só pode anexar a identidade previamente estabelecida; não cria novas identidades.
- Segurança não relaxada: micro_reid_threshold, micro_reid_margin e veto de sobreposição temporal permanecem obrigatórios; nenhum vínculo por posição da tela.
- Métricas adicionadas: micro_retrieval_fallback_attempts, micro_retrieval_fallback_matches e micro_retrieval_fallback_accepted.
- Testes de regressão para retorno entre shots e conflito simultâneo.

## Limitações

- Nenhum benchmark full-run foi executado nesta sessão: não afirmar redução de 70,12% de micro-tracklets ou melhora de speaker-person sem medir.
- A busca complementar só roda quando nenhum bucket retorna candidatos; regiões densas ainda precisam de revisão de recall e profiling.
- Requer exame dos artefatos de tracking e replay/full run em Windows Python 3.11 antes de homologar.
- O percentual bruto de micro-tracklets pode continuar alto: anexar micro-tracklets com segurança melhora continuidade de identidade, mas não altera o número bruto de fragmentos.

## Próximos blocos da Rodada 2

1. Avaliar micro_retrieval_fallback_accepted no benchmark Clóvis.
2. Medir qualidade das associações com amostras visuais anotadas e conflitos.
3. Melhorar coleta de face embedding em tracklets curtos e regiões de alta densidade de shots, com profiling de custo.
4. Integrar continuidade ao speaker-person / active speaker com replays comparativos.
5. Validar desempenho e estabilidade no Windows com Python 3.11.
