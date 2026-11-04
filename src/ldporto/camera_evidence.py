"""Visual target evidence independent of acoustic speaker identity."""
import math
from collections import Counter, deque


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


def candidate_delivery_evidence(proposed, selected, *, focus, layout, pair, requested_person,
                                reasons, suppression_reason, suppression_applied):
    """Compare the scored proposal with the framing that survives all safety gates."""
    def summary(candidate):
        return {'candidate': candidate['candidate'], 'layout': candidate['layout'],
                'focus_person': candidate['focus'], 'people': list(candidate.get('pair', ())),
                'score': candidate['score']}

    delivered_key = (layout, focus, tuple(pair))
    selected_key = (selected['layout'], selected['focus'], tuple(selected.get('pair', ())))
    proposed_key = (proposed['layout'], proposed['focus'], tuple(proposed.get('pair', ())))
    delivered = (summary(selected) if selected_key == delivered_key else
                 {'candidate': 'FULL_FRAME' if layout == 'full_frame' else 'SAFE_FRAMING',
                  'layout': layout, 'focus_person': focus, 'people': list(pair), 'score': None})
    if layout == 'full_frame' and proposed_key != delivered_key:
        outcome = 'REPLACED_BY_SOURCE'
    elif suppression_applied:
        outcome = 'SUPPRESSED'
    elif layout == 'full_frame':
        outcome = 'SOURCE_PRESERVED'
    elif proposed_key == delivered_key:
        outcome = 'ACCEPTED'
    else:
        outcome = 'REPLACED'
    return {'proposed': summary(proposed), 'delivered': delivered, 'outcome': outcome,
            'requested_person': requested_person, 'reason_codes': list(reasons),
            'switch_suppressed': bool(suppression_applied),
            'switch_suppression_reason': suppression_reason if suppression_applied else None,
            'suppression_considered_reason': suppression_reason,
            'score_semantics': 'editorial_heuristic_not_calibrated_probability',
            'execution_scope': 'camera_recommendation_not_rendered_video'}


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
                         'safe_crop_people': sorted(item['safe']), 'contradiction': contradiction,
                         'crop_rejection_reasons': {person: geo.get('reason') for person, geo in
                             item.get('crop_geometry', {}).items() if not geo.get('safe')}},
            'visual_target_evidence': item.get('visual_target_evidence'),
            'target_states': target_state_evidence(item),
            'coverage_effect': {'resolved_focus_seconds': item['end']-item['start'] if resolved else 0.,
                                'source_preserve_seconds': item['end']-item['start'] if layout == 'full_frame' else 0.}}


def target_state_evidence(item):
    """Keep spatial, temporal, acoustic and named-identity evidence independent.

    A face can be a valid visual target without being an identified speaker or
    musician. Missing instrument measurements remain unknown.
    """
    confirmed = {row['person_id'] for row in item['confident']}
    states = {}
    for person, obs in item['obs'].items():
        temporal = (item.get('visual_target_diagnostics') or {}).get(person, {})
        confirmation = obs.get('identity_confirmation') or {}
        name_confirmed = bool(confirmation.get('method') in {'user_verified', 'human_confirmed'}
                              and confirmation.get('confirmed_name') and confirmation.get('evidence_refs'))
        states[person] = {
            'track_id': obs.get('track_id'), 'target_seen': True,
            'face_seen': bool(obs.get('face_visible') and obs.get('face_bbox')),
            'target_stable': temporal.get('target_stable', False),
            'speaker_linked': person in confirmed,
            'instrument_linked': None,
            'instrument_measurement_status': 'UNKNOWN_NO_LINKED_SPATIAL_OBSERVATION',
            'crop_safe': person in item['safe'], 'identity_confirmed': name_confirmed,
            'persistent_identity_status': obs.get('identity_status', 'UNKNOWN'),
            'stability_reason_codes': temporal.get('reason_codes', ['NOT_EVALUATED']),
            'confidence_semantics': 'detector_score_not_calibrated_identity_probability',
        }
    return states


def zoom_gate_diagnostics(records, windows, counts, metadata, metrics):
    """Parallel measured bottlenecks supplement, rather than replace, legacy root cause."""
    funnel = metrics['focus_evidence_funnel']['window_counts']
    geometry_blocks = Counter()
    for row in records:
        geometry_blocks.update({geo.get('reason') for geo in row.get('crop_geometry', {}).values()
                                if not geo.get('safe') and geo.get('reason')})
    causes = []
    for code, kind in [('NO_CONTEMPORARY_VISUAL_SAMPLE', 'missing_data'),
                       ('NO_PERSON_OBSERVATION', 'missing_visual_evidence'),
                       ('NO_VISIBLE_FACE', 'missing_visual_evidence'),
                       ('NO_CONFIRMED_AUDIO_VISUAL_TARGET', 'unresolved_audio_visual_evidence'),
                       ('AUDIO_OVERLAP', 'ambiguous_audio_evidence')]:
        if funnel.get(code):
            causes.append({'code': code, 'type': kind, 'stage': 'target',
                           'window_count': funnel[code], 'denominator': len(records),
                           'counting_scope': 'exclusive_predecision_bucket'})
    for reason, count in sorted(geometry_blocks.items()):
        causes.append({'code': reason, 'type': 'source_limitation' if reason == 'upscale_limit' else 'crop_safety',
                       'stage': 'crop', 'window_count': count, 'denominator': len(records),
                       'counting_scope': 'parallel_observed_geometry_not_qualified_target'})
    if not counts['editorial_beat_raw_windows']:
        causes.append({'code': 'NO_GROUNDED_EDITORIAL_BEAT', 'type': 'editorial_grounding',
                       'stage': 'opportunity', 'window_count': len(records), 'denominator': len(records),
                       'counting_scope': 'parallel_editorial_evaluation'})
    for rank, cause in enumerate(causes, 1):
        cause['rank'] = rank
    return {'schema_version': '1.0', 'legacy_zero_root_cause': metrics['zoom_zero_root_cause'],
            'additional_root_causes': causes,
            'causes_are_parallel_do_not_sum': True,
            'source': {key: metadata.get(key) for key in ('width', 'height', 'fps', 'duration')},
            'stages': {
                'opportunity': {'raw_windows': counts['editorial_beat_raw_windows'],
                                'eligible_windows': counts['editorial_beat_eligible_windows']},
                'target': {'confirmed_crop_eligible_windows': funnel.get('CONFIRMED_TARGET_CROP_ELIGIBLE', 0),
                           'resolved_focus_windows': sum(bool(w['focus_person']) or w['layout'] == 'split_candidate' for w in windows)},
                'crop': {'observed_geometry_block_window_counts': dict(geometry_blocks),
                         'qualified_target_preflight_rejections': counts['crop_preflight_blocked_windows']},
                'proposal': {'requested_windows': counts['smart_zoom_requested_windows'],
                             'proposed_events': metrics['proposed_zoom_event_count']},
                'acceptance': {'accepted_windows': counts['smart_zoom_accepted_windows'],
                               'accepted_events': metrics['zoom_accepted_event_count']},
                'render': {'delivered_events': metrics['zoom_delivered_event_count'],
                           'delivery_verified': metrics['zoom_delivery_verified'],
                           'scope': 'director_recommendation_not_rendered_video'}},
            'window_count_denominator': len(records),
            'publication_approval_inferred': False}


class VisualTargetEvidence:
    def __init__(self):
        self.tracks = {}
        self.diagnostics = {}

    def update(self, observations, time, shot_id, cfg):
        # Keep a bounded history through a transient missing/low-confidence face.
        # The current sample must still satisfy the entrance threshold before it
        # can direct a crop; retained history never extrapolates a missing face.
        current = {person: track for person, track in self.tracks.items()
                   if track['key'][0] == shot_id and 0 <= time-track['last'] <= cfg['max_observation_gap_seconds'] * 2}
        diagnostics = {}
        for person, obs in observations.items():
            face = obs.get('face_bbox')
            reasons = []
            if not face or not obs.get('face_visible') or not obs.get('track_id'):
                diagnostics[person] = {'target_stable': False, 'reason_codes': ['NO_VISIBLE_TRACKED_FACE']}
                continue
            confidence = float(obs.get('detection_confidence') or 0)
            if confidence < cfg['minimum_target_confidence']:
                diagnostics[person] = {'target_stable': False, 'reason_codes': ['DETECTION_CONFIDENCE_BELOW_ENTRANCE']}
                continue
            key = (shot_id, obs['track_id'])
            center = (face['x'] + face['width'] / 2, face['y'] + face['height'] / 2)
            prior = self.tracks.get(person)
            if prior is None or prior['key'] != key or time - prior['last'] > cfg['max_observation_gap_seconds'] * 2:
                prior = {'key': key, 'first': time, 'last': time, 'samples': 0, 'center': center,
                         'velocities': deque(), 'max_velocity': 0., 'visible_seconds': 0.}
            dt = time - prior['last']
            if dt > 0:
                prior['velocities'].append((time, math.dist(center, prior['center']) / dt))
                prior['samples'] += 1
                prior['visible_seconds'] += min(dt, cfg['max_observation_gap_seconds'])
            while prior['velocities'] and prior['velocities'][0][0] < time-cfg['minimum_face_duration']:
                prior['velocities'].popleft()
            prior['max_velocity'] = max((value for _, value in prior['velocities']), default=0.)
            prior.update(last=time, center=center)
            current[person] = prior
            if time-prior['first'] < cfg['minimum_face_duration']:
                reasons.append('INSUFFICIENT_OBSERVED_DURATION')
            if prior['samples'] < 3:
                reasons.append('INSUFFICIENT_DISTINCT_SAMPLES')
            if prior['visible_seconds'] / max(time-prior['first'], 1e-9) < cfg['minimum_face_visibility']:
                reasons.append('INSUFFICIENT_SAMPLED_VISIBILITY')
            if prior['max_velocity'] > cfg['maximum_center_velocity']:
                reasons.append('RECENT_CENTER_VELOCITY_EXCEEDED')
            diagnostics[person] = {'target_stable': not reasons, 'reason_codes': reasons or ['STABLE_OBSERVED_TRACK'],
                                   'persistence_seconds': time-prior['first'],
                                   'recent_max_center_velocity': prior['max_velocity']}
        self.tracks = current
        self.diagnostics = diagnostics
        faces = sorted(((obs['face_bbox']['width'] * obs['face_bbox']['height'], person)
                        for person, obs in observations.items() if obs.get('face_bbox') and obs.get('face_visible')), reverse=True)
        if not faces:
            return None
        area, person = faces[0]
        margin = (area - faces[1][0]) / area if len(faces) > 1 and area > 0 else 1.
        track = current.get(person)
        if margin < cfg['minimum_dominance_margin'] and person in diagnostics:
            diagnostics[person]['reason_codes'] = list(dict.fromkeys(
                diagnostics[person]['reason_codes'] + ['AMBIGUOUS_FACE_DOMINANCE']))
        if (not track or not diagnostics.get(person, {}).get('target_stable')
                or margin < cfg['minimum_dominance_margin']):
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
