# V4.4 Final Audit — checkpoint pós-limite

## Ajustes finais aplicados

1. Corrigido o descompasso documental: o full run já havia confirmado tracking,
   speaker/person e active speaker, embora o relatório ainda dissesse “não executado”.
2. `P0-A` agora é `VERIFIED_FULL_RUN` para cobertura observada; continua sem
   certificação de identidade por ausência de ground truth anotado.
3. Adicionada regressão para impedir que propostas de Smart Zoom sejam contadas
   como movimento entregue. O contrato mantém `proposed_zoom_event_count` e
   `zoom_event_count` separados.
4. Adicionado finalizador idempotente `scripts/dev/finalize_v44.py`, que não
   retoma/reexecuta modelos: apenas valida um full run concluído e gera compare.
5. Criada documentação `V44_FINALIZATION.md` com o fechamento operacional.

## Validação neste pacote

- 405 testes passaram.
- 3 testes foram deselecionados por limitações do ambiente de auditoria:
  - Tkinter requer display gráfico;
  - um teste exige metadata do repositório `.git`, ausente no ZIP exportado;
  - o allowlist de raiz vê os `PROJECT_EXPORT_*` do próprio container de exportação,
    que não são código fonte e foram removidos do ZIP final devolvido.
- `py_compile` passou para finalizer/report/compare e componentes de câmera auditados.

## Evidência full-run já confirmada antes do limite

- diarização: `ok`, ~142.25 s;
- tracking: ~2754.265 s (+3.15% vs V4.3);
- tracklets raw/valid/micro: 6085 / 1818 / 4267;
- speaker/person: 15.0490% (V4.3 3.2065%);
- active speaker: 9.6733% (V4.3 2.4560%);
- provável sem overlap: 8.0853%; confirmado: 0%;
- último checkpoint conhecido da semântica: 13/46 chunks.

## O que não foi inventado/fechado sem os artefatos locais

O export do projeto não contém `.cache/v44_validation/full_run` nem a pasta de
analysis do benchmark. Portanto ficam honestamente dependentes do computador do
usuário após o pipeline concluir:

- semantic fallback final;
- story/payoff final;
- câmera/Smart Zoom final do full run;
- candidatos/shortlist/pacote final;
- compare V4.3→V4.4 completo.

Execute então:

```cmd
.venv\\Scripts\\python.exe scripts\\dev\\finalize_v44.py
```

O comando falha de forma segura se o benchmark ainda não estiver concluído.
