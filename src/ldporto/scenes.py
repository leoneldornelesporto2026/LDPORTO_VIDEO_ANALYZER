import math
import statistics
from collections import Counter
from time import perf_counter
from .core import ok, Unavailable


class _MeasuredSceneVideo:
    """Read telemetry in SceneDetect's existing decoder worker, without extra frames."""
    def __init__(self, video):
        self.video = video
        self.read_seconds = 0.
        self.read_calls = self.frames_returned = self.eof_calls = 0
        self.first_pts = self.last_pts = None
        self.nonmonotonic_pts = 0

    def __getattr__(self, name):
        return getattr(self.video, name)

    def read(self, *args, **kwargs):
        started = perf_counter()
        self.read_calls += 1
        try:
            frame = self.video.read(*args, **kwargs)
        finally:
            self.read_seconds += perf_counter() - started
        if frame is False:
            self.eof_calls += 1
        else:
            self.frames_returned += 1
            position = self.video.position
            stamp = float(position.seconds if hasattr(position, 'seconds') else position.get_seconds())
            if self.last_pts is not None and stamp <= self.last_pts:
                self.nonmonotonic_pts += 1
            if self.first_pts is None:
                self.first_pts = stamp
            self.last_pts = stamp
        return frame


def _close_scene_video(source):
    """Close after SceneManager has joined its decoder worker, including errors."""
    closed, errors = [], []
    for label, resource, method in (
        ('decoder', getattr(source, '_decoder', None), 'close'),
        ('container', getattr(source, '_container', None), 'close'),
        ('owned_io', getattr(source, '_io', None) if getattr(source, '_owns_io', False) else None, 'close'),
        ('capture', getattr(source, 'capture', None), 'release'),
    ):
        action = getattr(resource, method, None)
        if callable(action):
            try:
                action()
                closed.append(label)
            except Exception as exc:
                errors.append({'resource': label, 'exception_type': type(exc).__name__})
    return {'closed_resources': closed, 'errors': errors}


def _detect_measured_scenes(path, cfg, metadata):
    """Keep SceneManager's detector, downscale and bounded decoder prefetch intact."""
    from scenedetect import open_video, ContentDetector, SceneManager
    requested = cfg.get('backend', 'opencv')
    threading = cfg.get('pyav_threading_mode', 'SLICE')
    if requested not in ('opencv', 'pyav'):
        raise ValueError('scenes.backend must be opencv or pyav')
    if threading not in ('SLICE', 'AUTO', 'FRAME', 'NONE'):
        raise ValueError('Invalid scenes.pyav_threading_mode')

    attempts = []
    def consume(backend, source, open_seconds):
        detector_seconds = 0.
        detector_calls = 0
        class MeasuredContentDetector(ContentDetector):
            def process_frame(self, *args, **kwargs):
                nonlocal detector_seconds, detector_calls
                started = perf_counter()
                detector_calls += 1
                try:
                    return super().process_frame(*args, **kwargs)
                finally:
                    detector_seconds += perf_counter() - started
        video = _MeasuredSceneVideo(source)
        manager = SceneManager()
        manager.add_detector(MeasuredContentDetector(threshold=cfg['threshold'],
            min_scene_len=max(1, math.ceil(cfg['min_seconds'] * metadata['fps']))))
        started = perf_counter()
        manager.detect_scenes(video=video, show_progress=True, frame_skip=0)
        detect_seconds = perf_counter() - started
        pairs = manager.get_scene_list(start_in_scene=False)
        effective = getattr(source, 'BACKEND_NAME', type(source).__name__)
        stream = getattr(source, '_video_stream', None) if effective == 'pyav' else None
        codec = getattr(stream, 'codec_context', None)
        actual_threading = getattr(stream, 'thread_type', None)
        actual_threading = getattr(actual_threading, 'name', str(actual_threading)) if actual_threading is not None else None
        fps = float(source.frame_rate)
        tail_gap = (max(0., float(metadata['duration']) - video.last_pts - 1/fps)
                    if video.last_pts is not None and fps > 0 else None)
        performance = {
            'backend_requested': requested, 'backend_effective': effective,
            'fallback_reason': 'requested_backend_unavailable_or_open_failed' if effective != backend else None,
            'threading_requested': threading if requested == 'pyav' else None,
            'threading_effective': actual_threading, 'codec_name': getattr(codec, 'name', None),
            'codec_thread_count': getattr(codec, 'thread_count', None),
            'source_frame_size': list(source.frame_size), 'source_fps': fps,
            'auto_downscale': manager.auto_downscale, 'frame_skip': 0,
            'open_seconds': open_seconds, 'detect_wall_seconds': detect_seconds,
            'decode_seconds': video.read_seconds, 'detector_seconds': detector_seconds,
            'decode_ms': video.read_seconds * 1000, 'detector_ms': detector_seconds * 1000,
            'read_calls': video.read_calls, 'frames_returned': video.frames_returned,
            'detector_calls': detector_calls, 'eof_read_calls': video.eof_calls,
            'decode_mean_ms_per_read': video.read_seconds * 1000 / video.read_calls if video.read_calls else None,
            'detector_mean_ms_per_call': detector_seconds * 1000 / detector_calls if detector_calls else None,
            'first_pts_seconds': video.first_pts, 'last_pts_seconds': video.last_pts,
            'nonmonotonic_pts_count': video.nonmonotonic_pts, 'tail_gap_seconds': tail_gap,
            'eof_status': 'decoder_returned_false' if video.eof_calls else 'eof_not_observed',
            'eof_does_not_prove_all_source_frames': True,
            'decode_failure_count': getattr(source, '_decode_failures', None),
            'pts_method': 'backend_PTS; PyAV_normalizes_stream_start; OpenCV_POS_MSEC_with_frame_fallback',
            'thread_accounting': 'decoder_read_runs_in_existing_prefetch_worker; detector_runs_in_consumer; '
                'their_seconds_overlap_and_are_not_additive_to_wall; read_includes_BGR_conversion; '
                'library_downscale_and_queue_wait_are_not_separately_instrumented',
            'gpu_inference': False, 'boundary_quality_validated': False,
        }
        return pairs, performance

    def execute(backend):
        started = perf_counter()
        source = None
        attempt = {'backend_requested': backend, 'status': 'running'}
        attempts.append(attempt)
        try:
            options = {'threading_mode': threading, 'suppress_output': False} if backend == 'pyav' else {}
            source = open_video(path, backend=backend, **options)
            open_seconds = perf_counter() - started
            pairs, performance = consume(backend, source, open_seconds)
            attempt.update(status='succeeded', backend_effective=performance['backend_effective'],
                           open_seconds=open_seconds, decode_seconds=performance['decode_seconds'],
                           detector_seconds=performance['detector_seconds'], frames_returned=performance['frames_returned'])
            return pairs, performance
        except Exception as exc:
            attempt.update(status='failed', exception_type=type(exc).__name__)
            raise
        finally:
            if source is not None:
                attempt['resource_cleanup'] = _close_scene_video(source)
            attempt['elapsed_seconds'] = perf_counter() - started

    started = perf_counter()
    try:
        pairs, performance = execute(requested)
    except Exception as exc:
        if requested != 'pyav':
            raise
        pairs, performance = execute('opencv')
        performance.update(fallback_reason='pyav_execution_failed', fallback_exception_type=type(exc).__name__)
    performance['elapsed_seconds'] = perf_counter() - started
    performance['attempts'] = attempts
    performance['timing_scope'] = 'decode_and_detector_metrics_describe_successful_attempt; '
    performance['timing_scope'] += 'elapsed_seconds_and_attempts_include_failed_fallback_and_resource_cleanup'
    return pairs, performance


def summarize_scenes(scenes, duration, window_seconds=600.0):
    """Return explicit scene/cut counts and temporal density without conflating them."""
    rows = list(scenes or [])
    durations = [max(0.0, float(row.get("end", 0)) - float(row.get("start", 0))) for row in rows]
    bins = Counter(int(max(0.0, float(row.get("start", 0))) // window_seconds) for row in rows)
    last_index = int(max(0.0, float(duration) - 1e-9) // window_seconds) if duration else 0
    counts = [bins.get(index, 0) for index in range(last_index + 1)]
    positive = [value for value in counts if value > 0]
    median_density = statistics.median(positive) if positive else 0
    peak_index = max(range(len(counts)), key=lambda index: counts[index]) if counts else 0
    peak_count = counts[peak_index] if counts else 0
    last_count = counts[-1] if counts else 0
    dense_tail = bool(last_count >= 30 and median_density and last_count >= 2 * median_density)
    return {
        "scene_count": len(rows),
        "visual_boundary_count": max(0, len(rows) - 1),
        "median_scene_duration_seconds": statistics.median(durations) if durations else None,
        "short_scene_fraction_le_1s": (sum(value <= 1.0 for value in durations) / len(durations)) if durations else None,
        "short_scene_fraction_le_2s": (sum(value <= 2.0 for value in durations) / len(durations)) if durations else None,
        "density_window_seconds": window_seconds,
        "scene_count_by_window": [
            {"start": index * window_seconds, "end": min(float(duration), (index + 1) * window_seconds), "scene_count": count}
            for index, count in enumerate(counts)
        ],
        "median_scene_count_per_window": median_density,
        "peak_scene_window": {
            "start": peak_index * window_seconds,
            "end": min(float(duration), (peak_index + 1) * window_seconds),
            "scene_count": peak_count,
        } if counts else None,
        "last_window_scene_count": last_count,
        "dense_tail_region": dense_tail,
    }


class SceneEngine:
    def run(self, ctx, metadata):
        if not ctx.config["scenes"]["enabled"]:
            scenes = [{"scene_id": "SCENE_00000", "start": 0,
                       "end": metadata["duration"], "duration": metadata["duration"],
                       "detected": False, "scene_type": "unknown"}]
            return ok({"scenes": scenes, "scene_metrics": summarize_scenes(scenes, metadata["duration"])}, "skipped")
        try:
            from scenedetect import open_video, ContentDetector, SceneManager
        except ImportError:
            raise Unavailable("Instale scenedetect para detectar mudanças de câmera.")
        cfg = ctx.config["scenes"]
        pairs, performance = _detect_measured_scenes(str(ctx.video), cfg, metadata)
        def seconds(timecode):
            return timecode.seconds if hasattr(timecode, "seconds") else timecode.get_seconds()
        bounds = [(seconds(a), seconds(b)) for a, b in pairs]
        if not bounds:
            bounds = [(0, metadata["duration"])]
        scenes = [{"scene_id": f"SCENE_{i:05}", "start": a, "end": min(b, metadata["duration"]),
                   "duration": min(b, metadata["duration"])-a, "keyframe": None,
                   "visible_people": [], "predominant_person": None,
                   "scene_type": "unknown", "detected": True, "method": "content_detector"}
                  for i, (a, b) in enumerate(bounds)]
        scenes[0]["start"] = 0
        scenes[-1]["end"] = metadata["duration"]
        for scene in scenes:
            scene["duration"] = scene["end"]-scene["start"]
        metrics = summarize_scenes(scenes, metadata["duration"])
        ctx.logger.info("Cenas visuais: %s cenas / %s cortes; mediana %.2fs",
                        metrics["scene_count"], metrics["visual_boundary_count"],
                        metrics["median_scene_duration_seconds"] or 0.0)
        if metrics["dense_tail_region"]:
            peak = metrics["peak_scene_window"] or {}
            ctx.logger.warning(
                "Densidade visual elevada no trecho final: %s cenas nos últimos %.0fs; pico=%s cenas em %.0f–%.0fs. "
                "Tracking pode gerar mais tracklets nessa região; isso será tratado como contexto de fragmentação, não como identidade nova por si só.",
                metrics["last_window_scene_count"], metrics["density_window_seconds"], peak.get("scene_count", 0),
                peak.get("start", 0), peak.get("end", 0))
        ctx.progress("06_scenes", current=1, total=1, status="running",
                     substage=f'{metrics["scene_count"]} cenas / {metrics["visual_boundary_count"]} cortes')
        return ok({"scenes": scenes, "scene_metrics": metrics, 'performance': performance},
                  notes=["Cenas são mudanças visuais, não mudanças de assunto."])
