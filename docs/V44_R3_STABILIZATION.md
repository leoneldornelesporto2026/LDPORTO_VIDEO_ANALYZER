# V4.4 R3 — Stabilization Build

Build label: `R3`  
Semantic version/cache identity: `4.4.0`

A identificação interna permanece `4.4.0` de propósito. O cache usa a versão do
Analyzer como parte do fingerprint; trocar para 4.4.1 somente para nomear este
hotfix faria stages caros perderem reuse. O build `R3` é gravado na proveniência
e nos pacotes de segunda curadoria sem alterar essa identidade de cache.

## Ajustes consolidados

1. **Understanding contract hardening**
   - normaliza `topics`, `moments`, `questions_answers`, `program_sections`;
   - tolera `editorial_review` legado como lista;
   - descarta somente linhas não-objeto;
   - registra `semantic_contract_normalized`;
   - não inventa evidência.

2. **Downstream hardening**
   - relatórios e second-curation package não assumem mais que
     `ollama_editorial_review` é sempre mapping;
   - payload inválido não derruba uma análise já concluída.

3. **Readiness explicável**
   - `SECOND_CURATOR_BRIEF`, `CURATION_INDEX`, manifest e resultado exportam
     `readiness_reasons`/`capability_reasons`;
   - `PARTIAL` passa a informar a causa concreta, não apenas booleanos.

4. **Export limpo**
   - `PROJECT_EXPORT_*` agora vive sob `.package/` dentro do ZIP;
   - extrair o pacote não viola o root allowlist do repositório.

5. **Pequenos polimentos**
   - link duplicado removido do HTML;
   - testes Tk/Git diferenciam ambiente headless/exportado de regressão real.

## Validação

- `410 passed, 2 skipped` no ambiente de auditoria;
- skips: Tk sem display e ausência proposital de `.git` em pacote exportado;
- `python -m compileall` passou;
- exportador gerou pacote limpo com 221 arquivos e metadata em `.package/`.

## Retomada recomendada

Para um run que parou em `16_understanding`, manter `analysis/` e `.cache/`, usar
a mesma URL/configuração e **não usar `--force`**. Como a versão permanece 4.4.0
e somente os arquivos downstream mudaram, stages caros anteriores continuam
aptos a cache reuse; Understanding e dependentes são recalculados conforme seus
fingerprints.
