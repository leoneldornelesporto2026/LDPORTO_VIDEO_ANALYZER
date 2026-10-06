from collections import defaultdict
import gc
from .core import ok, Unavailable


class OcrEngine:
    def run(self, ctx, vision):
        cfg = ctx.config["ocr"]
        if not cfg["enabled"]:
            return ok({"texts": []}, "skipped")
        try:
            import cv2
            import pytesseract
        except ImportError:
            raise Unavailable("Instale requirements-ocr.txt e Tesseract com por/eng.")
        if cfg["tesseract_cmd"]:
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_cmd"]
        texts = []
        thumbnails = vision.get("thumbnails", [])
        if len(thumbnails) > cfg["max_frames"]:
            step = len(thumbnails)/cfg["max_frames"]
            thumbnails = [thumbnails[int(i*step)] for i in range(cfg["max_frames"])]
        for thumb in thumbnails:
            image = cv2.imread(str(ctx.output/thumb["path"]))
            if image is None:
                continue
            h, w = image.shape[:2]
            data = pytesseract.image_to_data(image, lang=cfg["languages"],
                                            output_type=pytesseract.Output.DICT)
            groups = defaultdict(list)
            for i, text in enumerate(data["text"]):
                confidence = float(data["conf"][i])
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
        return ok({"texts": texts}, notes=["OCR amostrado em keyframes. Tempo de permanência "
                                         "e vínculo do texto com pessoa não foram inventados."])
