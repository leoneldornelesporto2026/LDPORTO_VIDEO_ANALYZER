from collections import defaultdict
import math
import statistics
from .core import ok


def _mean(values):
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return sum(values)/len(values) if values else None


def _median(values):
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return statistics.median(values) if values else None


def _combine(*values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals)/len(vals) if vals else None


def classify_shot(frames, observations):
    if not frames:
        return "unknown"
    counts = [len(f.get("visible_people") or []) for f in frames]
    max_people = max(counts, default=0)
    if max_people >= 3:
        return "group"
    if max_people == 2:
        return "two_shot"
    if max_people == 1:
        heights = [o.get("face_height") for o in observations if o.get('face_visible') and o.get("face_height") is not None]
        h = _median(heights)
        if h is None:
            return "unknown"
        if h >= 0.42:
            return "close_up"
        if h >= 0.28:
            return "medium_close_up"
        if h >= 0.12:
            return "medium"
        return "wide"
    if all(f.get("possible_black_frame") for f in frames):
        return "empty"
    return "unknown"


def build_shots(scenes, vision, metadata, cfg):
    """Turn visual boundaries into camera-shot records without redefining semantic scenes."""
    frames_by_scene, obs_by_scene = defaultdict(list), defaultdict(list)
    for frame in vision.get("frames", []):
        frames_by_scene[frame.get("scene_id")].append(frame)
    for obs in vision.get("observations", []):
        obs_by_scene[obs.get("scene_id")].append(obs)

    sharp_values = [f.get("blur_laplacian_variance") for f in vision.get("frames", [])
                    if isinstance(f.get("blur_laplacian_variance"), (int, float))]
    sharp_ref = statistics.median(sharp_values) if sharp_values else 100.0
    shots = []
    last_seen = {}
    for index, scene in enumerate(scenes):
        # A scene ID alone must not admit stale samples or a frame on the next cut.
        frames = sorted((f for f in frames_by_scene.get(scene.get("scene_id"), [])
                         if scene['start'] <= f['time'] < scene['end']), key=lambda f: f['time'])
        frame_times = {f['time'] for f in frames}
        obs = [o for o in obs_by_scene.get(scene.get("scene_id"), [])
               if o.get('time') in frame_times]
        visible = sorted({p for f in frames for p in f.get('visible_people', []) if p})
        sole = {tuple(sorted(f.get('visible_people') or [])) for f in frames}
        primary = visible[0] if len(visible) == 1 and sole == {(visible[0],)} else None
        reactions = sorted({o['person_id'] for o in obs if o.get('person_id') in visible
                            and o.get('reaction_detected') is True
                            and o.get('reaction_type') in {'laugh', 'laughing', 'smile', 'smiling',
                                'surprise', 'surprised', 'applause', 'clapping', 'nod', 'nodding'}})
        tv_cut = scene.get('tv_cut_verified') is True
        role = 'tv_cut' if tv_cut else 'reaction' if reactions else 'main_person' if primary else 'unknown'
        inset = min(.15, (scene['end']-scene['start'])/4)
        sampling = {'first_sample_at': frames[0]['time'] if frames else None,
                    'last_sample_at': frames[-1]['time'] if frames else None,
                    'start_observed': bool(frames and frames[0]['time'] <= scene['start']+inset),
                    'end_observed': bool(frames and frames[-1]['time'] >= scene['end']-inset),
                    'method': 'existing_samples_only'}
        shot_id = f"SHOT_{index:05}"
        links = [{'person_id': p, 'previous_observed_shot_id': last_seen.get(p),
                  'track_ids': sorted({o['track_id'] for o in obs if o.get('person_id') == p and o.get('track_id')}),
                  'method': 'upstream_person_id', 'geometry_continuity': False} for p in visible]
        first_frame = frames[0] if frames else None
        boundary_diff = first_frame.get("boundary_difference") if first_frame else None
        hard_threshold = float(cfg.get("hard_cut_difference", 0.18))
        transition_in = None if index == 0 else ("hard_cut" if isinstance(boundary_diff, (int, float)) and boundary_diff >= hard_threshold else "unknown")
        transition_conf = None
        if transition_in == "hard_cut":
            transition_conf = min(1.0, max(0.0, (boundary_diff-hard_threshold)/max(1e-9, 0.6-hard_threshold)))

        face_obs = [o for o in obs if o.get("face_visible")]
        face_visibility = len(face_obs)/len(obs) if obs else None
        face_sizes = [o.get("face_height") for o in face_obs if o.get("face_height") is not None]
        subject_size = min(1.0, (_median(face_sizes) or 0.0)/0.45) if face_sizes else None
        raw_sharp = _median([f.get("blur_laplacian_variance") for f in frames])
        sharpness = min(1.0, raw_sharp/max(sharp_ref*1.8, 1e-9)) if raw_sharp is not None else None
        crop = _mean([1.0 if o.get("safe_crop_possible") else 0.0 for o in obs]) if obs else None
        headroom_values, composition_values = [], []
        for o in face_obs:
            face = o.get("face_bbox")
            if not face:
                continue
            headroom_values.append(max(0.0, 1.0-min(1.0, abs(face["y"]-0.08)/0.28)))
            cx = face["x"]+face["width"]/2
            thirds_distance = min(abs(cx-1/3), abs(cx-2/3))
            composition_values.append(max(0.0, 1.0-thirds_distance/(1/3)))
        headroom = _mean(headroom_values)
        composition = _mean(composition_values)
        thumbnail_score = _combine(sharpness, face_visibility, subject_size, composition)
        camera_score = _combine(sharpness, face_visibility, subject_size, headroom, composition, crop)
        shots.append({
            "shot_id": shot_id,
            "scene_id": scene.get("scene_id"),
            "start": float(scene["start"]), "end": float(scene["end"]),
            "duration": float(scene["end"]-scene["start"]),
            "transition_in": transition_in,
            "transition_out": None,
            "transition_confidence": transition_conf,
            "transition_method": "scenedetect_boundary_plus_sampled_frame_difference",
            "shot_type": classify_shot(frames, obs),
            "shot_type_confidence": None,
            "shot_role": role, "primary_visual_person": None if tv_cut else primary,
            "reaction_people": reactions, "tv_cut_verified": True if tv_cut else None,
            "sampling_coverage": sampling, "participant_links": links,
            "crop_continuity": "reset_at_source_boundary",
            "visible_people": sorted({o.get("person_id") for o in obs if o.get("person_id")}),
            "face_visibility_score": face_visibility,
            "subject_size_score": subject_size,
            "sharpness_score": sharpness,
            "motion_blur_score": None,
            "headroom_score": headroom,
            "composition_score": composition,
            "vertical_crop_score": crop,
            "thumbnail_score": thumbnail_score,
            "camera_score": camera_score,
            "sample_count": len(frames),
            "method": "visual_boundary_with_sampled_geometry",
            "inference": True,
        })
        for person in visible:
            last_seen[person] = shot_id
    for i in range(len(shots)-1):
        shots[i]["transition_out"] = shots[i+1]["transition_in"]
    notes = [
        "Shot e scene permanecem conceitos separados: shots usam limites visuais; topics/story arcs continuam semânticos.",
        "Dissolve/fade só são rotulados quando houver evidência dedicada; caso contrário transition=unknown em vez de inventar.",
    ]
    # Generated by GitHub Copilot - Oct-05-2026
    durations=[shot['duration'] for shot in shots]
    metrics={'visual_boundary_count':max(0,len(scenes)-1),'shot_count':len(shots),
             'scene_shot_same_boundary_fraction':sum((shot['start'],shot['end'])==(scene['start'],scene['end']) for shot,scene in zip(shots,scenes))/len(shots) if shots else None,
             'hard_cut_count':sum(shot['transition_in']=='hard_cut' for shot in shots),
             'unknown_transition_count':sum(shot['transition_in']=='unknown' for shot in shots),
             'shot_duration_p50':statistics.median(durations) if durations else None,
             'shot_duration_min':min(durations) if durations else None,'shot_duration_max':max(durations) if durations else None,
             'suspicious_micro_shot_count':sum(duration<.6 for duration in durations),
             'long_static_shot_count':'not_measured','shared_boundary_method':'scenedetect_visual_boundaries_shared_not_independent_segmentation'}
    return ok({"shots": shots,'metrics':metrics}, "ok" if shots else "partial", notes)
