# V4.4 Finalization

O desenvolvimento funcional principal está concluído. O ponto interrompido pela
cota do agente foi a homologação final do full run, não uma reimplementação.

## Estado confirmado antes da interrupção

- Windows/Python 3.11.9 nas validações locais.
- Suites registradas pelo agente: mais de 400 testes Analyzer e 37 Curator ao
  longo da rodada; o pacote exportado reproduz 404 testes funcionais neste
  ambiente sem GUI/Git.
- Full run retomado após corrigir a resolução local do cache de diarização.
- Diarização full-run: `ok`, ~142.25 s, 23 agrupamentos acústicos.
- Tracking full-run: ~2754.265 s; 6085 tracklets, 1818 válidos, 4267 micro.
- Speaker/person full-run: 15.0490%.
- Active speaker full-run: 9.6733%.
- Active provável sem overlap: 8.0853%; confirmado: 0%.
- A última evidência conhecida antes do limite registrava 13/46 chunks semânticos.

## Smart Zoom

O contrato distingue propostas de movimento de movimento realmente entregue:

- `proposed_zoom_event_count`: intenção/proposta do controlador.
- `zoom_event_count`: movimento observado nos keyframes finais.

No replay conhecido houve 7 propostas e 0 eventos entregues, com máximo 1.0x.
Isso permanece uma limitação real e não deve ser reportado como ganho de câmera.

## Fechamento automático

Quando o full run local terminar com sucesso, execute a partir da raiz:

```cmd
.venv\\Scripts\\python.exe scripts\\dev\\finalize_v44.py
```

O script não executa inferência. Ele apenas exige um run concluído e desbloqueado,
valida artefatos/pacote, preservação do baseline e gera `docs/benchmarks/V43_V44_COMPARE.*`.
Se o pipeline ainda estiver rodando ou incompleto, termina com status não-zero sem
inventar métricas.

## O que ainda depende do full run local

- semantic fallback final;
- story/payoff final;
- câmera final e zoom entregue no vídeo inteiro;
- candidatos/shortlist/package final;
- compare V4.3 → V4.4 completo;
- promoção do bloco geral do benchmark para `VERIFIED_FULL_RUN`.

## Retomada após `16_understanding`

Se um run V4.4 anterior terminou com `16_understanding: failed` e mensagem `list object has no attribute get`, aplique este hotfix e retome a mesma análise/configuração. Não force (`--force`) e não apague cache. Os hashes seletivos preservam ASR, diarização, cenas e tracking; `16_understanding` e dependentes serão recalculados.

O pacote `SECOND_CURATION_PARTIAL` desse run não deve ser tratado como curadoria final: story/entities/shortlist podem estar vazios e broadcast graphics/commercial visual/targeted ASR ficaram bloqueados pela falha upstream.
