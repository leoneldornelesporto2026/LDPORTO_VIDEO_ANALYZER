"""Causal scheduling in the shared visual pass, without repeated video decoding."""
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
