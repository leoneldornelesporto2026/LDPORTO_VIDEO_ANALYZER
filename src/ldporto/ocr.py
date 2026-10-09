from collections import defaultdict
import math
from .core import ok


def validate_observations(texts, *, max_gap_seconds=10.):
    """Validate sampled repeats, never infer continuous display or brand identity."""
    def geometry(row):
        try:
            x, y, w, h = (float(row['bbox'][k]) for k in ('x', 'y', 'width', 'height'))
            return (all(math.isfinite(v) for v in (x, y, w, h)) and
                    0 <= x < x+w <= 1 and 0 <= y < y+h <= 1 and
                    .005 <= h <= .25 and .01 <= w <= .95)
        except (KeyError, TypeError, ValueError):
            return False

    def instant(row):
        try:
            value = float(row.get('observed_at', row.get('start')))
            return value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            return None

    for row in texts:
        valid = geometry(row)
        when = instant(row)
        repeats = set()
        if valid and when is not None:
            box = row['bbox']
            for other in texts:
                t = instant(other)
                if (not geometry(other) or t is None or abs(t-when) > max_gap_seconds or
                        other.get('moment_id') != row.get('moment_id') or
                        str(other.get('text', '')).casefold().split() != str(row.get('text', '')).casefold().split()):
                    continue
                if all(abs(float(box[k])-float(other['bbox'][k])) <= .025
                       for k in ('x', 'y', 'width', 'height')):
                    repeats.add(t)
        persistent = len(repeats) >= 3
        try:
            confidence = float(row.get('confidence'))
            confident = math.isfinite(confidence) and .6 <= confidence <= 1
        except (TypeError, ValueError):
            confident = False
        row.update(spatial_validated=valid, temporal_validated=persistent,
                   persistence_sample_count=len(repeats),
                   persistence_observed_seconds=max(repeats)-min(repeats) if repeats else None,
                   uncertain=not (valid and persistent and confident), needs_review=True,
                   commercial_confirmed=None, continuity_established=False)
    return texts


class OcrEngine:
    def run(self, ctx, vision):
        cfg = ctx.config["ocr"]
        if not cfg["enabled"]:
            return ok({"texts": [], "measurement_state": "not_measured", "commercial_present": None}, "skipped")
        try:
            import cv2
            import pytesseract
        except ImportError:
            return ok({"texts": [], "measurement_state": "not_measured", "commercial_present": None,
                       "reason": "optional_ocr_dependency_missing"}, "unavailable")
        if cfg["tesseract_cmd"]:
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]
        try:
            pytesseract.get_tesseract_version()
        except (OSError, RuntimeError) as exc:
            return ok({"texts": [], "measurement_state": "not_measured", "commercial_present": None,
                       "reason": "optional_tesseract_missing", "detail": type(exc).__name__}, "unavailable")
        texts = []
        measured, failed = 0, 0
        thumbnails = vision.get("thumbnails", [])
        if len(thumbnails) > cfg["max_frames"]:
            step = len(thumbnails)/cfg["max_frames"]
            thumbnails = [thumbnails[int(i*step)] for i in range(cfg["max_frames"])]
        for thumb in thumbnails:
            image = cv2.imread(str(ctx.output/thumb["path"]))
            if image is None:
                failed += 1
                continue
            h, w = image.shape[:2]
            try:
                data = pytesseract.image_to_data(image, lang=cfg["languages"],
                                                output_type=pytesseract.Output.DICT, timeout=5)
            except (RuntimeError, pytesseract.TesseractError):
                failed += 1
                continue
            measured += 1
            groups = defaultdict(list)
            for i, text in enumerate(data["text"]):
                try:
                    confidence = float(data["conf"][i])
                except (TypeError, ValueError):
                    continue
                if text.strip() and confidence >= 40:
                    groups[(data["block_num"][i], data["par_num"][i], data["line_num"][i])].append(i)
            for ids in groups.values():
                x = min(data["left"][i] for i in ids)
                y = min(data["top"][i] for i in ids)
                x2 = max(data["left"][i]+data["width"][i] for i in ids)
                y2 = max(data["top"][i]+data["height"][i] for i in ids)
                texts.append({"start": thumb["time"], "end": thumb["time"],
                              "observed_at": thumb["time"], "duration_unknown": True,
                              "text": " ".join(data["text"][i] for i in ids),
                              "bbox": {"x": x/w, "y": y/h, "width": (x2-x)/w, "height": (y2-y)/h},
                              "confidence": sum(float(data["conf"][i]) for i in ids)/len(ids)/100,
                              "method": "tesseract_keyframe", "inference": True})
        return ok({"texts": validate_observations(texts), "measurement_state": "measured" if measured else "not_measured",
                   "commercial_present": None, "measured_frames": measured, "failed_frames_or_ocr": failed},
                  "partial" if failed or not measured else "ok", notes=["OCR amostrado em keyframes. Tempo de permanência "
                                         "e vínculo do texto com pessoa não foram inventados."])
