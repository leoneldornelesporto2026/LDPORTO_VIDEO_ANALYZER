# Documentacao central — L.D.PORTO VIDEO ANALYZER

Esta e a **porta de entrada para toda a documentacao**. O `README.md` da
raiz e um resumo para quem inicia o projeto. Aqui ficam o guia completo e
o indice do acervo tecnico.

## Uso e configuracao

| Tema | Documento |
| --- | --- |
| Instalacao, GUI, analise, exportacao e testes | [Guia completo](GUIA_COMPLETO.md) |
| Primeiro uso no Windows | [Passo a passo](../docs/setup/LEIA_PRIMEIRO.md) |
| Dependencias e extras Python | [Requirements](../requirements/README.md) |
| Ollama local | [Configuracao](../docs/setup/OLLAMA_MAXIMO.md) |
| GPU/YOLO | [YOLO local](../docs/YOLO_LOCAL_57.md) |
| Validacao e limites | [Validacao](../docs/VALIDACAO.md) |

## Modernizacao da GUI

- [P0-01 - Baseline](gui/P0_01_BASELINE.md)
- [P0-02 - Navegacao visual](gui/P0_02_SHELL.md)

## Arquitetura e desenvolvimento

| Tema | Documento |
| --- | --- |
| Arquitetura do Analyzer | [Arquitetura](../docs/ARQUITETURA.md) |
| Contratos e formatos de dados | [Contratos](../docs/CONTRATO_DADOS.md) |
| Estrutura de pastas | [Estrutura](../docs/REPOSITORY_STRUCTURE.md) |
| Ferramentas e scripts | [Scripts](../scripts/README.md) |
| Instrucoes operacionais dos agentes | [AGENTS.md](../AGENTS.md) |

## Historico e evidencias

| Tema | Documento |
| --- | --- |
| Alteracoes da versao 4.3 | [Changelog V4.3](historico/CHANGELOG_V43.md) |
| Alteracoes da versao 4.4 | [Changelog V4.4](../docs/CHANGELOG_V44.md) |
| Relatorios de auditoria | [Relatorios](../docs/reports/) |
| Historico preservado | [Arquivo](../docs/archive/README.md) |
| Indice legado de detalhes | [Documentacao tecnica existente](../docs/README.md) |

## Convencao de organizacao

- **Raiz:** `README.md` e a unica documentacao geral. `AGENTS.md` e
  mantido na raiz como configuracao para agentes de desenvolvimento;
  movê-lo poderia impedir que as ferramentas carregassem suas regras.
- **`.docs/`:** indice, guia principal, historico e futura documentacao
  narrativa centralizada. Documentos novos devem nascer aqui.
- **`docs/`:** acervo tecnico legado, evidencias e relatorios que
  continuam nos caminhos originais por compatibilidade com links, testes
  e referencias historicas. Nada foi apagado nem renomeado em massa.
- **`src/tests/`, `scripts/`, `requirements/`:** permanecem junto
  dos respectivos modulos, incluindo READMEs locais tecnicos.

Nao interpretar resultados historicos, testes de fixtures ou pacotes
como homologacao atual de GPU, Whisper ou um video real.
