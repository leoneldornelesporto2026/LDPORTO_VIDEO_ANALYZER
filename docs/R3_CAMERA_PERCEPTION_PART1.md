# Rodada 3 — Parte 1: Câmara e percepção (R4.5)

## Mudanças implementadas

1. `ShortShotSamplingPlan`: até três pontos adicionais planejados por cena de duração até 1,5 s, ordenados e sem atravessar cortes; configurável. A leitura principal continua sequencial com um só decoder; não se criam threads.
2. YuNet + SFace: quando o rosto **é detectado** em cena curta, tenta embedding fresco em amostras distintas. Não cria bbox/rosto ou pessoa por dedução. Sem SFace, a evidência permanece ausente.
3. `19_camera_director`: elimina evidências duplicadas do mesmo alvo; desconsidera mapeamento `UNCERTAIN`, `OFFSCREEN` ou marcado como sem presença contemporânea, além de exigir rosto visível. Conflitos entre duas pessoas continuam sem resolução automática.
4. Diagnósticos adicionais de funil de percepção/câmera e Smart Zoom, separando janelas com rosto, com locutor fundamentado, sem amostra, com beat editorial e com beat suprimido pela segurança de cortes/overlap.
5. Testes dirigidos à amostragem, continuidade em corte, dupla extração de embedding, falsos alvos, mapeamento contraditório e validação de parâmetros.

## Novas configurações

- `vision.short_shot_extra_sampling`: bool, `true` por padrão.
- `vision.short_shot_max_seconds`: número finito de 0,2 a 3, padrão `1.5`.

## Métricas observáveis

No `07_people_tracking.performance`: `short_shot_scheduled_frames`, `short_shot_scheduled_frames_with_face`, `short_shot_scheduled_frames_with_fresh_embedding`, `short_shot_embedding_attempts`. Em `19_camera_director.metrics`: `evaluation_windows_with_face_evidence`, `evaluation_windows_with_grounded_speaker`, `evaluation_windows_with_conflicting_person_targets`, `evaluation_windows_without_visual_sample`, `editorial_beat_raw_windows`, `editorial_beat_eligible_windows`, `editorial_beat_suppressed_due_to_cut_or_overlap`, `editorial_beat_without_focus_windows`, `editorial_beat_with_speaker_focus_windows`, `focused_windows_without_editorial_beat`.

**Importante:** são contagens de evidência, não prova de acerto humano, precisão ou melhoria de coverage. Smart Zoom permanece limitado a eventos editoriais fundamentados; sem beat comprovado, não aplica zoom decorativo.

## Cache e validação

- Preserva `__version__=4.4.0` para compatibilidade geral. Entretanto a etapa `07_people_tracking` possui fingerprint de código/configuração; como mudou `vision.py`, `visual_sampling.py` e config, **um novo run da etapa 07 pode ser necessário**. As etapas dependentes podem ser invalidadas seletivamente. Não excluir `.cache` nem executar `--force` sem necessidade.
- Os testes rodados neste ambiente são em Python 3.13, não substituem a homologação Windows/Python 3.11, YuNet/SFace/MediaPipe/CUDA.
- Próxima medição real: nº de amostras capturadas nas 556 cenas; comparativo de micros com/sem embedding, speaker/person e active speaker, foco resolved e Smart Zoom, erros de identidade por anotação humana em 3–5 clipes.

## Rodadas ainda necessárias

**R3 Parte 2 — Performance:** first-pass/repair semântico (principal custo), cache local, micro-benchmarks de decode/HOG, orçamento de CPU/RAM e workers controlados só após prova de equivalência.

**R4 — Homologação e produto:** benchmark real completo e comparação, revisão de rostos/identidades em amostras, câmera/render na aplicação Curator, Stories/legendas e controles de publicação. Provavelmente uma rodada após dados reais, podendo dividir em duas se erros importantes surgirem.
