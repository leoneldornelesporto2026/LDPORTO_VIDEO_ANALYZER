"""Deterministic coverage of supplied editorial evidence; no inference or approvals."""

AUDIT_PATH = 'editorial/audit_report.json'


def audit_handoff(candidates, collections):
    """Missing evidence is diagnostic; dangling essential references block readiness.

    Coverage is the fraction of resolved applicable checks, not editorial quality.
    Empty optional link lists are not applicable, not proof of completeness.
    """
    specs = {
        'segment_ids': ('transcript_segments', 'segment_id'),
        'speaker_ids': ('speakers', 'speaker_id'),
        'topic_ids': ('topics', 'topic_id'),
        'question_answer_linkage': ('qa_pairs', 'question_id'),
    }
    indices = {key: {row.get(id_key): row for row in collections.get(name, []) if row.get(id_key)}
               for key, (name, id_key) in specs.items()}
    ids = [row.get('candidate_id') for row in candidates]
    candidate_index = {row.get('candidate_id'): row for row in candidates}
    rows, missing, unresolved = [], [], []
    for candidate in candidates:
        cid = candidate.get('candidate_id')
        checks = []

        def check(field, value, valid, reason, optional=False, blocking=True):
            status = 'not_applicable' if optional else 'resolved' if valid else 'unresolved' if value is not None else 'missing'
            item = {'candidate_id': cid, 'field': field, 'id': value, 'status': status,
                    'reason': None if status in ('resolved', 'not_applicable') else reason,
                    'blocking': blocking and status in ('missing', 'unresolved')}
            checks.append(item)
            if status == 'missing':
                missing.append(item)
            elif status == 'unresolved':
                unresolved.append(item)

        check('candidate_id', cid, bool(cid) and ids.count(cid) == 1, 'missing_or_duplicate_candidate_id')
        values = {key: candidate.get(key) or [] for key in ('segment_ids', 'speaker_ids', 'question_answer_linkage')}
        values['topic_ids'] = ([candidate['primary_topic_id']] if candidate.get('primary_topic_id') else []) + (candidate.get('secondary_topic_ids') or [])
        for field, refs in values.items():
            if not refs:
                check(field, None, False, 'no_supplied_evidence',
                      optional=field == 'question_answer_linkage', blocking=field == 'segment_ids')
            for ref in refs:
                record = indices[field].get(ref)
                valid = record is not None and (field != 'question_answer_linkage' or
                                                record.get('reference_status') == 'resolved')
                check(field, ref, valid, (record or {}).get('reference_reason') or
                      ('question_resolution_unconfirmed' if record is not None and field == 'question_answer_linkage'
                       else 'record_missing_in_package'))
        alternate_refs = ([candidate['alternate_of']] if candidate.get('alternate_of') else [])
        alternate_refs += [row.get('moment_id') for row in candidate.get('alternates') or []]
        extra = candidate.get('alternate_ref')
        alternate_refs += extra if isinstance(extra, list) else [extra] if extra else []
        if not alternate_refs:
            check('alternate_ref', None, False, None, optional=True)
        for ref in alternate_refs:
            check('alternate_ref', ref, ref in candidate_index and ref != cid, 'alternate_candidate_missing_or_self_reference')
        segments = collections.get('transcript_segments', [])
        for field, boundary, time_key, comparison in (
                ('context_before', candidate.get('start'), 'end', lambda a, b: a <= b),
                ('context_after', candidate.get('end'), 'start', lambda a, b: a >= b)):
            context = candidate.get(field) or []
            available = [r for r in segments if isinstance(r.get(time_key), (int, float)) and
                         isinstance(boundary, (int, float)) and comparison(r[time_key], boundary)]
            if not context:
                check(field, None, False, 'surrounding_segments_not_exported', optional=not available, blocking=False)
            for record in context:
                ref = record.get('segment_id')
                canonical = indices['segment_ids'].get(ref)
                valid = canonical is not None and all(record.get(k) == canonical.get(k) for k in
                                                      ('start', 'end', 'speaker', 'text'))
                check(field, ref, valid, 'context_missing_or_disagrees_with_canonical_segment')
        applicable = [r for r in checks if r['status'] != 'not_applicable']
        rows.append({'candidate_id': cid, 'checks': checks,
                     'coverage_score': sum(r['status'] == 'resolved' for r in applicable) / len(applicable) if applicable else None})
    all_checks = [check for row in rows for check in row['checks'] if check['status'] != 'not_applicable']
    blockers = [r for r in missing + unresolved if r['blocking']]
    return {'contract_version': '18.1', 'candidate_count': len(candidates), 'candidates': rows,
            'missing': missing, 'unresolved': unresolved, 'blockers': blockers,
            'references_ready': bool(candidates) and not blockers,
            'coverage_score': sum(r['status'] == 'resolved' for r in all_checks) / len(all_checks) if all_checks else None,
            'coverage_counts': {'resolved': sum(r['status'] == 'resolved' for r in all_checks),
                                'applicable': len(all_checks)},
            'coverage_method': 'resolved_applicable_evidence_checks_not_editorial_quality',
            'publication_ready': False}


def audit_exported_handoff(candidates, read):
    """Read only package members, so local Analyzer collections cannot hide gaps."""
    import json
    collections = {'transcript_segments': [json.loads(line) for line in
                    read('transcript/relevant_segments.jsonl').decode('utf-8-sig').splitlines() if line]}
    for key, path in (('speakers', 'people/speakers.json'), ('topics', 'editorial/topics.json'),
                      ('qa_pairs', 'editorial/qa_pairs.json')):
        try:
            collections[key] = json.loads(read(path))
        except (KeyError, FileNotFoundError):
            collections[key] = []
    return audit_handoff(candidates, collections)
