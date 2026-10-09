"""S2: explicit, evidence-preserving contracts for second-curation readiness.

A successful media analysis is not equivalent to review, preview approval or
publication approval. This module never silently repairs upstream artifacts.
"""

BLOCKING_STATUSES = frozenset({'failed', 'blocked', 'unavailable', 'cancelled'})
MANDATORY_STAGES = ('15_semantic', '16_understanding')
EDITORIAL_DEPENDENCIES = ('17b_broadcast_graphics', '17c_commercial_visual', '17d_targeted_asr', '17e_subtitle_review_s7')
EVIDENCE_DEPENDENCIES = ('04_transcription', '05_diarization', '08_person_reid',
                         '10_active_speaker', '11_shots')

QA_TABLE_PATH = 'editorial/qa_pairs.json'


def stage_capability(row):
    """Additive v1 adapter: retain the producer status and loss reason verbatim."""
    row = row if isinstance(row, dict) else {}
    status = row.get('status')
    reason = row.get('reason') or row.get('message')
    if status in BLOCKING_STATUSES - {'unavailable'}:
        state = 'failed'
    elif status == 'unavailable':
        state = 'unavailable_dependency'
    elif row.get('failed_frames_or_ocr') and not row.get('measured_frames'):
        state = 'failed'
    elif status == 'skipped' and reason in {'ocr_disabled', 'disabled'}:
        state = 'not_measured_disabled'
    elif status in {'ok', 'measured'}:
        state = 'measured_ok'
    elif status in {'partial', 'degraded'} and row.get('measurement_state') != 'not_measured':
        state = 'measured_partial'
    else:
        state = 'unavailable_dependency'
    return {'state': state, 'legacy_status': status,
            'reason': reason or (None if state == 'measured_ok' else 'stage_evidence_incomplete')}


def capability_contract(analysis):
    stages = {stage: stage_capability(row)
              for stage, row in (analysis.get('stage_status') or {}).items()}
    visual = analysis.get('commercial_visual_s8')
    if isinstance(visual, dict) and visual:
        # A stage wrapper saying ok cannot overwrite an unmeasured OCR payload.
        payload = stage_capability(visual)
        prior = stages.get('17c_commercial_visual')
        if not prior or prior['state'] != 'failed':
            stages['17c_commercial_visual'] = payload
    return {'schema_version': '1.0', 'stages': stages,
            'unmeasured_capabilities': [stage for stage, row in stages.items()
                if row['state'] in {'not_measured_disabled', 'unavailable_dependency', 'failed'}]}


def canonical_report_metrics(analysis, candidates, shortlist, stories):
    """Count final records once; preserve upstream dedup measurements and unknowns.

    S7 word counts are episode measurements, not sums of overlapping clip reasons.
    Its reviewed ranges are independent from the final editorial shortlist.
    """
    metrics = dict(analysis.get('candidate_metrics') or {})
    metrics.update(final_candidate_count=len({r['candidate_id'] for r in candidates}),
                   final_shortlist_count=len(set(shortlist)),
                   excluded_commercial_count=len({r['candidate_id'] for r in candidates
                       if (r.get('commercial_classification') or {}).get('eligibility') == 'excluded'}),
                   commercial_review_count=len({r['candidate_id'] for r in candidates
                       if (r.get('commercial_classification') or {}).get('eligibility') == 'review'}),
                   final_story_count=len({r['story_id'] for r in stories}))
    review = analysis.get('subtitle_review_s7') or {}
    review_metrics = {key: review.get(key) for key in (
        'selected_candidate_count', 'total_words', 'originally_flagged_for_review',
        'words_flagged_for_review', 'audio_verification_performed')}
    if isinstance(review.get('candidates'), dict):
        review_metrics['selected_candidate_count'] = len(review['candidates'])
    review_metrics['scope'] = 'subtitle_review_s7_episode_words_and_reviewed_ranges'
    return metrics, review_metrics


def audit_report_fields(documents, expected):
    """Report each disagreement with its document/field; never silently approve it."""
    errors = []
    for name, fields in documents.items():
        for field, received in fields.items():
            if field in expected and received != expected[field]:
                errors.append({'code': 'report_field_disagreement', 'path': name + '.' + field,
                               'expected': expected[field], 'received': received})
    return {'status': 'blocked' if errors else 'valid', 'errors': errors}


def build_question_reference_table(analysis, candidates):
    """Keep stable upstream IDs, including questions without an expected answer.

    Reference resolution describes existence of the question, never answer quality.
    Missing records remain explicit placeholders; no transcript is reconstructed.
    """
    from copy import deepcopy
    by_id = {}
    for collection in ('question_answer_pairs', 'questions_answers',
                       'question_candidates', 'question_diagnostics'):
        for i, row in enumerate(analysis.get(collection) or []):
            if not isinstance(row, dict) or not row.get('question_id'):
                continue
            qid = row['question_id']
            if qid not in by_id:
                by_id[qid] = {**deepcopy(row), 'reference_status': 'resolved',
                              'reference_reason': None, 'reference_evidence': []}
            by_id[qid]['reference_evidence'].append({'source_collection': collection,
                                                     'source_path': f'{collection}[{i}]'})
    for candidate in candidates:
        for i, qid in enumerate(candidate.get('question_answer_linkage', [])):
            if qid not in by_id:
                by_id[qid] = {'question_id': qid, 'question': None, 'answer': None,
                              'reference_status': 'unresolved',
                              'reference_reason': 'question_record_missing_in_supplied_analysis',
                              'reference_evidence': []}
            if by_id[qid]['reference_status'] == 'unresolved':
                by_id[qid]['reference_evidence'].append({
                    'candidate_id': candidate['candidate_id'],
                    'source_path': f'candidates/{candidate["candidate_id"]}.json',
                    'json_pointer': f'/question_answer_linkage/{i}'})
    rows = list(by_id.values())
    positions = {row['question_id']: i for i, row in enumerate(rows)}
    for candidate in candidates:
        candidate['question_answer_resolution'] = [{
            'question_id': qid, 'status': by_id[qid]['reference_status'],
            'reason': by_id[qid]['reference_reason'], 'path': QA_TABLE_PATH,
            'json_pointer': f'/{positions[qid]}'}
            for qid in candidate.get('question_answer_linkage', [])]
    return rows


def audit_question_references(candidates, rows):
    """Cross-check every occurrence, its table pointer and unresolved evidence."""
    errors, unresolved = [], []
    by_id = {}
    for i, row in enumerate(rows):
        qid = row.get('question_id')
        if not qid or qid in by_id:
            errors.append(f'qa_ref:invalid_or_duplicate_id:{i}')
        by_id[qid] = (i, row)
        if row.get('reference_status') not in {'resolved', 'unresolved'}:
            errors.append(f'qa_ref:missing_status:{qid}')
        if row.get('reference_status') == 'resolved' and not row.get('reference_evidence'):
            errors.append(f'qa_ref:missing_source_provenance:{qid}')
        if row.get('reference_status') == 'unresolved' and (
                not row.get('reference_reason') or not row.get('reference_evidence')):
            errors.append(f'qa_ref:unexplained:{qid}')
    for candidate in candidates:
        cid = candidate['candidate_id']
        links = candidate.get('question_answer_linkage', [])
        resolutions = candidate.get('question_answer_resolution', [])
        if len(links) != len(resolutions):
            errors.append(f'qa_ref:resolution_count:{cid}')
        for i, qid in enumerate(links):
            found = by_id.get(qid)
            if found is None:
                errors.append(f'qa_ref:missing:{cid}:{qid}')
                continue
            position, row = found
            expected = {'question_id': qid, 'status': row.get('reference_status'),
                        'reason': row.get('reference_reason'), 'path': QA_TABLE_PATH,
                        'json_pointer': f'/{position}'}
            if i >= len(resolutions) or resolutions[i] != expected:
                errors.append(f'qa_ref:path_or_status_mismatch:{cid}:{qid}')
            if row.get('reference_status') == 'unresolved':
                evidence = {'candidate_id': cid, 'source_path': f'candidates/{cid}.json',
                            'json_pointer': f'/question_answer_linkage/{i}'}
                if evidence not in row.get('reference_evidence', []):
                    errors.append(f'qa_ref:missing_link_evidence:{cid}:{qid}')
                unresolved.append({'candidate_id': cid, 'field': 'question_answer_linkage',
                                   'id': qid, 'reason': row.get('reference_reason'),
                                   'path': QA_TABLE_PATH, 'json_pointer': f'/{position}'})
    return {'status': 'failed' if errors else 'unresolved' if unresolved else 'resolved',
            'errors': errors, 'unresolved': unresolved}


def audit_editorial_contract(analysis):
    """Return bounded, structured reasons without leaking transcripts or secrets."""
    errors = []

    def error(code, path, expected, received):
        errors.append({'code': code, 'path': path, 'expected': expected,
                       'received': received})

    statuses = analysis.get('stage_status') or {}
    capabilities = capability_contract(analysis)
    review = analysis.get('subtitle_review_s7') or {}
    if isinstance(review.get('candidates'), dict) and review.get('selected_candidate_count') != len(review['candidates']):
        error('subtitle_review_count_disagreement', 'subtitle_review_s7.selected_candidate_count',
              len(review['candidates']), review.get('selected_candidate_count'))
    for stage in ('04_transcription', '05_diarization', *MANDATORY_STAGES, *EDITORIAL_DEPENDENCIES):
        if stage not in statuses:
            continue  # Older synthetic/offline imports need not fabricate stages.
        row = statuses[stage]
        state = row.get('status') if isinstance(row, dict) else None
        invalid = state not in {'ok', 'partial', 'degraded'}
        if stage == '17c_commercial_visual' and state == 'skipped' and \
                capabilities['stages'][stage]['state'] == 'not_measured_disabled':
            invalid = False
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
    gate = analysis.get('quality_gate') or {}
    camera_only_missing = {'visual_tracking_unavailable', 'active_speaker_unavailable',
                           'camera_timeline_unavailable'}
    missing = gate.get('required_missing_capabilities') or []
    commercial_gap = capabilities['stages'].get('17c_commercial_visual', {}).get('state')
    if commercial_gap == 'not_measured_disabled':
        camera_only_missing |= {'commercial_visual_unavailable', 'ocr_disabled', '17c_commercial_visual'}
    if gate.get('status') == 'P0_FAIL' and not (missing and set(missing) <= camera_only_missing):
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
            'capability_contract': capabilities,
            'replay_scope': 'replay_editorial_and_export_without_reprocessing_media'}


def derive_review_state(readiness):
    """READY means ready FOR HUMAN SECOND CURATION, never for publication."""
    required = ('editorial_ready', 'transcript_ready', 'visual_ready')
    review_ready = all(readiness.get(key) is True for key in required)
    return {'review_ready': review_ready,
            'provisional_review_ready': readiness.get('editorial_ready') is True and readiness.get('transcript_ready') is True,
            'review_state': 'READY_FOR_REVIEW' if review_ready else 'PARTIAL',
            'preview_technical_ready': readiness.get('preview_ready') is True,
            'preview_state': 'TECHNICALLY_VERIFIED' if readiness.get('preview_ready') is True else 'PENDING',
            'preview_approved': False,
            'publication_ready': False,
            'review_required': True,
            'approval_authority': 'curator_human_review_and_preview_hash_gate'}


def preview_technical_readiness(validation):
    """Unknown evidence stays null; flags alone cannot prove a render was checked."""
    if not validation:
        return None
    sampled = validation.get('sampled_frames')
    if validation.get('status') in BLOCKING_STATUSES | {'skipped', 'partial'}:
        return False
    if validation.get('verifier_uses_rendered_frames') is False or sampled == 0:
        return False
    if (validation.get('status') != 'ok' or
            validation.get('verifier_uses_rendered_frames') is not True or
            not isinstance(sampled, (int, float)) or isinstance(sampled, bool)):
        return None
    return sampled > 0
