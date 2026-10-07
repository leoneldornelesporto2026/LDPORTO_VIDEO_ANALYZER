import math
import statistics
from collections import Counter
from .core import ok, Unavailable


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
            from scenedetect import detect, ContentDetector
        except ImportError:
            raise Unavailable("Instale scenedetect para detectar mudanças de câmera.")
        cfg = ctx.config["scenes"]
        pairs = detect(str(ctx.video), ContentDetector(threshold=cfg["threshold"],
                        min_scene_len=max(1, math.ceil(cfg["min_seconds"] * metadata["fps"]))),
                       show_progress=True)
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
        return ok({"scenes": scenes, "scene_metrics": metrics},
                  notes=["Cenas são mudanças visuais, não mudanças de assunto."])
