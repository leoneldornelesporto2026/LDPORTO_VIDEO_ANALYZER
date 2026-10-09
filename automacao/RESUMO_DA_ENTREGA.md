# Entrega — Autopilot 42 microetapas / 08-10-2026

**Fonte de código:** `LDPORTO_PROJETO_ATUAL_20261008_095709_977293.zip` (298 arquivos).
**Fontes de evidência:** `SECOND_CURATION_READY` e `CHATGPT_REVIEW` da mesma execução João Gordo (SHA-256 do vídeo comum), reportando build antigo S4.
**Planos:** 42 prompts individuais + mapa; D01–D12 preservado como referência.

Mudanças no Analyzer: **somente** `.gitignore` (duas regras de exclusão) e `src/tests/test_v43_runtime.py` (allowlist de dois arquivos de infraestrutura). Nenhuma alteração nas implementações `src/ldporto/`, `config/`, `analyze.py`, `app.py` etc.

Novos: `orquestrador.py`, `AGENTS.md`, pasta `automacao/` e `src/tests/test_autopilot_orquestrador.py`.

Todos os 42 prompts estão em `automacao/prompts/`, com um mapa em `automacao/MAPA_ETAPAS.json`.

**Limites da homologação:** nenhum comando real de Codex foi invocado nesta entrega. Os testes do orquestrador simulam execução/resposta e garantem gates locais; homologação Windows, CLI versão 0.161.0, limites de uso e regressão Windows precisam ser testados no computador do usuário.

Os ZIPs em `automacao/evidencias/` são grandes e nunca entram nos snapshots. O Analyzer atual deve ser modificado na mesma pasta do VS Code; o antigo projeto S9–S11 não deve ser extraído sobre ele.
