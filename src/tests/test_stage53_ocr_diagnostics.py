"""Offline synthetic diagnostics; mocked OCR is not production OCR evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import types

import pytest

from ldporto import ocr_diagnostics as d
from ldporto.config import load_config
from ldporto import preflight


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    binary = tmp_path / 'tesseract.exe'
    binary.write_bytes(b'fixture-only')
    binary.chmod(0o755)
    data = tmp_path / 'tessdata'
    data.mkdir()
    for lang in ('por', 'eng'):
        (data / (lang + '.traineddata')).write_bytes(b'synthetic')
    monkeypatch.setattr(d.importlib, 'import_module', lambda _: types.SimpleNamespace())
    monkeypatch.setattr(d.shutil, 'which', lambda _: str(binary))
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if '--version' in args:
            text = 'tesseract 5.4.1\n leptonica-1.84.1'
        elif '--list-langs' in args:
            text = f'List of available languages in "{data}" (2):\neng\npor\n'
        elif '--print-parameters' in args:
            text = 'Tesseract parameters:\n'
        else:
            text = 'PORTUGUES: acao e informacao\nENGLISH: clear text sample\n'
        return subprocess.CompletedProcess(args, 0, text, '')

    monkeypatch.setattr(d, '_run', run)
    monkeypatch.setattr(d, '_fixture', lambda path: (
        'PORTUGUES: acao e informacao\nENGLISH: clear text sample',
        'accent_font_unavailable_ascii_fixture'))
    return types.SimpleNamespace(binary=binary, data=data, calls=calls, run=run,
                                 cfg={'enabled': True, 'languages': 'por+eng'})


def test_disabled_never_imports_or_resolves(monkeypatch):
    monkeypatch.setattr(d.importlib, 'import_module', lambda _: pytest.fail('import'))
    monkeypatch.setattr(d.shutil, 'which', lambda _: pytest.fail('binary probe'))
    r = d.diagnose_ocr({'enabled': False}, smoke=True)
    assert r['status'] == 'DISABLED' and r['reason'] == 'disabled_by_user'
    assert not r['inference_executed'] and r['smoke']['success'] is None


def test_dependency_missing_and_scrub(runtime, monkeypatch):
    def missing(_):
        raise ImportError('C:\\Users\\private\\token hf_' + 'x' * 30)
    monkeypatch.setattr(d.importlib, 'import_module', missing)
    r = d.diagnose_ocr(runtime.cfg)
    assert r['status'] == 'dependency_missing'
    assert runtime.calls == [] and 'private' not in json.dumps(r) and 'hf_' not in json.dumps(r)


@pytest.mark.parametrize('command', [None, 'missing.exe', 'C:\\missing\\bad.exe', 'exe --evil', 'bad; echo secret'])
def test_binary_missing_or_invalid(runtime, monkeypatch, command):
    monkeypatch.setattr(d.shutil, 'which', lambda _: None)
    r = d.diagnose_ocr({**runtime.cfg, 'tesseract_cmd': command})
    assert r['status'] == 'binary_missing' and not runtime.calls


def test_resolved_directory_is_not_binary(runtime, monkeypatch):
    monkeypatch.setattr(d.shutil, 'which', lambda _: str(runtime.data))
    assert d.diagnose_ocr(runtime.cfg)['status'] == 'binary_missing'


def test_executable_permission_required(runtime, monkeypatch):
    monkeypatch.setattr(d.os, 'access', lambda *args: False)
    assert d.diagnose_ocr(runtime.cfg)['status'] == 'binary_missing'


@pytest.mark.parametrize('missing', ['por', 'eng'])
def test_each_requested_language_missing(runtime, monkeypatch, missing):
    def run(args, **kwargs):
        if '--list-langs' in args:
            return subprocess.CompletedProcess(args, 0,
                f'List of available languages in "{runtime.data}" (1):\n' +
                ('eng' if missing == 'por' else 'por') + '\n', '')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    r = d.diagnose_ocr(runtime.cfg, smoke=True)
    assert r['status'] == 'missing_languages' and r['missing_languages'] == [missing]
    assert not r['inference_executed']


def test_ready_proves_config_only(runtime):
    r = d.diagnose_ocr(runtime.cfg)
    assert r['status'] == 'READY' and r['version'] == '5.4.1'
    assert r['checks']['tessdata']['ok'] and r['checks']['model_load']['ok']
    assert not r['inference_executed'] and r['smoke']['success'] is None
    assert len(runtime.calls) == 3
    assert str(runtime.data) not in json.dumps(r) and str(runtime.binary) not in json.dumps(r)


@pytest.mark.parametrize('problem', ['missing_file', 'empty_file', 'load_failure', 'version_failure', 'bad_listing'])
def test_model_load_failed(runtime, monkeypatch, problem):
    if problem == 'missing_file':
        (runtime.data / 'por.traineddata').unlink()
    if problem == 'empty_file':
        (runtime.data / 'por.traineddata').write_bytes(b'')
    def run(args, **kwargs):
        if ((problem == 'load_failure' and '--print-parameters' in args) or
            (problem == 'version_failure' and '--version' in args)):
            return subprocess.CompletedProcess(args, 1, '', 'private path')
        if problem == 'bad_listing' and '--list-langs' in args:
            return subprocess.CompletedProcess(args, 0, 'eng\npor', '')
        return runtime.run(args, **kwargs)
    monkeypatch.setattr(d, '_run', run)
    r = d.diagnose_ocr(runtime.cfg)
    expected = 'binary_execution_failed' if problem == 'version_failure' else 'tessdata_unavailable'
    assert r['status'] == expected and not r['inference_executed']
    assert 'private' not in json.dumps(r)


def test_smoke_ok_and_temporary_paths_removed(runtime):
    r = d.diagnose_ocr(runtime.cfg, smoke=True)
    assert r['status'] == 'READY' and r['inference_executed'] and r['smoke']['success']
    assert r['smoke']['normalized_text'] == 'portugues acao e informacao english clear text sample'
    assert r['smoke']['elapsed_seconds'] >= 0
    assert r['smoke']['limitation'] == 'accent_font_unavailable_ascii_fixture'
    args, kwargs = runtime.calls[-1]
    assert args[-3:] == ['por+eng', '--psm', '6']
    temporary = Path(args[1]).parent
    assert not temporary.exists() and str(temporary) not in json.dumps(r)
    assert kwargs.get('cwd') is None  # preserve relative TESSDATA_PREFIX/PATH


@pytest.mark.parametrize('failure', ['timeout', 'exception', 'mismatch', 'path_output'])
def test_smoke_failed(runtime, monkeypatch, failure):
    def run(args, **kwargs):
        if '--psm' not in args:
            return runtime.run(args, **kwargs)
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 5)
        if failure == 'exception':
            raise RuntimeError('private C:\\Users\\name hf_' + 'a' * 30)
        return subprocess.CompletedProcess(args, 0,
            'wrong words' if failure == 'mismatch' else 'C:\\Users\\private', '')
    monkeypatch.setattr(d, '_run', run)
    r = d.diagnose_ocr(runtime.cfg, smoke=True)
    assert r['status'] == ('timeout' if failure == 'timeout' else 'smoke_failed') and r['smoke']['success'] is False
    assert r['smoke']['elapsed_seconds'] >= 0
    assert 'private' not in json.dumps(r) and 'hf_' not in json.dumps(r)
    if failure in ('timeout', 'exception'):
        assert r['inference_executed'] is None


def test_preflight_keeps_legacy_status_and_no_smoke(runtime, tmp_path, monkeypatch):
    cfg = load_config()
    cfg['transcription']['import_file'] = str(tmp_path / 'transcript.json')
    (tmp_path / 'transcript.json').write_text('{}')
    for name in ('vision', 'diarization', 'scenes', 'audio_events'):
        cfg[name]['enabled'] = False
    cfg['preview']['enabled'] = False
    cfg['semantic_analysis']['backend'] = 'heuristic'
    cfg['ocr'] = runtime.cfg
    monkeypatch.setattr(preflight, '_output_check', lambda _: {'ok': True})
    report = preflight.run_preflight(cfg)
    cap = report['capabilities']['ocr']
    assert cap['status'] == 'READY' and cap['diagnostic_state'] == 'READY'
    assert not cap['inference_executed'] and len(runtime.calls) == 3
    monkeypatch.setattr(d.shutil, 'which', lambda _: None)
    cap = preflight.run_preflight(cfg)['capabilities']['ocr']
    assert cap['status'] == 'ERROR' and cap['diagnostic_state'] == 'binary_missing'
    cfg['ocr']['enabled'] = False
    cap = preflight.run_preflight(cfg)['capabilities']['ocr']
    assert cap['status'] == 'DISABLED' and not cap['required']


def test_real_bounded_child_and_timeout():
    # Python only, no Tesseract/model/GPU: exercises Windows Job Object on this host.
    r = d._run([sys.executable, '-c', 'import os; print(os.environ["OMP_THREAD_LIMIT"])'])
    assert r.returncode == 0 and r.stdout.strip() == '1'
    with pytest.raises(subprocess.TimeoutExpired):
        d._run([sys.executable, '-c', 'import time; time.sleep(2)'], timeout=.1)


def test_real_child_memory_limit():
    code = 'try:\n data = bytearray(300 * 1024**2)\n print("unbounded")\nexcept MemoryError:\n print("limited")'
    r = d._run([sys.executable, '-c', code])
    assert r.returncode == 0 and r.stdout.strip() == 'limited'


def test_cli_explicit_smoke_only(runtime, capsys):
    assert d.main([]) == 0
    r = json.loads(capsys.readouterr().out)
    assert not r['smoke']['requested'] and not r['inference_executed']
    assert d.main(['--smoke']) == 0
    r = json.loads(capsys.readouterr().out)
    assert r['smoke']['requested'] and r['smoke']['success']


@pytest.mark.skipif(os.name != 'nt', reason='Windows executable suffix contract')
def test_windows_batch_rejected(runtime, monkeypatch):
    batch = runtime.binary.with_suffix('.cmd')
    batch.write_text('echo fixture')
    monkeypatch.setattr(d.shutil, 'which', lambda _: str(batch))
    assert d.diagnose_ocr(runtime.cfg)['status'] == 'binary_missing'
    assert not runtime.calls


def test_real_synthetic_image(tmp_path):
    path = tmp_path / 'synthetic.png'
    expected, limitation = d._fixture(path)
    from PIL import Image
    with Image.open(path) as image:
        assert image.size == (1000, 180)
    assert 'ENGLISH' in expected and 'informacao' in d._normalize(expected)
    assert limitation in (None, 'accent_font_unavailable_ascii_fixture')
