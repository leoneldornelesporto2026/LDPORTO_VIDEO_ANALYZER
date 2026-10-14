# SOL V4 — pacote B de identidade e janelas

Implementação concluída; benchmark físico ainda deve ser executado pela raiz.

- `active_speaker.evidence_window_policy` é opcional: `legacy`, `balanced_tail` ou `tail_anchor`. Nenhuma nova chave foi inserida nos defaults ou no YAML ativo.
- `speaker_windows.partition_evidence_slice` mantém a aritmética legacy. Balanceamento só recupera cauda menor que o mínimo; respeita cortes já delimitados, mínimo e máximo configurados.
- `ActiveSpeakerEngine` conserva critérios de associação e estabilidade. Acrescenta planejamento/causas agregadas e amostras/gaps apenas dos candidatos emitidos. Valores bucais nulos permanecem ausência de observação, sem inferir falha de landmarks.
- `_active_stage` preserva os três agregados novos; fingerprint da etapa 10 inclui o helper.
- Re-ID separa sementes, merges e não mapeados; explica gates do melhor candidato e oferece até 24 pares online/offline para revisão humana. Nenhum raw ID se torna prova e nenhum merge é aprovado por esse diagnóstico.
- Busca exata acima de 2.500 templates usa blocos de 256 e concorrente global. Galerias anteriores conservam o caminho numérico original. Robustez futura: o LONGO auditado tem 1.291 identidades, portanto o antigo teto não explica seu resultado.

## Validação executada

`identity_b_focus_01.json`, `.log` e `.xml`: primeira execução, 91 aprovados e uma falha na expectativa do novo canário sintético. A expectativa ignorava a fronteira real do primeiro frame; foi corrigida preservando essa fronteira e os critérios do engine.

`identity_b_focus_02.json`, `.log` e `.xml`: comando exato, duração e SHA-256 dos sete arquivos registrados. Resultado: **96 aprovados, nenhuma falha ou skip, 2,45 s**. Inclui testes novos e regressões de Re-ID, consenso, sincronização e diagnósticos anteriores. Fixtures e sinais são sintéticos, não prova de precisão humana.

## Replay físico preparado, ainda não executado aqui

```powershell
& .venv/Scripts/python.exe -B scripts/dev/benchmark_speaker_windows_sol_v4.py --analysis analysis/video_1da839aad175 --config config/config.yaml --output docs/reports/sol_v4_20261013/speaker_windows_b_cpu.json
```

Payload fixo: fatias 86.26221875–89.83971875, 105.47203333333334–112.82346875 e 164.51159375–168.56159375000001; compara `legacy` e `balanced_tail` sobre o áudio original mono 16 kHz e observações projetadas existentes, cujos chunks são verificados por SHA-256. Registra contadores, scores, bounds e lag recalculados, versões e fontes. Recusa sobrescrever o relatório. Não executa GPU, Ollama, ASR, diarizador ou detector visual.

O resultado mede sinal local em três fatias. Não homologa identidade humana, associação global ou ASD confirmado; a configuração padrão continua legacy.

## Revisão experimental com âncora de cauda

O primeiro replay físico, executado pela raiz e preservado em `speaker_windows_b_cpu.json`, mostrou legacy com 7 janelas / 4 medidas / 4 candidatos / 1 qualificado, contra balanced-tail com 7 / 7 / 7 / 0. Mais áudio medido não melhorou a qualificação; balanced-tail continua experimental e desativado.

A política adicional `tail_anchor` conserva todas as janelas, IDs e scores legacy e acrescenta uma janela limitada ao fim de cada fatia elegível. A âncora tem `measurement_window_kind=tail_anchor` e `measurement_overlap=true`; isso é sobreposição geométrica, não fala simultânea. O campo acústico `overlap` continua calculado pelas vozes originais. Guards existentes de independência por tempo impedem voto duplicado tanto na afinidade global quanto na consistência do lag.

Foco final da revisão: `identity_b_focus_03.{json,log,xml}` registra **101 aprovados, nenhuma falha ou skip, 2,62 s**, incluindo cinco novos canários de âncora — total de 41 casos novos B. O JSON contém comando real e SHA-256 das fontes. Nenhuma inferência real foi executada por este agente.

Novo replay a executar pela raiz, com saída exclusiva e os três modos:

```powershell
& .venv/Scripts/python.exe -B scripts/dev/benchmark_speaker_windows_sol_v4.py --analysis analysis/video_1da839aad175 --config config/config.yaml --output docs/reports/sol_v4_20261013/speaker_windows_b_cpu_anchor.json
```

Essa revisão também permanece desativada por padrão. Não altera thresholds, estabilidade, identidade, gates ou contratos de publicação.

## Fechamento integrado pela raiz

O replay acima foi executado e preservado em `speaker_windows_b_cpu_anchor.json`: legacy 7/4/4/1, balanced-tail 7/7/7/0 e tail-anchor 10/7/7/1 (janelas/medidas/candidatos/qualificados). A âncora preservou o sinal qualificado, sem aumentá-lo; ASD global não foi homologado. Replay integral de Re-ID em `reid_preservation.json` conservou todos os campos legados, 1.291 identidades e o mesmo proxy de fragmentação.

Regressão final **1.892 passed, três skipped, zero falhas**, 100 casos novos, todos os 1.795 anteriores preservados. `final_integrity.json` verifica 1.041 arquivos originais, ZIP, mídia, modelo, exports, HEAD e 478 fontes congelados. `RELATORIO_TECNICO.md`/`CHECKPOINT.md` finais prevalecem sobre os estados históricos deste documento.
