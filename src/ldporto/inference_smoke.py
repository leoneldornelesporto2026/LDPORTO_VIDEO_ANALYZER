"""Explicit synthetic canaries, isolated from readiness and editorial approval."""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone

from .config import ROOT, asset_path
from .core import digest, file_hash

ORDER = ('asr', 'diarization', 'vision', 'ocr', 'semantic')


class SmokeBlocked(RuntimeError):
    def __init__(self, report):
        self.report = report
        super().__init__('Inference smoke bloqueou execucao longa: ' + ', '.join(report['blocking_capabilities']))


class CanaryFailure(RuntimeError):
    """Only internal, allowlisted reasons; loader messages are never copied."""


def _enabled(cfg, name):
    section = 'semantic_analysis' if name == 'semantic' else name
    return name == 'asr' or bool(cfg[section]['enabled'])


def _worker_process(name, cfg, timeout):
    """Hard wall deadline; never export raw loader stdout/stderr or credentials."""
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
               PYTHONPATH=str(ROOT / 'src'), PYTHONIOENCODING='utf-8')
    for key in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='ldporto_smoke_') as temporary:
        request = Path(temporary) / 'request.json'
        response = Path(temporary) / 'response.json'
        request.write_text(json.dumps({'name': name, 'config': cfg}), encoding='utf-8')
        process = subprocess.Popen([sys.executable, '-m', 'ldporto.inference_smoke',
                                    str(request), str(response)], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        close_job = None
        try:
            if os.name == 'nt':
                from .ocr_diagnostics import _windows_job
                close_job = _windows_job(process, 64 * 1024**3, 300)
            process.wait(timeout=timeout)
            if process.returncode or not response.is_file():
                raise RuntimeError('worker_failed')
            return json.loads(response.read_text(encoding='utf-8'))
        finally:
            if close_job:
                close_job()  # kills descendants (including an OCR child)
            if process.poll() is None:
                process.kill()
            if os.name != 'nt':
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()


def run_inference_smoke(cfg, *, requested=None, per_test_seconds=None,
                        total_seconds=None, runner=None):
    """Calling this function is explicit opt-in; default doctor never calls it.

    runner injection is for offline fixtures only. Old receipts are never used to
    authorize a run. All requested enabled canaries must complete successfully.
    """
    settings = cfg.get('preflight', {})
    per_test = float(per_test_seconds if per_test_seconds is not None else settings.get('smoke_test_seconds', 30))
    total = float(total_seconds if total_seconds is not None else settings.get('smoke_total_seconds', 120))
    if not all(math.isfinite(v) and 0 < v <= 300 for v in (per_test, total)):
        raise ValueError('Smoke deadlines must be finite, positive and <=300 seconds')
    requested = set(ORDER if requested is None else requested)
    if requested - set(ORDER):
        raise ValueError('Unknown smoke capability')
    runner = runner or _worker_process
    started = time.monotonic()
    timestamp = datetime.now(timezone.utc).isoformat()
    capabilities = {}
    for name in ORDER:
        item = {'status': 'untested', 'reason': 'not_requested', 'requested': name in requested,
                'required': _enabled(cfg, name) and name in requested,
                'duration_seconds': 0.0, 'inference_executed': False,
                'model_load_verified': None, 'output_shape': None, 'device': None,
                'model_hashes': None, 'warnings': []}
        capabilities[name] = item
        if not _enabled(cfg, name):
            item.update(status='skipped_user_disabled', reason='disabled_by_user')
            continue
        no_model = ((name == 'asr' and cfg['transcription'].get('import_file')) or
                    (name == 'diarization' and cfg['diarization'].get('import_file')) or
                    (name == 'semantic' and cfg['semantic_analysis']['backend'] != 'ollama'))
        if no_model:
            item.update(status='available', reason='configured_non_inference_route', required=False)
            continue
        if name not in requested:
            continue
        remaining = total - (time.monotonic() - started)
        if remaining <= 0:
            item['reason'] = 'total_wall_clock_exhausted'
            continue
        tick = time.monotonic()
        try:
            result = runner(name, cfg, min(per_test, remaining))
            # Only explicit completed receipts count. No truthy default for old JSON.
            if result.get('inference_executed') is not True or result.get('ok') is not True:
                item.update(status='executed_fail', reason=result.get('reason', 'inference_not_proven'))
            else:
                item.update(status='executed_pass', reason='synthetic_canary_completed')
            for key in ('inference_executed', 'model_load_verified', 'output_shape', 'device',
                        'model_hashes', 'warnings', 'memory', 'fixture_sha256', 'components'):
                if key in result:
                    item[key] = result[key]
        except subprocess.TimeoutExpired:
            item.update(status='executed_fail', reason='hard_timeout', inference_executed=None)
        except Exception as exc:
            item.update(status='executed_fail', reason=type(exc).__name__, inference_executed=None)
        item['duration_seconds'] = round(time.monotonic() - tick, 6)
    blocking = [name for name, item in capabilities.items()
                if item['required'] and item['status'] != 'executed_pass']
    report = {'schema_version': '1.0', 'scope': 'synthetic_inference_canary_only',
              'timestamp': timestamp, 'duration_seconds': round(time.monotonic() - started, 6),
              'limits': {'per_test_seconds': per_test, 'total_seconds': total},
              'provenance': {'kind': 'current_execution', 'config_sha256': digest(cfg),
                             'canary_code_sha256': file_hash(Path(__file__)),
                             'backend': 'injected_fixture' if runner is not _worker_process else 'isolated_local'},
              'capabilities': capabilities, 'base_ready': not blocking,
              'long_execution_allowed': not blocking, 'blocking_capabilities': blocking,
              'publish_ready': False, 'quality': None,
              'warnings': ['Silence does not prove transcription or speaker attribution.',
                           'Synthetic frames do not measure face accuracy or identity.',
                           'Ollama schema canary does not prove editorial curation.',
                           'After timeout Ollama server inference may continue; inspect/stop it manually before retry.',
                           'External GPU users and Ollama server memory are not controlled.']}
    report['receipt_sha256'] = digest(report)
    return report


def save_smoke(report, path):
    """Exclusive output: preserve prior receipts and analysis artifacts."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)


def replay_smoke(path):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    original = dict(report)
    checksum = original.pop('receipt_sha256', None)
    if not checksum or digest(original) != checksum:
        raise ValueError('Smoke receipt checksum mismatch')
    return {'scope': 'read_only_replay', 'original_receipt': report,
            'actual_inference_executed_now': False, 'long_execution_allowed': False,
            'publish_ready': False}


def _memory():
    from .ollama_local import nvidia_smi
    snapshot = nvidia_smi()
    return {'available': snapshot.get('available', False), 'gpus': snapshot.get('gpus', [])}


def _infer(name, cfg, folder):
    """One tiny inference per backend; local assets only, no fallback on CUDA failure."""
    result = {'ok': False, 'inference_executed': False, 'model_load_verified': False,
              'device': None, 'model_hashes': None, 'warnings': [], 'output_shape': None}
    before = _memory()
    try:
        if name in ('asr', 'diarization'):
            wav = folder / 'silence.wav'
            with wave.open(str(wav), 'wb') as handle:
                handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                handle.writeframes(b'\0\0' * 32000)
            result['fixture_sha256'] = file_hash(wav)
            result['warnings'].append('Two-second synthetic silence; linguistic accuracy and speaker identity unmeasured.')
        if name == 'asr':
            if cfg['transcription'].get('import_file'):
                result.update(reason='imported_transcript_no_model_inference')
                return result
            from .gpu_runtime import configure_windows_nvidia_runtime
            configure_windows_nvidia_runtime()
            import ctranslate2
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
            device = cfg['device']
            if device == 'auto':
                device = 'cuda' if ctranslate2.get_cuda_device_count() else 'cpu'
                if device == 'cpu' and before.get('available') and not cfg['transcription'].get('allow_cpu_fallback'):
                    raise CanaryFailure('cuda_missing_no_fallback')
            if device == 'cuda' and not ctranslate2.get_cuda_device_count():
                raise CanaryFailure('cuda_missing')
            local = asset_path(cfg['transcription']['model'])
            if not local.is_dir():
                try:
                    local = Path(download_model(cfg['transcription']['model'],
                        local_files_only=True, use_auth_token=False))
                except Exception:
                    result['reason'] = 'whisper_cache_missing_manual_prepare_local_ctranslate2_model'
                    return result
            if not all((local / filename).is_file() and (local / filename).stat().st_size > 0
                       for filename in ('model.bin', 'config.json', 'tokenizer.json')):
                result['reason'] = 'whisper_local_assets_incomplete_no_tokenizer_download_allowed'
                return result
            compute = cfg['compute_type']
            if compute == 'auto':
                compute = 'int8_float16' if device == 'cuda' else 'int8'
            model = WhisperModel(str(local), device=device, compute_type=compute, local_files_only=True)
            result.update(model_load_verified=True, device=device)
            from .transcription import recognition_options
            segments, info = model.transcribe(str(wav), **recognition_options(cfg), beam_size=1,
                                             vad_filter=False, condition_on_previous_text=False)
            rows = list(segments)  # generator must be consumed to execute CTranslate2
            result['inference_executed'] = True
            result['output_shape'] = {'segments': len(rows), 'language': info.language}
            from .preflight import model_directory_fingerprint
            result['model_hashes'] = {'local_assets': model_directory_fingerprint(local)}
        elif name == 'diarization':
            if cfg['diarization'].get('import_file'):
                result.update(reason='imported_turns_no_model_inference')
                return result
            from .model_cache import cached_pipeline_snapshot
            local = cached_pipeline_snapshot(cfg['diarization']['model'])
            if local is None:
                result.update(reason='cache_missing_manual_accept_and_populate_community_1_before_retry')
                return result
            from .media_runtime import bootstrap_ffmpeg_shared
            bootstrap_ffmpeg_shared(cfg.get('media_tools', {}).get('ffmpeg_shared_dir'))
            import torch
            from pyannote.audio import Pipeline
            device = cfg['device']
            if device == 'auto':
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            if device == 'cuda' and not torch.cuda.is_available():
                raise CanaryFailure('cuda_missing')
            model = Pipeline.from_pretrained(str(local), token=None)
            model.to(torch.device(device))
            result.update(model_load_verified=True, device=device)
            with torch.inference_mode():
                output = model({'waveform': torch.zeros(1, 32000), 'sample_rate': 16000})
            annotation = getattr(output, 'speaker_diarization', output)
            result['output_shape'] = {'turns': len(list(annotation.itertracks(yield_label=True)))}
            from .preflight import model_directory_fingerprint
            result['model_hashes'] = {'local_assets': model_directory_fingerprint(local)}
        elif name == 'vision':
            import cv2
            import numpy as np
            vision = cfg['vision']
            frame = np.zeros((320, 320, 3), dtype=np.uint8)
            cv2.circle(frame, (160, 160), 90, (200, 200, 200), -1)
            result['fixture_sha256'] = digest(frame.tolist())
            hashes = {key: file_hash(asset_path(vision[key])) for key in ('yunet_model', 'sface_model')}
            detector = cv2.FaceDetectorYN.create(str(asset_path(vision['yunet_model'])), '', (320, 320))
            recognizer = cv2.FaceRecognizerSF.create(str(asset_path(vision['sface_model'])), '')
            result.update(model_load_verified=True, device='cpu', model_hashes=hashes)
            _, faces = detector.detect(frame)
            feature = recognizer.feature(cv2.resize(frame, (112, 112)))
            components = {'yunet': {'faces': 0 if faces is None else len(faces)},
                          'sface': {'embedding_shape': list(feature.shape)}}
            if vision['active_speaker']:
                from .vision import LipEngine
                landmarker = LipEngine(vision)
                try:
                    components['mediapipe'] = {'landmarks': len(landmarker.detect(frame))}
                    hashes['landmarker_model'] = file_hash(asset_path(vision['landmarker_model']))
                finally:
                    landmarker.close()
            if vision['body_detection']:
                from .vision import load_local_yolo
                body, receipt = load_local_yolo(vision)
                if body is None:
                    if vision['body_backend'] != 'hog':
                        result.update(reason='body_backend_fallback_requires_explicit_hog_selection', components=components)
                        return result
                    hog = cv2.HOGDescriptor()
                    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                    boxes, _ = hog.detectMultiScale(frame)
                    components['body'] = {'backend': 'hog', 'device': 'cpu', 'boxes': len(boxes)}
                else:
                    if vision.get('yolo_device') == 'cuda' and not str(receipt.get('device')).startswith('cuda'):
                        raise CanaryFailure('body_cuda_downgrade_forbidden')
                    output = body.predict(frame, classes=[0], verbose=False,
                        conf=vision.get('yolo_confidence', .5), device=receipt['device'])[0]
                    actual = str(getattr(getattr(body, 'predictor', None), 'device', 'unknown'))
                    if actual != receipt['device']:
                        raise CanaryFailure('body_device_execution_mismatch')
                    components['body'] = {'backend': 'yolo', 'device': actual, 'boxes': len(output.boxes)}
                    hashes['body'] = receipt.get('model_sha256')
            result.update(output_shape=components, components=components)
            result['warnings'].append('Synthetic crop embedding is not identity evidence; body accuracy is unmeasured.')
        elif name == 'ocr':
            from .ocr_diagnostics import diagnose_ocr
            diagnostic = diagnose_ocr(cfg['ocr'], smoke=True)
            result.update(ok=diagnostic['ok'], inference_executed=diagnostic['inference_executed'],
                          model_load_verified=diagnostic['checks'].get('model_load', {}).get('ok', False),
                          device='cpu', reason=diagnostic['reason'],
                          output_shape={'text_chars': len(diagnostic['smoke'].get('observed_text') or '')})
            if diagnostic['smoke'].get('limitation'):
                result['warnings'].append(diagnostic['smoke']['limitation'])
            return result
        elif name == 'semantic':
            sem = cfg['semantic_analysis']
            if sem['backend'] != 'ollama':
                result.update(reason='heuristic_backend_no_model_inference')
                return result
            from .ollama_local import service_info, chat, _request_json
            info = service_info(sem['ollama_url'], timeout=2)
            requested = sem['model'] if ':' in sem['model'] else sem['model'] + ':latest'
            entry = next((row for row in info['models'] if row.get('name') in (sem['model'], requested)), None)
            if not info['reachable'] or entry is None:
                result.update(reason='ollama_offline_or_model_not_installed')
                return result
            schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean', 'const': True}},
                      'required': ['ok'], 'additionalProperties': False}
            data, meta = chat(sem['ollama_url'], entry['name'],
                [{'role': 'user', 'content': 'Return only JSON: {"ok":true}'}], schema,
                {**sem, 'timeout_seconds': 15, 'num_ctx': 512, 'num_predict': 32, 'think': False, 'keep_alive': 0})
            if data != {'ok': True}:
                raise CanaryFailure('schema_failed')
            ps = _request_json(sem['ollama_url'], '/api/ps', timeout=2)
            running = next((row for row in ps.get('models', []) if row.get('name') == entry['name']), {})
            result.update(model_load_verified=True, device=('gpu_or_mixed' if running.get('size_vram') else None),
                          model_hashes={'ollama_digest': entry.get('digest')}, output_shape={'ok': 'boolean'})
            result['warnings'].append('keep_alive=0 requests release; server device may be unknown after unload.')
        result.update(ok=True, inference_executed=True)
    except Exception as exc:
        # Do not copy model exception messages, which may expose auth or paths.
        result.update(reason=str(exc) if isinstance(exc, CanaryFailure) else type(exc).__name__,
                      inference_executed=True if result['inference_executed'] is True else None)
    finally:
        result['memory'] = {'before': before, 'after': _memory(), 'scope': 'global_nvidia_snapshot_not_process_peak'}
        # Subprocess exit is the final native allocator cleanup, including on timeout.
    return result


def worker_main(request_path, response_path):
    request = json.loads(Path(request_path).read_text(encoding='utf-8'))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = _infer(request['name'], request['config'], Path(request_path).parent)
    Path(response_path).write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    worker_main(*sys.argv[1:])
