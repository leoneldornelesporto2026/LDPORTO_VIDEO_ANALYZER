"""Stage 41 offline fixtures; no real media, model inference or GPU work."""
import importlib.util
import json
import logging
from pathlib import Path
import sys
from collections import defaultdict

import numpy as np
import pytest

from ldporto.core import Context, ok
from ldporto.config import DEFAULTS
from ldporto.progress import WeightedProgress


def benchmark():
    path = Path(__file__).resolve().parents[2] / 'scripts/dev/benchmark_vision_r3b.py'
    spec = importlib.util.spec_from_file_location('stage41_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_gpu_smoke_never_enables_or_decodes(tmp_path, monkeypatch):
    module = benchmark()
    import ldporto.ollama_local as ollama
    monkeypatch.setattr(ollama.shutil, 'which', lambda name: None)
    monkeypatch.setattr(module, 'compare', lambda *a: pytest.fail('inference forbidden'))
    output = tmp_path / 'smoke.json'
    monkeypatch.setattr(sys, 'argv', ['benchmark', '--output', str(output)])
    module.main()
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['resources']['gpu'] == {'available': False, 'gpus': []}
    assert not report['optimization_enabled']
    assert not report['resources']['adaptive_parallelism_enabled']
    assert report['speedup_x'] is None
    before = output.read_bytes()
    with pytest.raises(SystemExit) as exc:
        module.main()
    assert exc.value.code == 2
    assert output.read_bytes() == before


class Detector:
    instances = []
    def __init__(self, cfg, notes, offline):
        assert offline and cfg['body_backend'] == 'hog'
        self.enable = cfg['parallel_hog_with_face']
        self.overlap_budget = {'enabled': self.enable, 'workers': int(self.enable)}
        self.calls = defaultdict(int)
        self.closed = False
        self.instances.append(self)
    def set_frame_context(self, *args):
        pass
    def detect(self, frame):
        self.calls['face_detection_calls'] += 1
        self.calls['body_detection_calls'] += 1
        return [{'bbox': [0, 0, 1, 1], 'confidence': .9, 'embedding': None}]
    def close(self):
        self.closed = True


def setup_benchmark(tmp_path, monkeypatch, detector=Detector):
    module = benchmark()
    import ldporto.vision as vision
    monkeypatch.setattr(vision, 'PersonDetectionEngine', detector)
    frames = [(float(i), np.zeros((128, 64, 3), dtype=np.uint8)) for i in range(2)]
    monkeypatch.setattr(module, 'collect', lambda *a: frames)
    monkeypatch.setattr(module, 'nvidia_smi', lambda: {'available': False, 'gpus': []})
    video = tmp_path / 'source.fixture'
    video.write_bytes(b'synthetic, not video')
    return module, video, frames


def test_identical_frames_alternating_modes_and_resource_logs(tmp_path, monkeypatch):
    Detector.instances = []
    module, video, frames = setup_benchmark(tmp_path, monkeypatch)
    report = module.compare(video, DEFAULTS['vision'], 2, repeats=3)
    assert [p['order'] for p in report['pairs']] == [['serial', 'parallel'], ['parallel', 'serial'], ['serial', 'parallel']]
    assert report['frame_manifest'] == module.frame_manifest(frames)
    assert report['detector_calls_identical'] and report['detection_boxes_identical']
    assert report['enable_recommendation'] == 'leave_disabled'
    assert not report['safe_to_enable_automatically']
    assert all(d.closed for d in Detector.instances)
    for pair in report['pairs']:
        for row in pair['modes'].values():
            assert len(row['resource_log']) == 2
            assert row['process_cpu_seconds_delta'] >= 0
            assert row['gpu_after']['available'] is False


@pytest.mark.parametrize('problem', ['confidence', 'failed', 'disabled', 'mutation'])
def test_invalid_ab_never_reports_gain(tmp_path, monkeypatch, problem):
    class BadDetector(Detector):
        def detect(self, frame):
            rows = super().detect(frame)
            if self.enable:
                if problem == 'confidence': rows[0]['confidence'] = .8
                if problem == 'failed': self.calls['face_detector_failed_frames'] += 1
                if problem == 'disabled': self.overlap_budget['enabled'] = False
                if problem == 'mutation': frame[0, 0, 0] = 255
            return rows
    module, video, frames = setup_benchmark(tmp_path, monkeypatch, BadDetector)
    if problem == 'mutation':
        with pytest.raises(ValueError, match='mutated'):
            module.compare(video, DEFAULTS['vision'], 2)
    else:
        assert module.compare(video, DEFAULTS['vision'], 2)['speedup_x'] is None


def test_collect_budget_releases_capture(monkeypatch):
    module = benchmark()
    import cv2
    class Capture:
        released = False
        def isOpened(self): return True
        def get(self, prop): return 30
        def set(self, *args): pass
        def read(self): return True, np.zeros((128, 64, 3), dtype=np.uint8)
        def release(self): self.released = True
    capture = Capture()
    monkeypatch.setattr(cv2, 'VideoCapture', lambda *a: capture)
    with pytest.raises(ValueError, match='budget'):
        module.collect('synthetic', 2, 64, max_frame_bytes=25000)
    assert capture.released


def running_model():
    model = WeightedProgress({'vision': 100, 'export': 20}, clock=lambda: 0)
    for i in range(5):
        model.update({'stage': 'vision', 'status': 'running', 'current': i, 'total': 10, 'elapsed_seconds': i * 2})
    return model


def test_eta_evidence_blocking_terminal_and_restart():
    model = running_model()
    snapshot = model.snapshot()
    assert snapshot['eta_sample_count'] == 4 and snapshot['stage_eta_seconds'] == 12
    assert snapshot['future_eta_basis'] == 'baseline_weights_unvalidated_on_current_hardware'
    model.update({'stage': 'export', 'status': 'blocked', 'cause': 'vision=unavailable'})
    assert model.snapshot()['stage'] == 'export'
    assert model.snapshot()['blocking_reason'] == 'vision=unavailable'
    assert model.snapshot()['stage_eta_seconds'] is None
    model = running_model()
    model.update({'stage': 'vision', 'status': 'running', 'current': 0, 'total': 10, 'elapsed_seconds': 0})
    assert model.snapshot()['eta_sample_count'] == 0
    assert model.snapshot()['stage_eta_seconds'] is None
    model = running_model()
    model.update({'event': 'run_failed'})
    assert model.snapshot()['stage_eta_seconds'] is None


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, -1])
def test_invalid_eta_units_stay_unknown(value):
    model = WeightedProgress({'vision': 1})
    model.update({'stage': 'vision', 'status': 'running', 'current': value, 'total': 10, 'elapsed_seconds': value})
    assert model.snapshot()['stage_fraction'] is None
    assert model.snapshot()['stage_eta_seconds'] is None


def test_restart_reuses_checkpoint_without_rewriting_valid_output(tmp_path):
    def context():
        return Context(tmp_path / 'absent.mp4', tmp_path, {'strict': False}, 'fixture41', logging.getLogger('stage41'))
    first = context()
    artifact = tmp_path / 'valid.json'
    artifact.write_text('{"synthetic": true}', encoding='utf-8')
    data = {'frames': [{'time': .5, 'person_id': None}], 'publish_ready': False}
    first.step('07_people_tracking', {}, lambda: ok(data, artifacts=[str(artifact)]), code_files=['vision.py'])
    path = first.cache / '07_people_tracking.json'
    before = (path.read_bytes(), path.stat().st_mtime_ns, artifact.read_bytes(), artifact.stat().st_mtime_ns)
    second = context()
    assert second.step('07_people_tracking', {}, lambda: pytest.fail('valid stage rerun'), code_files=['vision.py']) == data
    assert second.stage_metrics['07_people_tracking']['cache_hit']
    assert before == (path.read_bytes(), path.stat().st_mtime_ns, artifact.read_bytes(), artifact.stat().st_mtime_ns)


def test_gui_shows_eta_evidence_and_blocking_reason_without_tk_window():
    path = Path(__file__).resolve().parents[2] / 'app.py'
    spec = importlib.util.spec_from_file_location('stage41_app', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Var:
        value = ''
        def set(self, value): self.value = value
    class Bar(dict):
        def stop(self): pass
        def start(self, *a): pass
        def configure(self, **kw): self.update(kw)
        def cget(self, key): return self.get(key)
    class Tree:
        def exists(self, stage): return False
    app = object.__new__(module.App)
    app.in_execution = True
    app.progress_model = running_model()
    app.overall_bar, app.stage_bar, app.stage_tree = Bar(), Bar(), Tree()
    for name in ('overall_text', 'stage_text', 'elapsed_text', 'next_stage_text', 'execution_diagnostic'):
        setattr(app, name, Var())
    app.refresh_execution()
    assert 'amostras: 4' in app.elapsed_text.value
    assert 'baseline; hardware atual pendente' in app.elapsed_text.value
    app.progress_model.update({'stage': 'vision', 'status': 'blocked', 'cause': 'RAM desconhecida'})
    app.refresh_execution()
    assert 'RAM desconhecida' in app.execution_diagnostic.value
    assert 'amostras:' not in app.elapsed_text.value
