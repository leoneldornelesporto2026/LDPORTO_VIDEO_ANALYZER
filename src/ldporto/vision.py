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
from .visual_sampling import SamplingScheduler, ShortShotSamplingPlan, ShotBoundarySamplingPlan
from .face_quality import assess_face
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
    """Shot-local tracks; anonymous face hypotheses are consolidated by Re-ID."""
    def __init__(self, cfg):
        self.cfg, self.tracks, self.gallery = cfg, {}, {}
        self.next_id = 1
        self.next_track_id = 1
        self.completed_tracks = []
        self.association_count = 0
        self.conflicting_embedding_count = 0

    def _new_track_id(self):
        value = f"TRACK_{self.next_track_id:05}"
        self.next_track_id += 1
        return value

    def _gap_limit(self, track):
        base = float(self.cfg["track_max_gap_seconds"])
        if track.get("hits", 1) >= self.cfg.get("tracklet_min_observations", 3):
            return max(base, min(3.0, self.cfg.get("track_occlusion_max_seconds", 2.0)))
        return base

    def _retire(self, person_id, reason):
        track = self.tracks.pop(person_id)
        self.completed_tracks.append({"track_id": track["track_id"], "person_id": person_id,
            "state": "terminated_track", "shot_id": track["scene"],
            "first_seen": track.get("first_seen", track["time"]), "last_seen": track["time"],
            "observation_count": track.get("hits", 1), "termination_reason": reason})

    def _association(self, detection, track, time):
        gap = time - track["time"]
        if gap < 0 or gap > self._gap_limit(track):
            return None
        face_pair = bool(detection.get("face_bbox") and track.get("face_bbox"))
        if face_pair:
            current_box, previous_box = detection["face_bbox"], track["face_bbox"]
        elif detection.get("bbox_kind") == track.get("bbox_kind") or not track.get("bbox_kind"):
            current_box, previous_box = detection["bbox"], track["bbox"]
        else:
            return None
        similarity = None
        if detection.get("embedding") is not None and track.get("embedding") is not None:
            if len(detection["embedding"]) != len(track["embedding"]):
                return None
            similarity = finite_or_none(float(np.dot(detection["embedding"], track["embedding"])))
            if similarity is not None and similarity < .3:
                self.conflicting_embedding_count += 1
                return None
        current_center, previous_center = center(current_box), center(previous_box)
        velocity = track.get("velocity", {"x": 0.0, "y": 0.0})
        predicted = {axis: previous_center[axis] + velocity.get(axis, 0.0) * gap for axis in ("x", "y")}
        distance = math.hypot(current_center["x"] - predicted["x"], current_center["y"] - predicted["y"])
        limit = min(.45, max(.06, previous_box["width"] * 1.5) + .18 * gap)
        size_ratio = max(current_box["width"] / max(previous_box["width"], 1e-6),
                         previous_box["width"] / max(current_box["width"], 1e-6),
                         current_box["height"] / max(previous_box["height"], 1e-6),
                         previous_box["height"] / max(current_box["height"], 1e-6))
        overlap_score = iou(current_box, previous_box)
        if distance > limit or size_ratio > 3.0:
            return None
        strong_face = similarity is not None and similarity >= self.cfg["reid_threshold"]
        if overlap_score < .25 and not strong_face:
            return None
        motion_score = max(0.0, 1.0 - distance / max(limit, 1e-6))
        score = .55 * overlap_score + .25 * motion_score + .05 / size_ratio
        if similarity is not None:
            score += .15 * max(0.0, similarity)
        return score, overlap_score, similarity

    def update(self, detections, time, scene_id):
        from scipy.optimize import linear_sum_assignment

        for person_id, track in list(self.tracks.items()):
            if track["scene"] != scene_id:
                self._retire(person_id, "visual_shot_cut")
            elif time - track["time"] > self._gap_limit(track):
                self._retire(person_id, "occlusion_limit")
        assigned, used = {}, set()
        person_ids = sorted(self.tracks)
        matrix = np.full((len(detections), len(person_ids) + len(detections)), -1e6)
        pairs = {}
        if detections:
            matrix[:, len(person_ids):] = 0.0
            for detection_index, detection in enumerate(detections):
                for person_index, person_id in enumerate(person_ids):
                    evidence = self._association(detection, self.tracks[person_id], time)
                    if evidence is not None:
                        matrix[detection_index, person_index] = evidence[0]
                        pairs[detection_index, person_index] = evidence
            row_indices, columns = linear_sum_assignment(-matrix)
            for detection_index, person_index in zip(row_indices, columns):
                evidence = pairs.get((detection_index, person_index))
                if evidence is None:
                    continue
                person_id = person_ids[person_index]
                assigned[detection_index] = (person_id, self.tracks[person_id]["track_id"],
                    "shot_temporal_fusion", evidence[1], evidence[2])
                used.add(person_id)
                self.association_count += 1
        for i, d in enumerate(detections):
            if i in assigned:
                continue
            emb = d.get("embedding")
            scores = []
            if emb is not None:
                for pid, stored in self.gallery.items():
                    if pid in used or pid in self.tracks or len(emb) != len(stored):
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
            previous_track = self.tracks.get(pid) or {}
            continued = previous_track.get("track_id") == track_id
            hits = previous_track.get("hits", 1) + 1 if continued else 1
            first_seen = previous_track.get("first_seen", previous_track.get("time", time)) if continued else time
            confirmed = hits >= self.cfg.get("tracklet_min_observations", 3) and time - first_seen >= self.cfg.get("tracklet_min_visual_seconds", 1.0)
            anchor = d.get("face_bbox") or d["bbox"]
            previous_anchor = previous_track.get("face_bbox") or previous_track.get("bbox")
            velocity = {"x": 0.0, "y": 0.0}
            if continued and previous_anchor and time > previous_track["time"]:
                before, after = center(previous_anchor), center(anchor)
                velocity = {axis: max(-.65, min(.65, (after[axis] - before[axis]) / (time - previous_track["time"]))) for axis in ("x", "y")}
            embedding = d.get("embedding")
            observed_embedding = embedding is not None
            if embedding is None and continued:
                embedding = previous_track.get("embedding")
            self.tracks[pid] = {"bbox": d["bbox"], "time": time,
                                "bbox_kind": d.get("bbox_kind"), "face_bbox": d.get("face_bbox"),
                                "scene": scene_id, "embedding": embedding, "velocity": velocity,
                                "track_id": track_id, "hits": hits, "first_seen": first_seen,
                                "state": "confirmed_track" if confirmed else "tentative_track"}
            if d.get("embedding") is not None:
                self.gallery.setdefault(pid, d["embedding"])
            identity_confidence = None
            if method == "anonymous_face_embedding":
                identity_confidence = max(0.0, min(1.0, face_similarity)) if face_similarity is not None else None
            result.append({**{k: v for k, v in d.items() if k != "embedding"},
                           "person_id": pid, "track_id": track_id,
                           "shot_id": scene_id, "track_state": self.tracks[pid]["state"],
                           "raw_detection_state": "raw_detection", "track_observation_count": hits,
                           "occlusion_recovered": continued and previous_track.get("state") == "temporarily_lost",
                           "tracking_method": method,
                           "tracking_confidence": iou_score,
                           "tracking_similarity": face_similarity,
                           "same_person_confidence": identity_confidence,
                           "identity_is_inference": method == "anonymous_face_embedding",
                           "face_embedding_available": embedding is not None,
                           "face_embedding_observed": observed_embedding,
                           "embedding_reused": embedding is not None and not observed_embedding,
                           "face_embedding": np.asarray(d["embedding"]).tolist() if observed_embedding else None,
                           "embedding_method": "opencv_sface" if observed_embedding else None})
        for person_id, track in self.tracks.items():
            if person_id not in used:
                track["state"] = "temporarily_lost"
        return result


def load_local_yolo(cfg):
    """Select optional YOLO using an existing local asset, never a download name."""
    report = {"requested": cfg["body_backend"], "initialized": None,
              "fallback_reason": None, "exception_type": None, "device": "cpu"}
    if not cfg["body_detection"]:
        report["fallback_reason"] = "body_detection_disabled"
        return None, report
    if cfg["body_backend"] == "hog":
        report.update(initialized="hog", fallback_reason="hog_configured")
        return None, report
    model = asset_path(cfg["yolo_model"])
    if not model.is_file():
        report.update(initialized="hog", fallback_reason="yolo_local_model_missing")
        return None, report
    try:
        from ultralytics import YOLO
    except Exception as exc:
        report.update(initialized="hog", fallback_reason="yolo_import_failed",
                      exception_type=type(exc).__name__)
        return None, report
    try:
        body = YOLO(str(model.resolve()))
    except Exception as exc:
        report.update(initialized="hog", fallback_reason="yolo_model_load_failed",
                      exception_type=type(exc).__name__)
        return None, report
    report["initialized"] = "yolo"
    return body, report


class PersonDetectionEngine:
    def __init__(self, cfg, notes, offline=False):
        import cv2
        self.cv2, self.cfg, self.notes = cv2, cfg, notes
        self.phase_seconds=defaultdict(float)
        self.calls = defaultdict(int)
        self.face_history = []
        self.last_rescue_time = -math.inf
        self.last_body_time = -math.inf
        self.last_shot = None
        self.face = self.sface = self.hog = self.yolo = None
        self._hog_pool = None
        from .performance import cpu_overlap_budget
        self.overlap_budget = cpu_overlap_budget(requested=cfg.get("parallel_hog_with_face", False))
        yunet, sface = asset_path(cfg["yunet_model"]), asset_path(cfg["sface_model"])
        if yunet.is_file():
            self.face = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320),
                float(cfg.get("yunet_score_threshold", .82)), 0.3, 5000)
            if sface.is_file():
                self.sface = cv2.FaceRecognizerSF.create(str(sface), "")
        else:
            self.face = cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
            notes.append("YuNet ausente: usando Haar frontal. Perfis/oclusões podem não ser detectados.")
        if self.sface is None:
            notes.append("SFace ausente: IDs persistem apenas por continuidade; uma pessoa "
                         "pode receber novo ID após trocar câmera. Contagem é de tracks.")
        self.yolo, self.body_backend_report = load_local_yolo(cfg)
        if cfg["body_detection"]:
            if self.yolo is None:
                self._activate_hog()

    def _activate_hog(self):
        self.hog = self.cv2.HOGDescriptor()
        self.hog.setSVMDetector(self.cv2.HOGDescriptor_getDefaultPeopleDetector())
        if self.overlap_budget["enabled"]:
            from concurrent.futures import ThreadPoolExecutor
            self._hog_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ldporto-hog-cpu")
        self.notes.append("Visão de corpos degradada: HOG; motivo=" +
                          str(self.body_backend_report["fallback_reason"]) +
                          ". Corpos sentados/ocultos podem faltar; caixas de rosto são preservadas "
                          "sem inventar corpo ou identidade por localização.")

    def backend_execution(self):
        counts = {name: self.calls.get(name + "_inference_calls", 0) for name in ("yolo", "hog")}
        executed = [name for name in counts if counts[name]]
        return {**self.body_backend_report, "executed_backends": executed,
                "counts_scope": "current_process_only",
                "inference_calls": counts,
                "successful_calls": {name: self.calls.get(name + "_successful_calls", 0) for name in counts},
                "quality": "degraded" if self.hog is not None else "not_validated" if self.yolo is not None else "disabled",
                "seated_recall_validated": None, "nvidia_validated": None}

    def close(self):
        if getattr(self, "_hog_pool", None) is not None:
            self._hog_pool.shutdown(wait=True, cancel_futures=False)
            self._hog_pool = None

    def _hog_boxes(self, frame, width, height):
        self.calls["hog_inference_calls"] += 1
        values, scores = self.hog.detectMultiScale(frame, winStride=(8, 8), padding=(8, 8), scale=1.08)
        self.calls["hog_successful_calls"] += 1
        bodies = []
        for coords, score in sorted(zip(values, scores), key=lambda pair: float(pair[1]), reverse=True):
            box = bbox(coords, width, height)
            if all(iou(box, b["bbox"]) < .5 for b in bodies):
                bodies.append({"bbox": box, "confidence": None, "hog_score": float(score),
                               "source": "hog"})
        return bodies

    def set_frame_context(self, time, shot_id, shot_duration=None):
        self.frame_context = (time, shot_id, shot_duration)

    def detect(self, frame, time=None, shot_id=None):
        cv2 = self.cv2
        if time is None:
            context = getattr(self, "frame_context", (None, None, None))
            time, shot_id = context[:2]
        shot_duration = getattr(self, "frame_context", (None, None, None))[2]
        face_started=perf_counter()
        embedding_seconds=0.0
        height, width = frame.shape[:2]
        faces, bodies = [], []
        cascade = self.cfg.get("detector_cascade", False) and time is not None
        if not hasattr(self, "calls"):
            self.calls = defaultdict(int)
            self.face_history, self.last_body_time, self.last_shot = [], -math.inf, None
        shot_changed = shot_id != self.last_shot
        if shot_changed:
            self.face_history, self.last_body_time = [], -math.inf
        self.calls["face_detection_calls"] += 1
        # Scheduled refresh is independent of face results. Overlap exactly the
        # same HOG call with face work (no speculative extra detection calls).
        scheduled_hog = bool(getattr(self, "_hog_pool", None) is not None and self.hog is not None and
            width >= 64 and height >= 128 and
            (not cascade or time - self.last_body_time >= self.cfg.get("body_refresh_seconds", .5)))
        hog_future = self._hog_pool.submit(self._hog_boxes, frame, width, height) if scheduled_hog else None
        used_history = set()
        face_detector_status = 'available'
        if self.face is None:
            face_detector_status = 'unavailable'
            self.calls['face_detector_unavailable_frames'] += 1
        elif isinstance(self.face, cv2.CascadeClassifier):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            try:
                haar_detections = self.face.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            except (cv2.error, ValueError, RuntimeError):
                haar_detections = []
                face_detector_status = 'error'
                self.calls['face_detector_failed_frames'] += 1
            for values in haar_detections:
                faces.append({"face_bbox": bbox(values, width, height),
                              "confidence": None, "embedding": None, "eyes": None,
                              "face_quality": None, "embedding_missing_reason": "sface_unavailable_haar_fallback",
                              "face_detection_source": "haar"})
        else:
            self.face.setInputSize((width, height))
            try:
                _, detections = self.face.detect(frame)
            except (cv2.error, ValueError, RuntimeError):
                detections = None
                face_detector_status = 'error'
                self.calls['face_detector_failed_frames'] += 1
            # A second, bounded YuNet pass may recover small faces in a long
            # studio shot. Never hallucinate a face or stretch a face embedding.
            base_count = len(detections) if detections is not None else 0
            if (face_detector_status == 'available' and
                    self.cfg.get('face_rescue_upsample', False) and base_count < 2):
                cooldown = float(self.cfg.get('face_rescue_cooldown_seconds', 2.0))
                # Empty shots deserve an immediate retry. When a face is already
                # visible, limit the multi-face rescue to periodic checks.
                if ((not base_count and shot_changed) or time is None or
                        time - getattr(self, 'last_rescue_time', -math.inf) >= cooldown):
                    self.last_rescue_time = time if time is not None else -math.inf
                    multiplier = float(self.cfg.get('face_rescue_scale', 1.5))
                    max_pixels = int(self.cfg.get('face_rescue_max_pixels', 2500000))
                    if width*height*multiplier*multiplier <= max_pixels:
                        try:
                            enlarged = cv2.resize(frame, None, fx=multiplier, fy=multiplier)
                            self.face.setInputSize((enlarged.shape[1], enlarged.shape[0]))
                            self.calls['face_rescue_calls'] += 1
                            _, rescued = self.face.detect(enlarged)
                            if rescued is not None and len(rescued):
                                corrected = rescued.copy()
                                corrected[:, :14] /= multiplier
                                kept = [row for row in detections] if detections is not None else []
                                added = 0
                                for proposal in sorted(corrected, key=lambda r: -float(r[14])):
                                    box = bbox(proposal[:4], width, height)
                                    # Judge the ORIGINAL pixels, never the enlarged crop.
                                    rescue_quality = assess_face(frame, box,
                                        confidence=float(proposal[14]),
                                        eyes=[{'x': float(proposal[i])/width,
                                               'y': float(proposal[i+1])/height} for i in (4, 6)],
                                        min_pixels=int(self.cfg.get('face_min_pixels_for_embedding', 28)),
                                        min_sharpness=float(self.cfg.get('face_min_sharpness_for_embedding', 18)),
                                        min_confidence=float(self.cfg.get('face_min_confidence_for_embedding', .74)))
                                    if not rescue_quality['embedding_eligible']:
                                        self.calls['face_rescue_quality_rejections'] += 1
                                        continue
                                    if all(iou(box, bbox(existing[:4], width, height)) < .45
                                           for existing in kept):
                                        kept.append(proposal)
                                        added += 1
                                if kept:
                                    detections = np.stack(kept)
                                self.calls['face_rescue_detected_faces'] += added
                        except (cv2.error, ValueError, RuntimeError):
                            self.calls['face_rescue_failed_calls'] += 1
                        finally:
                            self.face.setInputSize((width, height))
                    else:
                        self.calls['face_rescue_budget_skipped'] += 1
            for row in detections if detections is not None else []:
                embedding = None
                face_box = bbox(row[:4], width, height)
                eyes = [{'x': float(row[i])/width, 'y': float(row[i+1])/height}
                        for i in (4, 6)]
                quality = (assess_face(frame, face_box, confidence=finite_or_none(float(row[14])),
                            eyes=eyes, min_pixels=int(self.cfg.get('face_min_pixels_for_embedding', 28)),
                            min_sharpness=float(self.cfg.get('face_min_sharpness_for_embedding', 18)),
                            min_confidence=float(self.cfg.get('face_min_confidence_for_embedding', .74)))
                    if self.cfg.get('face_quality_gate', False) else None)
                reason = None
                history_matches = [(iou(face_box, previous["bbox"]), index, previous)
                                   for index, previous in enumerate(self.face_history)
                                   if index not in used_history and iou(face_box, previous["bbox"]) >= .8]
                matched = max(history_matches, key=lambda match: match[0], default=None)
                short_shot = (shot_duration is not None and 0 < shot_duration <=
                              self.cfg.get("short_shot_max_seconds", 1.5))
                embedding_due = (short_shot or not cascade or matched is None or
                    time - matched[2]["embedding_time"] >= self.cfg.get("embedding_interval_seconds", 1.0))
                if matched:
                    used_history.add(matched[1])
                if self.sface and embedding_due and (quality is None or quality['embedding_eligible']):
                    embedding_started=perf_counter()
                    self.calls["embedding_calls"] += 1
                    if short_shot:
                        self.calls["short_shot_embedding_attempts"] += 1
                    try:
                        aligned = self.sface.alignCrop(frame, row)
                        embedding = self.sface.feature(aligned).reshape(-1)
                        norm = float(np.linalg.norm(embedding))
                        if not np.isfinite(embedding).all() or norm < 1e-9:
                            raise ValueError("Face embedding nao finito ou degenerado")
                        embedding = embedding / norm
                        self.calls["successful_embeddings"] += 1
                    except (cv2.error, ValueError, TypeError, RuntimeError):
                        embedding = None
                        reason = 'embedding_extraction_failed'
                        self.calls["failed_embeddings"] += 1
                    embedding_seconds+=perf_counter()-embedding_started
                elif self.sface and quality is not None and not quality['embedding_eligible']:
                    reason = 'quality_rejected'
                    self.calls['embedding_quality_rejections'] += 1
                    for quality_reason in quality['rejection_reasons']:
                        self.calls['quality_'+quality_reason] += 1
                elif self.sface:
                    reason = 'embedding_not_due'
                    self.calls["embedding_calls_avoided"] += 1
                else:
                    reason = 'sface_unavailable'
                    self.calls['face_without_sface'] += 1
                faces.append({"face_bbox": face_box,
                              "confidence": finite_or_none(float(row[14])), "embedding": embedding,
                              "embedding_time": time if embedding is not None else matched[2]["embedding_time"] if matched else -math.inf,
                              "eyes": eyes, "face_quality": quality,
                              "embedding_missing_reason": reason,
                              "face_detection_source": "yunet"})
        self.last_face_detector_status = face_detector_status
        self.phase_seconds['face_embedding']+=embedding_seconds
        self.phase_seconds['face_detection']+=max(0.0,perf_counter()-face_started-embedding_seconds)
        body_started=perf_counter()
        run_body = (not cascade or not faces or any((face.get("confidence") or 0) < .9 for face in faces) or
                    time - self.last_body_time >= self.cfg.get("body_refresh_seconds", .5))
        if run_body and (self.yolo or self.hog):
            self.calls["body_detection_calls"] += 1
            self.last_body_time = time if time is not None else -math.inf
        elif self.yolo or self.hog:
            self.calls["body_detection_calls_avoided"] += 1
        if self.yolo and run_body:
            self.calls["yolo_inference_calls"] += 1
            try:
                out = self.yolo.predict(frame, classes=[0], verbose=False, conf=0.5, device="cpu")[0]
                for row in out.boxes:
                    x1, y1, x2, y2 = row.xyxy[0].cpu().numpy()
                    bodies.append({"bbox": bbox([x1, y1, x2-x1, y2-y1], width, height),
                                   "confidence": finite_or_none(float(row.conf[0])), "source": "yolo"})
                self.calls["yolo_successful_calls"] += 1
            except Exception as exc:
                self.body_backend_report.update(fallback_reason="yolo_inference_failed",
                                                exception_type=type(exc).__name__)
                self.yolo = None
                bodies = []
                self._activate_hog()
                if width >= 64 and height >= 128:
                    bodies.extend(self._hog_boxes(frame, width, height))
        elif self.hog and run_body and width >= 64 and height >= 128:
            bodies.extend(hog_future.result() if hog_future else self._hog_boxes(frame, width, height))
        self.phase_seconds['body_detection']+=perf_counter()-body_started
        self.calls["successful_faces"] += len(faces)
        self.calls["frames_without_face"] += int(not faces)
        self.face_history = [{"bbox": face["face_bbox"], "embedding_time": face.get("embedding_time", -math.inf)} for face in faces]
        self.last_shot = shot_id
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
                               "body_detection_source": body.get("source") if body else None,
                               "body_detection_confidence": body.get("confidence") if body else None,
                               "body_hog_score": body.get("hog_score") if body else None,
                               "embedding": f["embedding"], "detection_confidence": f["confidence"],
                               "face_quality": f.get('face_quality'),
                               "embedding_missing_reason": f.get('embedding_missing_reason'),
                               "face_detection_source": f.get('face_detection_source')})
        for i, b in enumerate(bodies):
            if i not in used_bodies:
                detections.append({"bbox": b["bbox"], "bbox_kind": "body", "face_bbox": None,
                                   "face_visible": False, "body_visible": True,
                                   "eyes_position": None, "embedding": None,
                                   "detection_confidence": b["confidence"],
                                   "body_detection_source": b.get("source"),
                                   "body_detection_confidence": b.get("confidence"),
                                   "body_hog_score": b.get("hog_score"),
                                   "embedding_missing_reason": (
                                       'face_detector_unavailable' if face_detector_status == 'unavailable'
                                       else 'face_detector_error' if face_detector_status == 'error'
                                       else "body_only_no_face_detected"),
                                   "face_quality": None})
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
        ctx.logger.info("Visão: backend de corpos inicializado: %s",
                        getattr(detector, "body_backend_report", None))
        detector_counters = getattr(detector, "calls", None)
        detector_calls = detector_counters if isinstance(detector_counters, dict) else defaultdict(int)
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
        short_shot_plan = ShortShotSamplingPlan(scenes,
            enabled=cfg.get("short_shot_extra_sampling", True),
            max_seconds=cfg.get("short_shot_max_seconds", 1.5),
            start_time=float(resumed["end"]) if resumed else 0.)
        boundary_plan = ShotBoundarySamplingPlan(scenes,
            enabled=cfg.get('boundary_extra_sampling', False),
            short_max_seconds=cfg.get('short_shot_max_seconds', 1.5),
            inset_seconds=cfg.get('boundary_inset_seconds', .12),
            start_time=float(resumed['end']) if resumed else 0.)
        if resumed:
            scheduler.burst_until=float(resumed.get('sampling_state',{}).get('burst_until',0))
            scheduler.last_speaker=resumed.get('sampling_state',{}).get('last_speaker')
            scheduler.last_visible_count=resumed.get('sampling_state',{}).get('last_visible_count')
            scheduler.last_missing_lip_burst=float(resumed.get('sampling_state',{}).get('last_missing_lip_burst',-10))
        last_log, thumb_scenes = -60.0, {t.get("scene_id") for t in frames if t.get("scene_id")}
        last_progress = -3.
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
                short_shot_due = short_shot_plan.due(time)
                boundary_due = boundary_plan.due(time)
                if time+1/fps < next_sample and not short_shot_due and not boundary_due:
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
                           "short_shot_scheduled": bool(short_shot_due),
                           "boundary_scheduled": bool(boundary_due),
                           "brightness": finite_or_none(float(gray.mean()/255)),
                           "blur_laplacian_variance": finite_or_none(float(cv2.Laplacian(gray, cv2.CV_64F).var())),
                           "camera_motion_proxy": motion, "source_camera_motion": source_camera_motion,
                           "boundary_difference": boundary_difference if change else None,
                           "possible_black_frame": bool(gray.mean() < 5),
                           "possible_freeze_frame": bool(motion is not None and motion < 0.0005),
                           "visible_people": []}
                timings['motion_estimation']+=perf_counter()-motion_started
                phase_started=perf_counter()
                if hasattr(detector, "set_frame_context"):
                    scene_duration = scenes[scene_index]["end"] - scenes[scene_index]["start"] if scenes else None
                    detector.set_frame_context(time, scene_id, scene_duration)
                detections = detector.detect(frame)
                quality['face_detector_status'] = getattr(detector, 'last_face_detector_status', None)
                checkpoint_backend['body'] = "yolo" if detector.yolo is not None else "hog" if detector.hog is not None else None
                if hasattr(detector, "backend_execution"):
                    quality["body_backend_execution"] = detector.backend_execution()
                timings['face_body_embedding_detection']+=perf_counter()-phase_started
                phase_started=perf_counter()
                current = tracker.update(detections, time, scene_id)
                if boundary_due:
                    quality['boundary_face_observed'] = any(d.get('face_visible') for d in current)
                    quality['boundary_fresh_embedding_observed'] = any(
                        d.get('face_embedding_observed') for d in current)
                if short_shot_due:
                    quality['short_shot_face_observed'] = any(d.get('face_visible') for d in current)
                    quality['short_shot_fresh_embedding_observed'] = any(
                        d.get('face_embedding_observed') for d in current)
                timings['tracker_association']+=perf_counter()-phase_started
                phase_started=perf_counter()
                mouth = lips.detect(frame) if lips else []
                detector_calls["landmark_calls"] += int(lips is not None)
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
                           "person_detection_kind": ('FACE_BODY_PERSON' if obs['face_visible'] and obs['body_visible'] else
                                                     'FACE_ONLY_PERSON' if obs['face_visible'] else 'BODY_ONLY_PERSON'),
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
                quality["short_shot_scheduled"] = bool(short_shot_due)
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
                    ctx.check_cancel('07_people_tracking')
                if time - last_progress >= 3:
                    ctx.progress('07_people_tracking', current=time, total=metadata['duration'], unit='video_seconds', substage='visual_detection_and_tracking')
                    last_progress = time
                if time-last_log >= 60:
                    ctx.logger.info("Visão: %.1f / %.1fs; %s raw_person_hypotheses; %s raw_tracklets",
                                    time, metadata["duration"], len(people), tracker.next_track_id - 1)
                    last_log = time
        finally:
            cap.release()
            if hasattr(detector, "close"):
                detector.close()
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
        backend_execution = detector.backend_execution() if hasattr(detector, "backend_execution") else None
        ctx.logger.info("Visão: execução de backend de corpos: %s", backend_execution)
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
                                   'boundary_scheduled_frames':sum(bool(frame.get('boundary_scheduled')) for frame in frames),
                                   'boundary_scheduled_frames_with_face':sum(bool(frame.get('boundary_face_observed')) for frame in frames),
                                   'boundary_scheduled_frames_with_embedding':sum(bool(frame.get('boundary_fresh_embedding_observed')) for frame in frames),
                                   'face_detection_backend': 'haar' if isinstance(getattr(detector, 'face', None), cv2.CascadeClassifier) else 'yunet_or_test_backend',
                                   'body_detection_backend': (backend_execution['executed_backends'][0]
                                       if backend_execution and len(backend_execution['executed_backends']) == 1
                                       else 'mixed' if backend_execution and backend_execution['executed_backends']
                                       else None),
                                   'body_backend_execution': backend_execution,
                                   'short_shot_scheduled_frames':sum(bool(frame.get('short_shot_scheduled')) for frame in frames),
                                   'short_shot_scheduled_frames_with_face':sum(bool(frame.get('short_shot_face_observed')) for frame in frames),
                                   'short_shot_scheduled_frames_with_fresh_embedding':sum(bool(frame.get('short_shot_fresh_embedding_observed')) for frame in frames),
                                   'short_shot_embedding_attempts':detector_calls.get('short_shot_embedding_attempts', 0),
                                   **dict(detector_calls), 'candidate_tracks':tracker.next_track_id - 1,
                                   'association_count':tracker.association_count,
                                   'embedding_success_ratio':detector_calls['successful_embeddings']/detector_calls['embedding_calls'] if detector_calls['embedding_calls'] else None,
                                   'useful_detection_ratio':sum(bool(frame['visible_people']) for frame in frames)/len(frames),
                                   'frames_per_second':len(frames)/max(perf_counter()-stage_started,1e-9),
                                   'call_rates':{name:{'calls_per_second':count/max(perf_counter()-stage_started,1e-9),
                                       'ms_per_call':({**dict(timings),**dict(getattr(detector,'phase_seconds',{}))}).get(
                                           {'embedding_calls':'face_embedding','landmark_calls':'landmark_inference'}.get(name,name.removesuffix('_calls')),0)*1000/count if count else None}
                                       for name,count in detector_calls.items() if name.endswith('_calls')},
                                   'cpu_hog_overlap': dict(getattr(detector, 'overlap_budget', {})),
                                   'cpu_hog_overlap_enabled': bool(getattr(detector, '_hog_pool', None) or
                                           getattr(detector, 'overlap_budget', {}).get('enabled')),
                                   'gpu_time_seconds':None,'gpu_time_reason':'not_instrumented',
                                   'phase_accounting':'detector_subphases_partition_combined_detection; do_not_sum_both'},
                  "quality": {"body_detection": backend_execution,
                               "sample_count": len(frames), "actual_width": width, "actual_height": height,
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
        evidence_cfg = ctx.config.get("active_speaker", {})
        with sf.SoundFile(audio["mono"]) as f:
            windows = []
            turns = diarization.get("turns", [])
            boundaries = {row[key] for row in vision.get("scene_intervals", []) for key in ("start", "end")}
            previous_scene = None
            for frame in vision.get("frames", []):
                if frame.get("scene_id") != previous_scene:
                    boundaries.add(frame["time"])
                    previous_scene = frame.get("scene_id")
            overlap_rows = diarization.get("overlaps", [])
            boundaries.update(row[key] for row in overlap_rows for key in ("start", "end"))
            for turn_index, turn in enumerate(turns):
                cuts = sorted({turn["start"], turn["end"]} | {boundary for boundary in boundaries if turn["start"] < boundary < turn["end"]})
                for left, right in zip(cuts, cuts[1:]):
                    start = left
                    while start < right:
                        end = min(right, start + evidence_cfg.get("evidence_window_seconds", 3.))
                        simultaneous = any(other is not turn and other.get("speaker") != turn.get("speaker") and
                                           overlap(start, end, other["start"], other["end"]) > 0 for other in turns)
                        windows.append({**turn, "start": start, "end": end, "overlap": simultaneous,
                                        "turn_id": turn.get("turn_id") or f"TURN_{turn_index:06}",
                                        "evidence_window_id": f"ASD_WINDOW_{len(windows):06}"})
                        start = end
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
                screening = defaultdict(int)
                if not turn.get("overlap") and end-start >= evidence_cfg.get("min_audio_window_seconds", 1.5):
                    audio_start = max(0, start - .16)
                    f.seek(max(0, round(audio_start * rate)))
                    window_audio = f.read(max(1, round((end - audio_start + .16) * rate)), dtype="float32")
                    for pid, rows in tracks.items():
                        screening['mouth_tracks_examined'] += 1
                        times = track_times[pid]
                        selected = rows[bisect.bisect_left(times, start):bisect.bisect_left(times, end)]
                        if len(selected) < evidence_cfg.get("min_evidence_samples", 8):
                            screening['insufficient_mouth_samples'] += 1
                            continue
                        if selected[-1]["time"]-selected[0]["time"] < (end-start)*0.7:
                            screening['insufficient_visual_duration'] += 1
                            continue
                        if len({r["scene_id"] for r in selected}) > 1:
                            screening['shot_change_inside_evidence'] += 1
                            continue
                        from .speaker_signals import mouth_audio_evidence
                        signal = mouth_audio_evidence(selected, window_audio, rate, audio_start)
                        if signal:
                            screening['candidates_emitted'] += 1
                            candidates.append({"person_id": pid, **signal,
                                               "visibility_coverage": (selected[-1]["time"] - selected[0]["time"]) / (end - start),
                                               "track_stability": 1 / max(1, len({row.get('track_id') for row in selected})),
                                               "source_shot_id": selected[0].get("scene_id"),
                                               "mouth_activity_mean": float(np.mean([r.get("mouth_activity") or 0 for r in selected])),
                                               "face_visibility": sum(bool(r.get('face_visible')) for r in selected) / len(selected),
                                               "embedding_continuity": sum(bool(r.get('face_embedding_available')) for r in selected) / len(selected)})
                        else:
                            screening['no_reliable_mouth_audio_signal'] += 1
                elif turn.get('overlap'):
                    screening['simultaneous_audio_skipped'] += 1
                else:
                    screening['audio_window_below_minimum'] += 1
                candidates.sort(key=lambda c: c["correlation"], reverse=True)
                chosen = None
                if candidates and candidates[0]["correlation"] >= cfg["association_min_correlation"] and candidates[0]["correlation_lower_bound_proxy"] > 0:
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
                                 "evidence_window_id": turn["evidence_window_id"], "turn_id": turn["turn_id"],
                                 "overlap": turn.get("overlap", False),
                                 "speaker_id": speaker, "visible_person": chosen, "person_id": chosen,
                                 "association_confidence": confidence, "confidence": confidence,
                                 "association_evidence_score": top_score,
                                 "candidate_screening": dict(screening),
                                 "candidates": candidates, "method": "lip_audio_correlation" if chosen else "unresolved",
                                 "evidence": (["diarization", "mouth_activity", "face_visible"] if chosen else
                                              (["diarization"] if speaker else [])),
                                 "inference": chosen is not None,
                                 "needs_review": True})
        notes.append("Correlação boca/áudio é heurística, não um modelo ASD calibrado. "
                     "Um rosto sozinho ou centralizado não basta; associação incerta fica null.")
        return ok({"mappings": mappings}, "partial" if not any(row.get("person_id") for row in mappings) else "ok", notes)
