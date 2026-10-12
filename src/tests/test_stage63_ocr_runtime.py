"""Offline configuration regressions plus optional real Windows synthetic OCR."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from ldporto import ocr_diagnostics as d, ocr_runtime as runtime_api
from ldporto.config import load_config, save_ocr_options
from ldporto.ocr import OcrEngine
from ldporto.commercial_gate import targeted_ocr
from test_stage53_ocr_diagnostics import runtime
from test_stage54_ocr_gui import headless


@pytest.mark.parametrize('prefix', ['', 'v'])
def test_windows_version_and_language_order(runtime, monkeypatch, prefix):
    def run(args, **kwargs):
        if '--version' in args:
            return subprocess.CompletedProcess(args, 0, f'tesseract {prefix}5.5.3.20260724\r\n', '')
        if '--list-langs' in args:
            return subprocess.CompletedProcess(args, 0,
                f'List of available languages in "{runtime.data}" (3):\r\neng\r\nosd\r\npor\r\n', '')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    report = d.diagnose_ocr(runtime.cfg, smoke=True)
    assert report['ok'] and report['version'] == '5.5.3.20260724'
    assert report['requested_languages'] == ['por', 'eng']
    assert report['available_languages'] == ['eng', 'osd', 'por']
    assert report['smoke']['success'] and runtime.calls[-1][0][-3:] == ['por+eng', '--psm', '6']


@pytest.mark.parametrize('stage', ['--version', '--list-langs', '--print-parameters'])
@pytest.mark.parametrize('kind', ['error', 'timeout'])
def test_probe_failures_are_precise_and_private(runtime, monkeypatch, stage, kind):
    def run(args, **kwargs):
        if stage in args:
            if kind == 'timeout':
                raise subprocess.TimeoutExpired(args, 5, output='HF_TOKEN=secret')
            raise RuntimeError('C:/Users/private HF_TOKEN=secret prompt=private')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    report = d.diagnose_ocr(runtime.cfg)
    assert report['reason'] == ('timeout' if kind == 'timeout' else 'binary_execution_failed')
    assert report['missing_languages'] == [] and not report['ok']
    assert all(secret not in json.dumps(report) for secret in ('secret', 'private', 'HF_TOKEN', 'prompt='))


@pytest.mark.parametrize('command', ['C:/Program Files/Tesseract-OCR/tesseract.exe',
                                     r'C:\Program Files\Tesseract-OCR\tesseract.exe'])
def test_program_files_resolution_without_shell(runtime, monkeypatch, command):
    requests = []
    def which(value):
        requests.append(value)
        return str(runtime.binary)
    monkeypatch.setattr(runtime_api.shutil, 'which', which)
    report = d.diagnose_ocr({**runtime.cfg, 'tesseract_cmd': command})
    assert report['ok'] and requests == [command]
    assert all(call[0][0] == str(runtime.binary.resolve()) for call in runtime.calls)


def test_calls_serialize_restore_command_cache_and_language(runtime, monkeypatch):
    api = SimpleNamespace(tesseract_cmd='original')
    active = []
    entered = threading.Event()
    def infer(image, **kwargs):
        assert version._result is version  # run_once cache isolated per call
        active.append(api.tesseract_cmd)
        entered.set()
        time.sleep(.03)
        assert api.tesseract_cmd == active[-1]
        assert kwargs['lang'] == 'por+eng' and kwargs['timeout'] == 5
        if image == 'fail':
            raise RuntimeError('fixture')
        return image
    def version():
        version._result = 'changed'
        return '5.5'
    version._result = 'original-cache'
    module = SimpleNamespace(pytesseract=api, image_to_string=infer, get_tesseract_version=version)
    monkeypatch.setattr(runtime_api.importlib, 'import_module', lambda _: module)
    other = runtime.binary.parent / 'other.exe'
    other.write_bytes(b'fixture')
    other.chmod(0o755)
    monkeypatch.setattr(runtime_api.shutil, 'which', lambda cmd: str(other if cmd == 'other' else runtime.binary))
    outputs = []
    threads = [threading.Thread(target=lambda cmd=cmd: outputs.append(
        runtime_api.call({**runtime.cfg, 'tesseract_cmd': cmd}, 'image_to_string', cmd)))
        for cmd in ('first', 'other')]
    threads[0].start()
    assert entered.wait(2)
    threads[1].start()
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert outputs == ['first', 'other']
    assert active == [str(runtime.binary.resolve()), str(other.resolve())]
    assert api.tesseract_cmd == 'original'
    runtime_api.call(runtime.cfg, 'get_tesseract_version')
    assert version._result == 'original-cache'
    with pytest.raises(RuntimeError):
        runtime_api.call(runtime.cfg, 'image_to_string', 'fail')
    assert api.tesseract_cmd == 'original'


def test_tessdata_environment_is_inherited_not_mutated(monkeypatch):
    monkeypatch.setenv('TESSDATA_PREFIX', 'fixture-prefix')
    monkeypatch.setenv('TESSDATA_DIR', 'fixture-ignored-dir')
    code = 'import os; print(os.environ["TESSDATA_PREFIX"]); print(os.environ["TESSDATA_DIR"])'
    report = d._run([sys.executable, '-c', code])
    assert report.returncode == 0
    assert report.stdout.split() == ['fixture-prefix', 'fixture-ignored-dir']
    assert os.environ['TESSDATA_PREFIX'] == 'fixture-prefix'


def test_languages_header_on_stderr(runtime, monkeypatch):
    def run(args, **kwargs):
        if '--list-langs' in args:
            return subprocess.CompletedProcess(args, 0, 'eng\nosd\npor\n',
                f'List of available languages in "{runtime.data}" (3):\n')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    assert d.diagnose_ocr(runtime.cfg)['ok']


def test_smoke_preserves_relative_tessdata_and_scrubs_before_normalizing(runtime, monkeypatch):
    monkeypatch.setenv('TESSDATA_PREFIX', 'relative-fixture-tessdata')
    secret = 'hf_' + 'x' * 30
    def run(args, **kwargs):
        assert kwargs.get('cwd') is None
        assert os.environ['TESSDATA_PREFIX'] == 'relative-fixture-tessdata'
        if '--psm' in args:
            return subprocess.CompletedProcess(args, 0, secret, '')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    report = d.diagnose_ocr(runtime.cfg, smoke=True)
    assert report['reason'] == 'smoke_failed'
    assert 'x' * 30 not in json.dumps(report)
    assert report['smoke']['observed_text'] == '[REDACTED_SECRET]'


def test_gui_worker_with_real_diagnostic_mocked_binary(runtime, monkeypatch):
    app = headless()
    app.ocr_command.set('C:/Program Files/Tesseract-OCR/tesseract.exe')
    gate, release = threading.Event(), threading.Event()
    def run(args, **kwargs):
        gate.set()
        assert release.wait(2)
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    app.verify_ocr(smoke=True)
    assert gate.wait(2) and app.ocr_busy and app.messages.empty()
    assert app.ocr_status.get().startswith('Não testado')
    release.set()
    _, payload = app.messages.get(timeout=3)
    app.handle_ocr_result(payload)
    assert 'Pronto: por+eng | synthetic_smoke_only' == app.ocr_status.get()
    assert app.ocr_last_diagnostic['smoke']['elapsed_seconds'] >= 0
    app._start_checked.assert_not_called()


def test_engine_and_commercial_fail_closed_before_media(runtime, monkeypatch):
    monkeypatch.setitem(sys.modules, 'pytesseract', SimpleNamespace())
    def run(args, **kwargs):
        if '--list-langs' in args:
            return subprocess.CompletedProcess(args, 0,
                f'List of available languages in "{runtime.data}" (1):\neng\n', '')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    ctx = SimpleNamespace(config={'ocr': runtime.cfg})
    general = OcrEngine().run(ctx, {})['data']
    commercial = targeted_ocr('never-opened', [], runtime.cfg)
    for result in (general, commercial):
        assert result['reason'] == 'missing_languages'
        assert result['measurement_state'] == 'not_measured'
        assert result['commercial_present'] is None


def test_optional_real_windows_gui_smoke_and_engine(tmp_path, monkeypatch):
    if importlib.util.find_spec('pytesseract') is None:
        pytest.skip('optional pytesseract unavailable; no install')
    cfg = load_config(Path(__file__).resolve().parents[2] / 'config/config.yaml')['ocr']
    cfg = {**cfg, 'enabled': True, 'languages': 'por+eng'}
    try:
        runtime_api.resolve_executable(cfg)
    except OSError:
        pytest.skip('optional local Tesseract absent; no install')
    probe = d.diagnose_ocr(cfg)
    if probe['reason'] == 'missing_languages':
        pytest.skip('optional por/eng traineddata absent; no install')
    assert probe['ok'], probe
    app = headless()
    app.ocr_command.set(cfg['tesseract_cmd'] or '')
    app.verify_ocr()
    _, payload = app.messages.get(timeout=10)
    assert payload[2]['ok'] and payload[2]['inference_executed'] is False
    app.handle_ocr_result(payload)
    assert 'configuration_only' in app.ocr_status.get()
    app.verify_ocr(smoke=True)
    _, payload = app.messages.get(timeout=20)
    assert payload[2]['ok'] and payload[2]['smoke']['success']
    app.handle_ocr_result(payload)
    assert 'synthetic_smoke_only' in app.ocr_status.get()
    # Persist GUI choices in a temporary config only; use the real loader.
    config_path = tmp_path / 'config.yaml'
    config_path.write_text('ocr:\n  enabled: false\n  languages: eng\n  tesseract_cmd: null\n', encoding='utf-8')
    loaded = save_ocr_options(config_path, app.ocr_options())
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1100, 180), 'white')
    font = ImageFont.truetype('arial.ttf' if os.name == 'nt' else 'DejaVuSans.ttf', 42)
    phrase = 'PROMOCAO 60 POR CENTO OFF'
    ImageDraw.Draw(image).text((25, 40), phrase, font=font, fill='black')
    image.save(tmp_path / 'fixture.png')
    import pytesseract
    original = pytesseract.pytesseract.tesseract_cmd
    assert d._normalize(runtime_api.call(loaded['ocr'], 'image_to_string', image)) == d._normalize(phrase)
    ctx = SimpleNamespace(config=loaded, output=tmp_path)
    result = OcrEngine().run(ctx, {'thumbnails': [{'path': 'fixture.png', 'time': 1.}]})['data']
    assert result['measured_frames'] == 1
    assert d._normalize(' '.join(row['text'] for row in result['texts'])) == d._normalize(phrase)
    import cv2
    frame = cv2.imread(str(tmp_path / 'fixture.png'))
    class Capture:
        def __init__(self, *_): pass
        def isOpened(self): return True
        def set(self, *_): pass
        def read(self): return True, frame.copy()
        def release(self): pass
    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    result = targeted_ocr('synthetic-no-media', [{'moment_id': 'synthetic', 'start': 0., 'end': 1.}], loaded['ocr'])
    assert result['measured_frames'] == 3
    assert all(d._normalize(row['text']) == d._normalize(phrase) for row in result['texts'])
    assert result['commercial_present'] is None
    assert pytesseract.pytesseract.tesseract_cmd == original
    print(json.dumps({'fixture_kind': 'authored_synthetic_only',
        'version': probe['version'], 'languages': loaded['ocr']['languages'],
        'available_languages': probe['available_languages'],
        'gui_configuration_ready': True, 'gui_smoke_success': app.ocr_last_diagnostic['smoke']['success'],
        'gui_smoke_seconds': app.ocr_last_diagnostic['smoke']['elapsed_seconds'],
        'observed_phrase_normalized': d._normalize(' '.join(row['text'] for row in result['texts'][:1])),
        'general_measured_frames': 1, 'commercial_measured_frames': result['measured_frames'],
        'pytesseract_command_restored': True, 'publication_approved': False}))


def test_optional_tk_event_loop_stays_responsive(runtime, monkeypatch):
    import tkinter as tk
    from tkinter import ttk
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip('Tk display unavailable; headless worker tests still run')
    window.withdraw()
    app = headless()
    app.ocr_enabled = tk.BooleanVar(window, value=True)
    app.ocr_languages = tk.StringVar(window, value='por+eng')
    app.ocr_command = tk.StringVar(window, value='C:/Program Files/Tesseract-OCR/tesseract.exe')
    app.ocr_status = tk.StringVar(window, value='Não testado')
    app.start_button = ttk.Button(window)
    button = ttk.Button(window, command=app.verify_ocr)
    entered, release = threading.Event(), threading.Event()
    ticks = []
    def run(args, **kwargs):
        entered.set()
        assert release.wait(3)
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    try:
        button.invoke()
        assert entered.wait(2)
        window.after(0, lambda: ticks.append('responsive'))
        window.update()
        assert ticks == ['responsive'] and app.ocr_busy
        release.set()
        _, payload = app.messages.get(timeout=3)
        app.handle_ocr_result(payload)
        assert 'configuration_only' in app.ocr_status.get()
        assert str(app.start_button['state']) == 'normal'
    finally:
        release.set()
        window.destroy()
