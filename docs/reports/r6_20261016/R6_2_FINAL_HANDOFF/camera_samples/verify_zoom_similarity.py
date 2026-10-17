"""Uniform-scale evidence from the six-second real Curator zoom render."""
from __future__ import annotations
import math

import cv2
import numpy as np

from build_real_previews import HERE, sha256, write_json
from verify_real_previews import image_bytes


def measure(source, final):
    sift = cv2.SIFT_create(nfeatures=6000, contrastThreshold=.02)
    ka, da = sift.detectAndCompute(cv2.cvtColor(source, cv2.COLOR_BGR2GRAY), None)
    kb, db = sift.detectAndCompute(cv2.cvtColor(final, cv2.COLOR_BGR2GRAY), None)
    if da is None or db is None:
        return {"status": "ABSTAIN", "reason": "INSUFFICIENT_FEATURES"}
    good = [a for pair in cv2.BFMatcher().knnMatch(da, db, k=2) if len(pair) == 2
            for a, b in [pair] if a.distance < .68*b.distance]
    if len(good) < 20:
        return {"status": "ABSTAIN", "reason": "INSUFFICIENT_MATCHES"}
    pa = np.float32([ka[m.queryIdx].pt for m in good])
    pb = np.float32([kb[m.trainIdx].pt for m in good])
    matrix, mask = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC,
        ransacReprojThreshold=2., maxIters=5000, confidence=.995, refineIters=50)
    if matrix is None:
        return {"status": "ABSTAIN", "reason": "NO_SIMILARITY"}
    keep = mask.ravel().astype(bool)
    error = np.linalg.norm(cv2.transform(pa.reshape(-1, 1, 2), matrix).reshape(-1, 2)-pb, axis=1)[keep]
    scale = float(np.hypot(matrix[0, 0], matrix[1, 0]))
    rotation = float(math.atan2(matrix[1, 0], matrix[0, 0]))
    median_error = float(np.median(error))
    stable = int(keep.sum()) >= 20 and median_error < 1.5 and abs(rotation) < .02
    return {"status": "MEASURED" if stable else "ABSTAIN", "ratio_matches": len(good),
        "inliers": int(keep.sum()), "inlier_ratio": float(keep.mean()), "scale": scale,
        "rotation_radians": rotation, "median_reprojection_error_px": median_error,
        "source_to_final_similarity": matrix.tolist(),
        "reason": None if stable else "WEAK_OR_INCONSISTENT_SIMILARITY"}


if __name__ == "__main__":
    folder = HERE / "06_isolated_replanned/engine_r62_compat"
    times = [0, 1, 2, 3, 4, 5, 6-1/24]
    samples = []
    for i, time in enumerate(times):
        a, b = folder / f"source_{i:02}.png", folder / f"final_{i:02}.png"
        samples.append({"clip_time_s": time, "source_requested_time_s": 1601.792+time,
                        "source_frame": a.name, "source_sha256": sha256(a),
                        "final_frame": b.name, "final_sha256": sha256(b),
                        "measurement": measure(image_bytes(a), image_bytes(b))})
    valid = [s["measurement"] for s in samples if s["measurement"]["status"] == "MEASURED"]
    blank = np.zeros((180, 320, 3), np.uint8)
    report = {"schema_version": "1.0", "mp4_sha256": sha256(folder / "TECHNICAL_PREVIEW.mp4"),
        "method": "SIFT ratio .68, RANSAC partial affine (uniform scale + rotation + translation)",
        "method_rationale": "Installed Curator applies axis-uniform scale/crop; unconstrained homography can overfit face/hand motion.",
        "sparse_samples": samples, "negative_control": measure(blank, blank),
        "all_samples_measured": len(valid) == len(samples),
        "scale_strictly_monotonic": all(b["scale"] > a["scale"] for a, b in zip(valid, valid[1:])),
        "relative_scale_increase": valid[-1]["scale"]/valid[0]["scale"]-1 if len(valid) >= 2 else None,
        "FFmpeg_transform_observed": len(valid) >= 6 and valid[-1]["scale"]/valid[0]["scale"] > 1.01,
        "homography_cross_check": "Six of seven MEASURED; final homography ABSTAIN is retained in frame_transform_verification.json",
        "visual_acceptance": "REJECTED_HAND_GESTURE_EXITS_PORTRAIT_CROP",
        "delivered": False, "preview_approved": False, "publish_ready": False,
        "limits": "Sparse measurements verify a digital transformation; they do not certify full body, gesture safety, exact original PTS, captions or editorial approval."}
    write_json(folder / "zoom_similarity_verification.json", report)
    print({k: report[k] for k in ("all_samples_measured", "scale_strictly_monotonic", "relative_scale_increase", "FFmpeg_transform_observed", "visual_acceptance")})
