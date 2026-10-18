# Três regressões reproduzidas e corrigidas — 17/10/2026

Os três testes que falharam na regressão R6.2 foram executados novamente no código corrente. Resultado inicial real: três falhas em 57,16 s, registradas em `legacy_three_current.junit.xml`. Não se atribui automaticamente uma falha ao Windows, à codificação ou a uma versão histórica sem reprodução.

## Fila legada e dois ledgers de integridade

`test_new_package_has_one_actionable_queue_and_legacy_queue_still_validates` reconstruía a fila no formato 1.0 e atualizava somente `SECOND_CURATION_MANIFEST.json`. O contrato R6 também vincula essa fila em `HANDOFF_MASTER.json`. A validação retornou precisamente `r6:master_artifact_hash:editorial/human_review_queue.json`.

A correção está na fixture de teste: atualizar os dois ledgers da cópia temporária derivada, incluindo o hash do próprio HANDOFF_MASTER no manifesto externo. Foi acrescentada uma asserção de que o estado intermediário com ledger interno desatualizado permanece inválido. Nenhum gate de produção foi relaxado e nenhum pacote real foi reescrito.

## Pacote de fontes consumia o orçamento com derivados de relatórios

`test_exporter_self_test` e `test_work_package_has_single_derived_manifest_files` falhavam porque o pacote de fontes incluía timelines de replay de 17–18 MB, PNGs de homologação e cópias de diretórios editoriais derivados. O orçamento era consumido antes de `src/ldporto/pipeline.py` e `exportar_ldporto.py`; o manifesto real resultava em PARTIAL_EXPORT. Isso foi confirmado no ZIP temporário e em seus registros `total_limit`, sem executar modelos ou processamento de vídeo.

O exportador canônico `scripts/export/exportar_ldporto.py` agora reconhece contratos de evidência gerada **somente sob `docs/reports`**: manifests de pacote/handoff/projeto, o índice de amostras de câmera e o conjunto timeline/config/provenance de replays. Nesse escopo omite do ZIP de fontes imagens e dados JSON/JSONL/CSV/TSV maiores que 1 MiB. Mantém relatórios Markdown, JSONs leves, índices, scripts e código. Imagens de documentação ordinária e referências em `src/tests/fixtures/historical_evidence` não foram abrangidas pelo filtro novo.

Nenhum arquivo é apagado ou movido. O manifesto do pacote de fontes registra caminhos, bytes e o motivo `generated_report_payload_retained_locally`. Arquivos de raiz/código/configurações/testes/schemas/scripts têm prioridade anterior aos relatórios. Se o orçamento continuar insuficiente, o pacote permanece PARTIAL_EXPORT com a limitação real.

A leitura de escopo após a correção selecionou 3.013 arquivos, 124.223.496 bytes, e identificou 759 payloads derivados, 318.022.244 bytes, preservados localmente e omitidos do ZIP de fontes. Esses números são um inventário daquele instante; novos relatórios posteriores podem alterá-los. Evidência: `SOURCE_EXPORT_SCOPE.json`.

## Execuções reais

```powershell
./.venv/Scripts/python.exe -m pytest src/tests/test_sol_v4_post_integration.py::test_new_package_has_one_actionable_queue_and_legacy_queue_still_validates src/tests/test_v42_export.py::test_project_export_omits_generated_report_payloads_preserving_reports_and_fixtures src/tests/test_v42_export.py::test_source_priority_keeps_essential_code_when_report_exceeds_remaining_budget -q --junitxml=docs/reports/r63_20261017/legacy_repairs_focused.junit.xml
```

Resultado: três PASS em 1,86 s. Os dois testes novos verificam fontes essenciais dentro do orçamento, exclusão dos payloads gerados, manutenção dos relatórios/fixtures e hashes locais inalterados.

```powershell
./.venv/Scripts/python.exe -m pytest src/tests/test_v42_export.py::test_exporter_self_test src/tests/test_v4_final.py::test_work_package_has_single_derived_manifest_files -q --junitxml=docs/reports/r63_20261017/legacy_exports_repaired.junit.xml
```

Resultado: dois PASS em 24,82 s. Os pacotes de teste foram criados em pastas temporárias; não são o pacote compacto editorial R6.3.

A leitura independente R6.3 tem seus testes próprios em `reader_focused.junit.xml`; esses testes de pacote de fontes não substituem a abertura e a homologação do ZIP compacto real.
