"""Offline canary contract tests. Fixtures are not production inference proof."""
import json
import subprocess
import sys
import types
import wave

import pytest

from ldporto.config import load_config
from ldporto import inference_smoke as smoke, preflight


def cfg():
    config = load_config()
    config['semantic_analysis'].update(enabled=True, backend='ollama')
    return config


def passed(*args):
    return {'ok': True, 'inference_executed': True, 'model_load_verified': True,
            'device': 'fixture_cpu', 'output_shape': {'rows': 0}, 'model_hashes': None}


def test_sequential_partial_timeout_and_disabled():
    config = cfg()
    config['ocr']['enabled'] = False
    calls = []
    def runner(name, config, timeout):
        calls.append(name)
        assert 0 < timeout <= 3
        if name == 'diarization':
            raise subprocess.TimeoutExpired('fixture', timeout)
        if name == 'semantic':
            return {'ok': False, 'inference_executed': False, 'reason': 'ollama_offline'}
        return passed()
    report = smoke.run_inference_smoke(config, runner=runner, per_test_seconds=3, total_seconds=10)
    assert calls == ['asr', 'diarization', 'vision', 'semantic']
    assert report['capabilities']['ocr']['status'] == 'skipped_user_disabled'
    assert report['capabilities']['asr']['status'] == 'executed_pass'
    assert report['capabilities']['diarization']['reason'] == 'hard_timeout'
    assert report['capabilities']['diarization']['inference_executed'] is None
    assert report['blocking_capabilities'] == ['diarization', 'semantic']
    assert not report['base_ready'] and not report['publish_ready']
    assert report['quality'] is None
    assert report['provenance']['backend'] == 'injected_fixture'


def test_total_deadline_leaves_remaining_untested(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(smoke.time, 'monotonic', lambda: clock[0])
    def runner(*args):
        clock[0] += 2
        return passed()
    report = smoke.run_inference_smoke(cfg(), runner=runner, total_seconds=1)
    assert report['capabilities']['asr']['status'] == 'executed_pass'
    assert report['capabilities']['vision']['status'] == 'untested'
    assert report['capabilities']['vision']['reason'] == 'total_wall_clock_exhausted'
    assert not report['long_execution_allowed']


def test_load_only_receipt_cannot_pass():
    report = smoke.run_inference_smoke(cfg(), requested=['asr'], runner=lambda *a: {'ok': True})
    assert report['capabilities']['asr']['status'] == 'executed_fail'
    assert report['capabilities']['vision']['status'] == 'untested'


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), 301])
def test_bad_deadlines_rejected_before_execution(value):
    with pytest.raises(ValueError):
        smoke.run_inference_smoke(cfg(), total_seconds=value, runner=lambda *a: pytest.fail('called'))


def test_disabled_ocr_does_not_block():
    config = cfg()
    config['ocr']['enabled'] = False
    report = smoke.run_inference_smoke(config, runner=passed)
    assert report['base_ready'] and report['long_execution_allowed']


def test_non_inference_routes_available_without_false_receipt():
    config = cfg()
    config['transcription']['import_file'] = 'fixture.json'
    config['diarization']['import_file'] = 'fixture_turns.json'
    config['semantic_analysis']['backend'] = 'heuristic'
    report = smoke.run_inference_smoke(config, runner=passed)
    assert report['base_ready']
    for name in ('asr', 'diarization', 'semantic'):
        assert report['capabilities'][name]['status'] == 'available'
        assert report['capabilities'][name]['inference_executed'] is False


def test_gate_prevents_media_and_normal_doctor_unchanged(monkeypatch, tmp_path):
    config = cfg()
    config['preflight']['inference_smoke'] = True
    monkeypatch.setattr(smoke, 'run_inference_smoke', lambda c: {'long_execution_allowed': False,
        'blocking_capabilities': ['asr']})
    monkeypatch.setattr(preflight, 'run_preflight', lambda *a: pytest.fail('normal checks reached'))
    from ldporto import pipeline
    monkeypatch.setattr(pipeline, 'resolve_input', lambda *a: pytest.fail('media touched'))
    with pytest.raises(smoke.SmokeBlocked):
        pipeline.analyze('missing_fixture.wav', config, tmp_path)
    assert list(tmp_path.glob('inference_smoke_*.json'))
    config['preflight']['inference_smoke'] = False
    monkeypatch.setattr(preflight, 'run_preflight', lambda *a: {'ready': True})
    monkeypatch.setattr(smoke, 'run_inference_smoke', lambda c: pytest.fail('implicit inference'))
    assert preflight.require_preflight(config)['ready']


def test_replay_integrity_and_never_grants_execution(tmp_path):
    report = smoke.run_inference_smoke(cfg(), runner=passed)
    path = tmp_path / 'receipt.json'
    smoke.save_smoke(report, path)
    with pytest.raises(FileExistsError):
        smoke.save_smoke(report, path)
    replay = smoke.replay_smoke(path)
    assert replay['original_receipt']['provenance'] == report['provenance']
    assert not replay['actual_inference_executed_now'] and not replay['long_execution_allowed']
    report['capabilities']['asr']['device'] = 'forged'
    path.write_text(json.dumps(report), encoding='utf-8')
    with pytest.raises(ValueError, match='checksum'):
        smoke.replay_smoke(path)


def test_worker_timeout_kills_and_never_passes_tokens(monkeypatch):
    seen = {}
    class Process:
        pid = 987654321
        returncode = None
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired('fixture', timeout)
            return 0
        def poll(self):
            return self.returncode
        def kill(self):
            seen['killed'] = True
            self.returncode = -9
    def popen(args, **kwargs):
        seen.update(kwargs)
        return Process()
    monkeypatch.setenv('HF_TOKEN', 'fixture_secret')
    monkeypatch.setattr(smoke.subprocess, 'Popen', popen)
    from ldporto import ocr_diagnostics
    monkeypatch.setattr(ocr_diagnostics, '_windows_job', lambda *a: lambda: None)
    if smoke.os.name != 'nt':
        monkeypatch.setattr(smoke.os, 'killpg', lambda *a: None)
    with pytest.raises(subprocess.TimeoutExpired):
        smoke._worker_process('asr', cfg(), 0.1)
    assert seen['killed']
    assert 'HF_TOKEN' not in seen['env']
    assert seen['env']['HF_HUB_OFFLINE'] == '1'


def test_synthetic_wav_no_user_audio_and_cuda_missing(monkeypatch, tmp_path):
    config = cfg()
    config['device'] = 'cuda'
    monkeypatch.setattr(smoke, '_memory', lambda: {'available': False})
    from ldporto import gpu_runtime
    monkeypatch.setattr(gpu_runtime, 'configure_windows_nvidia_runtime', lambda: {})
    monkeypatch.setitem(sys.modules, 'ctranslate2', types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    monkeypatch.setitem(sys.modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=lambda *a, **k: pytest.fail('model loaded')))
    monkeypatch.setitem(sys.modules, 'faster_whisper.utils', types.SimpleNamespace(download_model=lambda *a, **k: pytest.fail('download')))
    result = smoke._infer('asr', config, tmp_path)
    assert not result['ok'] and result['device'] is None
    with wave.open(str(tmp_path / 'silence.wav')) as wav:
        assert wav.getnframes() == 32000 and wav.getframerate() == 16000
    assert result['fixture_sha256']


def test_pyannote_cache_missing_action_no_token(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, '_memory', lambda: {})
    from ldporto import model_cache
    monkeypatch.setattr(model_cache, 'cached_pipeline_snapshot', lambda *a: None)
    result = smoke._infer('diarization', cfg(), tmp_path)
    assert result['reason'] == 'cache_missing_manual_accept_and_populate_community_1_before_retry'
    assert result['inference_executed'] is False


def test_ollama_offline_never_calls_chat(monkeypatch, tmp_path):
    from ldporto import ollama_local
    monkeypatch.setattr(smoke, '_memory', lambda: {})
    monkeypatch.setattr(ollama_local, 'service_info', lambda *a, **k: {'reachable': False, 'models': []})
    monkeypatch.setattr(ollama_local, 'chat', lambda *a, **k: pytest.fail('inference'))
    result = smoke._infer('semantic', cfg(), tmp_path)
    assert result['reason'] == 'ollama_offline_or_model_not_installed'
    assert not result['ok']


def test_asr_consumes_lazy_generator_local_only(monkeypatch, tmp_path):
    config = cfg()
    config['device'] = 'cpu'
    local = tmp_path / 'model'
    local.mkdir()
    (local / 'model.bin').write_bytes(b'fake_weights_not_model')
    (local / 'config.json').write_text('{}')
    (local / 'tokenizer.json').write_text('{}')
    config['transcription']['model'] = str(local)
    calls = []
    class Model:
        def __init__(self, path, **kwargs):
            assert path == str(local) and kwargs['local_files_only'] is True
            assert kwargs['device'] == 'cpu'
        def transcribe(self, path, **kwargs):
            assert kwargs['vad_filter'] is False
            def segments():
                calls.append('actual_generator_iteration')
                yield types.SimpleNamespace(text='synthetic backend fixture')
            return segments(), types.SimpleNamespace(language='pt')
    monkeypatch.setattr(smoke, '_memory', lambda: {})
    from ldporto import gpu_runtime
    monkeypatch.setattr(gpu_runtime, 'configure_windows_nvidia_runtime', lambda: {})
    monkeypatch.setitem(sys.modules, 'ctranslate2', types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    monkeypatch.setitem(sys.modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, 'faster_whisper.utils', types.SimpleNamespace(download_model=lambda *a, **k: pytest.fail('download')))
    result = smoke._infer('asr', config, tmp_path)
    assert calls == ['actual_generator_iteration']
    assert result['ok'] and result['inference_executed'] is True
    assert result['output_shape'] == {'segments': 1, 'language': 'pt'}
    assert result['model_hashes']['local_assets']


def test_ocr_missing_font_failure_is_not_pass(monkeypatch, tmp_path):
    from ldporto import ocr_diagnostics
    monkeypatch.setattr(smoke, '_memory', lambda: {})
    monkeypatch.setattr(ocr_diagnostics, 'diagnose_ocr', lambda c, smoke: {
        'ok': False, 'inference_executed': False, 'reason': 'smoke_failed',
        'checks': {'model_load': {'ok': True}},
        'smoke': {'success': False, 'observed_text': None, 'limitation': 'font_unavailable'}})
    result = smoke._infer('ocr', cfg(), tmp_path)
    assert not result['ok'] and result['inference_executed'] is False
    assert result['model_load_verified'] is True
    assert 'font_unavailable' in result['warnings']


def test_cli_explicit_smoke_and_replay_do_not_call_doctor(monkeypatch, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('analyze_stage60', smoke.ROOT / 'analyze.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'configure_path', lambda: None)
    monkeypatch.setattr(cli, 'doctor', lambda *a: pytest.fail('doctor changed or invoked'))
    monkeypatch.setattr(smoke, 'run_inference_smoke', lambda c: smoke_report)
    smoke_report = {'base_ready': False, 'inference_executed': False}
    path = tmp_path / 'cli_receipt.json'
    monkeypatch.setattr(sys, 'argv', ['analyze', '--inference-smoke', '--smoke-output', str(path)])
    assert cli.main() == 2
    assert json.loads(path.read_text()) == smoke_report
    monkeypatch.setattr(smoke, 'replay_smoke', lambda p: {'long_execution_allowed': False})
    monkeypatch.setattr(smoke, 'run_inference_smoke', lambda *a: pytest.fail('replay executed inference'))
    monkeypatch.setattr(sys, 'argv', ['analyze', '--smoke-replay', str(path)])
    assert cli.main() == 0


def test_whisper_cached_lookup_cannot_write_model_directory(monkeypatch, tmp_path):
    config = cfg()
    config['device'] = 'cpu'
    monkeypatch.setattr(smoke, '_memory', lambda: {})
    from ldporto import gpu_runtime
    monkeypatch.setattr(gpu_runtime, 'configure_windows_nvidia_runtime', lambda: {})
    monkeypatch.setitem(sys.modules, 'ctranslate2', types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    monkeypatch.setitem(sys.modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=lambda *a, **k: pytest.fail('incomplete model loaded')))
    def lookup(model, **kwargs):
        assert kwargs == {'local_files_only': True, 'use_auth_token': False}
        return str(tmp_path)
    monkeypatch.setitem(sys.modules, 'faster_whisper.utils', types.SimpleNamespace(download_model=lookup))
    result = smoke._infer('asr', config, tmp_path)
    assert result['reason'] == 'whisper_local_assets_incomplete_no_tokenizer_download_allowed'
    assert not result['inference_executed']
