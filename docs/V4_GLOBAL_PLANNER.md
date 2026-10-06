# Global Camera Planner V4

O Planner executa depois de `camera_timeline` e antes do Camera Director. Ele gera um pequeno conjunto de estados válidos por janela, elimina geometrias inseguras e usa otimização dinâmica determinística com custo de transição e recompensa por permanecer no estado atual.

Estados atualmente materializados quando há evidência: `SOURCE_FULL_FRAME`, `SINGLE_PERSON_MEDIUM_CLOSE`, `TWO_SHOT`, `SPLIT`. Estados não são criados vazios só para cumprir nomenclatura.

O Planner considera source-frame como decisão válida, cobra custo por switch/split e produz `rejected_candidates`. `dynamic_short` altera preferência, nunca hard safety. O Director recebe o plano como orientação; qualquer conflito com segurança, presença contemporânea, hold, hard cut ou geometria pode ser rejeitado.

## Determinismo

Tempo de execução não entra em `camera_plan.json`. Mesma evidência + mesma config + mesma versão devem produzir o mesmo plano.
