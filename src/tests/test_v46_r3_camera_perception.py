"""R3 camera acquisition tests: synthetic fixtures, not performance claims."""
from copy import deepcopy
from collections import defaultdict

import numpy as np
import pytest

from director_fixtures import fixture, turn
from ldporto.camera_director import build_camera_director
from ldporto.config import DEFAULTS, validate
from ldporto.visual_sampling import ShortShotSamplingPlan
from ldporto.vision import PersonDetectionEngine


def test_short_shot_plan_bounded_and_no_long_scene_pollution():
    scenes = [{'start': 0., 'end': .45}, {'start': .45, 'end': 8.},
              {'start': 8., 'end': 9.2}]
    plan = ShortShotSamplingPlan(scenes, max_seconds=1.5)
    assert 2 <= len(plan.times) <= 6
    assert all(t < .45 or 8. <= t < 9.2 for t in plan.times)
    assert all(b>a for a,b in zip(plan.times, plan.times[1:]))
    for t in np.arange(0, 9.4, 1/30):
        plan.due(float(t))
    assert plan.due_count >= 4
    assert plan.due(20) is False


def test_short_shot_resume_never_replays_old_extra_samples():
    scenes = [{'start': 0., 'end': 1.}, {'start': 1., 'end': 2.}]
    plan = ShortShotSamplingPlan(scenes, start_time=1.1, max_seconds=1.5)
    assert plan.times and min(plan.times) > 1.1
    assert not plan.due(.8)
    assert plan.due(2.1)
    assert plan.due_count == 1


def test_short_shot_plan_can_be_disabled():
    assert ShortShotSamplingPlan([{'start':0., 'end':1.}], enabled=False).times == []


class FakeDetector:
    def setInputSize(self, dims):
        self.dims = dims

    def detect(self, frame):
        # YuNet format [x,y,w,h, eye ... , confidence].
        v = np.zeros((1, 15), dtype=np.float32)
        v[0, :4] = (12., 10., 24., 30.)
        v[0, 14] = .98
        return None, v


class FakeSFace:
    def __init__(self):
        self.calls = 0

    def alignCrop(self, frame, row):
        self.calls += 1
        return frame

    def feature(self, frame):
        return np.array([[1., 0., 0., 0.]], dtype=np.float32)


def make_detector():
    import cv2
    detector = object.__new__(PersonDetectionEngine)
    detector.cv2 = cv2
    detector.cfg = {**DEFAULTS['vision'], 'embedding_interval_seconds': 2.0}
    detector.cfg["face_quality_gate"] = False  # mocked flat-black frame
    detector.cfg["face_rescue_upsample"] = False  # mock detector does not scale rows
    detector.notes = []
    detector.phase_seconds = defaultdict(float)
    detector.calls = defaultdict(int)
    detector.face_history = []
    detector.last_body_time = -float('inf')
    detector.last_shot = None
    detector.face = FakeDetector()
    detector.sface = FakeSFace()
    detector.hog = detector.yolo = None
    return detector


def test_short_shot_collects_two_independent_embeddings_without_inventing_face():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    short = make_detector()
    for t in (.1, .5):
        short.set_frame_context(t, 'S1', 1.)
        rows = short.detect(frame)
        assert len(rows) == 1 and rows[0]['embedding'] is not None
    assert short.calls['short_shot_embedding_attempts'] == 2
    assert short.sface.calls == 2
    normal = make_detector()
    for t in (.1, .5):
        normal.set_frame_context(t, 'S1', 8.)
        normal.detect(frame)
    assert normal.sface.calls == 1


def test_short_shot_resets_embedding_history_at_hard_cut():
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    model = make_detector()
    model.set_frame_context(1., 'S1', 8.)
    model.detect(frame)
    model.set_frame_context(1.2, 'S2', 8.)
    model.detect(frame)
    assert model.sface.calls == 2


def test_camera_deduplicates_consistent_duplicate_windows():
    metadata, vision, shots = fixture(12)
    a = turn(0, 12, confidence=.95)
    b = dict(a, confidence=.91)
    result = build_camera_director(metadata, vision, shots, [a, b], [],
                                   {'dominant_face_fallback': False})['data']
    assert any(row.get('focus_person') == 'PERSON_A' for row in result['timeline'])
    assert result['metrics']['evaluation_windows_with_conflicting_person_targets'] == 0


def test_camera_ignores_explicitly_uncertain_or_offscreen_speaker():
    metadata, vision, shots = fixture(8)
    for field in ({'active_speaker_state': 'UNCERTAIN'},
                  {'offscreen_state': True},
                  {'contemporary_visual_presence': False}):
        raw = {**turn(0, 8, confidence=.98), **field}
        result = build_camera_director(metadata, vision, shots, [raw], [],
                                       {'dominant_face_fallback': False})['data']
        assert all(not row['focus_person'] for row in result['timeline'])
        assert result['metrics']['evaluation_windows_with_grounded_speaker'] == 0


def test_camera_rejects_conflicting_simultaneous_targets():
    metadata, vision, shots = fixture(10, pair=True)
    turns = [turn(0, 10, person='PERSON_A', speaker='S1'),
             turn(0, 10, person='PERSON_B', speaker='S1')]
    result = build_camera_director(metadata, vision, shots, turns, [],
                                   {'dominant_face_fallback': False})['data']
    assert all(row['focus_person'] is None for row in result['timeline'])
    assert result['metrics']['evaluation_windows_with_conflicting_person_targets'] > 0


def test_new_config_rejects_invalid_sampling_budget():
    cfg = deepcopy(DEFAULTS)
    cfg['vision']['short_shot_max_seconds'] = 22
    with pytest.raises(ValueError, match='short_shot_max_seconds'):
        validate(cfg)
