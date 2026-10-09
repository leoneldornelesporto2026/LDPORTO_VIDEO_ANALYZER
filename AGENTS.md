# L.D.PORTO — regras locais para agentes Codex

- Trabalhar **no projeto atual**; não recriar o Analyzer nem extrair ZIP antigo sobre os fontes.
- Alterar somente a etapa indicada pelo orquestrador; preservar todas as implementações anteriores.
- `automacao/evidencias/*.zip` são referências de leitura, NÃO fonte de código.
- A análise do João Gordo reporta build antigo; não apresentar testes nela como prova de execução do código atualizado.
- Não modificar `orquestrador.py`, `automacao/MAPA_ETAPAS.json` nem `automacao/prompts/`.
- Não executar pipelines completos, baixar pesos, instalar dependências, acessar serviços pagos ou publicar conteúdo automaticamente.
- Manter estados `PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED` e `PUBLISH_READY` separados; não contornar gates.
- Não inventar transcrições, risadas, identidades, falante ativo, evidência de imagem, scores ou resultados de testes.
- Registre mudanças e comandos reais no checkpoint pedido pelo orquestrador.
- Evite consumir GPU/Ollama com testes de regressão focados e fixtures; documente itens a homologar no Windows.
- Sem tocar em `.env`, credenciais, pasta `.git`, modelos e mídias locais.
