# Sessão 2 — Integridade de ponta a ponta (R4.9)

## Objetivo

Impedir que dados inconsistentes entre Semantic → Understanding → Ranking → Quality Gate → Social → Export façam um resultado parcial parecer pronto. Não elevar limiares artificialmente, não fabricar evidências, não aprovar publicação dentro do Analyzer.

## Mudanças

- `integrity_contracts.audit_editorial_contract`: verifica status de etapas editoriais, causas upstream, status P0 do Quality Gate e formatos de coleções; erros trazem `path`, `expected`, `received`, `code` sem expor falas nem credenciais.
- O exportador revalida as etapas e o pacote informado e bloqueia shortlist/Stories se qualquer uma das duas fontes indicar integridade comprometida. Mantém catálogo diagnóstico para auditoria, mas não o declara elegível.
- Métricas comerciais, shortlist, candidatos e Stories passam a usar **o mesmo conjunto definitivo de candidatos já reclassificados**. O `summary/quality_summary.json`, o `summary/analysis_summary.json`, o `summary/final_quality_gate.json`, `editorial/final_gate_report.json` e a lista `editorial/excluded_commercials.json` devem concordar.
- `SECOND_CURATION_MANIFEST.json`, `CURATION_INDEX.json` e `SECOND_CURATOR_BRIEF.json` recebem `workflow`, derivado centralmente de `readiness`. `READY_FOR_REVIEW` **não** significa preview aprovado ou publicação autorizada.
- `validate_core_package` confere consistência **semântica**, além dos hashes. Isso não é assinatura criptográfica nem impede adulteração maliciosa coordenada, mas impede bugs que produzem arquivos internamente contraditórios com checksums corretos.
- `generate_visuals_on_demand` atualiza o mesmo `workflow` sem promover a curadoria parcial por acidente.
- `quality_gate.preview_validated` passa a exigir `status=ok` + quadros realmente verificados; o campo é de **validação técnica**, não aprovação editorial. `preview_approved` e `publication_ready` continuam `false`.

## Contratos / linguagem de estado

- `PARTIAL`: falta evidência ou um upstream essencial falhou. Não existe shortlist/Story autorizado para avançar.
- `READY_FOR_REVIEW`: há shortlist, transcrição e contact sheet presentes, e integridade editorial aprovada para **segunda curadoria humana**. O nome histórico de arquivo `SECOND_CURATION_READY_...zip` mantém compatibilidade; não significa pronto para redes sociais.
- `preview_approved=false`: somente o Curator, após render válido + hash correspondente + revisão, pode aprovar preview.
- `publication_ready=false`: o Analyzer nunca concede essa autorização.

## Auditoria e recuperação seletiva (sem reprocessar vídeo)

Dentro da raiz do projeto no CMD:

```bat
py -3.11 scripts/dev/audit_pipeline_integrity_s2.py --package "C:\\CAMINHO\\SECOND_CURATION_....zip" --report "diagnostico_s2.json"
py -3.11 scripts/dev/audit_pipeline_integrity_s2.py --analysis "analysis\\video_ID\\analysis.json" --report "diagnostico_analysis_s2.json"
```

Para validar a **correção da Sessão 1** sem Whisper/visão/Ollama:

```bat
py -3.11 scripts/dev/replay_understanding_snapshot.py "CHATGPT_REVIEW_video_....zip" --output-dir "replay_understanding"
```

Esse replay isolado não refaz automaticamente todas as etapas pós-Understanding, nem promete que o pipeline GUI manterá o cache da Semântica: a assinatura de código de `editorial.py` pode alterar a invalidação. Antes de rerodar, confira os logs de `cache hit` por estágio.

## Testes

`src/tests/test_s2_pipeline_integrity.py` provoca falhas de etapa, P0 no quality gate, alterações de catálogo/relatórios/social/workflow com **hashes refeitos**, propagação de exclusão comercial e distinção entre preview técnico e publicação. Rodar suíte completa com `PYTHONPATH=src:. pytest -q` no ambiente auxiliar e depois no Windows/Python 3.11.

## Não alteramos

ASR, diarização, tracking, Re-ID, modelos, semântica/Ollama, performance, câmera ou thresholds. A aceitação final no Curator e a homologação em vídeo real ainda são etapas separadas.

## Auditoria de benchmarks históricos

- Emerson (23 min): ZIP antigo íntegro estruturalmente, mas `editorial_ready=false`, `PARTIAL`. Não publicar/encaminhar como curadoria concluída.
- Clóvis (2h17, pacote antigo): o validador S2 detecta dez candidatos com contradições entre `commercial_classification=excluded` e os campos de elegibilidade. Esse resultado demonstra o problema histórico; **não é um replay completo da nova execução**.
- Não regravamos os ZIPs originais e não simulamos aprovação de publicação.
