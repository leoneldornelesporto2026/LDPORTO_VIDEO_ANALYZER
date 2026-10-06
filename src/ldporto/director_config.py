"""Validated style parameters for the one shared camera director engine."""
import math

DEFAULTS = {
    'enabled': True, 'profile': 'natural', 'lookahead_seconds': 1.8,
    'min_hold_seconds': 3.0, 'preferred_hold_seconds': 6.0,
    'switch_cooldown_seconds': 3.0, 'speaker_confirm_seconds': .9,
    'short_interruption_seconds': 1.0, 'switch_margin': .15,
    'switch_cost': .08, 'persistence_bonus': .08,
    'enter_confidence': .70, 'exit_confidence': .45,
    'horizontal_deadzone': .06, 'vertical_deadzone': .05,
    'movement_confirm_seconds': .5, 'zoom_deadzone': .035,
    'max_zoom_default': 1.35, 'max_zoom_hard': 1.40,
    'normal_zoom': 1.18, 'breathing_zoom': 1.08, 'payoff_zoom': 1.28,
    'breathing_after_seconds': 20.0, 'tick_seconds': .25,
    'max_observation_gap_seconds': .6, 'max_pan_speed': .12,
    'max_pan_acceleration': .18, 'max_pan_jerk': .60,
    'max_zoom_speed': .035, 'max_zoom_acceleration': .045,
    'max_zoom_jerk': .15, 'output_width': 1080, 'output_height': 1920,
    'min_face_height': .06, 'min_sharpness': 40.0,
    'headroom': .04, 'lead_room': .04,
    'quick_exchange_switches': 3, 'quick_exchange_window_seconds': 5.0,
    'enable_split': True, 'enable_reaction_shots': True,
    'enable_lookahead': True, 'debug_output': True,
    'reaction_threshold': .70, 'reaction_delta': .35,
    'reaction_seconds': 1.8, 'reaction_cooldown_seconds': 20.0,
}
PROFILES = {
    'natural': {},
    'podcast': {'min_hold_seconds': 4., 'preferred_hold_seconds': 9.,
                'switch_cooldown_seconds': 4., 'reaction_cooldown_seconds': 35.},
    'dynamic_short': {'min_hold_seconds': 2.5, 'preferred_hold_seconds': 5.,
                      'switch_cooldown_seconds': 2.5, 'normal_zoom': 1.22},
    'documentary': {'min_hold_seconds': 5., 'preferred_hold_seconds': 10.,
                    'normal_zoom': 1.05, 'enable_reaction_shots': False},
    'conservative': {'min_hold_seconds': 6., 'preferred_hold_seconds': 12.,
                     'normal_zoom': 1.05, 'enable_split': False,
                     'enable_reaction_shots': False},
}


def resolve_config(raw=None):
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("camera_director deve ser objeto")
    raw = raw or {}
    unknown = set(raw)-set(DEFAULTS)
    if unknown:
        raise ValueError('camera_director: opções desconhecidas: '+', '.join(sorted(unknown)))
    profile = raw.get('profile', 'natural')
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError('camera_director.profile inválido')
    cfg = {**DEFAULTS, **PROFILES[profile], **{k: v for k, v in raw.items() if v is not None}}
    for key, default in DEFAULTS.items():
        value = cfg[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise ValueError(f'camera_director.{key} deve ser booleano')
        elif isinstance(default, (float, int)):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError(f'camera_director.{key} deve ser número finito')
            if value < 0:
                raise ValueError(f'camera_director.{key} deve ser não negativo')
            if isinstance(default, int) and (not isinstance(value, int) or value < 1):
                raise ValueError(f'camera_director.{key} deve ser inteiro positivo')
    for key in ('switch_margin', 'switch_cost', 'persistence_bonus', 'enter_confidence',
                'exit_confidence', 'horizontal_deadzone', 'vertical_deadzone', 'zoom_deadzone',
                'min_face_height', 'headroom', 'lead_room', 'reaction_threshold', 'reaction_delta'):
        if not 0 <= cfg[key] <= 1:
            raise ValueError(f'camera_director.{key} deve estar entre 0 e 1')
    if not .1 <= cfg['tick_seconds'] <= 1:
        raise ValueError('camera_director.tick_seconds deve estar entre .1 e 1')
    if not 0 < cfg['max_observation_gap_seconds'] <= 2:
        raise ValueError('camera_director.max_observation_gap_seconds deve estar em (0, 2]')
    for key in ('min_hold_seconds', 'speaker_confirm_seconds', 'max_pan_speed',
                'max_pan_acceleration', 'max_pan_jerk', 'max_zoom_speed',
                'max_zoom_acceleration', 'max_zoom_jerk', 'quick_exchange_window_seconds',
                'reaction_seconds'):
        if cfg[key] <= 0:
            raise ValueError(f'camera_director.{key} deve ser positivo')
    if cfg['preferred_hold_seconds'] < cfg['min_hold_seconds']:
        raise ValueError('preferred_hold_seconds deve ser >= min_hold_seconds')
    if cfg['exit_confidence'] > cfg['enter_confidence']:
        raise ValueError('exit_confidence deve ser <= enter_confidence')
    if not 1 <= cfg['max_zoom_default'] <= cfg['max_zoom_hard'] <= 2:
        raise ValueError('Exigir 1 <= max_zoom_default <= max_zoom_hard <= 2')
    for key in ('normal_zoom', 'breathing_zoom', 'payoff_zoom'):
        if not 1 <= cfg[key] <= cfg['max_zoom_hard']:
            raise ValueError(f'camera_director.{key} fora dos limites de zoom')
    if cfg['lookahead_seconds'] > 5:
        raise ValueError('lookahead_seconds deve ser <= 5')
    limits = {'min_hold_seconds': 60, 'preferred_hold_seconds': 120,
              'switch_cooldown_seconds': 60, 'speaker_confirm_seconds': 10,
              'short_interruption_seconds': 10, 'movement_confirm_seconds': 10,
              'breathing_after_seconds': 600, 'reaction_seconds': 10,
              'reaction_cooldown_seconds': 600, 'quick_exchange_window_seconds': 60,
              'max_pan_speed': 1, 'max_pan_acceleration': 4, 'max_pan_jerk': 20,
              'max_zoom_speed': 1, 'max_zoom_acceleration': 4, 'max_zoom_jerk': 20,
              'output_width': 16384, 'output_height': 16384, 'quick_exchange_switches': 100,
              'min_sharpness': 100000}
    for key, maximum in limits.items():
        if cfg[key] > maximum:
            raise ValueError(f'camera_director.{key} excede {maximum}')
    if cfg['horizontal_deadzone'] > .3 or cfg['vertical_deadzone'] > .3:
        raise ValueError('Deadzone não pode exceder .3 do frame')
    if cfg['headroom'] > .2 or cfg['lead_room'] > .2:
        raise ValueError('Headroom/lead_room não podem exceder .2 do frame')
    return cfg
