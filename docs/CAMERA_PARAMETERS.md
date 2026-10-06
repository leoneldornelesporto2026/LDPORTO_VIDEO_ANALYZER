# Parâmetros do Camera Director

Defaults do perfil natural. Overrides de perfis: CAMERA_DIRECTOR_V3.md.

Tempos em segundos; posições/deadzone em fração do frame; limites de pan em fração/s, /s², /s³; zoom em fator/s, /s², /s³. Scores não são probabilidades calibradas.

| Campo | Default |
|---|---|
| `enabled` | `true` |
| `profile` | `natural` |
| `lookahead_seconds` | `1.8` |
| `min_hold_seconds` | `3.0` |
| `preferred_hold_seconds` | `6.0` |
| `switch_cooldown_seconds` | `3.0` |
| `speaker_confirm_seconds` | `0.9` |
| `short_interruption_seconds` | `1.0` |
| `switch_margin` | `0.15` |
| `switch_cost` | `0.08` |
| `persistence_bonus` | `0.08` |
| `enter_confidence` | `0.7` |
| `exit_confidence` | `0.45` |
| `horizontal_deadzone` | `0.06` |
| `vertical_deadzone` | `0.05` |
| `movement_confirm_seconds` | `0.5` |
| `zoom_deadzone` | `0.035` |
| `max_zoom_default` | `1.35` |
| `max_zoom_hard` | `1.4` |
| `normal_zoom` | `1.18` |
| `breathing_zoom` | `1.08` |
| `payoff_zoom` | `1.28` |
| `breathing_after_seconds` | `20.0` |
| `tick_seconds` | `0.25` |
| `max_observation_gap_seconds` | `0.6` |
| `max_pan_speed` | `0.12` |
| `max_pan_acceleration` | `0.18` |
| `max_pan_jerk` | `0.6` |
| `max_zoom_speed` | `0.035` |
| `max_zoom_acceleration` | `0.045` |
| `max_zoom_jerk` | `0.15` |
| `output_width` | `1080` |
| `output_height` | `1920` |
| `min_face_height` | `0.06` |
| `min_sharpness` | `40.0` |
| `headroom` | `0.04` |
| `lead_room` | `0.04` |
| `quick_exchange_switches` | `3` |
| `quick_exchange_window_seconds` | `5.0` |
| `enable_split` | `true` |
| `enable_reaction_shots` | `true` |
| `enable_lookahead` | `true` |
| `debug_output` | `true` |
| `reaction_threshold` | `0.7` |
| `reaction_delta` | `0.35` |
| `reaction_seconds` | `1.8` |
| `reaction_cooldown_seconds` | `20.0` |

Tipos/limites e relações são validados em `src/ldporto/director_config.py`. Zoom tem teto hard 1.40 por padrão; elevar explicitamente até 2 é possível, mas ainda limitado pela resolução/geometria. Nenhum override libera crop inseguro.
