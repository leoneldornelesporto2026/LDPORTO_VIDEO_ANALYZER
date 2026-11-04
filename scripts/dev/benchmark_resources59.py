"""Bounded CPU HOG smoke, synthetic by default. No downloads or pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter, process_time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.core import file_hash
from ldporto.performance import FrameTelemetry


def frames_for_clip(path, expected_hash, count):
    import cv2
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 8:
        raise ValueError('Use 1..8 frames')
    if not expected_hash or file_hash(path) != expected_hash:
        raise ValueError('Local clip SHA256 mismatch before decode')
    cap = cv2.VideoCapture(str(path))
    try:
        fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if (not cap.isOpened() or not math.isfinite(fps) or not math.isfinite(total)
                or fps <= 0 or not 10 <= total / fps <= 30):
            raise ValueError('Provide an explicit local clip of 10..30 seconds')
        frames = []
        for i in range(count):
            cap.set(cv2.CAP_PROP_POS_FRAMES, round((i + .5) * total / count))
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Clip sample decode failed')
            # Do not change detector knobs. Reject oversized input instead.
            if (frame.nbytes > 8 * 1024**2 or frame.ndim != 3 or frame.shape[2] != 3
                    or frame.shape[0] < 128 or frame.shape[1] < 64):
                raise ValueError('Frame exceeds smoke memory budget')
            frames.append(frame)
    finally:
        cap.release()
    if file_hash(path) != expected_hash:
        raise ValueError('Local clip changed during decode')
    return frames


def run(frames, scope):
    import cv2
    previous = cv2.getNumThreads()
    cpu_started = process_time()
    started = perf_counter()
    telemetry = FrameTelemetry('benchmark_hog_cpu')
    detections, manifest = [], []
    try:
        cv2.setNumThreads(1)
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        for frame in frames:
            manifest.append({'shape': list(frame.shape),
                             'sha256': hashlib.sha256(frame.tobytes()).hexdigest()})
            tick = telemetry.attempt()
            boxes, _ = hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
            detections.append(len(boxes))
            telemetry.success(tick)
    finally:
        cv2.setNumThreads(previous)
    metrics = telemetry.report()
    metrics['latency_scope'] = 'last_512_successful_cpu_hog_calls;_fps_includes_initialization'
    return {'schema_version': '59.1', 'scope': scope, 'backend': 'hog', 'device': 'cpu',
            'policy': 'serial_cpu_one_frame_in_flight', 'opencv_threads': 1,
            'frame_manifest': manifest, 'body_detection_counts': detections,
            'telemetry': metrics, 'wall_seconds': perf_counter() - started,
            'process_cpu_seconds': process_time() - cpu_started,
            'quality': None, 'speedup_x': None, 'identity_evidence': None,
            'production_metrics': None, 'publish_ready': False,
            'knobs_changed': False, 'weights_loaded': False}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clip', type=Path)
    ap.add_argument('--sha256')
    ap.add_argument('--consent-local', action='store_true')
    ap.add_argument('--frames', type=int, default=3)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    if not 1 <= args.frames <= 8 or args.output.exists():
        ap.error('Use 1..8 frames and a new output path')
    if args.clip:
        if not args.consent_local or not args.sha256:
            ap.error('Local clip requires --consent-local and --sha256')
        frames = frames_for_clip(args.clip, args.sha256, args.frames)
        scope = 'explicit_short_local_clip_cpu_hog_only'
    else:
        import numpy as np
        rng = np.random.default_rng(59)
        frames = [rng.integers(0, 256, (128, 64, 3), dtype=np.uint8) for _ in range(args.frames)]
        scope = 'synthetic_real_cpu_hog_smoke_not_production'
    report = run(frames, scope)
    report['source_sha256'] = args.sha256 if args.clip else None
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'scope': scope, 'frames': len(frames), 'speedup_x': None}))


if __name__ == '__main__':
    main()
