# Reconciliação do baseline real V4.3

O run local `analysis/video_31329be78ca4` é evidência real: produtor 4.3.0,
`execution_scope=full_pipeline`, fonte yZ78vCgiPZk, 8245.014s, 1920×1080/30fps.
Status de qualidade `partial/P1_DEGRADED` não significa que o run não ocorreu.
As afirmações antigas de full run pendente refletem a auditoria anterior a este run.
Não há ainda um full run V4.4. As duas versões nunca devem ser confundidas.

## Contadores diferentes, ambos preservados

| Contador | Valor | Significado e evidência |
| --- | ---: | --- |
| Log em 8231.0s | 5755 | `VisionEngine`: `len(people)`, hipóteses anônimas de `person_id` acumuladas até aquela amostra; a mensagem dizia “tracks” incorretamente |
| Hipóteses online ao final | 5758 | `raw_people.json`; três novas hipóteses após a última mensagem periódica |
| Raw tracklets ao final | 6085 | `raw_tracks.json`, agrupamento de `track_id` no Re-ID; inclui micro-tracklets |
| Tracklets adicionais de hipóteses reaparecidas | 327 | A galeria online reutiliza `person_id` com um NOVO `track_id` após corte/oclusão: 5758 + 327 = 6085 |
| Tracklets válidos | 1818 | Passaram tempo visual e quantidade mínima de observações |
| Micro-tracklets | 4267 | Não passaram esses requisitos; 1818 + 4267 = 6085 |
| Identidades persistentes após Re-ID | 1510 | Hipóteses consolidadas, NÃO número de humanos únicos anotados |

O contador 5755 foi reconstruído pelos `first_seen <= 8231.0` de `raw_people.json`.
Nesse instante já havia 6082 tracklets observados; os três restantes apareceram
depois. Não se deve comparar a redução de “raw tracks” usando 5755 contra um
baseline que conte `track_id`. Os logs V4.4 distinguem explicitamente os dois.

## Métricas de qualidade preservadas

213 candidatos antes de deduplicação (209 principais + 4 alternativas), shortlist
12, speaker/person 0.032065393795803775, active speaker 0.024560099980789833,
foco resolvido 0, Smart Zoom 0, fallback semântico 0.2608695652173913,
histórias completas 0 e payoff 0. Tracking 2670.282s, semântica 6053.453s,
Global Review 454.406s e status `ok`.

O tempo total ~3h06 informado no benchmark é duração de parede histórica; a soma
dos estágios instrumentados não mede todo o tempo de I/O/preflight/source.
Não substituir esse total pela soma de estágios nem comparar replay com full run.

Auditoria reproduzível: `ldporto.baseline_audit.audit_baseline(folder)`.
Baseline e checksums foram preservados em `.cache/v44_baseline_v43` e
`.cache/v44_validation/V43_BASELINE_AUDIT.json`. Código e arquivos históricos de
análise não são regravados para “corrigir” contadores.

Runtime efetivamente verificado nos dois projetos: Windows/Python 3.11.9.
A referência a 3.11.17 no ledger V4.3 pertence a outro ambiente histórico.
