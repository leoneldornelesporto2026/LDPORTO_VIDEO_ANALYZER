"""Offline policy fixtures; fake CUDA measurements never prove GPU performance."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from ldporto import vision
from ldporto.config import DEFAULTS
from ldporto.core import Unavailable
from ldporto.performance import FrameTelemetry
from test_stage57_local_yolo import fake_local, boxes, Faces


def cuda(monkeypatch, free):
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(
        is_available=lambda: True, mem_get_info=lambda *_: (free * 1048576, 12000 * 1048576))))


@pytest.mark.parametrize('free,selected,reason', [(3071, 'cpu', 'insufficient_vram'),
                                               (3072, 'cuda:0', None)])
def test_reserve_and_timestamp(monkeypatch, free, selected, reason):
    cuda(monkeypatch, free)
    cfg = deepcopy(DEFAULTS['vision'])
    cfg['yolo_device'] = 'cuda'
    result = vision.yolo_device_preflight(cfg)
    assert result['selected'] == selected and result['reason'] == reason
    assert result['measured_at_utc'].endswith('+00:00')
    assert result['query_seconds'] >= 0
    assert result['measurement_scope'] == 'device_0_snapshot_not_reserved'
    assert 'not_attributed' in result['concurrent_consumers']


def test_blocked_load_and_runtime_loss(tmp_path, monkeypatch):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: boxes(),
                     yolo_device='cuda', yolo_resource_policy='blocked')
    cuda(monkeypatch, 100)
    with pytest.raises(Unavailable, match='insufficient_vram'):
        vision.load_local_yolo(cfg)
    cuda(monkeypatch, 4096)
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    detector.face = Faces([])
    cuda(monkeypatch, 100)
    try:
        with pytest.raises(Unavailable, match='insufficient_vram'):
            detector.detect(np.zeros((180,320,3), np.uint8))
        assert detector.calls['yolo_successful_calls'] == 0
        assert detector.hog is None
    finally:
        detector.close()


def test_reserve_can_force_cpu_fallback_before_model_load(tmp_path, monkeypatch):
    cfg = fake_local(tmp_path, monkeypatch, lambda *a, **kw: pytest.fail('GPU invoked'),
                     yolo_device='cuda', yolo_reserve_vram_mb=3000)
    cuda(monkeypatch, 4096)
    detector = vision.PersonDetectionEngine(cfg, [], offline=True)
    try:
        assert detector.yolo is None and detector.hog is not None
        assert detector.body_backend_report['diagnostic_reason'] == 'insufficient_vram'
        assert detector.body_backend_report['device_actually_used'] is None
        assert detector._hog_pool is None
    finally:
        detector.close()


@pytest.mark.parametrize('free', [float('nan'), float('inf'), -1, 13000])
def test_invalid_device_measurement_fail_closed(monkeypatch, free):
    cuda(monkeypatch, free)
    assert vision.yolo_device_preflight(dict(DEFAULTS['vision'], yolo_device='cuda'))['reason'] == 'cuda_preflight_failed'


def test_shutdown_cancels_queued_cpu_work():
    detector = object.__new__(vision.PersonDetectionEngine)
    calls = []
    detector._hog_pool = SimpleNamespace(shutdown=lambda **kw: calls.append(kw))
    detector.close()
    detector.close()
    assert calls == [{'wait': True, 'cancel_futures': True}]


def test_progress_exposes_measured_data_and_ui_without_inference():
    from ldporto.progress import WeightedProgress
    path = Path(__file__).resolve().parents[2] / 'app.py'
    spec = importlib.util.spec_from_file_location('stage59_app', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Var:
        value = ''
        def set(self, value): self.value = value
    class Bar(dict):
        def stop(self): pass
        def start(self, *args): pass
        def configure(self, **kw): self.update(kw)
        def cget(self, key): return self.get(key)
    class Tree:
        def exists(self, stage): return False
    model = WeightedProgress()
    model.update({'stage': '07_people_tracking', 'status': 'running',
                  'performance': {'frames_succeeded': 2, 'frames_attempted': 3, 'fps': 1.5,
                                  'latency_p95_seconds': .4,
                                  'body_backend': {'actually_executed_backend': 'hog', 'devices_used': {'hog': 'cpu'},
                                                   'fallback_reason': 'yolo_insufficient_vram'}}})
    app = object.__new__(module.App)
    app.in_execution, app.progress_model = True, model
    app.overall_bar, app.stage_bar, app.stage_tree = Bar(), Bar(), Tree()
    for name in ('overall_text', 'stage_text', 'elapsed_text', 'next_stage_text', 'execution_diagnostic'):
        setattr(app, name, Var())
    app.refresh_execution()
    assert '2/3 frames' in app.execution_diagnostic.value
    assert 'yolo_insufficient_vram' in app.execution_diagnostic.value
    assert 'p95=0.40s' in app.execution_diagnostic.value
    assert model.snapshot()['stage_eta_seconds'] is None


def test_bounded_telemetry_no_mock_speedup_or_eta():
    tick = [0.]
    stats = FrameTelemetry(clock=lambda: tick[0])
    assert stats.report()['latency_p95_seconds'] is None
    for _ in range(600):
        start = stats.attempt()
        tick[0] += .1
        stats.success(start)
    stats.attempt()  # failed decode: no success or latency
    result = stats.report()
    assert result['frames_attempted'] == 601 and result['frames_succeeded'] == 600
    assert result['latency_samples'] == 512
    assert result['latency_p50_seconds'] == pytest.approx(.1)
    assert result['fps'] == pytest.approx(10)
    assert result['speedup_x'] is result['peak_vram_mb'] is result['eta_seconds'] is None


def benchmark():
    path = Path(__file__).resolve().parents[2] / 'scripts/dev/benchmark_resources59.py'
    spec = importlib.util.spec_from_file_location('benchmark59', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clip_hash_rejected_before_decode(tmp_path, monkeypatch):
    import cv2
    module = benchmark()
    path = tmp_path / 'clip.fixture'
    path.write_bytes(b'not media')
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: pytest.fail('decode before hash'))
    with pytest.raises(ValueError, match='SHA256'):
        module.frames_for_clip(path, '0' * 64, 3)


def test_synthetic_real_hog_restores_threads():
    import cv2
    module = benchmark()
    before = cv2.getNumThreads()
    report = module.run([np.zeros((128,64,3), np.uint8)], 'synthetic')
    assert cv2.getNumThreads() == before
    assert report['telemetry']['frames_succeeded'] == 1
    assert report['speedup_x'] is report['quality'] is None
    assert report['device'] == 'cpu' and report['publish_ready'] is False


@pytest.mark.parametrize('count', [0, 9, True, 1.5])
def test_clip_api_bounds_before_hash_or_decode(count):
    with pytest.raises(ValueError, match='1..8'):
        benchmark().frames_for_clip(Path('absent.fixture'), '0' * 64, count)


@pytest.mark.parametrize('fps,total', [(float('nan'), 600), (30, float('inf')),
                                     (0, 600), (30, 270)])
def test_invalid_clip_metadata_releases_without_decode(tmp_path, monkeypatch, fps, total):
    import cv2
    from ldporto.core import file_hash
    source = tmp_path / 'clip.fixture'
    source.write_bytes(b'synthetic metadata only')
    released = []
    cap = SimpleNamespace(isOpened=lambda: True,
                          get=lambda prop: fps if prop == cv2.CAP_PROP_FPS else total,
                          read=lambda: pytest.fail('invalid clip decoded'),
                          release=lambda: released.append(True))
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *_: cap)
    with pytest.raises(ValueError, match='10..30'):
        benchmark().frames_for_clip(source, file_hash(source), 3)
    assert released == [True]


def test_preflight_resource_snapshot_independent_of_missing_assets(tmp_path, monkeypatch):
    from ldporto import preflight
    from test_v42_preflight import minimal_config
    cfg = minimal_config(tmp_path, monkeypatch)
    cfg['vision'].update(enabled=True, body_detection=True, body_backend='yolo',
                         yolo_device='cuda', active_speaker=False)
    monkeypatch.setattr(preflight, '_import_check', lambda *a: {'ok': False})
    monkeypatch.setattr(preflight, 'validate_vision_assets',
                        lambda *a: pytest.fail('missing assets must not load models'))
    cuda(monkeypatch, 100)
    report = preflight.run_preflight(cfg, tmp_path)
    sample = report['resource_strategy']['vision']['vram']
    assert sample['reason'] == 'insufficient_vram'
    assert sample['measured_at_utc'] and sample['selected'] == 'cpu'
    assert report['ready'] is False
