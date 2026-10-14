"""Bounded textual relationship proposals; never change canonical QA or approval.

These relations help a human inspect delayed answers and resumptions. A lexical
match alone cannot create an edge, establish causality, or complete a story.
"""
from collections import Counter, defaultdict
import math
import re

from .core import digest
from .editorial import fold_text, _story_component_ids
from .semantic import _qa_terms, _qa_continuity, classify_question, propagate_transcript_uncertainty
from .story_recovery import TOPIC_SHIFT


_REFERENCE = re.compile(r'\b(?:respondendo (?:a |a sua |sua |essa |aquela )?pergunta|'
                        r'(?:voltando|retomando).{0,35}pergunta|voce perguntou|voces perguntaram|'
                        r'a resposta (?:a|para).{0,35}pergunta)\b')
_RESUMPTION = re.compile(r'^(?:retomando|voltando (?:ao|a)|continuando (?:o|a)|'
                         r'como eu (?:estava|tava) (?:falando|dizendo))\b')
_EXPLANATION = re.compile(r'^(?:porque|pois|a resposta|na verdade|ou seja|por isso)\b')
_RHETORICAL = {'rhetorical_question', 'self_question'}


def _narrated_self_response(question_rows, answer, distance, shared, rows, positions):
    """Two narrow literal narration cues missing from the legacy question types.

    Number reading needs an actual preceding numeric reference; a numeric turn
    alone proves nothing. Polar narration needs an explicit reply and two anchors.
    Neither cue changes the canonical question type or validates source audio.
    """
    question = question_rows[-1]
    gap = answer['start']-question['end']
    if (len(question_rows) != 1 or distance != 1 or not question.get('speaker') or
            answer.get('speaker') != question['speaker'] or not 0 <= gap <= 2 or
            '?' in answer['text']):
        return None
    prompt, text = fold_text(question['text']).strip(), fold_text(answer['text']).strip()
    reading = re.fullmatch(r'como (?:a gente |nos |voce |voces |se )?(?:le|lemos|leem)'
                           r'(?: (?:isso|esse numero|este numero|o numero))?\s*\?', prompt)
    number = re.fullmatch(r'([0-9]{1,12})[.!]?', text)
    previous = positions[question['segment_id']]-1
    if reading and number and previous >= 0 and answer['end']-answer['start'] <= 8:
        context = rows[previous]
        reference = re.search(r'\bnumero\s+([0-9]{1,12})(?![0-9.,][0-9])\b', fold_text(context['text']))
        if (context.get('speaker') == question['speaker'] and 0 <= question['start']-context['end'] <= 2 and
                reference and int(reference.group(1)) == int(number.group(1)) and
                not TOPIC_SHIFT.search(fold_text(context['text'])) and '?' not in context['text']):
            return {'response_cue': 'numeric_reading_self_response',
                    'context_segment_ids': [context['segment_id']],
                    'referenced_numeric_literal': reference.group(1), 'response_numeric_literal': number.group(1),
                    'evidence_scope': 'literal_transcript_number_equivalence; no_screen_or_audio_verification'}
    core = re.sub(r'^(?:(?:ue|ora|entao|mas|afinal)[, !:]+)+', '', prompt)
    polar_shape = (classify_question(core)['question_type'] == 'yes_no_question' or
                   bool(re.match(r'^(?:a gente|nos|eu|voce|voces|ele|ela|isso)\s+\w+', core)))
    wh = re.search(r'\b(?:como|quando|onde|quem|qual|quais|quant[oa]s?|que)\b', core)
    if (core.endswith('?') and polar_shape and not wh and len(shared) >= 2 and
            re.match(r'^(?:sim|nao)\b', text) and answer['end']-answer['start'] <= 30):
        return {'response_cue': 'polar_narration_self_response', 'context_segment_ids': [],
                'evidence_scope': 'same_speaker_literal_polar_reply_and_two_anchors; no_audio_verification'}
    return None


def _rows(segments):
    if not isinstance(segments, list) or any(not isinstance(row, dict) for row in segments):
        return []
    ids = [row.get('segment_id') for row in segments]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
        return []
    for row in segments:
        if (not isinstance(row.get('text'), str) or not row['text'].strip() or
                not all(isinstance(row.get(key), (int, float)) and not isinstance(row[key], bool)
                        and math.isfinite(row[key]) for key in ('start', 'end')) or row['end'] <= row['start']):
            return []
    return sorted(segments, key=lambda row: (row['start'], row['end']))


def _context_ids(rows, collection, key, topics=None):
    ids = {row['segment_id'] for row in rows}
    result = []
    for context in collection or []:
        if not isinstance(context, dict) or not context.get(key):
            continue
        references = set(context.get('evidence_segment_ids') or context.get('segment_ids') or [])
        by_topic = key == 'section_id' and set(context.get('topic_ids') or []) & set(topics or [])
        by_interval = (not references and not context.get('topic_ids') and
                       isinstance(context.get('start'), (int, float)) and
                       isinstance(context.get('end'), (int, float)) and
                       any(row['end'] > context['start'] and row['start'] < context['end'] for row in rows))
        if ids & references or by_topic or by_interval:
            result.append(context[key])
    return list(dict.fromkeys(result))


def _interval(rows):
    return {'start': rows[0]['start'], 'end': rows[-1]['end']}


def _nonoverlapping_source_span(rows, positions, ids):
    indices = [positions[sid] for sid in ids]
    if indices != sorted(indices):
        return False
    observed = rows[indices[0]:indices[-1]+1]
    return all(right['start'] >= left['end'] for left, right in zip(observed, observed[1:]))


def _canonical_question(record, by_id, positions, source_rows):
    ids = record.get('question_segment_ids') or [record.get('question_segment_id')]
    if (not isinstance(ids, (list, tuple)) or not ids or any(not isinstance(sid, str) or sid not in by_id for sid in ids)
            or len(set(ids)) != len(ids)):
        return None
    rows = [by_id[sid] for sid in ids]
    if (not record.get('question_id') or
            any(row.get('speaker') != rows[0].get('speaker') for row in rows) or
            [positions[sid] for sid in ids] != sorted(positions[sid] for sid in ids) or
            not _nonoverlapping_source_span(source_rows, positions, ids)):
        return None
    text = ' '.join(row['text'] for row in rows)
    if record.get('question') is not None and (not isinstance(record['question'], str) or
            ' '.join(record['question'].split()) != ' '.join(text.split())):
        return None
    if any(record.get(key) is not None and record[key] != value for key, value in (
            ('question_start', rows[0]['start']), ('question_end', rows[-1]['end']),
            ('question_speaker', rows[0]['speaker']))):
        return None
    return rows


def _proposal(question, question_rows, answer_rows, association, evidence, topics, sections, entities):
    qtopics = _context_ids(question_rows, topics, 'topic_id')
    atopics = _context_ids(answer_rows, topics, 'topic_id')
    qsections = _context_ids(question_rows, sections, 'section_id', qtopics)
    asections = _context_ids(answer_rows, sections, 'section_id', atopics)
    qids = [row['segment_id'] for row in question_rows]
    aids = [row['segment_id'] for row in answer_rows]
    uncertainties = ['textual_association_unverified', 'answer_completeness_unverified']
    if qsections and asections and set(qsections).isdisjoint(asections):
        uncertainties.append('cross_section_context_requires_review')
    if any(not row['text'].rstrip().endswith(('.', '?', '!')) or row['text'].rstrip().endswith('...')
           for row in answer_rows[-1:]):
        uncertainties.append('partial_answer_observed')
    if question.get('question_type') in _RHETORICAL:
        uncertainties.append('rhetorical_followup_is_not_expected_answer')
    return {'link_id': 'QA_REL_' + digest({'question_id': question['question_id'], 'q': qids,
                'a': aids, 'type': association, 'spans': evidence.get('source_text_spans')})[:20],
            'question_id': question['question_id'], 'question_segment_ids': qids,
            'answer_segment_ids': aids,
            'evidence_segment_ids': list(dict.fromkeys(evidence.get('context_segment_ids', [])+qids+aids)),
            'question_interval': _interval(question_rows),
            'answer_interval': _interval(answer_rows) if answer_rows else None, 'question_speaker': question_rows[0].get('speaker'),
            'answer_speakers': list(dict.fromkeys(row.get('speaker') for row in answer_rows)),
            'association_type': association, 'evidence_status': 'unresolved' if not aids else 'textual_candidate_for_review',
            'rationale': evidence, 'question_topic_ids': qtopics, 'answer_topic_ids': atopics,
            'question_section_ids': qsections, 'answer_section_ids': asections,
            'entity_ids': [entity['entity_id'] for entity in entities or [] if isinstance(entity, dict)
                           and entity.get('entity_id') and set(entity.get('evidence_segment_ids') or []) & set(qids+aids)],
            'alternatives': [], 'uncertainties': uncertainties,
            'requires_review': True, 'confirmed': False, 'causality_confirmed': False,
            'question_answer_complete': None, 'audio_verified_complete': None,
            'changes_canonical_qa': False}


def build_question_answer_links(segments, questions, topics=None, sections=None, entities=None, cfg=None):
    """Propose source-grounded answers, including delayed, same-turn and rhetorical.

    Default search is bounded to 256 subsequent segments/600 seconds. Delayed or
    cross-section proposals require an explicit question reference and two literal
    anchors. Existing QA and its limits/gates remain untouched. At most four new
    proposals per question are emitted; ambiguity stays explicit, never resolved
    by a fabricated confidence score. Same-segment spans use text offsets, not
    invented subsegment timestamps.
    """
    cfg = cfg or {}
    for field in ('max_search_segments', 'max_search_seconds', 'max_proposals_per_question'):
        if field in cfg and (not isinstance(cfg[field], (int, float)) or isinstance(cfg[field], bool)
                             or not math.isfinite(cfg[field]) or cfg[field] < 1):
            raise ValueError('invalid_relation_search_bound:' + field)
    rows = _rows(segments)
    by_id = {row['segment_id']: row for row in rows}
    positions = {row['segment_id']: index for index, row in enumerate(rows)}
    canonical = [(question, _canonical_question(question, by_id, positions, rows))
                 for question in questions or [] if isinstance(question, dict)]
    canonical = [(question, qrows) for question, qrows in canonical if qrows]
    question_counts = Counter(question['question_id'] for question, _ in canonical)
    canonical = [(question, qrows) for question, qrows in canonical if question_counts[question['question_id']] == 1]
    result = []
    for question, qrows in canonical:
        kind = question.get('question_type') or classify_question(' '.join(row['text'] for row in qrows))['question_type']
        if question.get('answer_expected') is False and kind not in _RHETORICAL:
            continue
        question = {**question, 'question_type': kind}
        if not qrows[0].get('speaker'):
            result.append(_proposal(question, qrows, [], 'unresolved',
                {'basis': 'question_speaker_ownership_unresolved'}, topics, sections, entities))
            continue
        prompt = ' '.join(row['text'] for row in qrows)
        start = positions[qrows[-1]['segment_id']] + 1
        question_links = []
        # Literal references in an existing QA are retained as observations only.
        existing = question.get('answer_segment_ids') or []
        if isinstance(existing, (list, tuple)) and existing and all(
                isinstance(sid, str) and sid in by_id and by_id[sid].get('speaker') for sid in existing):
            observed = [by_id[sid] for sid in existing]
            if observed[0]['start'] >= qrows[-1]['end'] and _nonoverlapping_source_span(
                    rows, positions, [qrow['segment_id'] for qrow in qrows]+list(existing)):
                question_links.append(_proposal(question, qrows, observed, 'existing_qa_link',
                    {'basis': 'existing_canonical_qa_references', 'original_completeness': question.get('question_answer_complete')},
                    topics, sections, entities))
        if len(qrows) == 1 and '?' in prompt:
            boundary = prompt.index('?')+1
            answer_start = boundary + len(prompt[boundary:])-len(prompt[boundary:].lstrip())
            answer_text = prompt[answer_start:]
            shared, marker = _qa_continuity(prompt[:boundary], answer_text)
            if answer_text and (marker or (_EXPLANATION.search(fold_text(answer_text)) and len(shared) >= 2)):
                question_links.append(_proposal(question, qrows, qrows, 'same_segment_self_answer',
                    {'basis': 'literal_question_and_response_spans', 'shared_terms': shared, 'response_cue': marker,
                     'source_text_spans': {'question': {'segment_id': qrows[0]['segment_id'], 'start': 0, 'end': boundary},
                                           'answer': {'segment_id': qrows[0]['segment_id'], 'start': answer_start, 'end': len(prompt)}}},
                    topics, sections, entities))
                question_links[-1]['uncertainties'].append('same_segment_word_times_unresolved')
        previous_end = qrows[-1]['end']
        intervening = []
        for distance, answer in enumerate(rows[start:start+int(cfg.get('max_search_segments', 256))], 1):
            if len(question_links) >= int(cfg.get('max_proposals_per_question', 4)):
                break
            if (answer['start'] < previous_end or answer['end']-qrows[0]['end'] > cfg.get('max_search_seconds', 600)):
                break
            previous_end = answer['end']
            text = answer['text']
            if TOPIC_SHIFT.search(fold_text(text)):
                # A later explicit reference can still be proposed, with the shift visible.
                intervening.append(answer)
                continue
            shared, marker = _qa_continuity(prompt, text)
            narration = _narrated_self_response(qrows, answer, distance, shared, rows, positions)
            explicit = bool(_REFERENCE.search(fold_text(text)))
            qtopics = _context_ids(qrows, topics, 'topic_id')
            atopics = _context_ids([answer], topics, 'topic_id')
            qsections = _context_ids(qrows, sections, 'section_id', qtopics)
            asections = _context_ids([answer], sections, 'section_id', atopics)
            cross = bool(qsections and asections and set(qsections).isdisjoint(asections))
            delayed = distance > 10 or answer['start']-qrows[-1]['end'] > 30 or cross
            shifted = any(TOPIC_SHIFT.search(fold_text(row['text'])) for row in intervening)
            rhetorical = kind in _RHETORICAL
            explanatory = bool(_EXPLANATION.search(fold_text(text)))
            eligible = (explicit and len(shared) >= 2) if delayed or shifted else bool(
                explicit and len(shared) >= 2 or marker or narration or
                rhetorical and explanatory and len(shared) >= 2)
            answer_is_question = classify_question(text)['answer_expected'] and not (
                marker == 'causal_response_cue' and '?' not in text)
            if not answer.get('speaker') or not eligible or answer_is_question:
                intervening.append(answer)
                continue
            if rhetorical and answer['speaker'] != qrows[0]['speaker']:
                intervening.append(answer)
                continue
            if [answer['segment_id']] == existing:
                intervening.append(answer)
                continue
            association = ('rhetorical_followup' if rhetorical else
                           'delayed_self_answer' if delayed and answer['speaker'] == qrows[0]['speaker'] else
                           'self_answer' if answer['speaker'] == qrows[0]['speaker'] else
                           'cross_section_response' if cross else 'delayed_response' if delayed else 'response_candidate')
            evidence = {'basis': 'explicit_question_reference' if explicit else 'typed_response_cue',
                'shared_terms': shared, 'response_cue': marker, 'explicit_question_reference': explicit,
                'segment_distance': distance, 'elapsed_seconds': answer['start']-qrows[-1]['end'],
                'intervening_segment_ids': [row['segment_id'] for row in intervening],
                'topic_shift_segment_ids': [row['segment_id'] for row in intervening if TOPIC_SHIFT.search(fold_text(row['text']))]}
            if narration and not marker and not explicit:
                evidence.update(narration)
            link = _proposal(question, qrows, [answer], association, evidence, topics, sections, entities)
            if any(not row.get('speaker') for row in intervening):
                link['uncertainties'].append('intervening_speaker_ownership_unresolved')
            if any(TOPIC_SHIFT.search(fold_text(row['text'])) for row in intervening):
                link['uncertainties'].append('topic_shift_before_explicit_reference')
            if any(classify_question(row['text'])['answer_expected'] for row in intervening):
                link['uncertainties'].append('intervening_question_requires_disambiguation')
            question_links.append(link)
            intervening.append(answer)
            if len(question_links) >= int(cfg.get('max_proposals_per_question', 4)):
                break
        if not question_links:
            question_links.append(_proposal(question, qrows, [], 'unresolved',
                {'basis': 'no_qualifying_response_cue_observed',
                 'search_max_segments': int(cfg.get('max_search_segments', 256)),
                 'search_max_seconds': cfg.get('max_search_seconds', 600)}, topics, sections, entities))
        result.extend(question_links)
    by_question, by_answer = defaultdict(list), defaultdict(list)
    for link in result:
        by_question[link['question_id']].append(link)
        if link['answer_segment_ids']:
            by_answer[tuple(link['answer_segment_ids'])].append(link)
    for link in result:
        alternatives = [other for other in by_question[link['question_id']] + by_answer[tuple(link['answer_segment_ids'])]
                        if other['link_id'] != link['link_id']]
        link['alternatives'] = list(dict.fromkeys(other['link_id'] for other in alternatives))
        if any(other['question_id'] != link['question_id'] for other in alternatives):
            link['uncertainties'].append('multiple_questions_match_response')
        polarities = {re.match(r'^(sim|nao)\b', fold_text(by_id[other['answer_segment_ids'][0]]['text']).strip()).group(1)
                      for other in by_question[link['question_id']] if other['answer_segment_ids']
                      if re.match(r'^(sim|nao)\b', fold_text(by_id[other['answer_segment_ids'][0]]['text']).strip())}
        if len(polarities) > 1:
            link['uncertainties'].append('conflicting_response_polarity')
    return propagate_transcript_uncertainty(result, rows)


def build_arc_context_links(segments, arcs, topics=None, sections=None, entities=None, cfg=None):
    """Propose explicit later narrative resumptions without extending any arc."""
    cfg = cfg or {}
    for field in ('max_search_segments', 'max_search_seconds', 'max_proposals_per_arc'):
        if field in cfg and (not isinstance(cfg[field], (int, float)) or isinstance(cfg[field], bool)
                             or not math.isfinite(cfg[field]) or cfg[field] < 1):
            raise ValueError('invalid_relation_search_bound:' + field)
    rows = _rows(segments)
    by_id = {row['segment_id']: row for row in rows}
    result = []
    positions = {row['segment_id']: index for index, row in enumerate(rows)}
    for arc in arcs or []:
        ids = arc.get('evidence_segment_ids') or []
        if not arc.get('story_arc_id') or not ids or any(sid not in by_id for sid in ids):
            continue
        source = [by_id[sid] for sid in ids]
        if len(set(ids)) != len(ids) or not _nonoverlapping_source_span(rows, positions, ids):
            continue
        setup_ids = _story_component_ids(arc, 'setup')
        speaker = by_id[setup_ids[0]].get('speaker') if setup_ids and setup_ids[0] in by_id else source[0].get('speaker')
        if not speaker:
            continue
        found = 0
        previous_end = source[-1]['end']
        for row in rows[positions[ids[-1]]+1:positions[ids[-1]]+1+int(cfg.get('max_search_segments', 256))]:
            if row['start'] < previous_end:
                break
            previous_end = row['end']
            if row['end']-source[-1]['end'] > cfg.get('max_search_seconds', 600):
                break
            shared = sorted(_qa_terms(row['text']) & _qa_terms(' '.join(s['text'] for s in source if s.get('speaker') == speaker)))
            if (row.get('speaker') != speaker or not _RESUMPTION.search(fold_text(row['text'])) or
                    TOPIC_SHIFT.search(fold_text(row['text'])) or len(shared) < 2):
                continue
            containing = [other for other in arcs or [] if other.get('story_arc_id') != arc['story_arc_id']
                          and row['segment_id'] in (other.get('evidence_segment_ids') or [])]
            targets, overlapping = [], []
            for other in containing:
                target_ids = other.get('evidence_segment_ids') or []
                if not target_ids or any(sid not in by_id for sid in target_ids):
                    continue
                if min(by_id[sid]['start'] for sid in target_ids) >= source[-1]['end']:
                    targets.append(other['story_arc_id'])
                else:
                    overlapping.append(other['story_arc_id'])
            result.append({'link_id': 'ARC_REL_' + digest({'arc': arc['story_arc_id'], 'segment': row['segment_id']})[:20],
                'source_arc_id': arc['story_arc_id'], 'target_arc_id': targets[0] if len(targets) == 1 else None,
                'target_arc_alternatives': targets if len(targets) > 1 else [],
                'overlapping_target_arc_ids': overlapping,
                'from_segment_ids': ids.copy(), 'to_segment_ids': [row['segment_id']],
                'evidence_segment_ids': ids + [row['segment_id']], 'relation': 'references_previous_event',
                'source_interval': _interval(source), 'context_interval': _interval([row]),
                'association_type': 'explicit_narrative_resumption', 'evidence_status': 'proposed_context_link',
                'rationale': {'basis': 'literal_resumption_cue_and_shared_anchors', 'shared_terms': shared},
                'alternatives': [], 'uncertainties': ['event_identity_unverified', 'narrative_completeness_unverified'],
                'requires_review': True, 'confirmed': False, 'causality_confirmed': False,
                'promotes_narrative_support': False, 'extends_canonical_arc': False})
            if len(targets) > 1:
                result[-1]['uncertainties'].append('multiple_target_arcs_contain_resumption')
            if overlapping:
                result[-1]['uncertainties'].append('target_arc_overlaps_previous_event')
            found += 1
            if found >= int(cfg.get('max_proposals_per_arc', 2)):
                break
    for link in result:
        link['alternatives'] = [other['link_id'] for other in result if other['link_id'] != link['link_id']
                                and other['to_segment_ids'] == link['to_segment_ids']]
        if link['alternatives']:
            link['uncertainties'].append('multiple_arcs_match_resumption')
    return propagate_transcript_uncertainty(result, rows)
