# Referência do contrato histórico do orquestrador

Os 52 prompts e o mapa original de 42 entradas foram copiados, byte a byte,
dos blobs do commit `34797e164377f05e64ae628daf499cda2fb8bf55` do Git local.
`ORIGEM.json` registra os caminhos originais, IDs dos blobs e SHA-256.
Nenhum arquivo foi obtido dos ZIPs de evidência.

Esta fixture conserva o contrato antigo: descoberta contígua de todos os
prompts, integridade do mapa de 42 entradas, arquivos referenciados existentes
e títulos legados preservados. O teste redireciona somente `AUTO`, `PROMPTS`
e `PLAN` durante a leitura; o pytest restaura esses valores ao terminar.
Os testes de execução e recuperação continuam usando seus projetos temporários.

O ciclo ativo usa exclusivamente `automacao/prompts/`, atualmente com
`ETAPA_01.txt`, e é verificado separadamente. Não copie esta fixture para essa
pasta, nem a use como estado do orquestrador.

Esses documentos são referência histórica de planejamento. Não comprovam
execução, testes, aprovações ou as 63 aprovações informadas pelo usuário.
Não incluem estado, checkpoints, snapshots ou recibos históricos.
