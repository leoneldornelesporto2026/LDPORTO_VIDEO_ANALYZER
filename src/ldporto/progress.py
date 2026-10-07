"""Local structured execution events and empirical, weighted ETA estimates."""
from collections import deque
from statistics import median
import math
import time


EVENT_PREFIX = 'LDPORTO_EVENT '
STAGE_WEIGHTS = {
    '00_preflight': 8., '00_source': 20., '01_metadata': .453, '02_audio': 12.766,
    '03_audio_quality': 10.687, '04_transcription': 767.391,
    '05_diarization': 134.203, '06_scenes': 973.781,
    '07_people_tracking': 3211.469, '08_person_reid': .781,
    '09_person_motion': 1.344, '10_active_speaker': .953,
    '11_shots': .156, '12_camera_timeline': 1.516, '13_ocr': .1,
    '14_audio_events': .1, '15_semantic': 11606.375,
    '16_understanding': 8.484, '17_master_timeline': 2.782,
    '18_analysis_quality': .172, '18b_global_camera_planner': 1.,
    '19_camera_director': 4., '19b_preview_verifier': 30.,
    '20_handoff': 98.7, '21_second_curation_handoff': 20.,
}
STAGE_LABELS = {
    '00_preflight': 'Preflight', '00_source': 'Obtendo midia', '01_metadata': 'Metadata', '02_audio': 'Audio',
    '03_audio_quality': 'Qualidade de audio', '04_transcription': 'Transcricao',
    '05_diarization': 'Diarizacao', '06_scenes': 'Shots visuais',
    '07_people_tracking': 'Tracking visual', '08_person_reid': 'Re-ID',
    '09_person_motion': 'Movimento', '10_active_speaker': 'Active Speaker',
    '11_shots': 'Shot classification', '12_camera_timeline': 'Camera timeline',
    '13_ocr': 'OCR', '14_audio_events': 'Audio events', '15_semantic': 'Semantica',
    '16_understanding': 'Understanding', '17_master_timeline': 'Master timeline',
    '18_analysis_quality': 'Quality gates', '18b_global_camera_planner': 'Global Planner',
    '19_camera_director': 'Camera Director / Smart Zoom', '19b_preview_verifier': 'Preview Verifier',
    '20_handoff': 'Artefatos de analise', '21_second_curation_handoff': 'Pacote segunda curadoria',
}
TERMINAL = {'ok', 'partial', 'degraded', 'skipped', 'unavailable', 'failed', 'blocked', 'cancelled', 'complete'}


def emit_event(event):
    import json
    from .core import scrub, sanitize_json_numbers
    print(EVENT_PREFIX + scrub(json.dumps(sanitize_json_numbers(event), ensure_ascii=False, allow_nan=False, default=str)), flush=True)


def human_duration(seconds, approximate=False):
    if seconds is None:
        return 'calculando...'
    minutes = max(0, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    label = f'{hours}h{minutes:02d}m' if hours else f'{minutes}m' if minutes else '<1m'
    return ('~' if approximate else '') + label


class WeightedProgress:
    def __init__(self, weights=None, clock=None):
        self.weights = dict(weights or STAGE_WEIGHTS)
        self.clock = clock or time.monotonic
        self.started = self.clock()
        self.states = {}
        self.current_stage = None
        self.samples = {}
        self.last_units = {}
        self.last_fraction = 0.
        self.finished = False
        self.succeeded = False
        self.completion = None
        self.historical = {}

    def update(self, event):
        if event.get('historical_stage_estimates'):
            self.historical = event['historical_stage_estimates']
            for stage, row in self.historical.items():
                if stage in self.weights:
                    self.weights[stage] = row['median_seconds']
        if event.get('event') in {'run_completed', 'run_failed', 'run_cancelled'}:
            self.finished = True
            self.succeeded = event['event'] == 'run_completed'
            self.completion = event
            return self.snapshot()
        stage = event.get('stage')
        if not stage:
            return self.snapshot()
        self.weights.setdefault(stage, 1.)
        state = {**self.states.get(stage, {}), **event}
        state.setdefault('started_at', self.clock())
        self.states[stage] = state
        if state.get('status') == 'running':
            self.current_stage = stage
        current, elapsed = state.get('current'), state.get('elapsed_seconds')
        if isinstance(current, (int, float)) and isinstance(elapsed, (int, float)):
            previous = self.last_units.get(stage)
            if previous and current > previous[0] and elapsed >= previous[1]:
                self.samples.setdefault(stage, deque(maxlen=12)).append((elapsed - previous[1]) / (current - previous[0]))
            if not previous or current > previous[0]:
                self.last_units[stage] = current, elapsed
        return self.snapshot()

    def snapshot(self):
        now = self.clock()
        stage = self.current_stage
        state = self.states.get(stage, {})
        total, current = state.get('total'), state.get('current')
        stage_fraction = min(1., max(0., current / total)) if isinstance(total, (int, float)) and total > 0 and isinstance(current, (int, float)) else None
        completed = sum(self.weights[name] for name, value in self.states.items() if value.get('status') in TERMINAL)
        partial = self.weights.get(stage, 0) * (stage_fraction or 0) if state.get('status') not in TERMINAL else 0.
        fraction = (completed + partial) / max(1e-9, sum(self.weights.values()))
        self.last_fraction = max(self.last_fraction, min(.999 if not self.finished else 1., fraction))
        if self.finished and self.succeeded:
            self.last_fraction = 1.
        samples = list(self.samples.get(stage, []))
        stage_eta = eta_range = None
        if len(samples) >= 3 and stage_fraction is not None and total > current:
            center = median(samples)
            ordered = sorted(samples)
            lower, upper = ordered[int((len(ordered) - 1) * .1)], ordered[int((len(ordered) - 1) * .9)]
            typical = center
            stage_eta = typical * (total - current)
            if upper > max(1e-6, lower) * 1.8:
                eta_range = [lower * (total - current), upper * (total - current)]
        ordered_stages = list(self.weights)
        next_stage = next((name for name in ordered_stages[ordered_stages.index(stage) + 1:] if self.states.get(name, {}).get('status') not in TERMINAL), None) if stage in ordered_stages else None
        remaining = [name for name in ordered_stages if name != stage and self.states.get(name, {}).get('status') not in TERMINAL]
        future = sum(self.weights[name] for name in remaining)
        total_eta = stage_eta + future if stage_eta is not None else None
        total_range = [(eta_range or [stage_eta, stage_eta])[0] + .6*future,
                       (eta_range or [stage_eta, stage_eta])[1] + 1.8*future] if stage_eta is not None else None
        return {'overall_fraction': self.last_fraction, 'stage': stage, 'stage_label': STAGE_LABELS.get(stage, stage),
                'stage_fraction': stage_fraction, 'current': current, 'total': total,
                'elapsed_seconds': now - self.started,
                'stage_elapsed_seconds': now - state.get('started_at', now),
                'stage_eta_seconds': stage_eta, 'total_eta_seconds': total_eta,
                'stage_eta_range_seconds': eta_range,
                'total_eta_range_seconds': total_range,
                'historical_stage_count': len(self.historical),
                'eta_basis': 'rolling_unit_median_and_empirical_range' if stage_eta is not None else 'calculating',
                'next_stage': next_stage, 'next_stage_label': STAGE_LABELS.get(next_stage),
                'status': state.get('status', 'waiting'), 'substage': state.get('substage'),
                'stage_states': self.states, 'finished': self.finished, 'completion': self.completion}
