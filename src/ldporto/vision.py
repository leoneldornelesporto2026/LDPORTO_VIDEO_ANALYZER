from pathlib import Path
from collections import defaultdict
import bisect
import gc
import math
from time import perf_counter
import numpy as np
import soundfile as sf
from .core import ok, Unavailable, read_json, overlap, finite_or_none
from .config import asset_path
from .visual_sampling import SamplingScheduler
from .vision_checkpoint import VisionCheckpointStore


def bbox(values, width, height):
    x, y, w, h = map(float, values)
    x1, y1 = max(0, min(1, x/width)), max(0, min(1, y/height))
    x2, y2 = max(x1, min(1, (x+w)/width)), max(y1, min(1, (y+h)/height))
    return {"x": x1, "y": y1, "width": x2-x1, "height": y2-y1}


def center(box):
    return {"x": box["x"]+box["width"]/2, "y": box["y"]+box["height"]/2}


def iou(a, b):
    x = max(a["x"], b["x"])
    y = max(a["y"], b["y"])
    w = max(0, min(a["x"]+a["width"], b["x"]+b["width"])-x)
    h = max(0, min(a["y"]+a["height"], b["y"]+b["height"])-y)
    hit = w*h
    return hit/max(1e-9, a["width"]*a["height"]+b["width"]*b["height"]-hit)


def vertical_crop(box, width, height):
    crop_width = min(1.0, (height * 9 / 16) / width)
    c = center(box)
    x = max(0, min(1-crop_width, c["x"]-crop_width/2))
    crop = {"x": x, "y": 0.0, "width": crop_width, "height": 1.0}
    fits = box["x"] >= x and box["x"]+box["width"] <= x+crop_width
    return fits, crop


def get_scene(time, scenes):
    if not scenes:
        return None
    index = bisect.bisect_right([s["start"] for s in scenes], time)-1
    return scenes[max(0, index)]["scene_id"]


class Tracker:
    """Short-term tracker plus anonymous within-video face re-identification.

    ``person_id`` is the persistent anonymous identity. ``track_id`` identifies one
    continuous visual track. A person can therefore own multiple tracks after cuts
    while keeping the same PERSON id when face-embedding evidence is strong enough.
    """
    def __init__(self, cfg):
        self.cfg, self.tracks, self.gallery = cfg, {}, {}
        self.next_id = 1
        self.next_track_id = 1

    def _new_track_id(self):
        value = f"TRACK_{self.next_track_id:05}"
        self.next_track_id += 1
        return value

    def update(self, detections, time, scene_id):
        # Assign globally by highest IoU first. Do not identify a person by frame position.
        assigned, used = {}, set()
        pairs = []
        for i, d in enumerate(detections):
            for pid, track in self.tracks.items():
                if track["scene"] != scene_id or time-track["time"] > self.cfg["track_max_gap_seconds"]:
                    continue
                score = iou(d["bbox"], track["bbox"])
                face_similarity = None
                if d.get("embedding") is not None and track.get("embedding") is not None:
                    face_similarity = finite_or_none(float(np.dot(d["embedding"], track["embedding"])))
                    if face_similarity is not None and face_similarity < 0.3:
                        continue
                if score >= 0.25:
                    pairs.append((score, face_similarity, i, pid, track["track_id"]))
        # ``face_similarity`` is legitimately nullable. Tuple sorting used to compare
        # ``None`` with ``float`` whenever IoU tied, which crashed long analyses.
        # The deterministic key uses a private sentinel only for ordering; the exported
        # measurement remains ``None`` when it was not observed.
        ordered_pairs = sorted(
            pairs,
            key=lambda item: (item[0], -math.inf if item[1] is None else item[1], -item[2], item[3], item[4]),
            reverse=True,
        )
        for score, face_similarity, i, pid, track_id in ordered_pairs:
            if i not in assigned and pid not in used:
                assigned[i] = (pid, track_id, "temporal_iou", score, face_similarity)
                used.add(pid)
        for i, d in enumerate(detections):
            if i in assigned:
                continue
            emb = d.get("embedding")
            scores = []
            if emb is not None:
                for pid, stored in self.gallery.items():
                    if pid in used:
                        continue
                    similarity = finite_or_none(float(np.dot(emb, stored)))
                    if similarity is not None:
                        scores.append((similarity, pid))
                scores.sort(key=lambda item: (item[0], item[1]), reverse=True)
            if scores and scores[0][0] >= self.cfg["reid_threshold"] and (
                    len(scores) == 1 or scores[0][0]-scores[1][0] >= self.cfg["reid_margin"]):
                score, pid = scores[0]
                assigned[i] = (pid, self._new_track_id(), "anonymous_face_embedding", None, score)
            else:
                pid = f"PERSON_{self.next_id:03}"
                self.next_id += 1
                assigned[i] = (pid, self._new_track_id(), "new_identity", None, None)
            used.add(pid)
        result = []
        for i, d in enumerate(detections):
            pid, track_id, method, iou_score, face_similarity = assigned[i]
            # Generated by GitHub Copilot - Oct-05-2026
            previous_track = self.tracks.get(pid)
            new_template = d.get("embedding") is not None and (not previous_track or
                           previous_track.get("track_id") != track_id or previous_track.get("embedding") is None)
            self.tracks[pid] = {"bbox": d["bbox"], "time": time,
                                "scene": scene_id, "embedding": d.get("embedding"),
                                "track_id": track_id}
            if d.get("embedding") is not None:
                # Preserve a stable gallery template. Avoid uncontrolled drift from low-quality samples.
                self.gallery.setdefault(pid, d["embedding"])
            identity_confidence = None
            if method == "anonymous_face_embedding":
                identity_confidence = max(0.0, min(1.0, face_similarity)) if face_similarity is not None else None
            result.append({**{k: v for k, v in d.items() if k != "embedding"},
                           "person_id": pid, "track_id": track_id,
                           "tracking_method": method,
                           "tracking_confidence": iou_score,
                           "tracking_similarity": face_similarity,
                           "same_person_confidence": identity_confidence,
                           "identity_is_inference": method == "anonymous_face_embedding",
                           "face_embedding_available": d.get("embedding") is not None,
                           "face_embedding": np.asarray(d["embedding"]).tolist() if new_template else None,
                           "embedding_method": "opencv_sface" if d.get("embedding") is not None else None})
        self.tracks = {p: t for p, t in self.tracks.items()
                       if time-t["time"] <= self.cfg["track_max_gap_seconds"]}
        return result


class PersonDetectionEngine:
    def __init__(self, cfg, notes, offline=False):
        import cv2
        self.cv2, self.cfg, self.notes = cv2, cfg, notes
        self.phase_seconds=defaultdict(float)
        self.face = self.sface = self.hog = self.yolo = None
        yunet, sface = asset_path(cfg["yunet_model"]), asset_path(cfg["sface_model"])
        if yunet.is_file():
            self.face = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), 0.85, 0.3, 5000)
            if sface.is_file():
                self.sface = cv2.FaceRecognizerSF.create(str(sface), "")
        else:
            self.face = cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
            notes.append("YuNet ausente: usando Haar frontal. Perfis/oclusões podem não ser detectados.")
        if self.sface is None:
            notes.append("SFace ausente: IDs persistem apenas por continuidade; uma pessoa "
                         "pode receber novo ID após trocar câmera. Contagem é de tracks.")
        if cfg["body_detection"]:
            if cfg["body_backend"] == "yolo":
                try:
                    from ultralytics import YOLO
                    model = asset_path(cfg["yolo_model"])
                    if offline and not model.is_file():
                        raise Unavailable("YOLO offline exige modelo local.")
                    self.yolo = YOLO(str(model) if model.is_file() else cfg["yolo_model"])
                except Exception as exc:
                    notes.append(f"YOLO indisponível ({type(exc).__name__}); usando HOG.")
            if self.yolo is None:
                self.hog = cv2.HOGDescriptor()
                self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
                notes.append("HOG identifica melhor corpos inteiros. Pessoas sentadas podem "
                             "aparecer somente com caixa de rosto; não foi inventada caixa de corpo.")

    def detect(self, frame):
        cv2 = self.cv2
        # Generated by GitHub Copilot - Oct-05-2026
        face_started=perf_counter()
        embedding_seconds=0.0
        height, width = frame.shape[:2]
        faces, bodies = [], []
        if isinstance(self.face, cv2.CascadeClassifier):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for values in self.face.detectMultiScale(gray, 1.1, 5, minSize=(30, 30)):
                faces.append({"face_bbox": bbox(values, width, height),
                              "confidence": None, "embedding": None, "eyes": None})
        else:
            self.face.setInputSize((width, height))
            _, detections = self.face.detect(frame)
            for row in detections if detections is not None else []:
                embedding = None
                if self.sface:
                    embedding_started=perf_counter()
                    aligned = self.sface.alignCrop(frame, row)
                    embedding = self.sface.feature(aligned).reshape(-1)
                    embedding = embedding/max(np.linalg.norm(embedding), 1e-9)
                    embedding_seconds+=perf_counter()-embedding_started
                faces.append({"face_bbox": bbox(row[:4], width, height),
                              "confidence": finite_or_none(float(row[14])), "embedding": embedding,
                              "eyes": [{"x": float(row[i])/width, "y": float(row[i+1])/height}
                                       for i in (4, 6)]})
        self.phase_seconds['face_embedding']+=embedding_seconds
        self.phase_seconds['face_detection']+=max(0.0,perf_counter()-face_started-embedding_seconds)
        body_started=perf_counter()
        if self.yolo:
            out = self.yolo.predict(frame, classes=[0], verbose=False, conf=0.5, device="cpu")[0]
            for row in out.boxes:
                x1, y1, x2, y2 = row.xyxy[0].cpu().numpy()
                bodies.append({"bbox": bbox([x1, y1, x2-x1, y2-y1], width, height),
                               "confidence": finite_or_none(float(row.conf[0]))})
        elif self.hog and width >= 64 and height >= 128:
            values, scores = self.hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
            order = sorted(zip(values, scores), key=lambda pair: float(pair[1]), reverse=True)
            for values, score in order:
                box = bbox(values, width, height)
                if all(iou(box, b["bbox"]) < 0.5 for b in bodies):
                    bodies.append({"bbox": box, "confidence": None, "hog_score": float(score)})
        self.phase_seconds['body_detection']+=perf_counter()-body_started
        detections = []
        used_bodies = set()
        for f in faces:
            c = center(f["face_bbox"])
            matches = [(b["bbox"]["width"]*b["bbox"]["height"], i, b) for i, b in enumerate(bodies)
                       if i not in used_bodies and b["bbox"]["x"] <= c["x"] <= b["bbox"]["x"]+b["bbox"]["width"]
                       and b["bbox"]["y"] <= c["y"] <= b["bbox"]["y"]+b["bbox"]["height"]]
            match = min(matches, default=None)
            body = match[2] if match else None
            if match:
                used_bodies.add(match[1])
            detections.append({"bbox": body["bbox"] if body else f["face_bbox"],
                               "bbox_kind": "body" if body else "face",
                               "face_bbox": f["face_bbox"], "face_visible": True,
                               "body_visible": body is not None, "eyes_position": f["eyes"],
                               "embedding": f["embedding"], "detection_confidence": f["confidence"]})
        for i, b in enumerate(bodies):
            if i not in used_bodies:
                detections.append({"bbox": b["bbox"], "bbox_kind": "body", "face_bbox": None,
                                   "face_visible": False, "body_visible": True,
                                   "eyes_position": None, "embedding": None,
                                   "detection_confidence": b["confidence"]})
        return detections


class LipEngine:
    def __init__(self, cfg):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        model = asset_path(cfg["landmarker_model"])
        if not model.is_file():
            raise Unavailable("Face Landmarker não baixado; associação automática indisponível.")
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.IMAGE, num_faces=6)
        self.mp = mp
        self.model = vision.FaceLandmarker.create_from_options(options)

    def detect(self, frame):
        import cv2
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB,
                              data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = self.model.detect(image)
        rows = []
        for points in result.face_landmarks:
            upper, lower, left, right = [points[i] for i in (13, 14, 61, 291)]
            opening = math.hypot(upper.x-lower.x, upper.y-lower.y)
            span = math.hypot(left.x-right.x, left.y-right.y)
            rows.append({"x": (left.x+right.x)/2, "y": (left.y+right.y)/2,
                         "lip_opening": opening/max(span, 1e-9)})
        return rows

    def close(self):
        self.model.close()


class VisionEngine:
    def run(self, ctx, metadata, scenes, transcript):
        cfg = ctx.config["vision"]
        if not cfg["enabled"]:
            return ok({"people": [], "observations": [], "frames": [], "thumbnails": []}, "skipped")
        try:
            import cv2
        except ImportError:
            raise Unavailable("Instale opencv-python para análise visual.")
        notes = []
        detector = PersonDetectionEngine(cfg, notes, ctx.config["offline"])
        tracker = Tracker(cfg)
        lips = None
        if cfg["active_speaker"]:
            try:
                lips = LipEngine(cfg)
            except Exception as exc:
                notes.append(f"Active speaker: {exc}. Relação voz/rosto sem evidência fica null.")
        cap = cv2.VideoCapture(str(ctx.video))
        if not cap.isOpened():
            raise RuntimeError("OpenCV não conseguiu abrir o vídeo.")
        fps = cap.get(cv2.CAP_PROP_FPS) or metadata["fps"] or 25
        checkpoint_store = VisionCheckpointStore(ctx, cfg)
        resumed = checkpoint_store.load() if float(cfg.get("checkpoint_seconds", 0) or 0) > 0 else None
        # Generated by GitHub Copilot - Oct-05-2026
        timings=defaultdict(float)
        stage_started=perf_counter()
        observations, frames, thumbnails, people = [], [], [], {}
        scene_starts = [s["start"] for s in scenes]
        next_sample, frame_index, last_gray = 0.0, 0, None
        last_scene = None
        chunk_index, chunk_start = 0, 0.0
        obs_mark = frame_mark = thumb_mark = 0
        resume_cutoff = None
        if resumed:
            observations = list(resumed["observations"]); frames = list(resumed["frames"]); thumbnails = list(resumed["thumbnails"])
            people = dict(resumed.get("people") or {})
            checkpoint_store.restore_tracker(tracker, resumed.get("tracker") or {})
            last_gray = np.asarray(resumed["last_gray"], dtype=np.uint8) if resumed.get("last_gray") is not None else None
            last_scene = resumed.get("last_scene")
            next_sample = float(resumed.get("next_sample") or resumed["end"])
            frame_index = int(resumed.get("frame_index") or 0)
            chunk_index = int(resumed.get("next_chunk_index") or 0)
            chunk_start = float(resumed["end"]); resume_cutoff = chunk_start
            obs_mark, frame_mark, thumb_mark = len(observations), len(frames), len(thumbnails)
            if not cap.set(cv2.CAP_PROP_POS_FRAMES,frame_index):
                cap.release()
                if lips:
                    lips.close()
                raise RuntimeError('Decoder nao permite retomar no frame salvo; use --force para uma passada limpa.')
            notes.append(f"Visão retomada de checkpoint íntegro em {chunk_start:.3f}s.")
        thumbnail_dir = ctx.output / "thumbnails"
        thumbnail_dir.mkdir(exist_ok=True)
        segments = transcript.get("segments", [])
        speech_index = 0
        scheduler = SamplingScheduler(cfg)
        if resumed:
            scheduler.burst_until=float(resumed.get('sampling_state',{}).get('burst_until',0))
            scheduler.last_speaker=resumed.get('sampling_state',{}).get('last_speaker')
            scheduler.last_visible_count=resumed.get('sampling_state',{}).get('last_visible_count')
            scheduler.last_missing_lip_burst=float(resumed.get('sampling_state',{}).get('last_missing_lip_burst',-10))
        last_log, thumb_scenes = -60.0, {t.get("scene_id") for t in frames if t.get("scene_id")}
        checkpoint_seconds = float(cfg.get("checkpoint_seconds", 0) or 0)
        next_checkpoint = chunk_start + checkpoint_seconds if checkpoint_seconds > 0 else math.inf
        checkpoint_backend = {"face": type(detector.face).__name__ if detector.face is not None else None,
                              "body": "yolo" if detector.yolo is not None else "hog" if detector.hog is not None else None,
                              "lip": type(lips).__name__ if lips is not None else None}
        try:
            while True:
                phase_started=perf_counter()
                grabbed=cap.grab()
                timings['video_decode']+=perf_counter()-phase_started
                if not grabbed:
                    break
                time = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
                if time <= 0 and frame_index:
                    time = frame_index/fps
                index = frame_index
                frame_index += 1
                if resume_cutoff is not None and time <= resume_cutoff + max(1e-4, .25/fps):
                    continue
                resume_cutoff = None
                if time+1/fps < next_sample:
                    continue
                phase_started=perf_counter()
                got, frame = cap.retrieve()
                timings['video_decode']+=perf_counter()-phase_started
                if not got:
                    continue
                if time >= metadata["duration"]:
                    break
                height, width = frame.shape[:2]
                scale = min(1, cfg["max_width"]/width)
                if scale < 1:
                    frame = cv2.resize(frame, (round(width*scale), round(height*scale)))
                sh, sw = frame.shape[:2]
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(gray, (160, 90))
                motion_started=perf_counter()
                scene_index = max(0, bisect.bisect_right(scene_starts, time)-1)
                scene_id = scenes[scene_index]["scene_id"] if scenes else None
                change = scene_id != last_scene
                boundary_difference = float(np.mean(cv2.absdiff(small, last_gray))/255) if last_gray is not None else None
                motion = boundary_difference if boundary_difference is not None and not change else None
                source_camera_motion = None
                if last_gray is not None and not change:
                    try:
                        shift, response = cv2.phaseCorrelate(np.float32(last_gray), np.float32(small))
                        dx, dy = float(shift[0])/small.shape[1], float(shift[1])/small.shape[0]
                        if math.isfinite(dx+dy+float(response)) and response >= .05:
                            source_camera_motion = {"dx": finite_or_none(dx), "dy": finite_or_none(dy),
                                "magnitude": finite_or_none(math.hypot(dx,dy)), "confidence": finite_or_none(float(response)),
                                "method": "phase_correlation_global_translation"}
                    except (cv2.error, ValueError, TypeError):
                        source_camera_motion = None
                quality = {"time": time, "frame": index, "scene_id": scene_id,
                           "brightness": finite_or_none(float(gray.mean()/255)),
                           "blur_laplacian_variance": finite_or_none(float(cv2.Laplacian(gray, cv2.CV_64F).var())),
                           "camera_motion_proxy": motion, "source_camera_motion": source_camera_motion,
                           "boundary_difference": boundary_difference if change else None,
                           "possible_black_frame": bool(gray.mean() < 5),
                           "possible_freeze_frame": bool(motion is not None and motion < 0.0005),
                           "visible_people": []}
                timings['motion_estimation']+=perf_counter()-motion_started
                phase_started=perf_counter()
                detections = detector.detect(frame)
                timings['face_body_embedding_detection']+=perf_counter()-phase_started
                phase_started=perf_counter()
                current = tracker.update(detections, time, scene_id)
                timings['tracker_association']+=perf_counter()-phase_started
                phase_started=perf_counter()
                mouth = lips.detect(frame) if lips else []
                timings['landmark_inference']+=perf_counter()-phase_started
                for obs in current:
                    box, face = obs["bbox"], obs["face_bbox"]
                    face_center = center(face) if face else None
                    mouth_matches = [m for m in mouth if face and face["x"] <= m["x"] <= face["x"]+face["width"]
                                     and face["y"] <= m["y"] <= face["y"]+face["height"]]
                    fits, crop = vertical_crop(face or box, width, height)
                    pid = obs["person_id"]
                    sharpness = None
                    if face:
                        x1 = max(0, min(sw-1, int(face["x"] * sw)))
                        y1 = max(0, min(sh-1, int(face["y"] * sh)))
                        x2 = max(x1+1, min(sw, int((face["x"]+face["width"]) * sw)))
                        y2 = max(y1+1, min(sh, int((face["y"]+face["height"]) * sh)))
                        roi = gray[y1:y2, x1:x2]
                        if roi.size:
                            sharpness = finite_or_none(float(cv2.Laplacian(roi, cv2.CV_64F).var()))
                    lip_opening = mouth_matches[0]["lip_opening"] if len(mouth_matches) == 1 else None
                    row = {**obs, "time": time, "frame": index, "scene_id": scene_id,
                           "center": center(box), "head_center": face_center,
                           "body_center": center(box) if obs["body_visible"] else None,
                           "percent_frame": box["width"]*box["height"],
                           "face_width": face["width"] if face else None,
                           "face_height": face["height"] if face else None,
                           "face_area": face["width"]*face["height"] if face else None,
                           "visibility": obs.get("detection_confidence"),
                           "sharpness": sharpness, "motion_blur": None,
                           "source_camera_motion": source_camera_motion,
                           "head_pose": None, "eyes_open": None,
                           "distance_to_left": box["x"],
                           "distance_to_right": 1-box["x"]-box["width"],
                           "safe_crop_possible": fits, "crop_target": "face" if face else "body",
                           "estimated_vertical_crop": crop,
                           "lip_opening": lip_opening, "mouth_activity": None}
                    observations.append(row)
                    quality["visible_people"].append(pid)
                    if pid not in people:
                        people[pid] = {"person_id": pid, "name": None, "first_seen": time,
                                       "last_seen": time, "observation_count": 0, "portrait": None,
                                       "identity_method": obs["tracking_method"],
                                       "civil_identity_inferred": False}
                    people[pid]["last_seen"] = time
                    people[pid]["observation_count"] += 1
                    if (not people[pid]['portrait'] and people[pid]['observation_count'] >= cfg.get('tracklet_min_observations',3)
                            and time-people[pid]['first_seen'] >= cfg.get('identity_min_visual_seconds',3)
                            and len(thumbnails)<cfg['max_thumbnails'] and face and (sharpness or 0)>40):
                        phase_started=perf_counter()
                        path=thumbnail_dir/f'{pid}_{time:.3f}.jpg'
                        if cv2.imwrite(str(path),frame,[cv2.IMWRITE_JPEG_QUALITY,85]):
                            relative='thumbnails/'+path.name
                            people[pid]['portrait']=relative
                            thumbnails.append({'time':time,'reason':'qualified_visual_evidence','path':relative,'raw_person_id':pid})
                        timings['thumbnail_io']+=perf_counter()-phase_started
                if scene_id not in thumb_scenes and len(thumbnails) < cfg["max_thumbnails"]:
                    path = thumbnail_dir / f"{scene_id or 'frame'}_{time:.3f}.jpg"
                    cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    thumbnails.append({"time": time, "reason": "scene_start", "path": "thumbnails/"+path.name})
                    thumb_scenes.add(scene_id)
                frames.append(quality)
                while speech_index < len(segments) and segments[speech_index]["end"] < time:
                    speech_index += 1
                speaking = speech_index < len(segments) and segments[speech_index]["start"] <= time <= segments[speech_index]["end"]
                phase_started=perf_counter()
                frequency, sampling_reasons = scheduler.frequency(
                    time, speaking=speaking, speaker=segments[speech_index].get("speaker") if speaking else None,
                    boundary=change, motion=motion, visible_count=len(current), mouth_count=len(mouth))
                timings['sampling_schedule']+=perf_counter()-phase_started
                quality["sampling_fps"] = frequency
                quality["sampling_reasons"] = sampling_reasons
                next_sample = time+1/frequency
                last_gray, last_scene = small, scene_id
                if time >= next_checkpoint:
                    phase_started=perf_counter()
                    checkpoint_store.save(chunk_index, chunk_start, time,
                        observations[obs_mark:], frames[frame_mark:], thumbnails[thumb_mark:], people, tracker,
                        last_gray, last_scene, next_sample, frame_index, checkpoint_backend,
                        {'burst_until':scheduler.burst_until,'last_speaker':scheduler.last_speaker,
                         'last_visible_count':scheduler.last_visible_count,
                         'last_missing_lip_burst':scheduler.last_missing_lip_burst if math.isfinite(scheduler.last_missing_lip_burst) else -10})
                    timings['checkpoint_io']+=perf_counter()-phase_started
                    chunk_index += 1; chunk_start = time
                    obs_mark, frame_mark, thumb_mark = len(observations), len(frames), len(thumbnails)
                    next_checkpoint = chunk_start + checkpoint_seconds
                if time-last_log >= 60:
                    ctx.logger.info("Visão: %.1f / %.1fs; %s tracks", time, metadata["duration"], len(people))
                    last_log = time
        finally:
            cap.release()
            if lips:
                lips.close()
        if checkpoint_seconds > 0 and (len(frames) > frame_mark or len(observations) > obs_mark):
            final_end = min(float(metadata.get("duration") or chunk_start),
                            max([f.get("time", chunk_start) for f in frames[frame_mark:]] or [chunk_start]))
            checkpoint_store.save(chunk_index, chunk_start, max(final_end, chunk_start+1e-6),
                observations[obs_mark:], frames[frame_mark:], thumbnails[thumb_mark:], people, tracker,
                last_gray, last_scene, next_sample, frame_index, checkpoint_backend,
                {'burst_until':scheduler.burst_until,'last_speaker':scheduler.last_speaker,
                 'last_visible_count':scheduler.last_visible_count,
                 'last_missing_lip_burst':scheduler.last_missing_lip_burst if math.isfinite(scheduler.last_missing_lip_burst) else -10})
        if not frames:
            raise RuntimeError("Nenhum frame foi decodificado.")
        # Mouth activity is temporal change, not raw mouth opening. Preserve null when
        # landmarks are absent or the sampling gap is too large.
        by_person = defaultdict(list)
        for row in observations:
            by_person[row["person_id"]].append(row)
        for rows in by_person.values():
            rows.sort(key=lambda r: r["time"])
            previous = None
            for row in rows:
                if row.get("lip_opening") is not None and previous is not None and previous.get("lip_opening") is not None:
                    dt = row["time"] - previous["time"]
                    if (row.get("scene_id") == previous.get("scene_id") and
                            row.get("track_id") == previous.get("track_id") and
                            0 < dt <= max(1.5, cfg["track_max_gap_seconds"] * 1.25)):
                        row["mouth_activity"] = abs(row["lip_opening"] - previous["lip_opening"]) / dt
                previous = row
        for person in people.values():
            person_rows = by_person.get(person["person_id"], [])
            person["track_ids"] = sorted({r.get("track_id") for r in person_rows if r.get("track_id")})
            reid_scores = [float(r.get("same_person_confidence")) for r in person_rows
                           if isinstance(r.get("same_person_confidence"), (int, float))
                           and not isinstance(r.get("same_person_confidence"), bool)
                           and math.isfinite(float(r.get("same_person_confidence")))]
            person["reid_confidence"] = min(reid_scores) if reid_scores else None
            person["face_samples"] = sum(bool(r.get("face_visible")) for r in person_rows)
            person["sample_presence_fraction"] = person["observation_count"]/len(frames)
        return ok({"people": list(people.values()), "observations": observations,
                   "frames": frames, "thumbnails": thumbnails,
                   "scene_intervals": [{k: s[k] for k in ("start", "end", "scene_id")} for s in scenes],
                   "sample_fps": cfg["sample_fps"], "speech_sample_fps": cfg["speech_sample_fps"],
                   "performance": {'elapsed_seconds':perf_counter()-stage_started,'phase_seconds':{**dict(timings),**dict(getattr(detector,'phase_seconds',{}))},
                                   'decoded_frames':frame_index,'sampled_frames':len(frames),
                                   'phase_accounting':'detector_subphases_partition_combined_detection; do_not_sum_both'},
                   "quality": {"sample_count": len(frames), "actual_width": width, "actual_height": height,
                               "mean_brightness": float(np.mean([f["brightness"] for f in frames])),
                               "black_frame_samples": sum(f["possible_black_frame"] for f in frames),
                               "freeze_frame_samples": sum(f["possible_freeze_frame"] for f in frames)}},
                  "partial" if notes else "ok", notes,
                  [ctx.output/t["path"] for t in thumbnails])


class ActiveSpeakerEngine:
    def run(self, ctx, audio, diarization, vision, metadata):
        mappings, notes = [], []
        cfg = ctx.config["vision"]
        people = {p["person_id"] for p in vision.get("people", [])}
        speakers = {s["speaker_id"] for s in diarization.get("speakers", [])}
        manual = []
        if cfg["manual_mapping_file"]:
            data = read_json(asset_path(cfg["manual_mapping_file"]))
            manual = data if isinstance(data, list) else data.get("mappings", [])
            for row in manual:
                if row.get("person_id") not in people or row.get("speaker") not in speakers:
                    raise ValueError("Mapping manual faz referência a pessoa/locutor inexistente.")
                if not 0 <= row["start"] < row["end"] <= metadata["duration"]:
                    raise ValueError("Mapping manual com intervalo inválido.")
        tracks = defaultdict(list)
        for obs in vision.get("observations", []):
            if obs.get("lip_opening") is not None:
                tracks[obs["person_id"]].append(obs)
        track_times = {pid: [r["time"] for r in rows] for pid, rows in tracks.items()}
        rate = sf.info(audio["mono"]).samplerate
        with sf.SoundFile(audio["mono"]) as f:
            # Independent local windows retain evidence through long turns and source cuts.
            windows = []
            for turn in diarization.get("turns", []):
                a = turn["start"]
                while a < turn["end"]:
                    b = min(turn["end"], a+3.)
                    windows.append({**turn, "start": a, "end": b})
                    a = b
            for turn in windows:
                start, end, speaker = turn["start"], turn["end"], turn["speaker"]
                supplied = [m for m in manual if m["speaker"] == speaker and m["start"] <= start and m["end"] >= end]
                if len(supplied) == 1:
                    mappings.append({"start": start, "end": end, "speaker": speaker,
                                     "speaker_id": speaker,
                                     "visible_person": supplied[0]["person_id"],
                                     "person_id": supplied[0]["person_id"],
                                     "association_confidence": 1.0, "confidence": 1.0,
                                     "method": "user_verified",
                                     "evidence": ["user_verified_mapping"],
                                     "evidence_detail": supplied[0].get("evidence", "user mapping"),
                                     "inference": False, "needs_review": False})
                    continue
                candidates = []
                if not turn.get("overlap") and end-start >= 2.0:
                    for pid, rows in tracks.items():
                        times = track_times[pid]
                        selected = rows[bisect.bisect_left(times, start):bisect.bisect_left(times, end)]
                        if len(selected) < 12 or selected[-1]["time"]-selected[0]["time"] < (end-start)*0.7:
                            continue
                        if len({r["scene_id"] for r in selected}) > 1:
                            continue
                        values, rms = [], []
                        for r in selected:
                            f.seek(max(0, round((r["time"]-0.08)*rate)))
                            samples = f.read(round(0.16*rate), dtype="float32")
                            rms.append(float(np.sqrt(np.mean(samples**2))) if samples.size else 0)
                            values.append(r["lip_opening"])
                        if np.std(values) < 0.008 or np.std(rms) < 1e-5:
                            continue
                        correlation = float(np.corrcoef(values, rms)[0, 1])
                        if math.isfinite(correlation):
                            candidates.append({"person_id": pid, "correlation": correlation,
                                               "sample_count": len(selected),
                                               "mouth_activity_mean": float(np.mean([r.get("mouth_activity") or 0 for r in selected]))})
                candidates.sort(key=lambda c: c["correlation"], reverse=True)
                chosen = None
                if candidates and candidates[0]["correlation"] >= cfg["association_min_correlation"]:
                    if len(candidates) == 1 or candidates[0]["correlation"]-candidates[1]["correlation"] >= cfg["association_min_margin"]:
                        chosen = candidates[0]["person_id"]
                top_score = candidates[0]["correlation"] if candidates else None
                confidence = None
                if chosen is not None and top_score is not None:
                    floor = cfg["association_min_correlation"]
                    confidence = max(0.0, min(1.0, (top_score-floor)/max(1e-9, 1-floor)))
                    if len(candidates) > 1:
                        margin = top_score-candidates[1]["correlation"]
                        confidence *= max(0.0, min(1.0, margin/max(cfg["association_min_margin"], 1e-9)))
                mappings.append({"start": start, "end": end, "speaker": speaker,
                                 "speaker_id": speaker, "visible_person": chosen, "person_id": chosen,
                                 "association_confidence": confidence, "confidence": confidence,
                                 "association_evidence_score": top_score,
                                 "candidates": candidates, "method": "lip_audio_correlation" if chosen else "unresolved",
                                 "evidence": (["diarization", "mouth_activity", "face_visible"] if chosen else
                                              (["diarization"] if speaker else [])),
                                 "inference": chosen is not None,
                                 "needs_review": True})
        notes.append("Correlação boca/áudio é heurística, não um modelo ASD calibrado. "
                     "Um rosto sozinho ou centralizado não basta; associação incerta fica null.")
        return ok({"mappings": mappings}, "partial", notes)
