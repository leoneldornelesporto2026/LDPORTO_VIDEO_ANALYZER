"""Measure source-to-MP4 geometry; lack of visual features is an abstention."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

from build_real_previews import CASES, HERE, SOURCE, SOURCE_SHA256, probe, sha256, write_json


def image_bytes(path):
    value = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if value is None:
        raise ValueError("Unreadable image: " + str(path))
    return value


def measure_transform(source, final, *, foreground_only=False):
    """Feature evidence uses the pixels, never a commanded zoom value."""
    roi_y = 0
    if foreground_only:
        fg_h = round(final.shape[1] * source.shape[0] / source.shape[1])
        roi_y = (final.shape[0]-fg_h)//2
        final = final[roi_y:roi_y+fg_h]
    sift = cv2.SIFT_create(nfeatures=4000, contrastThreshold=.02)
    ka, da = sift.detectAndCompute(cv2.cvtColor(source, cv2.COLOR_BGR2GRAY), None)
    kb, db = sift.detectAndCompute(cv2.cvtColor(final, cv2.COLOR_BGR2GRAY), None)
    base = {"source_features": len(ka), "final_features": len(kb), "foreground_y": roi_y,
            "method": "SIFT ratio .72 + RANSAC homography, 2 px threshold"}
    if da is None or db is None:
        return {**base, "status": "ABSTAIN", "reason": "INSUFFICIENT_FEATURES"}
    pairs = cv2.BFMatcher().knnMatch(da, db, k=2)
    matches = [a for pair in pairs if len(pair) == 2 for a, b in [pair] if a.distance < .72*b.distance]
    base["ratio_matches"] = len(matches)
    if len(matches) < 20:
        return {**base, "status": "ABSTAIN", "reason": "INSUFFICIENT_MATCHES"}
    pa = np.float32([ka[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    pb = np.float32([kb[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    homography, mask = cv2.findHomography(pa, pb, cv2.RANSAC, 2.)
    if homography is None:
        return {**base, "status": "ABSTAIN", "reason": "NO_HOMOGRAPHY"}
    keep = mask.ravel().astype(bool)
    inliers = int(keep.sum())
    error = np.linalg.norm(cv2.perspectiveTransform(pa, homography)-pb, axis=2).ravel()[keep]
    sx = float(np.linalg.norm(homography[:2, 0]))
    sy = float(np.linalg.norm(homography[:2, 1]))
    med = float(np.median(error)) if len(error) else None
    stable = inliers >= 20 and med is not None and med < 1.5 and abs(sx/sy-1) < .02
    return {**base, "status": "MEASURED" if stable else "ABSTAIN",
            "reason": None if stable else "WEAK_OR_NONUNIFORM_TRANSFORM", "inliers": inliers,
            "inlier_ratio": float(keep.mean()), "scale_x": sx, "scale_y": sy,
            "median_reprojection_error_px": med,
            "homography_source_to_foreground": homography.tolist()}


def frame(path, timestamp, destination):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-ss", str(timestamp),
               "-i", str(path), "-frames:v", "1", "-threads", "2", str(destination)]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])
    return command


def verify_case(name, start, end, revision="engine_r62", *, foreground_only=True, sample_times=None):
    folder = HERE / name / revision
    output = folder / "TECHNICAL_PREVIEW.mp4"
    records, commands = [], []
    duration = end-start
    for i, time in enumerate(sample_times or [0., duration/2, duration-1/24]):
        source_path = folder / f"source_{i:02}.png"
        final_path = folder / f"final_{i:02}.png"
        commands.append(frame(SOURCE, start+time, source_path))
        commands.append(frame(output, time, final_path))
        source = image_bytes(source_path)
        final = image_bytes(final_path)
        result = measure_transform(source, final, foreground_only=foreground_only)
        records.append({"clip_time_s": time, "source_time_s": start+time,
                        "source_frame_index": round((start+time)*24),
                        "source_frame_index_basis": "nominal 24 fps; exact original PTS not certified",
                        "source_frame": source_path.name, "source_frame_sha256": sha256(source_path),
                        "final_frame": final_path.name, "final_frame_sha256": sha256(final_path),
                        "transform": result})
        # Centered portrait is an explicitly rejected proposal, not an observation.
        cw = round(source.shape[0]*9/16)
        x = (source.shape[1]-cw)//2
        proposed = source[:, x:x+cw]
        proposed_path = folder / f"rejected_center_crop_{i:02}.png"
        ok, encoded = cv2.imencode(".png", proposed)
        if not ok:
            raise ValueError("Could not encode proposed crop")
        encoded.tofile(str(proposed_path))
        canvas = Image.new("RGB", (1440, 820), "#191d25")
        draw = ImageDraw.Draw(canvas)
        draw.text((20, 15), f"{name} | source {start+time:.6f}s | clip {time:.6f}s", fill="white")
        draw.text((20, 46), "REAL SOURCE / original pixels", fill="white")
        source_pil = Image.open(source_path); source_pil.thumbnail((720, 700))
        canvas.paste(source_pil, (20, 85))
        crop_label = "REJECTED center portrait proposal" if foreground_only else "CENTER REFERENCE / not consumed plan"
        draw.text((760, 46), crop_label, fill="#ffb0a8")
        proposed_pil = Image.open(proposed_path); proposed_pil.thumbnail((300, 700))
        canvas.paste(proposed_pil, (760, 85))
        draw.text((1090, 46), "REAL MP4 / no approval", fill="#a4e1bc")
        final_pil = Image.open(final_path); final_pil.thumbnail((300, 700))
        canvas.paste(final_pil, (1090, 85))
        canvas.save(folder / f"comparison_{i:02}.jpg", quality=92)
    blank = np.zeros((180, 320, 3), np.uint8)
    abstention = measure_transform(blank, blank)
    write_json(folder / "frame_transform_verification.json", {
        "schema_version": "1.0", "source_sha256": SOURCE_SHA256, "mp4_sha256": sha256(output),
        "samples": records, "flat_frame_negative_control": abstention,
        "caption_overlay_safety": "UNVERIFIED: no subtitles/titles were rendered",
        "preview_approved": False, "publish_ready": False,
        "limits": "Sparse frame matches verify geometry only; they do not certify full-clip identity, hands, instrument or editorial approval."})
    write_json(folder / "frame_capture_commands.json", commands)
    print("verified", name, [r["transform"]["status"] for r in records], flush=True)
    return records


if __name__ == "__main__":
    for case in CASES:
        verify_case(*case)
