from collections import defaultdict
import math
from .core import ok


def _direction(vx, vy, deadzone):
    if abs(vx) <= deadzone and abs(vy) <= deadzone:
        return "stationary"
    horizontal = "right" if vx > deadzone else "left" if vx < -deadzone else ""
    vertical = "down" if vy > deadzone else "up" if vy < -deadzone else ""
    return "_".join(x for x in (vertical, horizontal) if x) or "stationary"


def build_person_motion(vision, cfg):
    """Estimate smoothed normalized motion without converting detector jitter into motion."""
    alpha = float(cfg.get("smoothing_alpha", 0.35))
    deadzone = float(cfg.get("deadzone_per_second", 0.012))
    max_gap = float(cfg.get("max_gap_seconds", 1.5))
    grouped = defaultdict(list)
    for row in vision.get("observations", []):
        if row.get("person_id") and row.get("center"):
            grouped[row["person_id"]].append(row)

    output = []
    for person_id, rows in sorted(grouped.items()):
        rows.sort(key=lambda r: r["time"])
        sx = sy = ss = None
        prev = None
        prev_vx = prev_vy = 0.0
        samples = []
        for row in rows:
            # Repeated frames must not smooth twice or become velocity evidence.
            if prev and row['time'] <= prev['time']:
                continue
            x, y = float(row["center"]["x"]), float(row["center"]["y"])
            area = row.get("face_area") or row.get("percent_frame")
            scale = math.sqrt(max(float(area), 1e-9)) if area is not None else None
            reset_reason = 'first_observation' if prev is None else None
            if prev and (row.get("scene_id") != prev.get("scene_id") or
                         row.get("track_id") != prev.get("track_id") or row["time"]-prev["time"] > max_gap):
                reset_reason = ('source_boundary' if row.get('scene_id') != prev.get('scene_id') else
                                'track_change' if row.get('track_id') != prev.get('track_id') else 'observation_gap')
                sx = sy = ss = prev = None
                prev_vx = prev_vy = 0.0
            sx = x if sx is None else alpha*x + (1-alpha)*sx
            sy = y if sy is None else alpha*y + (1-alpha)*sy
            if scale is not None:
                ss = scale if ss is None else alpha*scale + (1-alpha)*ss
            vx = vy = ax = ay = scale_v = None
            observed_vx = observed_vy = camera_vx = camera_vy = None
            if prev is not None:
                dt = row["time"] - prev["time"]
                if 0 < dt <= max_gap:
                    observed_vx = (sx-prev["sx"])/dt
                    observed_vy = (sy-prev["sy"])/dt
                    source_motion = row.get("source_camera_motion") or {}
                    camera_vx = float(source_motion.get("dx"))/dt if isinstance(source_motion.get("dx"),(int,float)) else 0.0
                    camera_vy = float(source_motion.get("dy"))/dt if isinstance(source_motion.get("dy"),(int,float)) else 0.0
                    vx = observed_vx-camera_vx
                    vy = observed_vy-camera_vy
                    if abs(vx) < deadzone:
                        vx = 0.0
                    if abs(vy) < deadzone:
                        vy = 0.0
                    if prev.get('velocity_measured'):
                        ax = (vx-prev_vx)/dt
                        ay = (vy-prev_vy)/dt
                    if ss is not None and prev["ss"] is not None:
                        scale_v = (ss-prev["ss"])/dt
                        if abs(scale_v) < deadzone:
                            scale_v = 0.0
                    prev_vx, prev_vy = vx, vy
            intensity = None if vx is None else min(1.0, math.hypot(vx, vy) / 0.35)
            samples.append({
                "time": row["time"], "person_id": person_id,
                "track_id": row.get("track_id"),
                "scene_id": row.get("scene_id"),
                "reset_reason": reset_reason,
                "geometry_continuity": prev is not None,
                "face_presence": 'observed' if row.get('face_visible') else 'unknown',
                "camera_compensation_measured": camera_vx is not None and
                    isinstance((row.get('source_camera_motion') or {}).get('dx'), (int, float)) and
                    isinstance((row.get('source_camera_motion') or {}).get('dy'), (int, float)),
                "center_x": sx, "center_y": sy,
                "velocity_x": vx, "velocity_y": vy,
                "residual_velocity_x": vx, "residual_velocity_y": vy,
                "observed_velocity_x": observed_vx,
                "observed_velocity_y": observed_vy,
                "source_camera_velocity_x": camera_vx,
                "source_camera_velocity_y": camera_vy,
                "acceleration_x": ax, "acceleration_y": ay,
                "scale_velocity": scale_v,
                "movement_intensity": intensity,
                "movement_direction": None if vx is None else _direction(vx, vy, deadzone),
                "source": "smoothed_visual_observations",
                "confidence": None,
            })
            prev = {"time": row["time"], "sx": sx, "sy": sy, "ss": ss,
                    "velocity_measured": vx is not None,
                    "scene_id": row.get("scene_id"), "track_id": row.get("track_id")}
        values = [s["movement_intensity"] for s in samples if s["movement_intensity"] is not None]
        output.append({
            "person_id": person_id,
            "sample_count": len(samples),
            "mean_movement_intensity": sum(values)/len(values) if values else None,
            "samples": samples,
        })
    notes = ["Movimento usa centros normalizados suavizados e deadzone; jitter abaixo do limiar não é tratado como deslocamento real.",
             "Quando há evidência de movimento global da câmera fonte, velocity_x/y representa movimento residual do sujeito após compensação."]
    return ok({"people": output}, "ok" if output else "partial", notes)
