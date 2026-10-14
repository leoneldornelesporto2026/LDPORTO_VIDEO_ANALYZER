"""Additive quality explanations; never change eligibility or measured evidence."""
from copy import deepcopy


ISSUE_STAGES = {
    'diarization_unavailable': '05_diarization',
    'visual_tracking_unavailable': '07_people_tracking',
    'understanding_unavailable': '16_understanding',
    'active_speaker_unavailable': '10_active_speaker',
    'fragmented_tracking': '07_people_tracking',
    'participant_explosion': '16_understanding',
    'qa_unresolved': '16_understanding',
    'semantic_fallbacks': '15_semantic',
    'global_review_unavailable': '15_semantic',
    'unresolved_camera_focus': '19_camera_director',
    'preview_skipped': '19b_preview_verifier',
    'cross_file_references_unresolved': '20_handoff',
    'primary_theme_unresolved': '16_understanding',
    'social_output_blocked': '21_second_curation_handoff',
}


def body_limitation_category(body):
    reason, diagnostic = body.get('fallback_reason'), body.get('diagnostic_reason')
    if reason == 'yolo_local_model_missing' or diagnostic in {'model_file_missing', 'dependency_missing'}:
        return 'dependency_unavailable'
    if reason in {'hog_configured', 'body_detection_disabled'}:
        return 'configuration'
    if body.get('exception_type') == 'OutOfMemoryError' or diagnostic in {'insufficient_vram', 'cuda_unavailable'}:
        return 'resource_unavailable'
    if diagnostic == 'model_file_invalid':
        return 'asset_invalid'
    if diagnostic in {'model_load_error', 'inference_error', 'inference_timeout'} or reason == 'yolo_inference_failed':
        return 'runtime_failure'
    return 'fallback_cause_unknown'


def quality_causal_diagnostics(analysis, issues):
    """Separate independent bottlenecks from the legacy first-partial-stage field."""
    manifest = analysis.get('run_manifest') or {}
    states = analysis.get('stage_status') or manifest.get('stage_status') or {}
    quality = analysis.get('analysis_quality') or {}
    roots = []
    for issue in issues:
        code = issue['code']
        stage = ISSUE_STAGES.get(code)
        state = states.get(stage) or {}
        category = ('availability_cause_unknown' if state.get('status') == 'unavailable' else
                    'technical_error' if state.get('status') == 'failed' else
                    'interrupted' if state.get('status') == 'cancelled' else
                    'blocked_reason_unknown' if state.get('status') == 'blocked' else
                    'not_validated' if code == 'preview_skipped' else 'insufficient_evidence')
        evidence = {'recorded_stage_status': state.get('status'),
                    'recorded_reason_code': state.get('reason_code')}
        if code == 'active_speaker_unavailable':
            summaries = analysis.get('speaker_person_summary') or []
            keys = ('raw_audio_windows', 'candidate_evidence_windows',
                    'independent_affinity_windows', 'qualified_positive_windows')
            # No counters in a legacy summary means unknown, not zero measured windows.
            evidence['speaker_windows'] = [{
                'speaker_id': row.get('speaker_id'),
                **{key: deepcopy(row.get(key)) for key in keys},
                'association_status': row.get('association_status'),
                'audio_video_sync': deepcopy(row.get('audio_video_sync')),
            } for row in summaries]
            evidence['measurement_accounting_available'] = any(
                any(key in row for key in keys) for row in summaries)
            evidence['active_speaker_coverage'] = quality.get('active_speaker_coverage')
        elif code == 'unresolved_camera_focus':
            evidence.update(resolved_focus_coverage=quality.get('resolved_focus_coverage'),
                            source_preservation_fraction=quality.get('source_preservation_fraction'))
            camera_metrics = ((analysis.get('video_understanding') or {}).get('camera_director') or {}).get('metrics') or {}
            evidence['camera_gate_diagnostics'] = deepcopy(quality.get('zoom_gate_diagnostics')
                if 'zoom_gate_diagnostics' in quality else camera_metrics.get('zoom_gate_diagnostics'))
        elif code == 'fragmented_tracking':
            evidence['micro_track_ratio'] = quality.get('micro_track_ratio')
        elif code == 'semantic_fallbacks':
            evidence['semantic_fallback_ratio'] = (analysis.get('semantic_metrics') or {}).get('semantic_fallback_ratio')
        roots.append({'stage': stage, 'reason_code': code, 'category': category,
                      'severity': issue.get('severity'), 'evidence': evidence,
                      'evidence_scope': 'recorded_status_and_observations',
                      'causal_claim': 'component_bottleneck_not_proof_of_a_single_upstream_origin'})
    body = (((analysis.get('video_analysis') or {}).get('quality') or {}).get('body_detection')
            or (analysis.get('vision_performance') or {}).get('body_backend_execution') or {})
    capabilities = []
    if body.get('fallback_reason'):
        capabilities.append({'stage': '07_people_tracking', 'reason_code': body['fallback_reason'],
                             'category': body_limitation_category(body),
                             'executed_backend': body.get('actually_executed_backend'),
                             'effect_on_speaker_person': 'not_independently_established'})
    return {'schema_version': '1.0', 'legacy_root_cause_stage': manifest.get('root_cause_stage'),
            'root_causes': roots, 'capability_limitations': capabilities,
            'interpretation': 'Multiple component bottlenecks; legacy root is the first stage in the run summary.',
            'changes_gate_policy': False, 'real_accuracy_verified': False}
