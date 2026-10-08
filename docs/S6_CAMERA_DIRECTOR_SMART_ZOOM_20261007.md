# R4.9 — Sessão 6: Camera Director e Smart Zoom

## Escopo implementado

Partiu do ZIP S5, mantendo API, esquema de timelines (v4.3), behavior fail-closed de identidade, checkpoints existentes, Curator/Preview e saída de segunda curadoria.

### 1) Foco: 4,39% não pode ser explicado somente pelo número final

Novo `metrics.focus_evidence_funnel` mede de forma **mutuamente exclusiva e por duração**:

- `NO_CONTEMPORARY_VISUAL_SAMPLE`: não há frame recente no mesmo shot;
- `NO_PERSON_OBSERVATION` / `NO_VISIBLE_FACE`: visibilidade insuficiente;
- `AUDIO_OVERLAP`: áudio ambíguo, sem alvo de fala única;
- `NO_CONFIRMED_AUDIO_VISUAL_TARGET`: a identidade do falante não foi confirmada no intervalo;
- `AMBIGUOUS_CONFIRMED_TARGETS`: múltiplos alvos contemporâneos;
- `CONFIRMED_TARGET_UNSAFE_CROP`: a associação é comprovada mas crop é inseguro;
- `CONFIRMED_TARGET_CROP_ELIGIBLE`: o candidato satisfaz a primeira triagem.

Buckets são diagnósticos da **entrada do Director**, não medem acurácia de identidade, nem substituem o ranking de layouts. Métricas adicionais: janelas com fallback visual, rejeição pelo pré-planejamento, splits inviáveis e supressões de trocas. Comparar `resolved_focus_coverage`, `known_speaker_focus_fraction` e `dominant_face_coverage`: aumentar a cobertura somente por rosto dominante NÃO aumenta a certeza sobre quem fala.

Sem os artefatos da execução Emerson/Clóvis contendo os 4,39%, nenhuma causa quantitativa está comprovada.

### 2) Crop preflight temporal antes de digital zoom

`src/ldporto/camera_preflight.py` valida geometria atual e frames seguintes **do mesmo shot e da mesma identidade já observada**. Verifica face, cabeça, limites e zoom máximo, evitando deslocar automaticamente a câmera para um crop que expulse o rosto. Um único frame não autoriza o Smart Zoom. Ausência de evidência é motivo de abstenção, não de completar dados imaginados. O crop seguro permite manter enquadramento base quando não há evidência suficiente para zoom.

Novas opções `camera_director`:

```yaml
camera_director:
  crop_preflight_seconds: 0.75
  split_preflight_seconds: 1.0
```

Limites: (0, 3] s, com comportamento conservador. Ajustar na GUI/arquivo config apenas após os testes do seu vídeo.

### 3) Split de dois participantes sem distorção

Antes o retângulo era calculado para a tela vertical completa, mas renderizado em cada **meia tela**. Agora cada crop é calculado com o aspecto da metade do quadro (por exemplo, 270x960 numa preview 540x960). São exigidos dois rostos associados a IDs persistentes, visão contemporânea, geometria segura e confirmação ao longo do lookahead. Não associar pessoa por estar à esquerda/direita nem inventar o falante durante sobreposição de áudio. Split não substitui a conservação de plano de TV já adequado.

### 4) Smart Zoom: investigação dos três zeros

Novos contadores separam:

1. `editorial_beat_raw_windows`: janela com hook/punchline/desfecho **referenciado por segmento**;
2. `editorial_beat_eligible_windows`: beats que sobreviveram a corte próximo/fala sobreposta/troca rápida;
3. `zoom_opportunity_window_count`: oportunidades elegíveis (contadas antes de compactar a timeline);
4. `zoom_request_window_count`: tentativas novas após persistência temporal (não repete pedido a cada tick);
5. `zoom_accepted_event_count` e `zoom_delivered_event_count`: state machine aceitou vs keyframes entregaram movimento efetivo;
6. `zoom_block_reason_counts` e `zoom_zero_root_cause`: triagem do possível gargalo.

Agora também usa `hook_type` da etapa Understanding **somente** quando é `reveal`/`emotional_statement`, com `hook_score >= 0.7` e `evidence_segment_ids`. Um Q&A somente produz beat de resposta quando `question_answer_complete=true`, timestamps e IDs de segmentos de resposta existem. Não criar beats pela simples presença de pergunta, música ou pontuação.

`zoom_zero_root_cause` é diagnóstico heurístico, não causalidade comprovada para o benchmark sem dados. Zoom só é solicitado quando o crop é seguro, existem pelo menos duas amostras temporais distintas, o participante está confirmado, há duração antes do próximo corte e o plano original não está fechado. Não alterar artificialmente a taxa de eventos.

### 5) Preview Verifier: borda não é sinônimo de fundo preto

`border_geometry_evidence` exige uma faixa escura quase uniforme, **descontinuidade perceptível** em direção ao interior e repetição ao longo de frames. O detector ignora barras pretas deliberadas de `SOURCE_FULL / fit_with_padding` e não confunde automaticamente estúdio escuro com erro. O alerta `UNEXPECTED_BORDER` agora relata lados/frequência/exemplo e sugere inspecionar o matte/fonte. Não tenta corrigir cegamente uma faixa de estúdio.

O Preview Verifier continua verificando clipping, zoom excessivo, bombeamento, fluxo e saída; o protocolo não prova ausência de erros sem rodar no arquivo fonte real.

### 6) Câmera sem movimentos nervosos

Preservados: histerese, duração mínima, cooldown, deadzone, limites de velocidade/aceleração/jerk, reset em corte real, antecipação limitada ao shot e veto a crops inseguros. Pré-planejamento descarta zoom inviável e split inseguro antes da animação. Uma falha crítica volta ao source, nunca a outro participante por inferência.

### 7) Auditoria offline (sem rerodar Whisper/visão/ASD)

Com artefatos da execução:

```powershell
.venv\Scripts\python.exe scripts\dev\audit_camera_s6.py "C:\analises\EMERSON_CLOVIS" --output "C:\analises\s6_audit"
```

Com ZIP do run contendo `19_camera_director.json`:

```powershell
.venv\Scripts\python.exe scripts\dev\audit_camera_s6.py "C:\pacotes\review.zip" --output "C:\analises\s6_audit"
```

Para **replay apenas do Director**, quando presentes `01_metadata`, `08_person_reid`, `11_shots`, `10_active_speaker`, `15_semantic`, `16_understanding`:

```powershell
.venv\Scripts\python.exe scripts\dev\audit_camera_s6.py "C:\analises\EMERSON_CLOVIS" --output "C:\analises\s6_replay" --replay
```

Artefatos: `camera_s6_diagnostic.json` e, para replay, `camera_director_s6_timeline.json`. A CLI não exige rede, não carrega modelos nem decodifica vídeo. O replay pode divergir de uma execução antiga se faltarem stages ou se o config/semântica do novo Director não for idêntico; não usá-lo como medição de produção.

### 8) Homologação real pendente

- Comparar 4,39% antigo com `resolved_focus_coverage` novo e as parcelas dos sete buckets;
- Registrar antes/depois para falante conhecido, fallback visual, source preservation e falsos focos;
- Revisar manualmente source close-ups, panorâmicas, reação, interrupção, split e TV cut;
- Auditar zero beats, zero requests e zero delivered **separadamente**; marcar vídeos naturalmente sem oportunidade válida;
- Renderizar canários reais, revisar alertas de borda e inspecionar com vídeo e player;
- Medir jitter, switches/minuto, zoom reversals, face clipping, ratio de upscale;
- Homologar `.venv` Python 3.11 + FFmpeg/OpenCV no Windows alvo.

**Limitações**: dados da rodada com 4,39%/zero zooms não estavam no ZIP de código. Testes sintéticos e replays são regressão, NÃO prova de melhora quantitativa no vídeo real. O modelo continua recomendando câmera: não há aprovação automática de publicação.
