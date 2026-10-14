# L.D.PORTO — regras locais para agentes Codex

- Trabalhar **no projeto atual**; não recriar o Analyzer nem extrair ZIP antigo sobre os fontes.
- Desenvolver diretamente com Git e testes, preservando implementações e contratos ativos; não fazer commits automáticos.
- `src/tests/fixtures/historical_evidence/*.zip` são referências de leitura, NÃO fonte de código.
- A análise do João Gordo reporta build antigo; não apresentar testes nela como prova de execução do código atualizado.
- A infraestrutura de automação foi aposentada; não recriar executor, fila de prompts, estados ou locks de desenvolvimento.
- Não executar pipelines completos, baixar pesos, instalar dependências, acessar serviços pagos ou publicar conteúdo automaticamente.
- Manter estados `PARTIAL`, `READY_FOR_REVIEW`, `PREVIEW_APPROVED` e `PUBLISH_READY` separados; não contornar gates.
- Não inventar transcrições, risadas, identidades, falante ativo, evidência de imagem, scores ou resultados de testes.
- Registrar mudanças, comandos e resultados reais em `docs/reports/`; auditorias anteriores em `docs/archive/` são históricas.
- Evite consumir GPU/Ollama com testes de regressão focados e fixtures; documente itens a homologar no Windows.
- Sem tocar em `.env`, credenciais, pasta `.git`, modelos e mídias locais.
