# Documentação por finalidade

O [README principal](../README.md) é a referência operacional atual.

| Finalidade | Documentos |
| --- | --- |
| Arquitetura e contratos | [ARQUITETURA](ARQUITETURA.md), [CONTRATO_DADOS](CONTRATO_DADOS.md), [estrutura](REPOSITORY_STRUCTURE.md) |
| Ambiente | [requirements](../requirements/README.md), [Ollama](setup/OLLAMA_MAXIMO.md), [YOLO local](YOLO_LOCAL_57.md), [OCR](OCR_GUI_54.md) |
| Validação | [VALIDACAO](VALIDACAO.md), [canários](INFERENCE_SMOKE_60.md) |
| Auditoria atual | [SOL V3 de 2026-10-13](reports/sol_v3_20261013/RELATORIO_TECNICO.md), [reestruturação de 2026-10-12](reports/restructuring_20261012/RELATORIO_TECNICO.md) |
| Requisitos preservados | [briefings](briefings/README.md) |
| Histórico | [arquivo](archive/README.md), releases e relatórios V3/V4/R3/R4/S1–S11/etapas |

Documentos datados ou vinculados a builds anteriores conservam o contexto da sua
execução. Contagens, hashes, paths antigos, snapshots e aprovações neles registrados
não substituem as evidências atuais. Relatórios 53–62 e changelogs são históricos;
nenhuma fila de desenvolvimento depende deles.

A retirada operacional da infraestrutura antiga está registrada no relatório de
2026-10-12. Seu backup fica fora do projeto; a proveniência das fixtures permanece
em `src/tests/fixtures/`.
