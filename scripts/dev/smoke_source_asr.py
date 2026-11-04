"""Explicit short local ASR inference; --help imports no model/runtime modules."""
import argparse
import gc
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inferencia ASR curta local, sem downloads; JSON novo exclusivo.')
    parser.add_argument('source', type=Path, help='Video local curto; nunca URL')
    parser.add_argument('--output', required=True, type=Path, help='JSON novo; arquivo existente nunca e substituido')
    parser.add_argument('--model', default='large-v3', help='Diretorio CTranslate2 existente ou nome no cache local')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--device', choices=('cuda', 'cpu', 'auto'), default='cuda')
    parser.add_argument('--compute-type', default='auto')
    parser.add_argument('--max-seconds', type=float, default=30., help='Recusa fontes mais longas; limite maximo 120s')
    parser.add_argument('--expect-text', help='Fragmento literal esperado, comparado sem caso/pontuacao; nunca corrige texto')
    parser.add_argument('--forbid-text', help='Fragmento proibido pelo diagnostico, sem reescrever a transcricao')
    args = parser.parse_args(argv)
    if not 0 < args.max_seconds <= 120:
        parser.error('--max-seconds deve estar entre 0 e 120')
    if not args.source.is_file():
        parser.error('source deve ser um arquivo local existente')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the artifact before any heavy work; a second run cannot overwrite
    # its evidence, even if a previous attempt failed after inference began.
    with args.output.open('x', encoding='utf-8') as handle:
        result = {'schema_version': '1.0', 'validation_kind': 'real_video_inference',
                  'status': 'failed', 'inference_executed': False, 'human_audio_review': False,
                  'publication_ready': False, 'translations': [], 'downloads_allowed': False,
                  'requested_device': args.device, 'source_filename': args.source.name}
        engine = None
        started = time.monotonic()
        try:
            root = Path(__file__).resolve().parents[2]
            sys.path.insert(0, str(root / 'src'))
            # Process-local offline flags complement both mandatory local-only
            # cache resolution and a complete existing-directory model path.
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            from ldporto.config import load_config, asset_path
            from ldporto.core import file_hash, digest, scrub
            from ldporto.media import inspect
            from ldporto.audio import ffmpeg_audio
            from ldporto.transcription import TranscriptionEngine, recognition_options, word_text
            from ldporto.asr_comparison import lexical_text
            cfg = load_config(args.config)
            cfg.update(language='auto', offline=True, device=args.device, compute_type=args.compute_type)
            cfg['transcription'].update(multilingual=True, multipass=False, source_selection='original',
                                        allow_cpu_fallback=False, glossary='')
            for tool in ('ffmpeg', 'ffprobe'):
                explicit = cfg.get('media_tools', {}).get(tool + '_path')
                if explicit:
                    os.environ['LDPORTO_' + tool.upper()] = str(asset_path(explicit))
            inspected = inspect(args.source.resolve())
            metadata = inspected['data']
            if metadata['duration'] > args.max_seconds:
                raise ValueError('Fonte excede o limite autorizado de inferencia curta.')
            result.update(source_sha256=file_hash(args.source), source_metadata=metadata,
                          recognition_options=recognition_options(cfg))
            local = asset_path(args.model)
            if not local.is_dir():
                from ldporto.gpu_runtime import configure_windows_nvidia_runtime
                configure_windows_nvidia_runtime()
                from faster_whisper.utils import download_model
                for cache in (str(root / 'models/whisper'), None):
                    try:
                        local = Path(download_model(args.model, cache_dir=cache,
                            local_files_only=True, use_auth_token=False))
                        break
                    except Exception:
                        continue
                if not local.is_dir():
                    raise ValueError('Modelo inexistente nos caches locais; downloads proibidos.')
            required = ('model.bin', 'config.json', 'tokenizer.json')
            if not all((local / filename).is_file() and (local / filename).stat().st_size > 0 for filename in required):
                raise ValueError('Modelo CTranslate2 local incompleto; nenhum download permitido.')
            hashed_at = time.monotonic()
            hashes = {filename: file_hash(local / filename) for filename in required}
            result.update(model_directory=str(local.resolve()), model_asset_sha256=hashes,
                          model_hash_seconds=time.monotonic()-hashed_at)
            cfg['transcription']['model'] = str(local.resolve())
            ctx = SimpleNamespace(config=cfg, logger=logging.getLogger('source-asr-smoke'),
                                  asr_model_fingerprint=digest(hashes))
            engine = TranscriptionEngine(ctx)
            with tempfile.TemporaryDirectory(prefix='ldporto_asr_smoke_') as folder:
                wav = Path(folder) / 'original_mono_16k.wav'
                offset = metadata['audio_start_time']-metadata['video_start_time']
                sync = f'atrim=start={-offset:.9f},asetpts=PTS-STARTPTS' if offset < 0 else 'asetpts=PTS-STARTPTS'
                if offset > 0:
                    sync += f',adelay={offset*1000:.6f}:all=1'
                sync += f",apad,atrim=duration={metadata['duration']:.9f}"
                extracted_at = time.monotonic()
                ffmpeg_audio(args.source.resolve(), wav, filters=sync, sample_rate=16000, channels=1)
                result.update(audio_sha256=file_hash(wav), audio_sample_rate=16000, audio_channels=1,
                              extraction_seconds=time.monotonic()-extracted_at)
                loaded_at = time.monotonic()
                engine._load()
                result['model_load_seconds'] = time.monotonic()-loaded_at
                inference_at = time.monotonic()
                recognized = engine.recognize(wav)
                result.update(inference_seconds=time.monotonic()-inference_at, inference_executed=True,
                              actual_device=engine.actual_device, actual_compute_type=engine.actual_compute,
                              text=word_text(recognized['words']), hypothesis=recognized)
            def contains(fragment):
                haystack, needle = lexical_text(result['text']), lexical_text(fragment)
                return bool(needle) and any(haystack[index:index+len(needle)] == needle
                                          for index in range(len(haystack)-len(needle)+1))
            checks = {'task_is_transcribe': recognized.get('task') == 'transcribe',
                      'text_is_original_hypothesis': recognized.get('text_kind') == 'original_asr_hypothesis',
                      'translation_artifact_separate_and_empty': result['translations'] == [],
                      'automatic_multilingual_requested': result['recognition_options'] ==
                         {'task': 'transcribe', 'language': None, 'multilingual': True}}
            if args.expect_text:
                checks['expected_literal_fragment_present'] = contains(args.expect_text)
            if args.forbid_text:
                checks['forbidden_literal_fragment_absent'] = not contains(args.forbid_text)
            result['checks'] = checks
            result['status'] = 'passed' if all(checks.values()) else 'failed_assertion'
            result['word_accuracy_verified'] = False
        except Exception as exc:
            from ldporto.core import scrub
            result.update(error_type=type(exc).__name__, error=scrub(exc))
        finally:
            if engine is not None:
                engine.model = None
            gc.collect()
            result['elapsed_seconds'] = time.monotonic()-started
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        print(json.dumps({key: result.get(key) for key in ('status', 'inference_executed', 'actual_device',
                                                         'actual_compute_type', 'inference_seconds', 'checks')}, ensure_ascii=False))
        return 0 if result['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
