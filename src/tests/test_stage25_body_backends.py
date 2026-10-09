"""Offline backend/geometry fixtures; no claim of real seated-person recall."""
import logging
import socket
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from ldporto.config import load_config
from ldporto.core import Context
from ldporto import preflight, vision


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("network access attempted")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def config(tmp_path, **updates):
    cfg = load_config()
    cfg['vision'].update(yunet_model=str(tmp_path/'missing.onnx'),
                         sface_model=str(tmp_path/'missing-sface.onnx'),
                         yolo_model=str(tmp_path/'missing.pt'),
                         active_speaker=False, checkpoint_seconds=0,
                         max_thumbnails=0, face_rescue_upsample=False,
                         **updates)
    return cfg


@pytest.mark.parametrize('backend', ['auto', 'yolo'])
@pytest.mark.parametrize('offline', [True, False])
def test_missing_local_weights_never_calls_yolo(tmp_path, monkeypatch, backend, offline):
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *a: pytest.fail('missing weights passed to YOLO')))
    cfg = config(tmp_path, body_backend=backend)
    notes = []
    detector = vision.PersonDetectionEngine(cfg['vision'], notes, offline)
    try:
        assert detector.body_backend_report['fallback_reason'] == 'yolo_local_model_missing'
        assert detector.backend_execution()['executed_backends'] == []
        assert detector.detect(np.zeros((180, 320, 3), dtype=np.uint8)) == []
        report = detector.backend_execution()
        assert report['executed_backends'] == ['hog']
        assert report['quality'] == 'degraded'
        assert report['inference_calls'] == {'yolo': 0, 'hog': 1}
        assert report['nvidia_validated'] is None
        assert notes
    finally:
        detector.close()


@pytest.mark.parametrize('failure', ['import', 'load'])
def test_local_weights_import_and_load_failures(tmp_path, monkeypatch, failure):
    path = tmp_path/'fixture.pt'
    path.write_bytes(b'synthetic placeholder, not model weights')
    cfg = config(tmp_path)
    cfg['vision']['yolo_model'] = str(path)
    def bad_load(*args):
        raise ValueError('fixture invalid weights')
    monkeypatch.setitem(sys.modules, 'ultralytics', None if failure == 'import'
                        else SimpleNamespace(YOLO=bad_load))
    model, report = vision.load_local_yolo(cfg['vision'])
    assert model is None
    assert report['fallback_reason'] == ('yolo_import_failed' if failure == 'import' else 'yolo_model_load_failed')
    assert report['exception_type'] == ('ModuleNotFoundError' if failure == 'import' else 'ValueError')


class Faces:
    def __init__(self, rows):
        self.rows = rows
    def setInputSize(self, dims):
        pass
    def detect(self, frame):
        rows = np.zeros((len(self.rows), 15), dtype=np.float32)
        for index, coords in enumerate(self.rows):
            rows[index, :4] = coords
            rows[index, 14] = .97
        return None, rows


class Hog:
    def __init__(self, boxes=()):
        self.boxes = boxes
    def detectMultiScale(self, frame, **kwargs):
        return np.array(self.boxes), np.ones(len(self.boxes))


def test_seated_wide_shot_and_partial_face_preserve_only_observed_boxes(tmp_path):
    cfg = config(tmp_path, body_backend='hog')
    detector = vision.PersonDetectionEngine(cfg['vision'], [])
    # Two seated guests with no full-body HOG detection; one face at frame edge.
    detector.face = Faces([(30, 40, 35, 40), (285, 35, 35, 45)])
    detector.hog = Hog()
    try:
        rows = detector.detect(np.zeros((180, 320, 3), dtype=np.uint8), 0., 'WIDE')
        assert len(rows) == 2
        assert all(r['bbox_kind'] == 'face' and r['bbox'] == r['face_bbox'] for r in rows)
        assert all(not r['body_visible'] and r['embedding'] is None for r in rows)
        tracker = vision.Tracker(cfg['vision'])
        first = tracker.update(rows, 0., 'WIDE')
        second = tracker.update(rows, .5, 'WIDE')
        cut = tracker.update(rows, 1., 'CLOSE')
        assert [r['track_id'] for r in first] == [r['track_id'] for r in second]
        assert {r['person_id'] for r in first}.isdisjoint(r['person_id'] for r in cut)
        assert all(r['same_person_confidence'] is None for r in first + second + cut)
        assert all(not r['identity_is_inference'] for r in first + second + cut)
        assert tracker.gallery == {}
    finally:
        detector.close()


def test_seated_yolo_cpu_and_body_only_evidence(tmp_path, monkeypatch):
    path = tmp_path/'fixture.pt'
    path.write_bytes(b'synthetic placeholder')
    calls = []
    def predict(frame, **kwargs):
        calls.append(kwargs)
        # Partial seated bodies, no full-height requirement.
        boxes = [SimpleNamespace(xyxy=[SimpleNamespace(cpu=lambda coords=coords: SimpleNamespace(
            numpy=lambda coords=coords: np.array(coords)))], conf=[.88])
                 for coords in [(20, 25, 100, 120), (180, 30, 290, 130)]]
        return [SimpleNamespace(boxes=boxes)]
    def load(name):
        assert name == str(path.resolve())
        return SimpleNamespace(predict=predict)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=load))
    cfg = config(tmp_path, body_backend='yolo')
    cfg['vision']['yolo_model'] = str(path)
    detector = vision.PersonDetectionEngine(cfg['vision'], [])
    detector.face = Faces([(35, 30, 30, 35)])
    try:
        rows = detector.detect(np.zeros((180, 320, 3), dtype=np.uint8))
        assert len(rows) == 2
        assert rows[0]['body_visible'] and rows[0]['face_visible']
        assert rows[0]['body_detection_source'] == 'yolo'
        assert rows[0]['body_detection_confidence'] == .88
        assert rows[1]['face_bbox'] is None and rows[1]['embedding'] is None
        assert calls == [dict(classes=[0], verbose=False, conf=.5, device='cpu')]
        report = detector.backend_execution()
        assert report['successful_calls'] == {'yolo': 1, 'hog': 0}
        assert report['quality'] == 'not_validated'
        assert report['seated_recall_validated'] is None
    finally:
        detector.close()


def test_predict_failure_falls_back_once_and_keeps_faces(tmp_path, monkeypatch):
    path = tmp_path/'fixture.pt'
    path.write_bytes(b'synthetic placeholder')
    def fail(*args, **kwargs):
        raise RuntimeError('fixture CPU prediction failure')
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *a: SimpleNamespace(predict=fail)))
    cfg = config(tmp_path)
    cfg['vision']['yolo_model'] = str(path)
    notes = []
    detector = vision.PersonDetectionEngine(cfg['vision'], notes)
    detector.face = Faces([(30, 40, 35, 40)])
    try:
        for t in (0., 1.):
            assert detector.detect(np.zeros((180, 320, 3), dtype=np.uint8), t, 'S')[0]['face_visible']
        report = detector.backend_execution()
        assert report['fallback_reason'] == 'yolo_inference_failed'
        assert report['inference_calls'] == {'yolo': 1, 'hog': 2}
        assert report['successful_calls'] == {'yolo': 0, 'hog': 2}
        assert report['quality'] == 'degraded'
        assert any('yolo_inference_failed' in note for note in notes)
    finally:
        detector.close()


def test_preflight_accepts_hog_when_explicit_yolo_missing(tmp_path, monkeypatch):
    import cv2
    cfg = config(tmp_path, body_backend='yolo')
    monkeypatch.setattr(cv2.FaceDetectorYN, 'create', lambda *a: object())
    monkeypatch.setattr(cv2.FaceRecognizerSF, 'create', lambda *a: object())
    monkeypatch.setitem(sys.modules, 'ultralytics', None)
    result = preflight.validate_vision_assets(cfg)
    assert result['ok']
    assert result['models']['body_backend']['fallback_reason'] == 'yolo_local_model_missing'
    assert result['models']['body_backend']['quality'] == 'degraded'
    assert result['inference_executed'] is False


def test_hog_raw_score_is_not_detection_confidence(tmp_path):
    detector = vision.PersonDetectionEngine(config(tmp_path, body_backend='hog')['vision'], [])
    detector.face = Faces([(35, 30, 30, 35)])
    detector.hog = Hog([(20, 20, 80, 100)])
    try:
        row = detector.detect(np.zeros((180, 320, 3), dtype=np.uint8))[0]
        assert row['body_detection_source'] == 'hog'
        assert row['body_hog_score'] == 1.
        assert row['body_detection_confidence'] is None
        assert row['detection_confidence'] != row['body_hog_score']
    finally:
        detector.close()


def test_small_frame_and_disabled_backend_do_not_claim_execution(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(
        YOLO=lambda *a: pytest.fail('YOLO should not be called')))
    for enabled in (True, False):
        detector = vision.PersonDetectionEngine(config(tmp_path, body_detection=enabled)['vision'], [])
        detector.face = Faces([])
        try:
            assert detector.detect(np.zeros((60, 60, 3), dtype=np.uint8)) == []
            report = detector.backend_execution()
            assert report['executed_backends'] == []
            assert report['inference_calls'] == {'yolo': 0, 'hog': 0}
            assert report['quality'] == ('degraded' if enabled else 'disabled')
        finally:
            detector.close()


def test_vision_offline_pipeline_logs_actual_hog_and_partial(tmp_path, monkeypatch, caplog):
    import cv2
    video = tmp_path/'synthetic.mp4'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 180))
    assert writer.isOpened()
    try:
        for _ in range(10):
            writer.write(np.full((180, 320, 3), 120, dtype=np.uint8))
    finally:
        writer.release()
    cfg = config(tmp_path, body_backend='yolo')
    cfg['offline'] = True
    monkeypatch.setitem(sys.modules, 'ultralytics', None)
    output = tmp_path/'output'
    output.mkdir()
    ctx = Context(video, output, cfg, 'fixture', logging.getLogger('stage25'))
    with caplog.at_level(logging.INFO, logger='stage25'):
        result = vision.VisionEngine().run(ctx, {'duration':1., 'fps':10},
                                         [{'start':0., 'end':1., 'scene_id':'S'}], {'segments':[]})
    assert result['status'] == 'partial'
    report = result['data']['quality']['body_detection']
    assert report['executed_backends'] == ['hog']
    assert report['quality'] == 'degraded'
    assert result['data']['performance']['body_detection_backend'] == 'hog'
    assert report['fallback_reason'] in caplog.text
    assert 'execução de backend' in caplog.text
    assert result['data']['people'] == []
