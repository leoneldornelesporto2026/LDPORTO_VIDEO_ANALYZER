"""Offline Q&A diagnostics. Associations and punctuation never prove an answer."""
from collections import Counter, defaultdict
import math
import re

from .semantic import classify_question, normalized


def _rate(ids, denominator_ids, denominator_name):
    return {'numerator': len(ids), 'denominator': len(denominator_ids),
            'denominator_name': denominator_name,
            'value': len(ids) / len(denominator_ids) if denominator_ids else None,
            'question_ids': sorted(ids)}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def audit_qa(analysis, *, exported_rows=None, candidates=None, sample_limit=10):
    """Audit supplied records without creating questions, repairing links or approving.

    Counts use unique Q_IDs; link occurrences are counted separately. Categories
    are overlapping text cues for review, not measured linguistic accuracy.
    exported_rows=None means export evidence is unavailable, not zero exports.
    """
    sources = defaultdict(list)
    for name in ('questions_answers', 'question_candidates', 'question_answer_pairs', 'question_diagnostics'):
        for index, row in enumerate(analysis.get(name) or []):
            if isinstance(row, dict) and row.get('question_id'):
                sources[row['question_id']].append((name, index, row))
    segments = defaultdict(list)
    for segment in analysis.get('transcript_segments') or []:
        if isinstance(segment, dict) and segment.get('segment_id'):
            segments[segment['segment_id']].append(segment)
    links = defaultdict(list)
    for candidate in candidates or []:
        for index, qid in enumerate(candidate.get('question_answer_linkage') or []):
            links[qid].append({'candidate_id': candidate.get('candidate_id'), 'link_index': index})
    exports = defaultdict(list)
    for index, row in enumerate(exported_rows or []):
        if row.get('question_id'):
            exports[row['question_id']].append(index)

    cases = []
    fields = ('question', 'answer', 'question_segment_ids', 'answer_segment_ids',
              'question_start', 'question_end', 'answer_start', 'answer_end',
              'question_speaker', 'answer_speaker', 'answer_expected', 'question_answer_complete')
    for qid in sorted(set(sources) | set(exports) | set(links)):
        origins = sources.get(qid, [])
        record = origins[0][2] if origins else {}
        reasons, categories, traces = [], [], {}
        if not origins:
            reasons.append('question_record_missing')
        conflicts = [field for field in fields if any(
            field in row and field in record and row[field] != record[field] for _, _, row in origins)]
        if conflicts:
            reasons.append('source_record_conflict')
        if len(exports.get(qid, [])) > 1:
            reasons.append('duplicate_export_id')
        if exported_rows is not None and links.get(qid) and not exports.get(qid):
            reasons.append('candidate_reference_not_exported')
        for index in exports.get(qid, []):
            exported = exported_rows[index]
            if any(field in exported and field in record and exported[field] != record[field]
                   for field in fields):
                reasons.append('export_record_conflict')

        text = record.get('question')
        value = normalized(text).strip() if isinstance(text, str) else ''
        kind = record.get('question_type') or (classify_question(text)['question_type'] if value else None)
        if kind in {'direct_question', 'yes_no_question'}:
            categories.append('direct_question_candidate')
        if kind in {'rhetorical_question', 'self_question'}:
            categories.append('rhetorical_question_candidate')
        if value and re.search(r'\b(?:quer dizer|ou melhor|reformulando|perguntando de outro jeito)\b', value):
            categories.append('reformulation_cue')
        if value and (value.endswith(('...', '\u2026', '-')) or re.search(
                r'\b(?:tu|voce|voces|o|a|de|do|da|que|pra|para)\s*$', value)):
            categories.append('truncated_phrase_cue')
        if value.startswith('porque ') and '?' not in value:
            reasons.append('porque_without_question_mark_ambiguous')
        if kind == 'banter' and '?' in value and re.match(r'^(?:voce|voces|foi|tem|pode)\b', value):
            reasons.append('short_interrogative_classified_as_banter')
        if not value:
            reasons.append('question_text_unavailable')

        associated = bool(record.get('answer') and record.get('answer_segment_ids')) if origins else None
        expected = record.get('answer_expected') if origins else None
        complete = record.get('question_answer_complete') if origins else None
        if expected is True and not associated:
            categories.append('question_without_observed_answer_span')
            reasons.append(record.get('unresolved_reason') or 'no_observed_answer_span')
        if expected is False:
            categories.append('answer_not_expected')
        if complete is True:
            reasons.append('heuristic_completeness_not_audio_verified')
            if not associated:
                reasons.append('complete_without_associated_answer')
        relevance = record.get('answer_relevance') or {}
        if associated and relevance.get('substantive_different_speaker_candidate') and not (
                relevance.get('shared_terms') or relevance.get('direct_response_marker')):
            reasons.append('substantive_turn_only_relevance')

        for side in ('question', 'answer'):
            ids = record.get(side + '_segment_ids') or ([record['question_segment_id']]
                if side == 'question' and record.get('question_segment_id') else [])
            traces[side] = [{'segment_id': sid, 'matches': segments.get(sid, [])} for sid in ids]
            active = bool(origins) if side == 'question' else associated
            if not active:
                continue
            if not ids:
                reasons.append(side + '_segment_ids_missing')
            found = []
            for sid in ids:
                matches = segments.get(sid, [])
                if len(matches) != 1:
                    reasons.append(side + ('_segment_missing' if not matches else '_segment_ambiguous'))
                else:
                    found.append(matches[0])
            if ids and len(found) == len(ids):
                for edge in ('start', 'end'):
                    measured = record.get(side + '_' + edge)
                    actual = found[0 if edge == 'start' else -1].get(edge)
                    if not (_number(measured) and _number(actual)):
                        reasons.append(side + '_timestamp_unavailable')
                    elif abs(measured - actual) > .01:
                        reasons.append(side + '_timestamp_mismatch')
                speaker = record.get(side + '_speaker')
                if speaker is None or any(s.get('speaker') is None for s in found):
                    reasons.append(side + '_speaker_unavailable')
                elif any(s.get('speaker') != speaker for s in found):
                    reasons.append(side + '_speaker_mismatch')
                observed = ' '.join(str(s.get('text') or '') for s in found)
                literal = record.get(side)
                if literal is None:
                    reasons.append(side + '_text_unavailable')
                elif ' '.join(literal.split()) != ' '.join(observed.split()):
                    reasons.append(side + '_text_mismatch')
        if associated:
            if record.get('question_speaker') is None or record.get('answer_speaker') is None:
                reasons.append('turn_ownership_unavailable')
            elif record['question_speaker'] == record['answer_speaker']:
                reasons.append('same_speaker_association')
            qend, astart = record.get('question_end'), record.get('answer_start')
            if _number(qend) and _number(astart) and astart < qend:
                reasons.append('answer_precedes_question_end')
        cases.append({'question_id': qid, 'question': text, 'answer': record.get('answer'),
                      'source_paths': [f'{name}[{index}]' for name, index, _ in origins],
                      'conflicting_fields': conflicts, 'categories': categories,
                      'answer_expected': expected, 'associated_candidate': associated,
                      'heuristic_complete': complete, 'audio_verified_complete': None,
                      'requires_review': True, 'reasons': sorted(set(reasons)),
                      'segment_evidence': traces, 'candidate_links': links.get(qid, []),
                      'export_indices': exports.get(qid, []) if exported_rows is not None else None})

    # Repeated answer spans are review evidence, never extra independent answers.
    groups = defaultdict(list)
    for case in cases:
        if case['associated_candidate']:
            ids = tuple(t['segment_id'] for t in case['segment_evidence']['answer'])
            groups[ids].append(case)
    for group in groups.values():
        if len(group) > 1:
            for case in group:
                case['reasons'] = sorted(set(case['reasons'] + ['shared_answer_span']))
                case['shared_answer_question_ids'] = sorted(c['question_id'] for c in group)

    detected = set(sources)
    expected_ids = {c['question_id'] for c in cases if c['answer_expected'] is not False and c['source_paths']}
    associated_ids = {c['question_id'] for c in cases if c['associated_candidate']}
    complete_ids = {c['question_id'] for c in cases if c['heuristic_complete'] is True and c['associated_candidate']}
    unresolved_ids = expected_ids - associated_ids
    reason_counts = Counter(r for c in cases for r in c['reasons'])
    suspect = [c['question_id'] for c in cases if c['associated_candidate'] and any(
        r != 'heuristic_completeness_not_audio_verified' for r in c['reasons'])]
    return {'schema_version': '1.0-stage07', 'method': 'supplied_records_offline_audit',
            'audio_verification_performed': False, 'verified_complete_count': None,
            'counts': {'detected_question_ids': len(detected), 'expected_answer_candidate_ids': len(expected_ids),
                       'non_answer_diagnostic_ids': len(detected - expected_ids),
                       'associated_pair_ids': len(associated_ids), 'heuristic_complete_pair_ids': len(complete_ids),
                       'unresolved_candidate_ids': len(unresolved_ids),
                       'distinct_associated_answer_spans': len(groups),
                       'exported_reference_ids': len(exports) if exported_rows is not None else None,
                       'exported_reference_rows': len(exported_rows) if exported_rows is not None else None,
                       'candidate_link_occurrences': sum(map(len, links.values())),
                       'candidate_link_ids': len(links)},
            'rates': {'association': _rate(associated_ids & expected_ids, expected_ids, 'expected_answer_candidate_ids'),
                      'heuristic_completion': _rate(complete_ids, associated_ids, 'associated_pair_ids'),
                      'unresolved': _rate(unresolved_ids, expected_ids, 'expected_answer_candidate_ids'),
                      'candidate_reference_export_coverage': _rate(
                          set(links) & set(exports), set(links), 'candidate_link_ids')
                          if exported_rows is not None else None},
            'reason_counts': dict(sorted(reason_counts.items())),
            'category_counts': dict(sorted(Counter(k for c in cases for k in c['categories']).items())),
            'suspect_pair_sample': suspect[:max(0, sample_limit)],
            'sample_method': 'sorted_Q_IDs_with_review_reasons_not_confirmed_false_pairs',
            'cases': cases}


def qa_audit_markdown(audit):
    """Compact per-ID reason table; literal evidence stays in the JSON companion."""
    lines = ['# Auditoria Q&A — etapa 07', '',
             'Auditoria offline; completude heurística exige revisão. Sem escuta realizada.', '',
             '| Medição | Contagem |', '|---|---:|']
    lines += [f'| {key} | {value if value is not None else "null"} |' for key, value in audit['counts'].items()]
    lines += ['', '| Taxa | Numerador | Denominador explícito | Valor |', '|---|---:|---|---:|']
    for key, rate in audit['rates'].items():
        if rate is None:
            lines.append(f'| {key} | null | export evidence unavailable | null |')
        else:
            lines.append(f'| {key} | {rate["numerator"]} | {rate["denominator"]} {rate["denominator_name"]} | {rate["value"]} |')
    lines += ['', 'Categorias e motivos podem se sobrepor; não somar como casos independentes.', '',
              '| Q_ID | Categorias/cues | Associado | Completo heurístico | Motivos |', '|---|---|---|---|---|']
    for case in audit['cases']:
        lines.append('| ' + ' | '.join(str(v).replace('|', '\\|').replace('\n', ' ') for v in (
            case['question_id'], ', '.join(case['categories']), case['associated_candidate'],
            case['heuristic_complete'], ', '.join(case['reasons']))) + ' |')
    return '\n'.join(lines) + '\n'
