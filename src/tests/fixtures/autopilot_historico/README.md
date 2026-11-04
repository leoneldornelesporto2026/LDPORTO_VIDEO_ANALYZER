# Referência do contrato histórico do orquestrador

Os 52 prompts e o mapa original de 42 entradas foram copiados, byte a byte,
dos blobs do commit `34797e164377f05e64ae628daf499cda2fb8bf55` do Git local.
`ORIGEM.json` registra os caminhos originais, IDs dos blobs e SHA-256.
Nenhum arquivo foi obtido dos ZIPs de evidência.

Esta fixture conserva os documentos do contrato antigo e sua proveniência.
`test_historical_fixture_provenance.py` verifica os hashes diretamente, sem
importar nem executar infraestrutura de automação. O Prompt 02 também permanece
como briefing de engenharia, referenciado em `docs/briefings/`.

O desenvolvimento atual usa Git e testes diretamente. Não copie esta coleção
para uma fila executável nem a use como estado ou aprovação de desenvolvimento.

Esses documentos são referência histórica de planejamento. Não comprovam
execução, testes, aprovações ou as 63 aprovações informadas pelo usuário.
Não incluem estado, checkpoints, snapshots ou recibos históricos.
