"""S2: explicit, evidence-preserving contracts for second-curation readiness.

A successful media analysis is not equivalent to review, preview approval or
publication approval. This module never silently repairs upstream artifacts.
"""

BLOCKING_STATUSES = frozenset({'failed', 'blocked', 'unavailable', 'cancelled'})
MANDATORY_STAGES = ('15_semantic', '16_understanding')
EDITORIAL_DEPENDENCIES = ('17b_broadcast_graphics', '17c_commercial_visual', '17d_targeted_asr', '17e_subtitle_review_s7')
EVIDENCE_DEPENDENCIES = ('04_transcription', '05_diarization', '08_person_reid',
                         '10_active_speaker', '11_shots')


def audit_editorial_contract(analysis):
    """Return bounded, structured reasons without leaking transcripts or secrets."""
    errors = []

    def error(code, path, expected, received):
        errors.append({'code': code, 'path': path, 'expected': expected,
                       'received': received})

    statuses = analysis.get('stage_status') or {}
    for stage in (*EVIDENCE_DEPENDENCIES, *MANDATORY_STAGES, *EDITORIAL_DEPENDENCIES):
        if stage not in statuses:
            continue  # Older synthetic/offline imports need not fabricate stages.
        row = statuses[stage]
        state = row.get('status') if isinstance(row, dict) else None
        invalid = (state in BLOCKING_STATUSES or
                   (stage in MANDATORY_STAGES and state == 'skipped') or not isinstance(state, str))
        if invalid:
            error('upstream_stage_not_usable', 'stage_status.' + stage + '.status',
                  'ok_or_evidence_backed_partial', str(state))

    manifest = analysis.get('run_manifest') or {}
    if manifest:
        for stage in MANDATORY_STAGES:
            if stage not in statuses:
                error('mandatory_stage_status_missing', 'stage_status.' + stage,
                      'explicit_completed_stage', 'missing')
    if manifest.get('root_cause_stage') in (*MANDATORY_STAGES, *EDITORIAL_DEPENDENCIES) and \
            manifest.get('root_cause_status') in BLOCKING_STATUSES:
        error('upstream_root_cause', 'run_manifest.root_cause_stage',
              'no_editorial_blocking_root_cause', manifest['root_cause_stage'])
    if (analysis.get('quality_gate') or {}).get('status') == 'P0_FAIL':
        error('quality_gate_p0', 'quality_gate.status', 'non_blocking', 'P0_FAIL')

    for collection in ('transcript_segments', 'topics', 'story_arcs', 'entities',
                       'main_moments', 'editorial_shortlist'):
        if collection not in analysis:
            continue
        rows = analysis[collection]
        if not isinstance(rows, list):
            error('collection_type', collection, 'list', type(rows).__name__)
        elif collection != 'editorial_shortlist':
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    error('collection_row_type', f'{collection}[{i}]', 'object', type(row).__name__)
                    if len(errors) >= 32:
                        break
    moments = analysis.get('main_moments')
    if isinstance(moments, list):
        for i, moment in enumerate(moments):
            if not isinstance(moment, dict):
                continue
            if not moment.get('moment_id'):
                error('moment_missing_id', f'main_moments[{i}].moment_id', 'nonempty_id', 'missing')
            if len(errors) >= 32:
                break
    understanding_stage = statuses.get('16_understanding') or {}
    understanding_status = understanding_stage.get('status') if isinstance(understanding_stage, dict) else None
    if understanding_status in {'ok', 'partial'} and \
            analysis.get('editorial_moments') and not moments:
        error('understanding_output_missing', 'main_moments',
              'nonempty_when_editorial_moments_exist', 'empty_or_missing')

    return {'schema_version': '1.0', 'status': 'blocked' if errors else 'valid',
            'editorial_integrity_ready': not errors, 'errors': errors[:32],
            'replay_scope': 'replay_editorial_and_export_without_reprocessing_media'}


def derive_review_state(readiness):
    """READY means ready FOR HUMAN SECOND CURATION, never for publication."""
    required = ('editorial_ready', 'transcript_ready', 'visual_ready')
    review_ready = all(readiness.get(key) is True for key in required)
    return {'review_ready': review_ready,
            'review_state': 'READY_FOR_REVIEW' if review_ready else 'PARTIAL',
            'preview_approved': False,
            'publication_ready': False,
            'review_required': True,
            'approval_authority': 'curator_human_review_and_preview_hash_gate'}
