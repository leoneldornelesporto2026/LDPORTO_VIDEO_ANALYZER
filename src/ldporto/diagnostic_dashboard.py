"""Compact measured diagnostic dashboard and causal dependency evidence."""
from .perception_diagnostics import tracking_profile


def build_dashboard(analysis):
    quality = analysis.get('analysis_quality', {})
    profile = tracking_profile(analysis.get('people_observations', []), analysis.get('shots', []), analysis['metadata']['duration'])
    return {'schema_version':'4.4.0', 'scope':analysis.get('execution_scope','full_pipeline'),
            'source_sha256':analysis['metadata'].get('sha256'), 'tracking':profile,
            'speaker_diagnostics':analysis.get('speaker_person_diagnostics', []),
            'semantic_chunks':analysis.get('semantic_chunk_profile', []),
            'camera':{k:quality.get(k) for k in ('resolved_focus_coverage','known_speaker_focus_fraction','dominant_face_coverage',
                  'source_preservation_fraction','zoom_event_count','proposed_zoom_event_count','max_zoom_factor')},
            'causal_dependencies':[['tracking','speaker_person'],['speaker_person','active_speaker'],
                  ['active_speaker','speaker_camera'],['visual_fallback','visual_camera'],['semantic','stories'],
                  ['stories','ranking'],['second_curation','curator'],['graphics','safe_composition']],
            'stage_states':analysis.get('stage_status',{}),
            'limits':'Observed coverage and heuristic evidence; calibrated identity/ASR/perceptual accuracy require annotations.'}
