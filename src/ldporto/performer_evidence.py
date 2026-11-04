"""Additive performer review contracts from existing observations only.

No face naming, instrument detection, diarization or tracking runs here. Missing
measurements stay absent and anonymous identities are never civil identities.
"""
from copy import deepcopy
import math

from .core import digest


def _time(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def build_performer_evidence(analysis):
    tracks = deepcopy(analysis.get('raw_tracks') or [])
    mapping = {r.get('track_id') or r.get('tracklet_id'): r.get('person_id') for r in tracks}
    participants = []
    for source in analysis.get('participants') or []:
        row = deepcopy(source)
        confirmation = row.get('identity_confirmation') or {}
        name_confirmed = bool(row.get('person_id') and confirmation.get('method') == 'user_verified'
            and confirmation.get('confirmed_name') and confirmation.get('evidence_refs'))
        # Legacy "confirmed_editorial_participant" describes editorial relevance,
        # not a confirmed face, name or performer role.
        row.update(confirmed_name=confirmation['confirmed_name'] if name_confirmed else None,
            name_confirmation_status='CONFIRMED' if name_confirmed else 'UNCONFIRMED',
            person_association_status='UNRESOLVED' if not row.get('person_id') else 'ANONYMOUS_VISUAL_ASSOCIATION',
            observed_role_status='HYPOTHESIS' if row.get('role') not in (None, 'unknown') else 'UNKNOWN',
            civil_identity_confirmed=name_confirmed,
            identity_confirmation_required=not name_confirmed)
        participants.append(row)
    raw_observations = bool(analysis.get('tracklet_observations'))
    observations = analysis.get('tracklet_observations') or analysis.get('people_observations') or []
    appearances = []
    for index, obs in enumerate(observations):
        if not _time(obs.get('time')):
            continue
        tid = obs.get('track_id') or obs.get('tracklet_id')
        # Never use the raw online identity as a persistent identity if Re-ID
        # explicitly abstained for this track.
        person = mapping[tid] if tid in mapping else obs.get('persistent_person_id')
        appearances.append({'appearance_id': 'APPEARANCE_' + digest([tid, obs['time'], index])[:16],
            'observed_at': obs['time'], 'track_id': tid, 'person_id': person,
            'raw_person_id': obs.get('raw_person_id', obs.get('person_id')),
            'identity_status': 'ANONYMOUS_PERSON' if person else 'UNKNOWN_PERSON',
            'scene_id': obs.get('scene_id'), 'face_bbox': deepcopy(obs.get('face_bbox')),
            'body_bbox': deepcopy(obs.get('bbox')) if obs.get('bbox_kind') == 'body' else None,
            'face_visible': obs.get('face_visible'), 'body_visible': obs.get('body_visible'),
            'confidence': obs.get('detection_confidence'), 'quality': deepcopy(obs.get('face_quality')),
            'sharpness': obs.get('sharpness'), 'safe_crop_possible': obs.get('safe_crop_possible'),
            'source_observation_index': index,
            'source_artifact': 'tracklet_observations.json' if raw_observations else 'people_observations.json',
            'source_artifact_scope': 'original_analysis_not_necessarily_in_review_package',
            'evidence_scope': 'sampled_observation_not_continuous_visibility'})
    instruments, rejected = [], 0
    for obs in analysis.get('instrument_observations') or []:
        # Retain externally supplied observations only with explicit provenance;
        # do not derive guitar, singing or microphone use from metadata/title.
        if (not _time(obs.get('start')) or not _time(obs.get('end')) or obs['end'] <= obs['start']
                or not obs.get('evidence_refs') or not obs.get('source')):
            rejected += 1
            continue
        instruments.append({**deepcopy(obs), 'review_required': True})
    speaker_mapping = []
    for source in analysis.get('speaker_person_summary') or []:
        row = deepcopy(source)
        status = row.get('association_status')
        row['review_state'] = ('CONFLICTING' if 'conflict' in str(row.get('unresolved_reason', '')).lower() else
            'CONFIRMED' if status == 'CONFIRMED' else 'PROBABLE' if status in ('PROVISIONAL', 'PROBABLE') else 'UNRESOLVED')
        speaker_mapping.append(row)
    review = [{'review_id': 'PERFORMER_' + str(p.get('participant_id') or index),
        'participant_id': p.get('participant_id'), 'person_id': p.get('person_id'),
        'speaker_ids': p.get('speaker_ids', []), 'confirmed_name': p.get('confirmed_name'),
        'proposed_name': p.get('possible_name'), 'role_hypothesis': p.get('role'),
        'name_evidence_segment_id': p.get('name_evidence_segment_id'),
        'required_review': ['confirm_person_association', 'verify_name_and_role_sources'],
        'status': 'UNREVIEWED', 'human_confirmation': None, 'auto_merge': False}
        for index, p in enumerate(participants) if p['identity_confirmation_required']]
    return {'schema_version': '1.0', 'participants': participants, 'person_tracks': tracks,
        'person_appearances': appearances, 'instrument_observations': instruments,
        'speaker_person_mapping': speaker_mapping, 'performer_review_queue': review,
        'metrics': {'track_count': len(tracks), 'appearance_count': len(appearances),
            'instrument_observation_count': len(instruments), 'rejected_instrument_observations': rejected,
            'instrument_measurement_status': 'provided_observations_require_review' if instruments else 'NOT_MEASURED',
            'confirmed_civil_identity_count': sum(p['civil_identity_confirmed'] for p in participants)},
        'identity_policy': 'person_id_to_participant_id_to_human_confirmed_name_with_evidence',
        'inference_executed': False, 'review_required': True, 'publish_ready': False}
