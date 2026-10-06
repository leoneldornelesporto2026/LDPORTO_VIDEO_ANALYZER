import math
from .core import ok, Unavailable


class SceneEngine:
    def run(self, ctx, metadata):
        if not ctx.config["scenes"]["enabled"]:
            return ok({"scenes": [{"scene_id": "SCENE_00000", "start": 0,
                                   "end": metadata["duration"], "duration": metadata["duration"],
                                   "detected": False, "scene_type": "unknown"}]}, "skipped")
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
        for s in scenes:
            s["duration"] = s["end"]-s["start"]
        return ok({"scenes": scenes}, notes=["Cenas são mudanças visuais, não mudanças de assunto."])
