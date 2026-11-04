"""SOL V4 offline equivalence/policy tests, without real models or GPU."""
from copy import deepcopy
from types import SimpleNamespace
import logging
import sys

import cv2
import numpy as np
import pytest

from ldporto import scenes, vision
from ldporto.config import DEFAULTS, load_config, merge, validate
from ldporto.core import Context, digest
from ldporto.face_quality import assess_face
from ldporto.run_status import STAGE_PACKAGES
from test_stage25_body_backends import Faces, Hog, config, no_network
from test_stage57_local_yolo import fake_local


class CpuBoxes:
    def __init__(self, data):
        self.data = np.asarray(data, dtype=np.float32).reshape(-1, 6)
        self.transfers = 0

    def cpu(self):
        self.transfers += 1
        return self


def test_batched_boxes_preserve_filtered_geometry_and_one_transfer(tmp_path, monkeypatch):
    boxes = CpuBoxes([[-10, -5, 330, 190, .8, 0], [10, 20, 60, 100, .9, 1],
                      [0, 0, 20, 30, float('nan'), 0], [30, 20, 10, 100, .9, 0]])
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: [SimpleNamespace(boxes=boxes)])
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([])
    try:
        rows = detector.detect(np.zeros((180, 320, 3), np.uint8))
        assert boxes.transfers == 1
        assert len(rows) == 1 and rows[0]['bbox'] == dict(x=0., y=0., width=1., height=1.)
        assert rows[0]['body_detection_confidence'] == pytest.approx(.8)
        assert detector.calls['yolo_successful_calls'] == 1
        assert detector.hog is None
    finally:
        detector.close()


def test_batched_transfer_failure_uses_existing_hog_policy(tmp_path, monkeypatch):
    class Broken:
        def cpu(self): raise RuntimeError('controlled transfer failure')
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: [SimpleNamespace(boxes=Broken())])
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([])
    original = detector._activate_hog
    def hog():
        original()
        detector.hog = Hog()
    monkeypatch.setattr(detector, '_activate_hog', hog)
    try:
        assert detector.detect(np.zeros((180, 320, 3), np.uint8)) == []
        assert detector.calls['yolo_successful_calls'] == 0
        assert detector.calls['hog_inference_calls'] == 1
        assert detector.body_backend_report['fallback_reason'] == 'yolo_inference_failed'
    finally:
        detector.close()


@pytest.mark.parametrize('box', [dict(x=.2, y=.3, width=.4, height=.4),
                                     dict(x=0., y=0., width=.5, height=.5),
                                     dict(x=.999, y=.999, width=.001, height=.001)])
def test_shared_gray_preserves_quality_and_exact_roi(box, monkeypatch):
    frame = np.random.default_rng(432).integers(0, 256, (80, 120, 3), dtype=np.uint8)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    original = assess_face(frame, box, confidence=.95)
    shared = assess_face(frame, box, confidence=.95, gray=gray)
    assert shared['sharpness'] == original['sharpness']
    assert shared['brightness'] == original['brightness']
    assert shared['rejection_reasons'] == original['rejection_reasons']
    monkeypatch.setattr(cv2, 'Laplacian', lambda *a, **k: pytest.fail('exact ROI recalculated'))
    value, reused = vision._observation_sharpness(gray, box, shared)
    assert reused and value == original['sharpness']


@pytest.mark.parametrize('changed', ['sharpness_roi_pixels', 'sharpness_method',
                                    'sharpness_gray_source', 'sharpness'])
def test_sharpness_mismatch_computes_actual_pixels(changed):
    gray = np.random.default_rng(55).integers(0, 256, (80, 120), dtype=np.uint8)
    face = dict(x=.2, y=.3, width=.4, height=.4)
    quality = dict(sharpness_roi_pixels=[24, 24, 72, 56],
                   sharpness_method='cv2_laplacian_cv64f_variance_gray_v1',
                   sharpness_gray_source='shared_frame_gray', sharpness=1.)
    quality[changed] = float('nan') if changed == 'sharpness' else 'different'
    expected = float(cv2.Laplacian(gray[24:56, 24:72], cv2.CV_64F).var())
    value, reused = vision._observation_sharpness(gray, face, quality)
    assert not reused and value == expected


def test_detector_consumes_shared_gray_once():
    from test_s4_tracking_face_recovery import detector, FakeYuNet, image
    model = detector(FakeYuNet())
    model.cfg['face_rescue_upsample'] = False
    frame = image()
    model.set_frame_gray(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    first = model.detect(frame, 0., 'S')[0]
    second = model.detect(frame, .1, 'S')[0]
    assert first['face_quality']['sharpness_gray_source'] == 'shared_frame_gray'
    assert second['face_quality']['sharpness_gray_source'] == 'bgr_roi'
    assert model.calls['face_quality_calls'] == 2
    assert model.phase_seconds['face_quality'] > 0


def test_subtask_latencies_have_real_denominators_and_unknown_is_null():
    rows = vision._subtask_measurements(
        dict(video_grab=1., video_retrieve=.3, checkpoint_io=.2),
        dict(grab_calls=10, retrieve_calls=3, checkpoint_calls=1), {}, {})
    assert rows['decode']['total_ms'] == 1300 and rows['decode']['mean_ms_per_call'] == 130
    assert rows['retrieve']['mean_ms_per_call'] == 100
    assert rows['serialization']['mean_ms_per_call'] == 200
    assert rows['embedding']['calls'] == 0 and rows['embedding']['mean_ms_per_call'] is None


class Stamp:
    def __init__(self, seconds): self.seconds = seconds


def fake_scenedetect(monkeypatch, *, fail_pyav=False, fallback=False, pts=(0., .4, .8),
                    fail_pyav_decode=False, events=None):
    openings, configured = [], []
    class Video:
        frame_size = (1920, 1080)
        frame_rate = 30.
        base_timecode = Stamp(0.)
        def __init__(self, backend, options):
            self.BACKEND_NAME = 'opencv' if fallback else backend
            self.index = 0
            self.position = Stamp(0.)
            if self.BACKEND_NAME == 'pyav':
                self._video_stream = SimpleNamespace(thread_type=SimpleNamespace(name=options['threading_mode']),
                    codec_context=SimpleNamespace(name='fixture_codec', thread_count=0))
                self._container = SimpleNamespace(close=lambda: events.append('close_pyav_container') if events is not None else None)
                self._io = SimpleNamespace(close=lambda: events.append('close_pyav_io') if events is not None else None)
                self._owns_io = True
            else:
                self.capture = SimpleNamespace(release=lambda: events.append('release_opencv') if events is not None else None)
        def read(self):
            if self.index >= len(pts): return False
            self.position = Stamp(pts[self.index])
            self.index += 1
            return np.zeros((2, 2, 3), np.uint8)
    def open_video(path, backend, **options):
        openings.append((backend, options))
        if events is not None:
            events.append('open_' + backend)
        if fail_pyav and backend == 'pyav': raise RuntimeError('fixture unavailable')
        return Video(backend, options)
    class Detector:
        def __init__(self, **options): configured.append(options)
        def process_frame(self, *args, **kwargs): return []
    class Manager:
        auto_downscale = True
        def add_detector(self, detector): self.detector = detector
        def detect_scenes(self, video, show_progress, frame_skip):
            assert frame_skip == 0 and show_progress is True
            while True:
                frame = video.read()
                if frame is False: break
                if fail_pyav_decode and video.BACKEND_NAME == 'pyav':
                    raise RuntimeError('controlled consumer failure')
                self.detector.process_frame(video.position, frame)
        def get_scene_list(self, start_in_scene):
            assert start_in_scene is False
            return [(Stamp(0.), Stamp(.5)), (Stamp(.5), Stamp(1.))]
    monkeypatch.setitem(sys.modules, 'scenedetect', SimpleNamespace(
        open_video=open_video, ContentDetector=Detector, SceneManager=Manager))
    return openings, configured


def test_default_scene_decoder_preserves_threshold_boundaries_and_eof(monkeypatch, tmp_path):
    openings, configured = fake_scenedetect(monkeypatch)
    cfg = load_config()
    ctx = Context(tmp_path/'fixture.mp4', tmp_path/'out', cfg, 'synthetic', logging.getLogger('scene'))
    result = scenes.SceneEngine().run(ctx, dict(duration=1., fps=30))['data']
    assert openings == [('opencv', {})]
    assert configured == [dict(threshold=27, min_scene_len=18)]
    assert [(row['start'], row['end']) for row in result['scenes']] == [(0., .5), (.5, 1.)]
    performance = result['performance']
    assert performance['frames_returned'] == performance['detector_calls'] == 3
    assert performance['read_calls'] == 4 and performance['eof_read_calls'] == 1
    assert performance['first_pts_seconds'] == 0 and performance['last_pts_seconds'] == .8
    assert performance['boundary_quality_validated'] is False
    assert 'not_additive_to_wall' in performance['thread_accounting']


@pytest.mark.parametrize('mode', ['AUTO', 'FRAME', 'SLICE'])
def test_pyav_threading_is_opt_in_and_preserves_pts(monkeypatch, mode):
    openings, configured = fake_scenedetect(monkeypatch)
    cfg = dict(DEFAULTS['scenes'], backend='pyav', pyav_threading_mode=mode)
    pairs, performance = scenes._detect_measured_scenes('fixture.mp4', cfg, dict(fps=30, duration=1.))
    assert openings == [('pyav', dict(threading_mode=mode, suppress_output=False))]
    assert performance['backend_effective'] == 'pyav' and performance['threading_effective'] == mode
    assert performance['source_fps'] == 30 and performance['frame_skip'] == 0
    assert performance['last_pts_seconds'] == .8 and len(pairs) == 2


@pytest.mark.parametrize('automatic', [False, True])
def test_pyav_failure_and_library_fallback_are_explicit(monkeypatch, automatic):
    openings, _ = fake_scenedetect(monkeypatch, fail_pyav=not automatic, fallback=automatic)
    cfg = dict(DEFAULTS['scenes'], backend='pyav', pyav_threading_mode='AUTO')
    _, performance = scenes._detect_measured_scenes('fixture.mp4', cfg, dict(fps=30, duration=1.))
    assert performance['backend_requested'] == 'pyav' and performance['backend_effective'] == 'opencv'
    assert performance['fallback_reason']
    assert len(openings) == (1 if automatic else 2)


def test_pts_regression_is_reported_without_claiming_complete_decode(monkeypatch):
    fake_scenedetect(monkeypatch, pts=(0., .4, .3))
    _, performance = scenes._detect_measured_scenes('fixture.mp4', DEFAULTS['scenes'], dict(fps=30, duration=1.))
    assert performance['nonmonotonic_pts_count'] == 1
    assert performance['eof_does_not_prove_all_source_frames'] is True
    assert performance['tail_gap_seconds'] > .6


def test_failed_pyav_attempt_closes_before_opencv_fallback(monkeypatch):
    events = []
    fake_scenedetect(monkeypatch, fail_pyav_decode=True, events=events)
    cfg = dict(DEFAULTS['scenes'], backend='pyav', pyav_threading_mode='AUTO')
    _, performance = scenes._detect_measured_scenes('fixture.mp4', cfg, dict(fps=30, duration=1.))
    assert events == ['open_pyav', 'close_pyav_container', 'close_pyav_io', 'open_opencv', 'release_opencv']
    assert [row['status'] for row in performance['attempts']] == ['failed', 'succeeded']
    assert performance['attempts'][0]['resource_cleanup']['closed_resources'] == ['container', 'owned_io']
    assert performance['elapsed_seconds'] >= performance['attempts'][1]['elapsed_seconds']
    assert performance['fallback_exception_type'] == 'RuntimeError'


def test_scene_options_do_not_change_default_config_and_are_cache_dependencies():
    before = digest(DEFAULTS)
    cfg = merge(DEFAULTS, {'scenes': {'backend': 'pyav', 'pyav_threading_mode': 'AUTO'}})
    validate(cfg)
    assert cfg['scenes']['backend'] == 'pyav'
    assert digest(DEFAULTS) == before and 'backend' not in DEFAULTS['scenes']
    assert 'av' in STAGE_PACKAGES['06_scenes']
    with pytest.raises(ValueError, match='desconhecida'):
        merge(DEFAULTS, {'scenes': {'arbitrary_option': True}})


@pytest.mark.parametrize('option,value', [('backend', 'cuda'), ('pyav_threading_mode', 'INVALID')])
def test_invalid_scene_options_are_rejected(option, value):
    cfg = deepcopy(DEFAULTS)
    cfg['scenes'][option] = value
    with pytest.raises(ValueError, match='scenes'):
        validate(cfg)
