"""Source-bound narrative planning for a curator; no inference, rendering or approval."""
from collections import Counter
from copy import deepcopy
import math
import re

from .core import digest, overlap
from .editorial import fold_text
from .export_privacy import sanitize_export


ARTIFACTS = {
    'units': 'editorial/story_units.json',
    'graph': 'editorial/narrative_graph.json',
    'qa': 'editorial/question_answer_links.json',
    'sequences': 'editorial/story_sequence_candidates.json',
    'titles': 'social/narrative_title_suggestions.json',
    'quality': 'editorial/narrative_quality_report.json',
    'repair': 'editorial/narrative_repair_plan.json',
}


def _valid_interval(start, end, duration):
    return (all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                for x in (start, end, duration)) and 0 <= start < end <= duration + 1e-6)


def _intervals(ids, by_id):
    """Keep every source interval individual; a distant montage is never implicit."""
    return [{'segment_id': sid, 'start': by_id[sid]['start'], 'end': by_id[sid]['end']} for sid in ids]


def _literal(ids, by_id):
    return ' '.join(by_id[sid]['text'] for sid in ids)


def _chunks(rows, maximum=60):
    result, current = [], []
    for row in rows:
        if current and (row['start'] - current[-1]['end'] > 8 or
                current[-1]['end'] - current[0]['start'] >= maximum and
                re.search(r'[.!?]$', current[-1]['text'].strip())):
            result.append(current)
            current = []
        current.append(row)
    if current:
        result.append(current)
    return result


def _role(arc, ids, by_id):
    for field, role in (('setup', 'setup'), ('payoff', 'resolution'), ('climax', 'turning_point'),
                        ('development', 'development')):
        source = (arc.get(field) or {}).get('segment_ids') or []
        if source and set(source) >= set(ids):
            return role, 'recorded_component_requires_review'
    text = fold_text(_literal(ids, by_id))
    if re.search(r'\b(?:significa|por exemplo|ou seja|isso acontece|porque)\b', text):
        return 'explanation', 'literal_explanation_cue_requires_review'
    return 'context', 'source_context_only_not_narrative_completion'


def narrative_repair_plan(analysis, units, links, max_regions=4, max_audio_seconds=60):
    """Budget critical source review even when no standalone clip is selected."""
    segments = {r['segment_id']: r for r in analysis.get('transcript_segments') or []}
    duration = (analysis.get('metadata') or {}).get('duration', 0)
    role_ids = {sid for u in units if u['narrative_role'] in {'resolution', 'turning_point', 'setup'}
                for sid in u['source_segment_ids']}
    qa_ids = {sid for link in links for key in ('question_segment_ids', 'answer_segment_ids')
              for sid in link.get(key) or []}
    entity_ids = {sid for row in analysis.get('entities') or [] for sid in row.get('evidence_segment_ids') or []}
    options = []
    for word in analysis.get('low_confidence_words') or []:
        sid = word.get('segment_id')
        if sid not in segments:
            continue
        row = segments[sid]
        if not _valid_interval(word.get('start'), word.get('end'), duration):
            continue
        reasons = []
        if sid in role_ids:
            reasons.append('narrative_boundary_or_resolution')
        if sid in qa_ids:
            reasons.append('question_or_possible_answer')
        token = word.get('word') or word.get('text') or ''
        if re.search(r'\d', token) or sid in entity_ids:
            reasons.append('number_or_entity_context')
        reasons = reasons or ['remaining_flagged_asr']
        ordinal = min({'narrative_boundary_or_resolution': 0, 'question_or_possible_answer': 1,
                       'number_or_entity_context': 2, 'remaining_flagged_asr': 3}[r] for r in reasons)
        options.append((ordinal, word['start'], sid, word, reasons))
    regions, selected = [], set()
    for _, _, sid, word, reasons in sorted(options, key=lambda item: item[:3]):
        if sid in selected:
            continue
        row = segments[sid]
        start, end = max(0, row['start'] - 1), min(duration, row['end'] + 1)
        if len(regions) >= max_regions or sum(r['end'] - r['start'] for r in regions) + end - start > max_audio_seconds:
            continue
        if any(overlap(start, end, r['start'], r['end']) > 0 for r in regions):
            continue
        selected.add(sid)
        regions.append({'region_id': 'ASR_REVIEW_' + sid, 'start': start, 'end': end,
            'segment_ids': [sid], 'word_ids': [w['word_id'] for w in analysis.get('low_confidence_words') or []
                                              if w.get('segment_id') == sid and w.get('word_id')],
            'priority_reasons': reasons, 'original_text': row['text'], 'state': 'PENDING_SOURCE_AUDIO_REVIEW',
            'audio_verified': False, 'repair_executed': False})
    return {'schema_version': '1.0', 'mode': 'targeted_repair_plan_only', 'regions': regions,
        'max_regions': max_regions, 'max_audio_seconds': max_audio_seconds,
        'planned_audio_seconds': round(sum(r['end']-r['start'] for r in regions), 6),
        'flagged_word_count': len(analysis.get('low_confidence_words') or []),
        'selected_word_count': len({wid for r in regions for wid in r['word_ids']}),
        'additional_inference_executed': False, 'original_transcript_modified': False,
        'remaining_flags_preserved': True, 'publication_ready': False}


def build_narrative_handoff(analysis, candidates):
    from .narrative_relations import build_question_answer_links, build_arc_context_links
    from .commercial_context import contextual_commercial_review
    metadata = analysis.get('metadata') or {}
    duration = metadata.get('duration', 0)
    rows = [sanitize_export(r) for r in analysis.get('transcript_segments') or [] if isinstance(r, dict) and
            r.get('segment_id') and isinstance(r.get('text'), str) and r['text'].strip() and
            _valid_interval(r.get('start'), r.get('end'), duration)]
    rows.sort(key=lambda r: (r['start'], r['end'], r['segment_id']))
    if len({r['segment_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate_canonical_segment_id')
    by_id = {r['segment_id']: r for r in rows}
    positions = {r['segment_id']: i for i, r in enumerate(rows)}
    arcs = analysis.get('story_arcs') or []
    topics, sections = analysis.get('topics') or [], analysis.get('program_sections') or []
    links = build_question_answer_links(rows, analysis.get('questions_answers') or [],
        topics=topics, sections=sections, entities=analysis.get('entities') or [])
    context_links = build_arc_context_links(rows, arcs, topics=topics, sections=sections,
                                           entities=analysis.get('entities') or [])
    commercial = {c['candidate_id']: contextual_commercial_review(c, segments=rows) for c in candidates}
    units, seen = [], {}
    for arc in arcs:
        source_ids = arc.get('evidence_segment_ids') or []
        if not source_ids or any(sid not in by_id for sid in source_ids):
            continue
        source_ids = sorted(set(source_ids), key=positions.get)
        # A single unit only spans adjacent canonical segments. Explicitly split discontinuities.
        contiguous, part = [], []
        for sid in source_ids:
            if part and (positions[sid] != positions[part[-1]] + 1 or
                         _role(arc, [sid], by_id)[0] != _role(arc, [part[-1]], by_id)[0]):
                contiguous.append(part)
                part = []
            part.append(sid)
        if part:
            contiguous.append(part)
        for group in contiguous:
            for chunk in _chunks([by_id[sid] for sid in group]):
                ids = [r['segment_id'] for r in chunk]
                signature = tuple(ids)
                if signature in seen:
                    previous = seen[signature]
                    if arc['story_arc_id'] not in previous['story_arc_ids']:
                        previous['story_arc_ids'].append(arc['story_arc_id'])
                    continue
                start, end = chunk[0]['start'], chunk[-1]['end']
                related = [c for c in candidates if set(c.get('segment_ids') or []) & set(ids)]
                role, role_status = _role(arc, ids, by_id)
                uncertainty = [sid for sid in ids if by_id[sid].get('needs_review') or
                               by_id[sid].get('uncertain_word_ids')]
                blockers = ['human_audio_review_pending', 'rights_review_pending', 'preview_not_approved']
                if uncertainty:
                    blockers.append('source_transcript_uncertain')
                commercial_blocked = any((c.get('commercial_classification') or {}).get('eligibility') == 'excluded'
                                         for c in related)
                if commercial_blocked:
                    blockers.append('recorded_commercial_exclusion')
                if any(c.get('commercial_review_state') != 'verified' for c in related):
                    blockers.append('commercial_review_pending')
                if not re.search(r'[.!?]$', chunk[-1]['text'].rstrip()) or chunk[-1]['text'].rstrip().endswith(('...', '…')):
                    blockers.append('ending_requires_context_review')
                if end-start > 90:
                    blockers.append('long_source_unit_requires_curator_split')
                uid = 'UNIT_' + digest(ids)[:16]
                unit = {'unit_id': uid, 'story_arc_id': arc['story_arc_id'], 'story_arc_ids': [arc['story_arc_id']],
                    'topic_ids': [t['topic_id'] for t in topics if set(t.get('evidence_segment_ids') or []) & set(ids)],
                    'section_ids': [s['section_id'] for s in sections if set(s.get('evidence_segment_ids') or []) & set(ids)],
                    'source_segment_ids': ids, 'source_intervals': _intervals(ids, by_id),
                    'start': start, 'end': end, 'literal_text': _literal(ids, by_id),
                    'summary': None, 'summary_status': 'literal_source_available_no_new_factual_summary',
                    'narrative_role': role, 'role_evidence_status': role_status,
                    'editorial_unit_type': 'explanation_candidate' if role == 'explanation' else
                        'discussion_context' if arc.get('kind') == 'discussion_segment' else 'narrative_fragment',
                    'candidate_ids': [c['candidate_id'] for c in related],
                    'speaker_ids': sorted({r['speaker'] for r in chunk if r.get('speaker')}),
                    'active_person': None, 'visual_identity_inferred': False, 'visual_mode': 'SOURCE_PRESERVE',
                    'required_context_unit_ids': [], 'context_dependency_status': 'requires_curator_review',
                    'uncertain_segment_ids': uncertainty, 'blockers': sorted(set(blockers)),
                    'standalone_eligibility': 'RECORDED_CANDIDATE_GATE_PRESERVED' if related else 'NOT_EVALUATED_AS_REEL',
                    'sequence_unit_eligibility': 'BLOCKED_RECORDED_COMMERCIAL' if commercial_blocked else 'PROVISIONAL_REVIEW_READY',
                    'eligibility': 'BLOCKED_RECORDED_COMMERCIAL' if commercial_blocked else 'PROVISIONAL_REVIEW_READY',
                    'requires_curator_review': True, 'human_review_completed': False,
                    'preview_approved': False, 'publication_ready': False}
                seen[signature] = unit
                units.append(unit)
    units.sort(key=lambda u: (u['start'], u['end'], u['unit_id']))
    # Dependencies describe retained context, not automatic narrative conclusions.
    for arc in arcs:
        members = [u for u in units if arc['story_arc_id'] in u['story_arc_ids']]
        for previous, current in zip(members, members[1:]):
            current['required_context_unit_ids'] = sorted(set(current['required_context_unit_ids'] + [previous['unit_id']]))
    for link in links:
        rationale = link.get('rationale') or {}
        context_ids = set(rationale.get('context_segment_ids') or []) if isinstance(rationale, dict) else set()
        required_units = [u for u in units if context_ids & set(u['source_segment_ids'])]
        link['required_context_unit_ids'] = [u['unit_id'] for u in required_units]
        for index, unit in enumerate(units):
            if set(link.get('answer_segment_ids') or []) & set(unit['source_segment_ids']):
                earlier = {u['unit_id'] for u in required_units if units.index(u) < index}
                unit['required_context_unit_ids'] = sorted(set(unit['required_context_unit_ids']) | earlier)
    sequences = []
    sequence_signatures = set()
    by_unit = {u['unit_id']: u for u in units}
    for arc in arcs:
        members = [u for u in units if arc['story_arc_id'] in u['story_arc_ids']]
        if not members or all(u['sequence_unit_eligibility'] != 'PROVISIONAL_REVIEW_READY' for u in members):
            continue
        ids = [u['unit_id'] for u in members]
        included = set(ids)
        pending = list(ids)
        while pending:
            for dep in by_unit[pending.pop()]['required_context_unit_ids']:
                if dep not in included:
                    included.add(dep)
                    pending.append(dep)
        members = [u for u in units if u['unit_id'] in included]
        ids = [u['unit_id'] for u in members]
        if tuple(ids) in sequence_signatures:
            continue
        sequence_signatures.add(tuple(ids))
        required = sorted({uid for u in members for uid in u['required_context_unit_ids']})
        supported = (arc.get('narrative_supported') is True and
                     (arc.get('support_diagnostics') or {}).get('ordered_setup_development_payoff') is True)
        sequences.append({'sequence_id': 'SEQUENCE_' + digest(ids)[:16], 'story_arc_ids': [arc['story_arc_id']],
            'unit_ids': ids, 'required_context_unit_ids': required,
            'source_intervals': [span for u in members for span in u['source_intervals']],
            'ordering_scope': 'source_presentation_order_not_event_chronology',
            'assembly_disclosure_required': len(members) > 1,
            'complete_supported': supported,
            'narrative_support': {key: deepcopy(arc.get(key)) for key in ('setup', 'development', 'payoff')},
            'source_arc_narrative_supported': arc.get('narrative_supported') is True,
            'completeness': 'complete_supported' if supported else 'discussion_without_narrative' if
                arc.get('kind') == 'discussion_segment' else 'partial_supported',
            'missing_components': list((arc.get('support_diagnostics') or {}).get('missing_support_reasons') or []),
            'blockers': sorted({b for u in members for b in u['blockers']}),
            'eligible_for_curator_review': True, 'requires_curator_review': True,
            'human_review_completed': False, 'preview_approved': False, 'publication_ready': False})
    titles = []
    for unit in units:
        if unit['sequence_unit_eligibility'] != 'PROVISIONAL_REVIEW_READY':
            continue
        first = by_id[unit['source_segment_ids'][0]]
        tokens = list(re.finditer(r'\S+', first['text']))
        literal = first['text'][:tokens[min(11, len(tokens)-1)].end()].strip()
        # Extractive seeds make every displayed claim traceable, without invented paraphrases.
        variants = [{'title': literal, 'kind': 'literal_excerpt', 'support_segment_ids': [first['segment_id']],
            'start_char': 0, 'end_char': len(literal), 'factual_claims': [literal], 'requires_review': True}]
        if len(tokens) > 12:
            shorter = first['text'][:tokens[5].end()].strip()
            variants.append({'title': shorter, 'kind': 'literal_excerpt', 'support_segment_ids': [first['segment_id']],
                'start_char': 0, 'end_char': len(shorter), 'factual_claims': [shorter], 'requires_review': True})
        titles.append({'title_id': 'TITLE_' + unit['unit_id'], 'source_id': unit['unit_id'],
            'unit_id': unit['unit_id'], 'candidate_ids': unit['candidate_ids'],
            'suggested_titles': variants, 'hook_text': first['text'], 'hook_segment_ids': [first['segment_id']],
            'topic_ids': unit['topic_ids'], 'narrative_role': unit['narrative_role'],
            'curiosity_angle': None, 'prohibited_or_unverified_claims': ['virality', 'causality_not_explicit_in_source',
                'speaker_visual_identity', 'asr_correction_without_audio'],
            'supporting_evidence': [{'segment_id': first['segment_id'], 'text': first['text'],
                                     'start': first['start'], 'end': first['end']}],
            'evidence_status': 'asr_uncertain' if unit['uncertain_segment_ids'] else 'canonical_text_not_audio_verified',
            'requires_review': True, 'publication_ready': False})
    nodes = [{'node_id': u['unit_id'], 'kind': 'story_unit', 'source_segment_ids': u['source_segment_ids'],
              'source_intervals': u['source_intervals']} for u in units]
    nodes += [{'node_id': arc['story_arc_id'], 'kind': 'recorded_arc',
               'source_segment_ids': [sid for sid in arc.get('evidence_segment_ids') or [] if sid in by_id],
               'source_intervals': _intervals([sid for sid in arc.get('evidence_segment_ids') or [] if sid in by_id], by_id)}
              for arc in arcs]
    edges = []
    def edge(source, target, relation, ids, rationale, status='proposed_context_link'):
        ids = sorted(set(sid for sid in ids if sid in by_id), key=positions.get)
        if not ids:
            return
        edges.append({'edge_id': 'EDGE_' + digest([source, target, relation, ids])[:16],
            'source_id': source, 'target_id': target, 'relation': relation,
            'evidence_segment_ids': ids, 'source_intervals': _intervals(ids, by_id),
            'rationale': rationale, 'evidence_status': status, 'requires_review': True,
            'uncertainties': ['event_chronology_not_inferred', 'not_human_validated']})
    for unit in units:
        for aid in unit['story_arc_ids']:
            edge(aid, unit['unit_id'], 'contains_source_unit', unit['source_segment_ids'], 'Recorded arc source membership',
                 'canonical_source_membership')
        for uid in unit['required_context_unit_ids']:
            edge(uid, unit['unit_id'], 'provides_context', unit['source_segment_ids'], 'Preserve previous unit of the recorded arc')
    for link in context_links:
        if link.get('source_arc_id') not in {a['story_arc_id'] for a in arcs} or link.get('target_arc_id') not in {a['story_arc_id'] for a in arcs}:
            continue
        edge(link['source_arc_id'], link['target_arc_id'], 'references_previous_event',
             link.get('evidence_segment_ids') or [], link.get('rationale') or 'Explicit source resumption, review required')
    for link in links:
        qids, aids = link.get('question_segment_ids') or [], link.get('answer_segment_ids') or []
        if not qids or any(sid not in by_id for sid in qids + aids):
            continue
        qnode = 'QUESTION_' + str(link['question_id'])
        if not any(n['node_id'] == qnode for n in nodes):
            nodes.append({'node_id': qnode, 'kind': 'question', 'source_segment_ids': qids,
                          'source_intervals': _intervals(qids, by_id)})
        if aids:
            anode = 'ANSWER_' + str(link['link_id'])
            nodes.append({'node_id': anode, 'kind': 'possible_answer', 'source_segment_ids': aids,
                          'source_intervals': _intervals(aids, by_id)})
            edge(qnode, anode, 'possible_answer', link.get('evidence_segment_ids') or qids+aids,
                 link.get('rationale') or 'Source-bound answer proposal',
                 link.get('evidence_status', 'requires_review'))
    entity_context_count = 0
    for entity in analysis.get('entities') or []:
        name = entity.get('name') or ''
        if len(name.strip()) < 4:
            continue
        pattern = re.compile(r'(?<!\w)' + re.escape(fold_text(name)) + r'(?!\w)')
        grounded = [sid for sid in entity.get('evidence_segment_ids') or [] if sid in by_id and
                    pattern.search(fold_text(by_id[sid]['text']))]
        if not grounded:
            continue
        eid = 'ENTITY_' + digest([name, entity.get('type')])[:16]
        if eid in {n['node_id'] for n in nodes}:
            continue
        nodes.append({'node_id': eid, 'kind': 'transcript_entity_reference', 'label': name,
            'entity_type': entity.get('type'), 'source_segment_ids': grounded,
            'source_intervals': _intervals(grounded, by_id), 'visual_identity_verified': None})
        mentions = [u for u in units if set(u['source_segment_ids']) & set(grounded)]
        for unit in mentions:
            ids = sorted(set(unit['source_segment_ids']) & set(grounded), key=positions.get)
            edge(unit['unit_id'], eid, 'mentions_in_transcript', ids,
                 'Literal named reference, not a visual person association', 'canonical_literal_reference')
        for previous, current in zip(mentions, mentions[1:]):
            if (not previous['section_ids'] or not current['section_ids'] or
                    set(previous['section_ids']) & set(current['section_ids']) or
                    not 0 < current['start'] - previous['end'] <= 900):
                continue
            ids = sorted((set(previous['source_segment_ids']) | set(current['source_segment_ids'])) & set(grounded), key=positions.get)
            edge(previous['unit_id'], current['unit_id'], 'related_context_candidate', ids,
                 'Shared literal entity: ' + name + '; inspect both contexts before joining',
                 'retrieval_only_no_causality_or_continuity_confirmation')
            entity_context_count += 1
    quality = {'schema_version': '1.0', 'unit_count': len(units), 'sequence_count': len(sequences),
        'complete_supported_sequence_count': sum(s['complete_supported'] for s in sequences),
        'provisional_unit_count': sum(u['eligibility'] == 'PROVISIONAL_REVIEW_READY' for u in units),
        'title_seed_count': sum(len(t['suggested_titles']) for t in titles),
        'question_answer_link_count': sum(bool(l.get('answer_segment_ids')) for l in links),
        'confirmed_answer_count': 0, 'arc_context_link_count': len(context_links),
        'cross_section_entity_context_candidates': entity_context_count,
        'arc_context_links': context_links,
        'commercial_context_review': commercial, 'source_arcs': len(arcs),
        'selection_diagnostics': {c['candidate_id']: {
            'historical_standalone_eligible': c.get('default_shortlist_eligible'),
            'recorded_score': c.get('editorial_score_final'),
            'recorded_reasons': (c.get('review_plan') or {}).get('local_gate_reasons') or c.get('editorial_blockers') or [],
            'blocking_for_current_proposal': [reason for reason in c.get('editorial_blockers') or [] if reason in
                {'commercial_boundary_crossed', 'duration_budget_exceeded', 'source_ids_do_not_cover_original'}],
            'review_pending_not_automatic_rejection_of_source': True,
            'rights_status': 'unknown', 'publication_ready': False} for c in candidates},
        'standalone_candidate_count': len(candidates), 'official_shortlist_changed': False,
        'source_narrative_status_counts': dict(Counter(a.get('kind') for a in arcs)),
        'reference_resolution_means_narrative_completion': False,
        'visual_limitations': {'active_person_inferred': False, 'source_preserve_required': True,
                               'existing_diagnostics': analysis.get('analysis_quality') or {},
                               'new_visual_inference': False},
        'rights_status': 'unknown_requires_human_review', 'publication_ready': False}
    repair = narrative_repair_plan(analysis, units, links)
    artifacts = {ARTIFACTS['units']: {'schema_version': '1.0', 'units': units},
        ARTIFACTS['graph']: {'schema_version': '1.0', 'nodes': nodes, 'edges': edges,
                            'event_chronology': 'not_inferred', 'presentation_order': 'canonical_source_time'},
        ARTIFACTS['qa']: {'schema_version': '1.0', 'links': links, 'canonical_qa_modified': False},
        ARTIFACTS['sequences']: {'schema_version': '1.0', 'sequences': sequences},
        ARTIFACTS['titles']: {'schema_version': '1.0', 'titles': titles},
        ARTIFACTS['quality']: quality, ARTIFACTS['repair']: repair}
    state = 'ANALYZER_REPAIR_REQUIRED' if candidates and not rows else 'SECOND_CURATION_PARTIAL'
    handoff = {'schema_version': '1.0', 'contract': 'ldporto.narrative_handoff',
        'project_id': (metadata.get('source') or {}).get('id'),
        'run_id': (analysis.get('run_manifest') or {}).get('run_id'),
        'source_sha256': metadata.get('sha256'), 'duration': duration,
        'analyzer_version': metadata.get('analyzer_version'),
        'canonical_transcript_ref': 'transcript/relevant_segments.jsonl', 'artifact_refs': deepcopy(ARTIFACTS),
        'candidate_catalog_ref': 'editorial/candidate_catalog.json',
        'status': state, 'mode': 'editorial_replay_or_persisted_evidence_only',
        'legacy_social_scope': 'independent_stories_unchanged_sequences_are_provisional_separate_contract',
        'readiness': {key: {'ready': False if key != 'transcription' else bool(rows), 'reason': reason}
            for key, reason in {'transcription': 'canonical_ASR_available_not_human_audio_verified' if rows else 'canonical_transcript_missing',
                'narrative': 'source_units_and_provisional_sequences_require_editorial_review',
                'commercial': 'contextual_diagnostics_do_not_clear_existing_gates',
                'visual': 'original_frame_review_required', 'speaker': 'no_new_identity_or_active_speaker_association',
                'camera': 'source_preserve_without_new_crop_authorization', 'preview': 'separate_hash_approval_required',
                'publication': 'no_human_publication_authorization'}.items()},
        'no_final_render': True, 'requires_curator_review': True,
        'preview_approved': False, 'publication_ready': False}
    return {'handoff': handoff, 'artifacts': artifacts}


def validate_narrative_handoff(bundle, segments, candidates, metadata):
    """Independent source/reference audit. A valid plan still requires a curator."""
    errors = []
    try:
        handoff, artifacts = bundle['handoff'], bundle['artifacts']
        import json
        from pathlib import Path
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).parents[2]/'schemas/narrative_handoff.schema.json').read_text(encoding='utf-8'))
        errors.extend('narrative_schema:' + error.message for error in Draft202012Validator(schema).iter_errors(handoff))
        if (handoff.get('schema_version') != '1.0' or handoff.get('contract') != 'ldporto.narrative_handoff' or
                handoff.get('artifact_refs') != ARTIFACTS or handoff.get('source_sha256') != metadata.get('sha256') or
                handoff.get('duration') != metadata.get('duration')):
            errors.append('handoff_identity_or_schema_disagreement')
        if handoff.get('publication_ready') is not False or handoff.get('preview_approved') is not False:
            errors.append('handoff_approval_unverified')
        if handoff.get('requires_curator_review') is not True or handoff.get('no_final_render') is not True:
            errors.append('handoff_review_or_render_scope_invalid')
        if any(path not in artifacts for path in ARTIFACTS.values()):
            return {'status': 'failed', 'errors': errors + ['missing_narrative_artifact']}
        by_id = {r['segment_id']: sanitize_export(r) for r in segments}
        positions = {r['segment_id']: i for i, r in enumerate(sorted(segments, key=lambda r: (r['start'], r['end'], r['segment_id'])))}
        duration = metadata.get('duration', 0)
        candidate_ids = {c['candidate_id'] for c in candidates}
        def spans_valid(spans, label):
            if not isinstance(spans, list) or any(not isinstance(s, dict) or not
                    _valid_interval(s.get('start'), s.get('end'), duration) for s in spans):
                errors.append('invalid_interval_type_or_range:' + label)
        def refs(ids, label):
            if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids)) or
                    any(sid not in by_id for sid in ids)):
                errors.append('invalid_segment_reference:' + label)
                return False
            if any(not _valid_interval(by_id[sid].get('start'), by_id[sid].get('end'), duration) for sid in ids):
                errors.append('invalid_source_timestamp:' + label)
                return False
            return True
        units = artifacts[ARTIFACTS['units']]['units']
        unit_ids = [u['unit_id'] for u in units]
        if len(set(unit_ids)) != len(unit_ids):
            errors.append('duplicate_story_unit_id')
        by_unit = {u['unit_id']: u for u in units}
        signatures = []
        for unit in units:
            uid, ids = unit['unit_id'], unit['source_segment_ids']
            spans_valid(unit.get('source_intervals'), uid)
            if not _valid_interval(unit.get('start'), unit.get('end'), duration):
                errors.append('invalid_unit_timestamp:' + uid)
            signatures.append(tuple(ids))
            if refs(ids, uid):
                if unit.get('source_intervals') != _intervals(ids, by_id):
                    errors.append('unit_source_interval_disagreement:' + uid)
                if unit.get('literal_text') != _literal(ids, by_id):
                    errors.append('unit_literal_source_disagreement:' + uid)
                if (unit.get('start'), unit.get('end')) != (by_id[ids[0]]['start'], by_id[ids[-1]]['end']):
                    errors.append('unit_boundary_disagreement:' + uid)
                source_positions = [positions[sid] for sid in ids]
                if source_positions != list(range(source_positions[0], source_positions[-1] + 1)):
                    errors.append('unit_implicit_distant_montage:' + uid)
            if not set(unit.get('candidate_ids') or []) <= candidate_ids:
                errors.append('unit_candidate_reference:' + uid)
            if not set(unit.get('required_context_unit_ids') or []) <= set(unit_ids) or uid in unit.get('required_context_unit_ids', []):
                errors.append('unit_context_reference:' + uid)
            if (unit.get('requires_curator_review') is not True or unit.get('human_review_completed') is not False or
                    unit.get('publication_ready') is not False or unit.get('preview_approved') is not False or
                    unit.get('active_person') is not None):
                errors.append('unit_approval_or_identity_unverified:' + uid)
        if len(signatures) != len(set(signatures)):
            errors.append('duplicate_unit_source_signature')
        # Detect cycles independently of the builder's ordering.
        visiting, visited = set(), set()
        def visit(uid):
            if uid in visiting:
                errors.append('cyclic_unit_context:' + uid)
                return
            if uid in visited or uid not in by_unit:
                return
            visiting.add(uid)
            for previous in by_unit[uid].get('required_context_unit_ids') or []:
                visit(previous)
            visiting.remove(uid)
            visited.add(uid)
        for uid in unit_ids:
            visit(uid)
        sequences = artifacts[ARTIFACTS['sequences']]['sequences']
        seq_signatures = []
        for seq in sequences:
            sid, ids = seq['sequence_id'], seq.get('unit_ids') or []
            spans_valid(seq.get('source_intervals'), sid)
            seq_signatures.append(tuple(ids))
            if not ids or len(ids) != len(set(ids)) or not set(ids) <= set(unit_ids):
                errors.append('sequence_unit_reference:' + sid)
                continue
            required = {dep for uid in ids for dep in by_unit[uid]['required_context_unit_ids']}
            if not required <= set(ids) or set(seq.get('required_context_unit_ids') or []) != required:
                errors.append('sequence_missing_required_context:' + sid)
            expected = [span for uid in ids for span in by_unit[uid]['source_intervals']]
            if seq.get('source_intervals') != expected:
                errors.append('sequence_source_intervals:' + sid)
            if (seq.get('requires_curator_review') is not True or seq.get('publication_ready') is not False or
                    seq.get('preview_approved') is not False or seq.get('human_review_completed') is not False):
                errors.append('sequence_approval_unverified:' + sid)
            if seq.get('complete_supported'):
                support = seq.get('narrative_support') or {}
                parts = [support.get(k) or {} for k in ('setup', 'development', 'payoff')]
                all_ids = {ref for uid in ids for ref in by_unit[uid]['source_segment_ids']}
                complete = (seq.get('source_arc_narrative_supported') is True and
                    all(refs(p.get('segment_ids'), sid) and set(p['segment_ids']) <= all_ids for p in parts))
                if complete:
                    bounds = [(min(by_id[r]['start'] for r in p['segment_ids']), max(by_id[r]['end'] for r in p['segment_ids'])) for p in parts]
                    complete = bounds[0][1] <= bounds[1][0] and bounds[1][1] <= bounds[2][0]
                    complete = complete and all(' '.join(str(p.get('text') or '').split()) ==
                        ' '.join(_literal(p['segment_ids'], by_id).split()) for p in parts)
                if not complete:
                    errors.append('sequence_completion_unsupported:' + sid)
        if len(seq_signatures) != len(set(seq_signatures)):
            errors.append('duplicate_sequence_source_signature')
        graph = artifacts[ARTIFACTS['graph']]
        nodes = graph['nodes']
        node_ids = {n['node_id'] for n in nodes}
        if len(node_ids) != len(nodes):
            errors.append('duplicate_graph_node')
        for node in nodes:
            spans_valid(node.get('source_intervals'), node['node_id'])
            if node.get('source_segment_ids') and refs(node['source_segment_ids'], node['node_id']):
                if node.get('source_intervals') != _intervals(node['source_segment_ids'], by_id):
                    errors.append('graph_node_interval:' + node['node_id'])
                if node.get('kind') == 'transcript_entity_reference':
                    label = fold_text(node.get('label') or '')
                    if (not label or node.get('visual_identity_verified') is not None or
                            any(not re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)',
                                fold_text(by_id[sid]['text'])) for sid in node['source_segment_ids'])):
                        errors.append('graph_entity_without_literal_support:' + node['node_id'])
        for edge in graph['edges']:
            spans_valid(edge.get('source_intervals'), edge['edge_id'])
            if edge['source_id'] not in node_ids or edge['target_id'] not in node_ids:
                errors.append('graph_edge_reference:' + edge['edge_id'])
            if refs(edge.get('evidence_segment_ids'), edge['edge_id']):
                if edge.get('source_intervals') != _intervals(edge['evidence_segment_ids'], by_id):
                    errors.append('graph_edge_interval:' + edge['edge_id'])
            if edge.get('relation') not in {'contains_source_unit', 'provides_context', 'references_previous_event',
                    'possible_answer', 'mentions_in_transcript', 'related_context_candidate'}:
                errors.append('graph_unverified_semantic_relation:' + edge['edge_id'])
            if edge.get('requires_review') is not True:
                errors.append('graph_unreviewed_edge:' + edge['edge_id'])
        for link in artifacts[ARTIFACTS['qa']]['links']:
            lid = str(link.get('link_id'))
            refs(link.get('question_segment_ids'), lid)
            if link.get('answer_segment_ids'):
                refs(link['answer_segment_ids'], lid)
            if link.get('evidence_segment_ids'):
                refs(link['evidence_segment_ids'], lid)
            for ids_key, interval_key in [('question_segment_ids', 'question_interval'),
                                          ('answer_segment_ids', 'answer_interval')]:
                ids = link.get(ids_key) or []
                if ids and all(sid in by_id for sid in ids):
                    interval = link.get(interval_key) or {}
                    if (not _valid_interval(interval.get('start'), interval.get('end'), duration) or
                            interval != {'start': min(by_id[sid]['start'] for sid in ids),
                                         'end': max(by_id[sid]['end'] for sid in ids)}):
                        errors.append('qa_interval_disagreement:' + lid)
            if not set(link.get('required_context_unit_ids') or []) <= set(unit_ids):
                errors.append('qa_context_unit_reference:' + lid)
            if link.get('confirmed') is not False or link.get('requires_review') is not True:
                errors.append('qa_link_confirmation_unverified:' + lid)
        titles = artifacts[ARTIFACTS['titles']]['titles']
        for title in titles:
            if title.get('unit_id') not in by_unit:
                errors.append('title_unit_reference:' + str(title.get('title_id')))
                continue
            allowed = set(by_unit[title['unit_id']]['source_segment_ids'])
            hook_ids = title.get('hook_segment_ids') or []
            if (not refs(hook_ids, title['title_id']) or not set(hook_ids) <= allowed or
                    title.get('hook_text') != _literal(hook_ids, by_id)):
                errors.append('title_hook_without_literal_support:' + title['title_id'])
            for variant in title['suggested_titles']:
                ids = variant.get('support_segment_ids') or []
                if (not refs(ids, title['title_id']) or not set(ids) <= allowed or
                        len(ids) != 1 or not isinstance(variant.get('start_char'), int) or
                        not isinstance(variant.get('end_char'), int) or
                        not 0 <= variant['start_char'] < variant['end_char'] <= len(by_id[ids[0]]['text']) or
                        variant['title'] != by_id[ids[0]]['text'][variant['start_char']:variant['end_char']] or
                        variant.get('factual_claims') != [variant['title']]):
                    errors.append('title_claim_without_literal_support:' + title['title_id'])
            if title.get('requires_review') is not True or title.get('publication_ready') is not False:
                errors.append('title_approval_unverified:' + title['title_id'])
        quality = artifacts[ARTIFACTS['quality']]
        for key, expected in {'unit_count': len(units), 'sequence_count': len(sequences),
            'complete_supported_sequence_count': sum(bool(s.get('complete_supported')) for s in sequences),
            'title_seed_count': sum(len(t['suggested_titles']) for t in titles)}.items():
            if quality.get(key) != expected:
                errors.append('narrative_metric_disagreement:' + key)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as exc:
        errors.append('invalid_narrative_contract:' + type(exc).__name__)
    return {'schema_version': '1.0', 'stage': 'SECOND_CURATION_HANDOFF_VALIDATION',
            'status': 'failed' if errors else 'valid', 'errors': sorted(set(errors)),
            'publication_ready': False, 'validation_scope': 'source_references_and_planning_contract_not_human_quality'}


def narrative_audit_documents(bundle, analysis, validation):
    """Compact review packet, including explicit scopes of legacy and R5 outputs."""
    import html
    handoff, artifacts = bundle['handoff'], bundle['artifacts']
    quality = artifacts[ARTIFACTS['quality']]
    baseline = analysis.get('narrative_baseline_metrics') or {}
    comparison = {'schema_version': '1.0', 'before': baseline,
        'after': {key: quality[key] for key in ('source_arcs', 'unit_count', 'sequence_count',
            'complete_supported_sequence_count', 'question_answer_link_count', 'confirmed_answer_count', 'title_seed_count')},
        'count_scopes': {'question_answer_link_count': 'proposed_not_confirmed_answers',
            'sequence_count': 'provisional_source_groupings_not_final_stories',
            'title_seed_count': 'extractive_literal_seeds_not_approved_titles'},
        'new_inference': False, 'official_shortlist_changed': False}
    review = {'schema_version': '1.0', 'decision': handoff['status'], 'validation': validation,
        'quality': quality, 'tests': analysis.get('narrative_test_evidence') or {'status': 'see_external_test_report'},
        'scope': 'read_only_curator_planning', 'requires_curator_review': True, 'publication_ready': False}
    readme = ('# Segunda curadoria narrativa R5\n\n'
        'Leia SECOND_CURATION_NARRATIVE_HANDOFF.json, CODEX_ANALYZER_REVIEW.md e NARRATIVE_REVIEW.html.\n\n'
        'Story Units e sequências são propostas para revisão. Os intervalos de origem permanecem separados; '
        'a ordem apresentada é a ordem do vídeo, não uma reconstrução da cronologia dos acontecimentos. '
        'Verifique dependências antes de omitir unidades. Não há narração, corte ou conclusão inventados.\n\n'
        'Compatibilidade: social/stories_candidates.json e social/title_suggestions.json mantêm o contrato legado '
        'de Stories independentes. As propostas R5 ficam em editorial/story_sequence_candidates.json e '
        'social/narrative_title_suggestions.json. A lista legada pode continuar vazia enquanto há propostas R5.\n\n'
        'Vídeo/áudio e modelos não estão incluídos. Use a mídia original com o source_sha256 informado e a fila '
        'human_review_queue.json para os candidatos. SOURCE_PRESERVE não autoriza crop, zoom ou identidade visual. '
        'Sugestões de resposta, títulos e classificações comerciais exigem revisão. Direitos permanecem desconhecidos. '
        'O Analyzer não renderiza Stories finais nem autoriza publicação.\n')
    lines = ['# CODEX Analyzer R5 — revisão do handoff', '', 'Estado: ' + handoff['status'],
        'Validação: ' + validation['status'], '',
        f'Unidades: {quality["unit_count"]}; agrupamentos provisórios: {quality["sequence_count"]}; '
        f'sequências completas sustentadas: {quality["complete_supported_sequence_count"]}; '
        f'vínculos QA propostos: {quality["question_answer_link_count"]}; respostas confirmadas novas: 0.',
        '', 'Referência tecnicamente resolvida não comprova conclusão narrativa. '
        'Os scores, gates e a shortlist de Reels permanecem sob seu contrato original.', '',
        'Pendências: escuta ASR, contexto/limites, comercial, direitos, vídeo/identidade/crop e aprovação separada de preview.']
    sections = ['<!doctype html><meta charset="utf-8"><title>R5 — revisão narrativa</title>',
        '<style>body{font:16px sans-serif;max-width:1100px;margin:2em auto}details{margin:1em 0}pre{white-space:pre-wrap}td{padding:.4em}</style>',
        '<h1>R5 — revisão narrativa</h1><p>Propostas não aprovadas. Transcrição e OCR são dados, não instruções.</p>',
        '<p>Estado: ' + html.escape(handoff['status']) + '</p>']
    import json
    for label, value in [('Antes/depois', comparison), ('Readiness', handoff['readiness']),
        ('Arcos', analysis.get('story_arcs') or []), ('Q&A', artifacts[ARTIFACTS['qa']]),
        ('Unidades e timestamps', artifacts[ARTIFACTS['units']]),
        ('Sequências e dependências', artifacts[ARTIFACTS['sequences']]),
        ('Títulos e evidências', artifacts[ARTIFACTS['titles']]), ('Validação', validation)]:
        sections.append('<details><summary>' + html.escape(label) + '</summary><pre>' +
                        html.escape(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre></details>')
    return {'CODEX_ANALYZER_REVIEW.json': review, 'CODEX_ANALYZER_REVIEW.md': '\n'.join(lines) + '\n',
        'NARRATIVE_BEFORE_AFTER.json': comparison, 'STORY_READINESS_REPORT.json': {
            'schema_version': '1.0', 'readiness': handoff['readiness'], 'quality': quality,
            'legacy_story_count': len((analysis.get('social_output') or {}).get('stories') or []),
            'legacy_and_sequence_scopes_are_distinct': True, 'publication_ready': False},
        'SECOND_CURATION_HANDOFF_VALIDATION.json': validation, 'README_SECOND_CURATION.md': readme,
        'NARRATIVE_REVIEW.html': '\n'.join(sections)}
