"""Visual target evidence independent of acoustic speaker identity."""
import math


def local_speaker_supported(row):
    """Accept legacy local rows, but never promote an explicit uncertain state."""
    person = row.get('person_id')
    return bool(person and row.get('active_speaker_state') in (None, 'CONFIRMED')
                and ('active_person' not in row or row['active_person'] == person)
                and row.get('contemporary_visual_presence') is not False
                and row.get('offscreen_state') is not True)


def target_contradiction(voices):
    return any(row.get('active_person') is not None and row.get('person_id') is not None
               and row['active_person'] != row['person_id'] for row in voices)


def focus_window_evidence(item, focus, layout, role, reasons, selected):
    """Retain one diagnostic per evaluation window independently of compaction."""
    faces = sorted(p for p, obs in item['obs'].items() if obs.get('face_visible') and obs.get('face_bbox'))
    confirmed = sorted(row['person_id'] for row in item['confident'])
    contradiction = target_contradiction(item['voices']) or len(confirmed) > 1
    if not item['shot'] or item['frame'] is None:
        cause = 'NO_CONTEMPORARY_VISUAL_SAMPLE'
    elif not faces:
        cause = 'NO_VISIBLE_FACE'
    elif contradiction:
        cause = 'CONTRADICTORY_TARGET_EVIDENCE'
    elif item['overlap']:
        cause = 'AUDIO_OVERLAP'
    elif focus and role == 'DOMINANT_FACE':
        cause = 'VISUAL_ONLY_FALLBACK'
    elif focus and role == 'REACTION':
        cause = 'LOCAL_VISUAL_REACTION'
    elif focus:
        cause = 'LOCAL_SPEAKER_FOCUS'
    elif item['shot'].get('shot_type') in {'close_up', 'medium_close_up'} and item['safe']:
        cause = 'SAFE_ORIGINAL_CLOSEUP_PRESERVED'
    elif not confirmed:
        cause = 'NO_CONFIRMED_ACTIVE_SPEAKER'
    elif confirmed[0] not in item['safe']:
        cause = 'CONFIRMED_TARGET_UNSAFE_CROP'
    else:
        cause = 'DIRECTOR_SAFETY_OR_CONTINUITY_GATE'
    resolved = bool(focus or layout == 'split_candidate')
    return {'start': item['start'], 'end': item['end'], 'shot_id': item['shot'].get('shot_id'),
            'decision': selected, 'layout': layout, 'focus_person': focus,
            'camera_evidence_role': role, 'reason_code': cause, 'director_reasons': list(reasons),
            'evidence': {'visual_observed_at': item['frame']['time'] if item['frame'] else None,
                         'visible_faces': faces, 'confirmed_local_people': confirmed,
                         'safe_crop_people': sorted(item['safe']), 'contradiction': contradiction},
            'visual_target_evidence': item.get('visual_target_evidence'),
            'coverage_effect': {'resolved_focus_seconds': item['end']-item['start'] if resolved else 0.,
                                'source_preserve_seconds': item['end']-item['start'] if layout == 'full_frame' else 0.}}


class VisualTargetEvidence:
    def __init__(self):
        self.tracks = {}

    def update(self, observations, time, shot_id, cfg):
        current = {}
        for person, obs in observations.items():
            face = obs.get('face_bbox')
            if not face or not obs.get('face_visible') or not obs.get('track_id'):
                continue
            confidence = float(obs.get('detection_confidence') or 0)
            if confidence < cfg['minimum_target_confidence']:
                continue
            key = (shot_id, obs['track_id'])
            center = (face['x'] + face['width'] / 2, face['y'] + face['height'] / 2)
            prior = self.tracks.get(person)
            if prior is None or prior['key'] != key or time - prior['last'] > cfg['max_observation_gap_seconds'] * 2:
                prior = {'key': key, 'first': time, 'last': time, 'samples': 0, 'center': center, 'max_velocity': 0., 'visible_seconds': 0.}
            dt = time - prior['last']
            if dt > 0:
                prior['max_velocity'] = max(prior['max_velocity'], math.dist(center, prior['center']) / dt)
                prior['samples'] += 1
                prior['visible_seconds'] += min(dt, cfg['max_observation_gap_seconds'])
            prior.update(last=time, center=center)
            current[person] = prior
        self.tracks = current
        faces = sorted(((obs['face_bbox']['width'] * obs['face_bbox']['height'], person)
                        for person, obs in observations.items() if obs.get('face_bbox') and obs.get('face_visible')), reverse=True)
        if not faces:
            return None
        area, person = faces[0]
        margin = (area - faces[1][0]) / area if len(faces) > 1 and area > 0 else 1.
        track = current.get(person)
        if (not track or time - track['first'] < cfg['minimum_face_duration'] or track['samples'] < 3
                or track['visible_seconds'] / max(time - track['first'], 1e-9) < cfg['minimum_face_visibility']
                or margin < cfg['minimum_dominance_margin'] or track['max_velocity'] > cfg['maximum_center_velocity']):
            return None
        return {'person_id': person, 'confidence': float(observations[person]['detection_confidence']),
                'reason': 'DOMINANT_FACE', 'persistence_seconds': time - track['first'],
                'dominance_margin': margin, 'speaker_identity_confirmed': False}


def camera_state(transition, layout, movement, reaction=False, previous_focus=None, focus=None):
    if transition in {'source_cut', 'initial'}:
        return 'SHOT_SWITCH'
    if layout == 'full_frame':
        return 'RETURN_SOURCE' if transition != 'hold' else 'HOLD'
    if reaction:
        return 'REACTION'
    if layout == 'two_shot':
        return 'TWO_SHOT'
    if layout == 'split_candidate':
        return 'SPLIT'
    if transition != 'hold' and focus != previous_focus:
        return 'TARGET_SWITCH'
    return {'slow_push_in': 'ZOOM_IN', 'slow_pull_out': 'ZOOM_OUT', 'pan': 'RECENTER'}.get(movement, 'HOLD')
