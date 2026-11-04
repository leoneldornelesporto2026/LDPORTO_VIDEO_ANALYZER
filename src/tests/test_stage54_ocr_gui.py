"""Headless GUI handlers and synthetic receipts; no production OCR claims."""
import importlib.util
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ldporto.config import load_config, save_ocr_options
from ldporto.ocr import OcrEngine
from ldporto.commercial_gate import targeted_ocr
from ldporto.ocr_execution import execution_summary, receipt

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('stage54_app', ROOT/'app.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


class Var:
    def __init__(self, value):
        self.value = value
        self.thread = threading.get_ident()

    def get(self):
        assert threading.get_ident() == self.thread
        return self.value

    def set(self, value):
        assert threading.get_ident() == self.thread
        self.value = value


def headless():
    app = gui.App.__new__(gui.App)
    app.ocr_enabled, app.ocr_languages, app.ocr_command = Var(True), Var('por+eng'), Var('')
    app.ocr_status = Var('Não testado')
    app.ocr_generation, app.ocr_busy, app.proc = 0, False, None
    app.start_button = Mock()
    app.messages = queue.Queue()
    app.source = Var('fixture.mp4')
    app._start_checked = Mock()
    return app


def test_config_roundtrip_preserves_other_bytes(tmp_path):
    target = tmp_path/'config.yaml'
    original = (ROOT/'config'/'config.yaml').read_bytes()
    target.write_bytes(original)
    before = load_config(target)
    after = save_ocr_options(target, {'enabled': True, 'tesseract_cmd': 'C:/Program Files/OCR/tesseract.exe'})
    assert after['ocr']['enabled']
    assert after['ocr']['tesseract_cmd'] == 'C:/Program Files/OCR/tesseract.exe'
    assert {k: v for k, v in before.items() if k != 'ocr'} == {k: v for k, v in after.items() if k != 'ocr'}
    updated = target.read_bytes()
    assert original.split(b'ocr:')[0] == updated.split(b'ocr:')[0]
    assert original.split(b'audio_events:')[1] == updated.split(b'audio_events:')[1]
    save_ocr_options(target, {'enabled': before['ocr']['enabled'],
                              'tesseract_cmd': before['ocr']['tesseract_cmd']})
    assert target.read_bytes() == original
    with pytest.raises(ValueError):
        save_ocr_options(target, {'HF_TOKEN': 'never'})
    assert target.read_bytes() == original


def test_cancel_selection_has_no_effect(monkeypatch):
    app = headless()
    app.change_ocr = Mock()
    monkeypatch.setattr(gui.filedialog, 'askopenfilename', lambda **kw: '')
    app.select_ocr_command()
    assert app.ocr_command.get() == ''
    app.change_ocr.assert_not_called()


@pytest.mark.parametrize('enabled,ok,reason,expected', [
    (False, False, 'disabled_by_user', 'Desligado'),
    (True, False, 'binary_missing', 'Bloqueado'),
    (True, True, None, 'Pronto'),
    (True, False, 'language_missing', 'Bloqueado'),
])
def test_worker_gate_and_thread_signalling(monkeypatch, enabled, ok, reason, expected):
    app = headless()
    app.ocr_enabled.set(enabled)
    entered, release = threading.Event(), threading.Event()
    calls = []
    def diagnose(options, smoke=False):
        calls.append((options, smoke, threading.get_ident()))
        entered.set()
        assert release.wait(3)
        return {'ok': ok, 'reason': reason, 'missing_languages': ['por'], 'readiness_scope': 'configuration_only'}
    monkeypatch.setattr('ldporto.ocr_diagnostics.diagnose_ocr', diagnose)
    app.start()
    assert entered.wait(3)
    assert app.ocr_busy and app.messages.empty()
    app._start_checked.assert_not_called()
    release.set()
    kind, value = app.messages.get(timeout=3)
    assert kind == 'ocr_result'
    app.handle_ocr_result(value)
    assert expected in app.ocr_status.get()
    assert app._start_checked.call_count == int(not enabled or ok)
    assert calls[0][2] != threading.get_ident()
    assert not app.ocr_busy


def test_explicit_smoke_uses_worker(monkeypatch):
    app = headless()
    probe = Mock(return_value={'ok': True, 'reason': None, 'readiness_scope': 'synthetic_smoke_only'})
    monkeypatch.setattr('ldporto.ocr_diagnostics.diagnose_ocr', probe)
    app.verify_ocr(smoke=True)
    _, value = app.messages.get(timeout=3)
    app.handle_ocr_result(value)
    assert probe.call_args.kwargs == {'smoke': True}
    app._start_checked.assert_not_called()


def test_stale_result_never_starts(monkeypatch):
    app = headless()
    app.verify_ocr = Mock()
    old = app.ocr_options()
    app.ocr_generation += 1
    app.handle_ocr_result((0, old, {'ok': True}, True))
    app._start_checked.assert_not_called()
    app.verify_ocr.assert_called_once()


def test_explicit_change_only_persists_ocr(tmp_path, monkeypatch):
    (tmp_path/'config').mkdir()
    target = tmp_path/'config'/'config.yaml'
    target.write_bytes((ROOT/'config'/'config.yaml').read_bytes())
    monkeypatch.setattr(gui, 'ROOT', tmp_path)
    app = headless()
    app.verify_ocr = Mock()
    app.change_ocr('enabled')
    assert load_config(target)['ocr']['enabled']
    app.verify_ocr.assert_called_once()
    app.ocr_enabled.set(False)
    app.change_ocr('enabled')
    assert not load_config(target)['ocr']['enabled']
    assert 'requires_review' in app.ocr_status.get()


def test_disabled_receipts_and_historical_null():
    general = OcrEngine().run(SimpleNamespace(config={'ocr': {'enabled': False, 'languages': 'por+eng'}}), {})['data']
    commercial = targeted_ocr('no-media', [], {'enabled': False, 'languages': 'por+eng'})
    summary = execution_summary(general, commercial)
    for row in summary.values():
        assert row['state'] == 'ignored' and row['measured_frames'] == 0
        assert row['measurement_state'] == 'not_measured' and row['requires_review']
        assert row['commercial_present'] is None
        assert row['elapsed_seconds'] >= 0 and row['languages'] == 'por+eng'
    assert execution_summary({}, {})['general_13']['measured_frames'] is None


def test_sampled_receipt_uses_frame_counts():
    @receipt('commercial_17c')
    def synthetic(video, candidates, cfg):
        return {'status': 'partial', 'measurement_state': 'measured', 'measured_frames': 2, 'failed_frames_or_ocr': 1}
    row = synthetic(None, [], {'enabled': True, 'languages': 'eng'})['execution']
    assert row['state'] == 'sampled' and row['measured_frames'] == 2
    assert row['failed_frames_or_ocr'] == 1 and row['languages'] == 'eng'


def test_worker_exception_blocks_launch(monkeypatch):
    app = headless()
    monkeypatch.setattr('ldporto.ocr_diagnostics.diagnose_ocr', Mock(side_effect=RuntimeError('fixture failure')))
    app.start()
    _, value = app.messages.get(timeout=3)
    app.handle_ocr_result(value)
    assert 'Bloqueado' in app.ocr_status.get()
    app._start_checked.assert_not_called()


def test_execution_screen_reads_separate_receipts(tmp_path):
    import json
    app = headless()
    app.output_folder = tmp_path
    app.ocr_execution_status = Var('')
    (tmp_path/'ocr_execution.json').write_text(json.dumps({'general_13': {
        'state': 'sampled', 'measured_frames': 4, 'failed_frames_or_ocr': 1,
        'languages': 'por+eng', 'elapsed_seconds': .5}, 'commercial_17c': {
        'state': 'unavailable', 'measured_frames': 0, 'failed_frames_or_ocr': 0,
        'languages': 'por+eng', 'elapsed_seconds': .2}}), encoding='utf-8')
    app.update_ocr_execution()
    assert 'geral 13: sampled | frames=4 | falhas=1' in app.ocr_execution_status.get()
    assert 'comercial 17c: unavailable | frames=0' in app.ocr_execution_status.get()
