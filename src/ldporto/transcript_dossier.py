"""Compact, reference-based transcript review evidence; no acoustic inference."""


def review_word_ids(document):
    """Read only explicit canonical ID fields from a versioned review dossier."""
    references = set()
    if isinstance(document, dict):
        for key, value in document.items():
            if key in {'word_ids', 'affected_word_ids', 'boundary_word_ids', 'canonical_word_ids'} and isinstance(value, list):
                references.update(item for item in value if isinstance(item, str))
            elif key == 'ORIGINAL' and isinstance(value, list):
                references.update(row['word_id'] for row in value if isinstance(row, dict) and isinstance(row.get('word_id'), str))
            elif isinstance(value, (dict, list)):
                references.update(review_word_ids(value))
    elif isinstance(document, list):
        for value in document:
            references.update(review_word_ids(value))
    return references


def raw_hypothesis_dossier(analysis, exported_words):
    """Describe inaccessible producer files and link available original evidence."""
    provenance = analysis.get('transcription_provenance') or {}
    language_rows = analysis.get('transcription_language_hypotheses') or []
    metadata = {row['hypothesis_id']: row for row in language_rows if row.get('hypothesis_id')}
    segments = analysis.get('transcript_segments') or []
    identifiers = set(metadata)
    identifiers.update(row['hypothesis_id'] for row in exported_words if row.get('hypothesis_id'))
    identifiers.update(hid for row in segments for hid in row.get('hypothesis_ids') or [] if isinstance(hid, str))
    hypotheses = []
    for identifier in sorted(identifiers):
        row = metadata.get(identifier) or {}
        hypotheses.append({
            'hypothesis_id': identifier,
            **{key: row.get(key) for key in ('task', 'text_kind', 'source', 'start', 'end',
                'language_hint', 'language_detection_scope', 'language_probability')},
            'language_metadata_available': bool(row),
            'canonical_word_ids': [word['word_id'] for word in exported_words if word.get('word_id') and word.get('hypothesis_id') == identifier],
            'canonical_segment_ids': [segment['segment_id'] for segment in segments
                                      if segment.get('segment_id') and identifier in (segment.get('hypothesis_ids') or [])],
        })
    return {'schema_version': '1.0', 'scope': 'exported_canonical_evidence_and_reported_producer_metadata',
            'producer_raw_artifacts': [
                {'path': row.get('path'), 'sha256': row.get('sha256'),
                 'reference_scope': 'external_producer_artifact', 'included_in_package': False,
                 'availability_in_package': 'unavailable',
                 'hash_verification_scope': 'reported_by_producer_not_verified_in_package'}
                for row in provenance.get('raw_hypotheses_ref') or []],
            'hypotheses': hypotheses, 'canonical_word_scope': 'exported_relevant_words_only',
            'original_segments_ref': 'transcript/relevant_segments.jsonl',
            'original_words_ref': 'transcript/relevant_words.jsonl',
            'language_hypotheses_ref': 'transcript/language_hypotheses.json',
            'alternatives_ref': 'transcript/transcription_alternatives.json',
            'acoustic_verification_performed': False, 'human_audio_review_performed': False,
            'publication_ready': False}


def validate_review_dossier(contract, read, segments, words, provenance):
    """Legacy 1.0 contracts omit these new files; 1.1 checks their actual links."""
    if contract.get('schema_version') != '1.1':
        return []
    import json
    errors = []
    required = {'source_audio_review_ref', 'hypothesis_comparison_ref', 'raw_hypothesis_dossier_ref'}
    if not required <= set(contract):
        return ['transcript_contract:missing_review_dossier_references']
    review = json.loads(read(contract['source_audio_review_ref']))
    comparison = json.loads(read(contract['hypothesis_comparison_ref']))
    dossier = json.loads(read(contract['raw_hypothesis_dossier_ref']))
    word_ids = {row['word_id'] for row in words if row.get('word_id')}
    segment_ids = {row['segment_id'] for row in segments if row.get('segment_id')}
    word_by_id = {row['word_id']: row for row in words if row.get('word_id')}
    if not (review_word_ids(review) | review_word_ids(comparison)) <= word_ids:
        errors.append('transcript_contract:review_word_reference_unresolved')
    if review.get('publication_ready') is not False:
        errors.append('transcript_contract:source_review_is_not_publication_approval')
    for window in review.get('windows') or []:
        for row in window.get('ORIGINAL') or []:
            canonical = word_by_id.get(row.get('word_id')) or {}
            if not canonical or any(row.get(key) != canonical.get(key) for key in ('word', 'raw', 'start', 'end')):
                errors.append('transcript_contract:source_review_original_word_disagreement')
    if (dossier.get('publication_ready') is not False or dossier.get('acoustic_verification_performed') is not False
            or dossier.get('human_audio_review_performed') is not False):
        errors.append('transcript_contract:raw_dossier_must_not_claim_verification')
    external = dossier.get('producer_raw_artifacts') or []
    expected_refs = [{'path': row.get('path'), 'sha256': row.get('sha256')} for row in provenance.get('raw_hypotheses_ref') or []]
    if [{'path': row.get('path'), 'sha256': row.get('sha256')} for row in external] != expected_refs:
        errors.append('transcript_contract:producer_raw_reference_disagreement')
    if any(row.get('included_in_package') is not False or row.get('availability_in_package') != 'unavailable'
           or row.get('reference_scope') != 'external_producer_artifact' for row in external):
        errors.append('transcript_contract:raw_external_availability_disagreement')
    segment_by_id = {row['segment_id']: row for row in segments if row.get('segment_id')}
    for row in dossier.get('hypotheses') or []:
        if not set(row.get('canonical_word_ids') or []) <= word_ids or not set(row.get('canonical_segment_ids') or []) <= segment_ids:
            errors.append('transcript_contract:hypothesis_reference_unresolved')
        identifier = row.get('hypothesis_id')
        if any(word_by_id[ident].get('hypothesis_id') != identifier
               for ident in row.get('canonical_word_ids') or [] if ident in word_by_id):
            errors.append('transcript_contract:hypothesis_word_binding_disagreement')
        if any(identifier not in (segment_by_id[ident].get('hypothesis_ids') or [])
               for ident in row.get('canonical_segment_ids') or [] if ident in segment_by_id):
            errors.append('transcript_contract:hypothesis_segment_binding_disagreement')
    return errors
