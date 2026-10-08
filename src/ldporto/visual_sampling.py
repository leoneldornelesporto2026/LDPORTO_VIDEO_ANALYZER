"""Causal scheduling in the shared visual pass, without repeated video decoding."""
from .core import digest


def speaker_sampling_fingerprint(transcript):
    return digest([{key: segment.get(key) for key in ("start", "end", "speaker")}
                   for segment in transcript.get("segments", [])])


class SamplingScheduler:
    def __init__(self, cfg):
        self.cfg = cfg
        self.burst_until = 0.
        self.last_speaker = None
        self.last_visible_count=None
        self.last_missing_lip_burst=-float('inf')

    def frequency(self, time, *, speaking, speaker, boundary, motion, visible_count, mouth_count):
        cfg = self.cfg
        reasons = []
        if boundary:
            reasons.append('source_boundary')
        if speaking and speaker != self.last_speaker:
            reasons.append('speaker_transition')
        if motion is not None and motion > .08:
            reasons.append('high_motion')
        if speaking and visible_count >= 2 and visible_count!=self.last_visible_count:
            reasons.append('multiple_visible_candidates')
        if speaking and mouth_count == 0 and time-self.last_missing_lip_burst>=10:
            reasons.append('missing_lip_evidence')
            self.last_missing_lip_burst=time
        if reasons:
            self.burst_until = time+1.5
        self.last_speaker = speaker if speaking else None
        self.last_visible_count=visible_count
        if not cfg.get('adaptive_sampling', True):
            return (cfg['speech_sample_fps'] if speaking else cfg['sample_fps']), ['legacy_schedule']
        if time < self.burst_until:
            return max(cfg['sample_fps'], cfg['speech_sample_fps']), reasons or ['burst_hold']
        if speaking:
            return min(cfg['speech_sample_fps'], max(cfg['sample_fps'], 4.)), ['stable_speech']
        return cfg['sample_fps'], ['stable_no_speech']


class ShortShotSamplingPlan:
    """Bounded extra observations for *known* short source shots.

    This is acquisition scheduling, not synthetic identity/face evidence.  It
    never bridges a cut, and cannot generate more than three targets per shot.
    """
    def __init__(self, scenes, *, enabled=True, max_seconds=1.5, start_time=0.):
        self.times = []
        if enabled:
            for scene in scenes:
                a, b = float(scene['start']), float(scene['end'])
                duration = b-a
                if not 0 < duration <= max_seconds:
                    continue
                inset = min(.10, duration * .2)
                targets = [a+inset, (a+b)/2, b-inset]
                for target in targets:
                    if target > start_time + 1e-6 and (not self.times or target-self.times[-1] >= .10):
                        self.times.append(target)
        self.index = 0
        self.due_count = 0

    def due(self, time):
        if self.index >= len(self.times) or time + 1e-6 < self.times[self.index]:
            return False
        while self.index < len(self.times) and self.times[self.index] <= time + 1e-6:
            self.index += 1
        self.due_count += 1
        return True


class ShotBoundarySamplingPlan:
    """At most two additional samples per *long* source shot, on each side of cuts.

    Frames are still read sequentially and a plan never forges a detection.
    Short scenes remain under ShortShotSamplingPlan to avoid duplicate bursts.
    """
    def __init__(self, scenes, *, enabled=True, short_max_seconds=1.5,
                 inset_seconds=.12, start_time=0.):
        targets = set()
        if enabled:
            for shot in scenes:
                start, end = float(shot['start']), float(shot['end'])
                if end-start <= short_max_seconds:
                    continue
                inset = min(inset_seconds, (end-start)/4)
                for target in (start+inset, end-inset):
                    if target > start_time + .000001:
                        targets.add(round(target, 6))
        self.times = sorted(targets)
        self.index = 0
        self.due_count = 0

    def due(self, timestamp):
        if self.index >= len(self.times) or timestamp + 1e-6 < self.times[self.index]:
            return False
        while self.index < len(self.times) and self.times[self.index] <= timestamp + 1e-6:
            self.index += 1
        self.due_count += 1
        return True
