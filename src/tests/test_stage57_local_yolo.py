"""Offline synthetic evidence only; never load real checkpoints or use CUDA."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from ldporto import vision
from ldporto.config import load_config, save_body_options
from ldporto.core import external_fingerprints
from test_stage25_body_backends import config, Faces, Hog, no_network


def fake_local(tmp_path, monkeypatch, predict, **options):
    path = tmp_path/'fixture.pt'
    path.write_bytes(b'synthetic checkpoint placeholder')
    cfg = config(tmp_path, **options)['vision']
    cfg['yolo_model'] = str(path)
    def load(name):
        assert name == str(path.resolve())
        return SimpleNamespace(task='detect', names={0: 'person'}, predict=predict)
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=load))
    return cfg


def boxes():
    def row(coords, conf=.8, cls=0):
        return SimpleNamespace(xyxy=[SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(coords)))],
                               conf=[conf], cls=[cls])
    return [SimpleNamespace(boxes=[row([-10, -5, 330, 190]), row([0,0,40,50], cls=1),
                                  row([0,0,40,50], conf=float('nan'))])]


def test_cpu_success_benchmark_origin_and_person_only(tmp_path, monkeypatch):
    calls = []
    def predict(frame, **kw):
        calls.append(kw)
        return boxes()
    cfg = fake_local(tmp_path, monkeypatch, predict, body_max_frames=1)
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([])
    try:
        assert detector.backend_execution()['readiness'] == 'NOT_READY'
        rows = detector.detect(np.zeros((180,320,3), np.uint8))
        assert len(rows) == 1
        assert rows[0]['bbox'] == dict(x=0, y=0, width=1, height=1)
        assert rows[0]['body_detection_confidence'] == .8
        assert rows[0]['embedding'] is None
        assert detector.detect(np.zeros((180,320,3), np.uint8)) == []
        report = detector.backend_execution()
        assert report['actually_executed_backend'] == 'yolo'
        assert report['devices_used'] == {'yolo': 'cpu'}
        assert report['benchmark_frame_seconds'] >= 0
        assert len(report['model_sha256']) == 64
        assert report['body_limit_reason'] == 'body_frame_cap'
        assert report['identity_evidence'] is False and report['active_speaker_evidence'] is False
        assert report['quality'] == 'degraded'  # cap means incomplete body coverage
        assert calls[0]['device'] == 'cpu'
    finally:
        detector.close()


@pytest.mark.parametrize('free,available,reason', [(100, True, 'insufficient_vram'), (4000, False, 'cuda_unavailable')])
def test_cuda_not_ready_never_loads(tmp_path, monkeypatch, free, available, reason):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: pytest.fail('CUDA invoked'), yolo_device='cuda')
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: available, mem_get_info=lambda *a: (free*1048576, 12000*1048576))))
    monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=lambda *a: pytest.fail('must not load')))
    model, report = vision.load_local_yolo(cfg)
    assert model is None and report['diagnostic_reason'] == reason
    assert report['device_actually_used'] is None and report['readiness'] == 'NOT_READY'


def test_fake_cuda_executed_and_later_vram_loss_falls_to_hog(tmp_path, monkeypatch):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: boxes(), yolo_device='cuda')
    free = [4096]
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: True, mem_get_info=lambda *a: (free[0]*1048576,12000*1048576))))
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.yolo.predictor = SimpleNamespace(device='cuda:0')
    detector.face = Faces([])
    try:
        detector.detect(np.zeros((180,320,3), np.uint8))
        assert detector.backend_execution()['devices_used'] == {'yolo': 'cuda:0'}
        free[0] = 100
        detector.detect(np.zeros((180,320,3), np.uint8))
        report = detector.backend_execution()
        assert report['readiness'] == 'NOT_READY' and report['quality'] == 'degraded'
        assert report['device_preflight']['reason'] == 'insufficient_vram'
        assert report['devices_used'] == {'yolo':'cuda:0', 'hog':'cpu'}
    finally:
        detector.close()


def test_cuda_device_mismatch_cannot_claim_success(tmp_path, monkeypatch):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: boxes(), yolo_device='cuda')
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: True, mem_get_info=lambda *a: (4096*1048576,12000*1048576))))
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.yolo.predictor = SimpleNamespace(device='cpu')
    detector.face = Faces([])
    try:
        detector.detect(np.zeros((180,320,3), np.uint8))
        report = detector.backend_execution()
        assert report['device_actually_used'] == 'cpu'
        assert report['device'] == 'cpu'
        assert report['successful_calls']['yolo'] == 0
        assert report['actually_executed_backend'] == 'hog'
        assert report['readiness'] == 'NOT_READY'
    finally:
        detector.close()


def test_soft_timeout_discards_yolo_and_exposes_hog(tmp_path, monkeypatch):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: boxes(), body_frame_timeout_seconds=.01)
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([])
    # Deterministic clock, no actual sleep or GPU benchmark.
    tick = iter(range(1000))
    monkeypatch.setattr(vision, 'perf_counter', lambda: next(tick))
    try:
        assert detector.detect(np.zeros((180,320,3),np.uint8)) == []
        report = detector.backend_execution()
        assert report['fallback_reason'] == 'yolo_inference_failed'
        assert report['diagnostic_reason'] == 'inference_timeout'
        assert report['successful_calls']['yolo'] == 0
        assert report['quality'] == 'degraded' and report['readiness'] == 'NOT_READY'
    finally:
        detector.close()


@pytest.mark.parametrize('kind,reason', [('missing','model_file_missing'), ('empty','model_file_invalid'),
                                       ('suffix','model_file_invalid'), ('import','dependency_missing'),
                                       ('task','model_load_error')])
def test_diagnostic_reasons(tmp_path, monkeypatch, kind, reason):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: boxes())
    from pathlib import Path
    path = Path(cfg['yolo_model'])
    if kind == 'missing':
        path.unlink()
    elif kind == 'empty':
        path.write_bytes(b'')
    elif kind == 'suffix':
        other = tmp_path/'fixture.yaml'
        other.write_text('not weights')
        cfg['yolo_model'] = str(other)
    elif kind == 'import':
        monkeypatch.setitem(sys.modules, 'ultralytics', None)
    elif kind == 'task':
        monkeypatch.setitem(sys.modules, 'ultralytics', SimpleNamespace(YOLO=lambda *a: SimpleNamespace(task='classify')))
    model, report = vision.load_local_yolo(cfg)
    assert model is None and report['diagnostic_reason'] == reason
    assert report['readiness'] == 'NOT_READY'


def test_total_budget_keeps_face_and_hog_raw_score(tmp_path):
    cfg = config(tmp_path, body_backend='hog', body_total_timeout_seconds=.01)['vision']
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([(35,30,30,35)])
    detector.hog = Hog([(20,20,80,100)])
    try:
        rows = detector.detect(np.zeros((180,320,3),np.uint8))
        assert rows[0]['body_detection_confidence'] is None
        detector.phase_seconds['body_detection'] = 1
        rows = detector.detect(np.zeros((180,320,3),np.uint8))
        assert rows[0]['face_visible'] and not rows[0]['body_visible']
        assert detector.backend_execution()['body_limit_reason'] == 'body_time_budget'
    finally:
        detector.close()


def test_hog_failure_stops_body_and_preserves_faces(tmp_path):
    detector = vision.PersonDetectionEngine(config(tmp_path, body_backend='hog')['vision'], [], offline=True)
    detector.face = Faces([(35,30,30,35)])
    def fail(*a, **kw):
        raise RuntimeError('synthetic HOG failure')
    detector.hog = SimpleNamespace(detectMultiScale=fail)
    try:
        for _ in range(2):
            row = detector.detect(np.zeros((180,320,3),np.uint8))[0]
            assert row['face_visible'] and not row['body_visible']
        report = detector.backend_execution()
        assert report['actually_executed_backend'] is None
        assert report['inference_calls']['hog'] == 1
        assert report['body_limit_reason'] == 'hog_inference_failed'
        assert report['quality'] == 'degraded'
    finally:
        detector.close()


def test_explicit_config_save_and_cache_model_change(tmp_path):
    from pathlib import Path
    original = (Path(__file__).resolve().parents[2]/'config'/'config.yaml').read_bytes()
    target = tmp_path/'config.yaml'
    target.write_bytes(original)
    before = load_config(target)
    assert save_body_options(target, {'body_backend': before['vision']['body_backend']}) == before
    assert target.read_bytes() == original
    model = tmp_path/'fixture.pt'
    model.write_bytes(b'first placeholder')
    after = save_body_options(target, {'body_backend':'yolo','yolo_model':str(model),'yolo_device':'cuda'})
    assert {k:v for k,v in before.items() if k != 'vision'} == {k:v for k,v in after.items() if k != 'vision'}
    assert after['vision']['yolo_device'] == 'cuda'
    audio_before = external_fingerprints(after, '02_audio')
    vision_before = external_fingerprints(after, '07_people_tracking')
    model.write_bytes(b'second placeholder')
    assert external_fingerprints(after, '07_people_tracking') != vision_before
    assert external_fingerprints(after, '02_audio') == audio_before
    with pytest.raises(ValueError):
        save_body_options(target, {'enabled':True})


def test_visual_chunk_hash_changes_with_local_checkpoint(tmp_path):
    from ldporto.vision_checkpoint import VisionCheckpointStore
    cfg = config(tmp_path)['vision']
    model = tmp_path/'fixture.pt'
    cfg['yolo_model'] = str(model)
    ctx = SimpleNamespace(cache=tmp_path/'cache')
    before = VisionCheckpointStore(ctx, cfg).model_hash
    model.write_bytes(b'synthetic first')
    present = VisionCheckpointStore(ctx, cfg).model_hash
    model.write_bytes(b'synthetic second')
    assert before != present != VisionCheckpointStore(ctx, cfg).model_hash


def test_gui_cancel_and_explicit_save(tmp_path, monkeypatch):
    from pathlib import Path
    from test_stage54_ocr_gui import gui, Var
    (tmp_path/'config').mkdir()
    target = tmp_path/'config'/'config.yaml'
    target.write_bytes((Path(__file__).resolve().parents[2]/'config'/'config.yaml').read_bytes())
    original = target.read_bytes()
    commands, variables = {}, []
    class Widget:
        def __init__(self, *a, **kw):
            if 'command' in kw:
                commands[kw['text']] = kw['command']
        def pack(self, **kw):
            pass
        def title(self, value):
            pass
        def destroy(self):
            pass
    def variable(value):
        result = Var(value)
        variables.append(result)
        return result
    monkeypatch.setattr(gui, 'ROOT', tmp_path)
    monkeypatch.setattr(gui.tk, 'Toplevel', Widget)
    monkeypatch.setattr(gui.tk, 'StringVar', variable)
    for name in ('Label','Entry','Combobox','Button'):
        monkeypatch.setattr(gui.ttk, name, Widget)
    monkeypatch.setattr(gui.filedialog, 'askopenfilename', lambda **kw: '')
    app = gui.App.__new__(gui.App)
    app.window, app.body_status = None, Var('initial')
    app.body_settings()
    commands['Selecionar arquivo .pt local']()
    commands['Cancelar']()
    assert target.read_bytes() == original
    app.body_settings()
    variables[-3].set('hog')
    commands['Salvar escolhas']()
    assert load_config(target)['vision']['body_backend'] == 'hog'
    assert 'NOT_READY' in app.body_status.get()
