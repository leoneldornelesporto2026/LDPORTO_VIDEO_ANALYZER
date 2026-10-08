"""Conservative, explainable quality gating of detected faces for SFace Re-ID.

Detection != identity evidence. A visible face may be too small, blurred,
clipped or poorly localized to generate a trustworthy embedding.
"""
import math


def assess_face(frame, box, *, confidence=None, eyes=None, min_pixels=28,
                min_sharpness=18., min_confidence=.74):
    import cv2
    height, width = frame.shape[:2]
    left = max(0, int(box['x'] * width))
    top = max(0, int(box['y'] * height))
    right = min(width, max(left + 1, int((box['x'] + box['width']) * width)))
    bottom = min(height, max(top + 1, int((box['y'] + box['height']) * height)))
    roi = frame[top:bottom, left:right]
    reasons = []
    size = min(right-left, bottom-top)
    if size < min_pixels:
        reasons.append('face_too_small')
    edge = .004
    if left <= edge * width or top <= edge * height or right >= (1-edge)*width or bottom >= (1-edge)*height:
        reasons.append('face_clipped_at_frame_edge')
    if confidence is not None and (not math.isfinite(confidence) or confidence < min_confidence):
        reasons.append('low_detection_confidence')
    sharpness = brightness = None
    if roi.size:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        brightness = float(gray.mean()) / 255.
        if sharpness < min_sharpness:
            reasons.append('face_blurred')
        if brightness < .075 or brightness > .95:
            reasons.append('face_bad_exposure')
    else:
        reasons.append('empty_face_crop')
    if eyes and len(eyes) >= 2:
        # YuNet landmarks occasionally fall outside the detected face in
        # profiles/occlusions. Keep visibility but refuse untrustworthy Re-ID.
        if not all(box['x']-.02 <= eye['x'] <= box['x']+box['width']+.02 and
                   box['y']-.02 <= eye['y'] <= box['y']+box['height']+.02 for eye in eyes[:2]):
            reasons.append('landmarks_outside_face')
        elif abs(eyes[0]['x']-eyes[1]['x']) < .08 * box['width']:
            reasons.append('eye_landmarks_collapsed')
    return {'embedding_eligible': not reasons, 'rejection_reasons': reasons,
            'face_width_px': right-left, 'face_height_px': bottom-top,
            'sharpness': sharpness, 'brightness': brightness,
            'detection_confidence': confidence,
            'quality_method': 'face_size_sharpness_exposure_edge_landmarks_v1'}
