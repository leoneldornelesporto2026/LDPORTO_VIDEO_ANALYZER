"""Bounded isolated HOG/face CPU A/B; default is diagnostics without inference.

Windows homologation needs --run-detectors and an explicitly selected source.
No Analyzer outputs/cache/configuration are changed. No performance promotion.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.config import load_config
from ldporto.core import digest, file_hash, sanitize_json_numbers, write_json
from ldporto.runtime_metrics import resource_snapshot
from ldporto.performance_acceptance import resource_diagnostic
from ldporto.ollama_local import nvidia_smi


def collect(video, sample_count, max_width, max_frame_bytes=64 * 1024 ** 2):
    """Bound retained decoded frames; one source decode/rescale is extra RAM."""
    if not 1 <= sample_count <= 256 or not 64 <= max_width <= 1920:
        raise ValueError('Use 1..256 frames e largura 64..1920')
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError(f'Video inacessivel: {video}')
    frames, retained = [], 0
    try:
        total = max(0., cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        for index in range(sample_count):
            frame_no = min(int(total) - 1, round((index + .5) * total / sample_count)) if total > 0 else index * 30
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ok, frame = cap.read()
            if not ok:
                raise ValueError(f'Frame solicitado indisponivel: {frame_no}')
            height, width = frame.shape[:2]
            scale = min(1., max_width / width)
            if scale < 1:
                frame = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))))
            retained += frame.nbytes
            if retained > max_frame_bytes:
                raise ValueError('Frame RAM budget exceeded; reduce --frames/--max-width')
            frames.append((frame_no / fps if fps > 0 else float(index), frame))
    finally:
        cap.release()
    return frames


def frame_manifest(frames):
    return [{'time': stamp, 'shape': list(frame.shape), 'dtype': str(frame.dtype),
             'sha256': hashlib.sha256(frame.tobytes()).hexdigest()} for stamp, frame in frames]


def bench(frames, cfg, enable):
    from ldporto.vision import PersonDetectionEngine
    # HOG only, never YOLO or a GPU backend.
    conf = dict(cfg, body_detection=True, body_backend='hog', parallel_hog_with_face=enable)
    notes = []
    detector = PersonDetectionEngine(conf, notes, offline=True)
    result, logs, elapsed = [], [], 0.
    try:
        before = resource_snapshot()
        measurement_started = perf_counter()
        gpu_before = nvidia_smi()
        for i, (stamp, frame) in enumerate(frames):
            detector.set_frame_context(stamp, f'SAMPLE_{i:04}', 3.0)
            started = perf_counter()
            rows = detector.detect(frame)
            cost = perf_counter() - started
            elapsed += cost
            # Include confidences/quality/reasons; embedding equality is outside scope.
            result.append(sanitize_json_numbers([{k: v for k, v in row.items() if k != 'embedding'} for row in rows]))
            logs.append({'sample_index': i, 'time': stamp, 'detector_seconds': cost,
                         'resources': resource_snapshot()})
    finally:
        detector.close()
    after = resource_snapshot()
    measurement_seconds = perf_counter() - measurement_started
    return {'elapsed_seconds': elapsed, 'frames': len(result),
            'face_detection_calls': detector.calls['face_detection_calls'],
            'body_detection_calls': detector.calls['body_detection_calls'],
            'calls': dict(detector.calls), 'boxes': result,
            'guard': detector.overlap_budget, 'notes': notes,
            'resources_before': before, 'resources_after': after,
            'process_cpu_seconds_delta': after['process_cpu_seconds'] - before['process_cpu_seconds'],
            'resource_window_seconds': measurement_seconds,
            'cpu_percent_of_one_logical_cpu': (after['process_cpu_seconds'] - before['process_cpu_seconds']) / measurement_seconds * 100 if measurement_seconds > 0 else None,
            'resource_log': logs, 'gpu_before': gpu_before, 'gpu_after': nvidia_smi(),
            'resource_scope': 'CPU process includes HOG thread and telemetry in resource window; RAM sampled per frame; peak is process lifetime; VRAM system snapshots, no peak or process attribution',
            'timing_scope': 'detector calls only; initialization, decode, hashes and telemetry excluded'}


def compare(video, cfg, sample_count, repeats=3, max_frame_bytes=64 * 1024 ** 2):
    if not 1 <= repeats <= 10:
        raise ValueError('Use 1..10 repeticoes')
    frames = collect(video, sample_count, int(cfg['max_width']), max_frame_bytes)
    if not frames:
        raise ValueError('Nenhum frame amostrado do video')
    manifest = frame_manifest(frames)
    pairs = []
    for repeat in range(repeats):
        order = ['serial', 'parallel'] if repeat % 2 == 0 else ['parallel', 'serial']
        modes = {}
        for mode in order:
            modes[mode] = bench(frames, cfg, mode == 'parallel')
            if frame_manifest(frames) != manifest:
                raise ValueError('Detector mutated A/B input frames')
        a, b = modes['serial'], modes['parallel']
        same = a['boxes'] == b['boxes']
        calls_same = a['calls'] == b['calls']
        available = b['guard']['enabled']
        failures = any(count for mode in modes.values() for name, count in mode['calls'].items()
                       if 'failed' in name or 'unavailable' in name)
        speedup = a['elapsed_seconds'] / b['elapsed_seconds'] if same and calls_same and available and not failures and b['elapsed_seconds'] > 0 else None
        pairs.append({'repeat': repeat, 'order': order, 'modes': modes,
                      'detection_boxes_identical': same, 'detector_calls_identical': calls_same,
                      'speedup_x': speedup})
    valid = all(pair['speedup_x'] is not None for pair in pairs)
    return {'schema_version': '41.1', 'source': str(video), 'source_sha256': file_hash(video),
            'platform': platform.platform(), 'python': platform.python_version(),
            'config': dict(deepcopy(cfg), body_detection=True, body_backend='hog'),
            'benchmark_code_sha256': file_hash(Path(__file__)),
            'sample_count': len(frames), 'frame_manifest': manifest, 'frames_sha256': digest(manifest),
            'retained_frame_bytes': sum(frame.nbytes for _, frame in frames), 'max_frame_bytes': max_frame_bytes,
            'cpu_parallel_available': all(pair['modes']['parallel']['guard']['enabled'] for pair in pairs),
            'detection_boxes_identical': all(pair['detection_boxes_identical'] for pair in pairs),
            'detector_calls_identical': all(pair['detector_calls_identical'] for pair in pairs),
            'serial_seconds': median([pair['modes']['serial']['elapsed_seconds'] for pair in pairs]),
            'parallel_seconds': median([pair['modes']['parallel']['elapsed_seconds'] for pair in pairs]),
            'speedup_x': median([pair['speedup_x'] for pair in pairs]) if valid else None,
            'parallel_guard': pairs[-1]['modes']['parallel']['guard'], 'pairs': pairs,
            'safe_to_enable_automatically': False, 'enable_recommendation': 'leave_disabled',
            'caution': 'Frame-only CPU experiment. Embeddings excluded from equivalence. No warm-up; alternating order includes cold-start effects. No full-stage quality or hardware performance promise.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--video', type=Path)
    ap.add_argument('--run-detectors', action='store_true')
    ap.add_argument('--frames', type=int, default=12)
    ap.add_argument('--repeats', type=int, default=3)
    ap.add_argument('--max-width', type=int, default=960)
    ap.add_argument('--max-frame-mib', type=int, default=64)
    ap.add_argument('--output', type=Path, default=Path('r3b_vision_ab.json'))
    args = ap.parse_args()
    if args.output.exists():
        ap.error('Output already exists; select a new path to preserve previous evidence')
    if not 1 <= args.max_frame_mib <= 256:
        ap.error('--max-frame-mib must be 1..256')
    if args.run_detectors:
        if not args.video:
            ap.error('--run-detectors requires --video')
        cfg = load_config(ROOT / 'config/config.yaml')['vision']
        cfg['max_width'] = args.max_width
        report = compare(args.video, cfg, args.frames, args.repeats, args.max_frame_mib * 1024 ** 2)
    else:
        report = {'schema_version': '41.1', 'execution_scope': 'diagnostics_only_no_inference',
                  'resources': resource_diagnostic(), 'speedup_x': None,
                  'optimization_enabled': False, 'safe_to_enable_automatically': False,
                  'enable_recommendation': 'leave_disabled',
                  'blocking_reasons': ['paired_windows_detector_benchmark_pending'],
                  'plan': {'modes': ['serial', 'one_cpu_hog_worker'], 'repeats': args.repeats,
                           'frames': args.frames, 'max_frame_mib': args.max_frame_mib,
                           'gpu_tasks': 0, 'identical_frames_required': True}}
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
