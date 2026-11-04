"""Explicit, bounded local YOLO inference diagnostic; never a pipeline or download."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/config.yaml')
    parser.add_argument('--model')
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    args = parser.parse_args(argv)
    video = args.video.resolve(strict=True)
    if not video.is_file():
        parser.error('video must be an existing local file')
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['YOLO_CONFIG_DIR'] = str((args.output / 'ultralytics_local').resolve())
    os.environ['YOLO_AUTOINSTALL'] = 'false'
    sys.path.insert(0, str(ROOT / 'src'))
    from ldporto.config import load_config
    from ldporto.vision import load_local_yolo
    import cv2
    import torch
    import psutil
    cfg = dict(load_config(args.config)['vision'])
    cfg.update(body_detection=True, body_backend='yolo', yolo_device=args.device)
    if args.model:
        cfg['yolo_model'] = args.model
    started = perf_counter()
    model, backend = load_local_yolo(cfg)
    record = {'schema_version': '1.0', 'scope': 'four_frame_local_inference',
              'video_path': str(video), 'video_sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
              'requested_device': args.device, 'backend': backend,
              'load_seconds': perf_counter() - started, 'frames': [],
              'human_detection_accuracy': None, 'speaker_identity_validated': False,
              'two_seated_people_recall': 'PENDING_GROUND_TRUTH', 'model_downloads': 0,
              'dependency_installs': 0, 'publication_ready': False}
    record['code_sha256'] = {name: hashlib.sha256((ROOT/'src/ldporto'/name).read_bytes()).hexdigest()
                            for name in ('vision.py', 'body_model_paths.py', 'config.py')}
    exit_code = 2
    cap = None
    try:
        if model is None:
            raise RuntimeError(backend.get('fallback_reason') or 'model_not_loaded')
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            raise RuntimeError('local_video_open_failed')
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1e-9)
        record['source'] = {'duration': duration, 'width': cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                            'height': cap.get(cv2.CAP_PROP_FRAME_HEIGHT), 'fps': cap.get(cv2.CAP_PROP_FPS)}
        if backend['device'].startswith('cuda'):
            torch.cuda.reset_peak_memory_stats()
        for index, requested in enumerate((2., 6., 12., 18.)):
            position = min(requested, max(0., duration - .1))
            cap.set(cv2.CAP_PROP_POS_MSEC, position * 1000)
            read, frame = cap.read()
            if not read:
                raise RuntimeError('frame_decode_failed')
            t0 = perf_counter()
            result = model.predict(frame, classes=[0], conf=cfg['yolo_confidence'],
                                   device=backend['device'], verbose=False)[0]
            if backend['device'].startswith('cuda'):
                torch.cuda.synchronize()
            elapsed = perf_counter() - t0
            actual_device = str(next(model.model.parameters()).device)
            detections = []
            height, width = frame.shape[:2]
            annotated = frame.copy()
            for box in result.boxes:
                coordinates = box.xyxy[0].detach().cpu().tolist()
                score = float(box.conf[0].detach().cpu())
                x1, y1, x2, y2 = coordinates
                detections.append({'class_id': int(box.cls[0]), 'class_name': 'person',
                    'confidence_raw_not_calibrated': score,
                    'xyxy_pixels': coordinates, 'bbox_normalized':
                    {'x': x1 / width, 'y': y1 / height, 'width': (x2-x1)/width, 'height': (y2-y1)/height}})
                cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0,255,0), 1)
            image_path = args.output / f'frame_{index:02}.png'
            if not cv2.imwrite(str(image_path), annotated):
                raise RuntimeError('evidence_frame_write_failed')
            record['frames'].append({'requested_time': position, 'decoded_time': cap.get(cv2.CAP_PROP_POS_MSEC)/1000,
                'inference_seconds': elapsed, 'device_actually_used': actual_device,
                'frame_pixels_sha256': hashlib.sha256(frame.tobytes()).hexdigest(),
                'laplacian_variance': float(cv2.Laplacian(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()),
                'detections': detections, 'evidence_path': image_path.name,
                'evidence_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'process_rss_bytes': psutil.Process().memory_info().rss})
        backend.update(inference_executed=True, inference_successful=True,
                       device_actually_used=actual_device, local_smoke_validated=True,
                       readiness='INFERENCE_EXECUTED')
        record['inference_call_count'] = len(record['frames'])
        record['measured_peak_torch_vram_bytes'] = (torch.cuda.max_memory_allocated()
            if backend['device'].startswith('cuda') else None)
        exit_code = 0
    except Exception as exc:
        record.update(error_type=type(exc).__name__, error=str(exc))
        backend.update(readiness='NOT_READY', inference_successful=False)
    finally:
        if cap is not None:
            cap.release()
        record['wall_seconds'] = perf_counter() - started
        record['exit_code'] = exit_code
        record['command'] = sys.argv
        with (args.output / 'result.json').open('x', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'output': str(args.output / 'result.json'), 'exit_code': exit_code,
                      'readiness': backend['readiness'], 'frames': len(record['frames'])}))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
