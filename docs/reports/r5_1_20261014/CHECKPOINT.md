# R5.1 — execução incremental

Documento mestre lido integralmente antes de qualquer alteração (1.542 linhas).

A — baseline verificado em `baseline.json`: HEAD 3a301576064d9e34b8e4e3385bd7a0d8f61f3e4b, Git inicialmente limpo; 621 hashes originais, 27 checkpoints e ZIP R5 SHA a84ede22de5fe91b8a5e1abe7044229534fe55943777d769364ff58842ab9807 conferidos. Fontes Python e schemas coincidem com o congelamento R5; somente `.gitignore` mudou por intervenção anterior do usuário. Testes anteriores: 2.078 aprovados, 3 skips, 0 falhas. P0 em execução; nenhuma inferência incorporada.

Comandos de validação executados nesta sessão:

- Inventário Python somente leitura contra `initial_state.json` e `sources_frozen_final.json`; resultado em `baseline.json`.
- `python -m pytest -q src/tests/test_r51_embedded_schema.py --junitxml=docs/reports/r5_1_20261014/checkpoint_a_embedded.xml`: falhou antes da coleta, Python global sem pytest.
- `.venv/Scripts/python.exe -m pytest -q src/tests/test_r51_embedded_schema.py --junitxml=docs/reports/r5_1_20261014/checkpoint_a_embedded.xml`: 5 aprovados, 0,10 s. Ambiente existente reutilizado, nenhuma instalação.
- Consulta `ollama_local.service_info`: serviço 0.35.1, qwen3:14b instalado, digest bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8. Consulta de disponibilidade, nenhuma inferência.

Saídas R5, análise original e VIDEO CURATOR permanecem referências de leitura.


Entrega: A/B/C/D validados tecnicamente, estado editorial SEMANTIC_HANDOFF_PARTIAL. Integridade VERIFIED; regressão 2290 aprovados/3 ignorados. Próximo passo: escutar e revisar as 118 palavras dos segmentos 126–132; ampliar QA/completude e melhorar geração automática de títulos, sem novo processamento audiovisual. Caminhos e hashes no RELATORIO_TECNICO.md e FINAL_INTEGRITY.json.

Comandos finais realmente executados:

- `.venv/Scripts/python.exe docs/reports/r5_1_20261014/run_regression.py final_validation`: regressão completa, 2.290 aprovados, três skips, zero falhas/erros, 257,48 s. O comando pytest exato está em `final_validation.json`. As 2.078 aprovações R5 foram reproduzidas.
- `.venv/Scripts/python.exe docs/reports/r5_1_20261014/prepare_final_evidence.py`: evidência final e correção de referência documental do Checkpoint A; nenhuma mudança em código de produção.
- Comando `--semantic-phase package` registrado integralmente no relatório, com `--semantic-test-evidence docs/reports/r5_1_20261014/test_evidence_final.json`: exportação e consumo real validados, 187 hashes, 122 documentos preservados. Repetição idêntica: mesmo ZIP/SHA, `cache_hit=true`, zero chamadas novas; `cached_repeat_validation.json` registra os dois logs e tempos.
- `.venv/Scripts/python.exe docs/reports/r5_1_20261014/finalize.py`: 621 hashes originais, 27 checkpoints, 282 fontes testados sem divergência, sete renders com stat inalterado, CRC e contratos do ZIP válidos; resultado VERIFIED.
- `git status --short` e `git diff --stat`: preservadas as alterações anteriores; nenhuma alteração no orquestrador, prompts, modelos ou mídia; nenhum commit/push/reset.

Nota de execução: a primeira leitura automatizada dos logs PowerShell como UTF-8 falhou; os logs têm BOM UTF-16. A leitura foi corrigida sem reexportar o ZIP nem repetir inferências.
