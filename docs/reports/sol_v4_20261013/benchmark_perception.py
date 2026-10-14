"""Run only scenes/vision on the same bounded local excerpt in isolated output."""
from pathlib import Path
import argparse
import json
import logging
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.config import load_config
from ldporto.core import digest, file_hash, read_json, write_json
from ldporto.runtime_metrics import resource_snapshot

def prepare():
    source = ROOT / 'input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4'
    clip = REPORT / 'source_0000_0120_av1.mp4'
    if not clip.exists():
        from ldporto.media_runtime import find_media_tool
        command = [find_media_tool('ffmpeg'), '-v', 'error', '-n', '-i', str(source),
                   '-t', '120', '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', str(clip)]
        subprocess.run(command, check=True, timeout=60)
        write_json(REPORT / 'excerpt_manifest.json', {'command': command,
                   'original_source_sha256': file_hash(source), 'clip_sha256': file_hash(clip),
                   'requested_start': 0, 'requested_end': 120,
                   'method': 'local_stream_copy_no_resolution_fps_or_codec_change',
                   'visual_inspection': 'Existing thumbnails at 10.043s and 85.152s show two visible faces and a camera change; speaker identities are not human annotated.'})
    return clip

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--scenes-only', action='store_true')
    parser.add_argument('--backend', choices=['opencv','pyav'], default='opencv')
    parser.add_argument('--threading', choices=['SLICE','AUTO','FRAME'], default='SLICE')
    args = parser.parse_args()
    output = REPORT / args.label
    output.mkdir(exist_ok=False)
    cache = output / 'cache'; cache.mkdir()
    clip = prepare()
    import cv2
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS)
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    metadata = {'duration': count/fps, 'fps': fps,
                'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    cap.release()
    cfg = load_config(ROOT / 'config/config.yaml')
    cfg['offline'] = True
    if args.backend != 'opencv':
        cfg['scenes'].update(backend=args.backend, pyav_threading_mode=args.threading)
    logger = logging.getLogger(args.label)
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
    ctx = SimpleNamespace(video=clip, output=output, cache=cache, config=cfg,
                          signature=file_hash(clip), force=True, logger=logger,
                          progress=lambda *a, **kw: None, check_cancel=lambda *a: None)
    from ldporto.scenes import SceneEngine
    scene_started = time.perf_counter()
    scenes = SceneEngine().run(ctx, metadata)
    scene_seconds = time.perf_counter()-scene_started
    write_json(output / 'scenes.json', scenes)
    result = {'config': cfg, 'configuration_sha256': digest(cfg), 'metadata': metadata,
              'clip_sha256': ctx.signature, 'scene_seconds': scene_seconds,
              'scene_data': scenes['data'], 'source_modules': {p.name:file_hash(p)
                  for p in (ROOT/'src/ldporto').glob('*.py')},
              'scope': 'Scenes and visual inference only; no ASR, Qwen, editor or pipeline export rerun.'}
    if not args.scenes_only:
        from ldporto.diarization import align_speakers
        base = ROOT/'analysis/video_1da839aad175/cache/0231c20cfd8147d9'
        transcript = align_speakers(read_json(base/'04_transcription.json')['data'],
                                   read_json(base/'05_diarization.json')['data'])
        transcript = {'segments': [r for r in transcript['segments'] if r['start'] < metadata['duration']]}
        from ldporto.vision import VisionEngine
        from ldporto.ollama_local import nvidia_smi
        result['gpu_before'] = nvidia_smi()
        vision_started = time.perf_counter()
        visual = VisionEngine().run(ctx, metadata, scenes['data']['scenes'], transcript)
        result['vision_seconds'] = time.perf_counter()-vision_started
        result['vision_performance'] = visual['data'].get('performance')
        result['vision_quality'] = visual['data'].get('quality')
        result['vision_counts'] = {k:len(visual['data'].get(k,[])) for k in ('people','observations','frames','thumbnails')}
        persist = time.perf_counter()
        write_json(output/'vision.json', visual)
        result['final_json_serialization_seconds'] = time.perf_counter()-persist
        result['vision_json_bytes'] = (output/'vision.json').stat().st_size
        result['logical_visual_sha256'] = digest(visual['data'])
        result['gpu_after'] = nvidia_smi()
    result['resources'] = resource_snapshot()
    write_json(output/'result.json', result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('config','scene_data','source_modules','vision_quality','vision_performance')},ensure_ascii=False))

if __name__ == '__main__':
    main()
