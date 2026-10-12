"""Bounded narrative resumption from literal action/conflict/outcome anchors."""
import re
from collections import Counter
from .editorial import fold_text, classify_content


def candidate_recovery(candidate, prior_score=None):
    """Describe downstream recovery after grounded boundaries and ranking.

    This record never grants eligibility. Missing data and unresolved inference
    are distinct; a score only orders review, it does not supply evidence.
    """
    from .editorial import finite_score, COMMERCIAL_TYPES
    blockers = sorted(set((candidate.get('editorial_blockers') or []) +
                          (candidate.get('boundary_blockers') or [])))
    classification = candidate.get('commercial_classification') or {}
    absolute = []
    if classification.get('eligibility') == 'excluded' or candidate.get('content_type') in COMMERCIAL_TYPES:
        absolute.append('commercial_content_excluded')
    if 'commercial_boundary_crossed' in blockers:
        absolute.append('commercial_boundary_crossed')
    # These prohibit the proposed extension, not all future versions of a clip.
    forbidden = {'explicit_topic_transition_crossed', 'topic_boundary_crossed',
                 'duration_budget_exceeded', 'source_ids_do_not_cover_original'}
    absolute.extend(reason for reason in blockers if reason in forbidden)
    recoverable = [reason for reason in blockers if reason not in absolute]
    gaps = []
    for field, value in (candidate.get('score_components') or {}).items():
        if value is not None:
            continue
        applicability = ((candidate.get('narrative_integrity') or {}).get('status') if field == 'story_completeness' else
                         candidate.get('qa_integrity_status') if field == 'qa_completeness' else None)
        status = 'not_applicable' if applicability == 'not_applicable' else 'missing'
        gaps.append({'field': 'score_components.' + field, 'value': None,
                     'status': status, 'reason': 'not_required_for_this_unit' if status == 'not_applicable' else 'no_observed_score'})
    narrative = candidate.get('narrative_integrity') or {}
    if narrative.get('status') == 'not_applicable':
        gaps.append({'field': 'payoff', 'value': None, 'status': 'not_applicable',
                     'reason': 'no_narrative_obligation'})
    elif 'story_payoff_not_grounded' in blockers:
        gaps.append({'field': 'payoff', 'value': None, 'status': 'unresolved',
                     'reason': 'story_payoff_not_grounded'})
    for reason in recoverable:
        gaps.append({'field': 'context.' + reason, 'value': None,
                     'status': 'missing' if reason in {'missing_text', 'missing_segment_evidence'} else 'unresolved',
                     'reason': reason})
    required = (candidate.get('ranking_uncertainty') or {}).get('missing_required_components', [])
    uncertainty = ['missing_required_score:' + field for field in required]
    if classification.get('eligibility') == 'review':
        uncertainty.append('commercial_classification_requires_review')
    origin = ('preserved' if candidate.get('moment_id', '').startswith('MOMENT_PRESERVED_') else
              'fallback' if candidate.get('moment_id', '').startswith('MOMENT_FALLBACK_') else 'candidate')
    expanded = (candidate.get('context_added_before', 0) or 0) > 0 or (candidate.get('context_added_after', 0) or 0) > 0
    status = ('blocked' if absolute else 'context_pending' if recoverable else
              'review_pending' if uncertainty else 'recovered_requires_review' if expanded else 'evaluated_requires_review')
    return {'status': status, 'origin': origin, 'candidate_preserved': True,
            'absolute_blockers': sorted(set(absolute)), 'recoverable_context': recoverable,
            'reviewable_uncertainty': uncertainty, 'evidence_gaps': gaps,
            'prior_editorial_score': finite_score(prior_score),
            'post_context_editorial_score': candidate.get('editorial_score_final'),
            'editorial_evaluation': 'ranked_after_grounded_context_attempt',
            'action': 'retain_blocked_alternative' if absolute else 'inspect_existing_context' if recoverable else 'human_editorial_review',
            'attempt': {'original_interval': candidate.get('original_interval'),
                        'selected_interval': {'start': candidate.get('ideal_start'), 'end': candidate.get('ideal_end')},
                        'boundary_decision': candidate.get('boundary_decision'),
                        'source_segment_ids': list(candidate.get('evidence_segment_ids') or [])},
            'requires_review': True, 'publish_ready': False}


def candidate_recovery_queue(candidates):
    """Retain pending/fallback IDs, including dedup alternates, outside shortlist."""
    queue = []
    for primary in candidates:
        for candidate in [primary, *primary.get('alternates', [])]:
            recovery = candidate.get('recovery') or {}
            if candidate.get('default_shortlist_eligible') and recovery.get('origin') == 'candidate':
                continue
            queue.append({'moment_id': candidate['moment_id'],
                          'alternate_of': primary['moment_id'] if candidate is not primary else None,
                          'recovery': recovery})
    queue.sort(key=lambda row: (row['recovery'].get('status') == 'blocked',
                               -(row['recovery'].get('post_context_editorial_score') or 0), row['moment_id']))
    return queue


def editorial_recovery_report(questions, arcs, candidates, analysis=None):
    """Report supplied evidence and alternatives, without inventing complete arcs."""
    expected = [q for q in questions if q.get('answer_expected') is not False]
    linked = [q for q in expected if q.get('answer') and q.get('answer_segment_ids')]
    complete = [q for q in linked if q.get('question_answer_complete') is True and not q.get('unresolved_reason')]
    from .qa_audit import audit_qa
    audit = audit_qa(analysis if analysis is not None else {'questions_answers': questions})
    conflicts = {case['question_id'] for case in audit['cases'] if case['conflicting_fields']}
    complete = [q for q in complete if q.get('question_id') not in conflicts]
    groups = [{'story_arc_id': a.get('story_arc_id'), 'kind': a.get('kind'),
               'start': a.get('start'), 'end': a.get('end'),
               'source_segment_ids': list(a.get('evidence_segment_ids') or []),
               'candidate_ids': [c.get('candidate_id', c.get('moment_id')) for c in candidates
                                 if c.get('story_arc', c.get('story_arc_id')) == a.get('story_arc_id')],
               'requires_review': True} for a in arcs if a.get('story_arc_id')]
    return {'schema_version': '1.0-stage48', 'method': 'supplied_literal_evidence_only',
            'qa': {'expected': len(expected), 'linked': len(linked),
                   'textually_complete_requires_review': len(complete),
                   'partial_linked': len(linked) - len(complete),
                   'unresolved': len(expected) - len(complete),
                   'conflicting_record_ids': len(conflicts),
                   'verified_complete': None},
            'qa_audit': audit,
            'arc_kind_counts': dict(sorted(Counter(a.get('kind', 'unknown') for a in arcs).items())),
            'narrative_groups': groups,
            'candidate_count': len(candidates),
            'missing_required_score_count': sum(bool((c.get('ranking_uncertainty') or {}).get('missing_required_components')) for c in candidates),
            'shortlist_eligible_count': sum(c.get('default_shortlist_eligible') is True for c in candidates),
            'requires_review': True, 'publish_ready': False}

ACTION = re.compile(r'\b(?:eu (?:subi|fui|recebi|tentei|lembrei|falei|pensei|continuei|comecei|estava|tava)|me chamaram|me encontrava|na epoca|um dia|certa vez|quando eu|quando comecei|teve uma vez|aconteceu comigo|lembro que)\b')
CONFLICT = re.compile(r'\b(?:mas|so que|problema|dificuldade|nao tenho saida|alternativas|saio correndo|sair correndo|humilhado|coracao vazio|mente perturbada|acovardado)\b')
OUTCOME = re.compile(r'\b(?:aplaudindo|aplaudiram|consegui|deu certo|ganhou o campeonato|mente se apazigou|coracao.{0,30}cheio|agora.{0,50}confianca|sabe do que voce e capaz)\b')
TOPIC_SHIFT = re.compile(r'\b(?:mudando de assunto|outro assunto|agora sobre|vamos falar de)\b')
UNCERTAIN_OUTCOME = re.compile(r'\b(?:nao|nunca|talvez|quem sabe|se|sera|espero|tomara|conseguir|conseguiria)\b')
_GENERIC = set('quando como para porque depois antes agora ainda muito tudo uma umas esse essa isso aquele aquela tinha tenho estava continuei consegui certo problema final resultado'.split())


def literal_outcome(text):
    """Observed affirmative outcome cue, never ASR punctuation or a score.

    This conservative lexical heuristic remains an inference for human review.
    Negation, questions and hypothetical/future contexts stay unresolved.
    """
    text = fold_text(text or '')
    return bool(OUTCOME.search(text) and not UNCERTAIN_OUTCOME.search(text)
                and '?' not in text
                and not re.search(r'\b(?:e|mas|que|porque|para|com|o|a|um|uma)\W*$', text))


def _terms(text):
    return {w for w in re.findall(r'\w+', fold_text(text))
            if len(w) > 3 and w not in _GENERIC}


def outcome_continuity(text, preceding):
    """Record lexical or explicit event-closing evidence; never a quality score."""
    shared = sorted(_terms(text) & _terms(' '.join(s['text'] for s in preceding)))
    closing = bool(re.match(r'^(?:quando terminou|quando acabou|ao terminar)\b', fold_text(text))
                   and re.search(r'\b(?:aplaudindo|aplaudiram)\b', fold_text(text)))
    resolution = bool(re.fullmatch(r'(?:no final|no fim) (?:eu )?consegui resolver(?: tudo| e deu certo)?[.!]*', fold_text(text).strip())
                      and any(CONFLICT.search(fold_text(s['text'])) for s in preceding))
    # Explicit recording-role nouns can differ between setup and resolution.
    # Require two earlier literal anchors, plus a stated successful resolution;
    # a topic title or a single generic music word supplies no such evidence.
    music = {'banda', 'gravadora', 'disco', 'album', 'musicos', 'estudio'}
    earlier_music = sorted(_terms(' '.join(s['text'] for s in preceding)) & music)
    payoff_music = sorted(_terms(text) & music)
    recording_resolution = bool(len(earlier_music) >= 2 and payoff_music
                                and re.match(r'^(?:no final|no fim) deu certo\b', fold_text(text))
                                and any(CONFLICT.search(fold_text(s['text'])) for s in preceding))
    return {'shared_terms': shared, 'event_closing_cue': closing,
            'resolution_reference_cue': resolution,
            'recording_resolution_anchors': {'preceding': earlier_music, 'payoff': payoff_music} if recording_resolution else None,
            'supported': bool(shared or closing or resolution or recording_resolution), 'inference': True}


def _topic_ids(segment, topics):
    return {t['topic_id'] for t in topics if segment['segment_id'] in t.get('evidence_segment_ids', [])}


def _part(segments):
    if not segments:
        return None
    return {'text': ' '.join(s['text'] for s in segments),
            'segment_ids': [s['segment_id'] for s in segments],
            'start': segments[0]['start'], 'end': segments[-1]['end']}


def recover_story_arcs(segments, topics, max_seconds=360, max_gap=15):
    segments = sorted(segments, key=lambda s: s['start'])
    recovered = []
    for index, setup in enumerate(segments):
        # Tiny diarization fragments remain literal evidence, joined only for detection.
        speaker = setup.get('speaker')
        initial = []
        for s in segments[index:index + 4]:
            if (s.get('speaker') != speaker or s['start'] >= setup['start'] + 6
                    or (initial and s['start'] - initial[-1]['end'] > max_gap)
                    or (initial and CONFLICT.search(fold_text(s['text'])))
                    or TOPIC_SHIFT.search(fold_text(s['text']))):
                break
            initial.append(s)
        if not ACTION.search(fold_text(' '.join(s['text'] for s in initial))):
            continue
        if not speaker:
            continue
        window = []
        conflict = payoff = None
        action_count = 0
        stop_reason = 'outcome_not_observed'
        previous_topics = _topic_ids(setup, topics)
        for s in segments[index:]:
            if s['end'] - setup['start'] > max_seconds:
                stop_reason = 'story_time_window_exhausted'
                break
            if window and s['start'] - window[-1]['end'] > max_gap:
                stop_reason = 'story_pause_exceeds_window'
                break
            if TOPIC_SHIFT.search(fold_text(s['text'])):
                stop_reason = 'topic_change_observed'
                break
            current_topics = _topic_ids(s, topics)
            if window and current_topics and previous_topics and current_topics.isdisjoint(previous_topics):
                # Chunk IDs/titles alone are not semantic change evidence. Require
                # literal continuity before crossing an unanchored boundary.
                shared = _terms(s['text']) & _terms(' '.join(w['text'] for w in window if w.get('speaker') == speaker))
                if not shared:
                    stop_reason = 'cross_chunk_continuity_unresolved'
                    break
            if current_topics:
                previous_topics = current_topics
            if s.get('speaker') != speaker:
                if not s.get('speaker'):
                    stop_reason = 'missing_speaker_evidence'
                    break
                if s['end'] - s['start'] > 12:
                    stop_reason = 'long_speaker_interruption'
                    break
                window.append(s)
                continue
            window.append(s)
            text = fold_text(s['text'])
            action_count += bool(ACTION.search(text))
            if s['start'] > initial[-1]['start'] and not conflict and CONFLICT.search(text):
                conflict = s
            if conflict and s['start'] > conflict['start'] and literal_outcome(text) and action_count >= 1:
                continuity = outcome_continuity(s['text'], [w for w in window[:-1] if w.get('speaker') == speaker])
                if not continuity['supported']:
                    stop_reason = 'outcome_continuity_unresolved'
                    break
                payoff = s
                break
        if not conflict or not window or window[-1]['end'] - setup['start'] < 8:
            continue
        known = Counter()
        for s in window:
            if s.get('speaker'):
                known[s['speaker']] += s['end'] - s['start']
        if known[speaker] / max(sum(known.values()), 1e-9) < .7:
            continue
        if classify_content(' '.join(s['text'] for s in window))['eligibility'] == 'excluded':
            continue
        if any(a['start'] <= setup['start'] and a['end'] >= window[-1]['end'] for a in recovered):
            continue
        setup_ids = [s['segment_id'] for s in initial]
        development = [s for s in window if s not in initial and s is not payoff and s.get('speaker') == speaker]
        complete = payoff is not None and bool(development)
        recovered.append({'story_arc_id': f'RECOVERED_STORY_{len(recovered):04}', 'kind': 'complete_story' if complete else 'partial_story',
            'narrative_supported': complete, 'start': setup['start'], 'end': window[-1]['end'],
            'topic_id': next((t['topic_id'] for t in topics if setup['segment_id'] in t.get('evidence_segment_ids', [])), None),
            'topic_ids': [t['topic_id'] for t in topics if t['end'] > setup['start'] and t['start'] < window[-1]['end']],
            'section_id': None, 'title': 'Relato com desfecho literal' if complete else 'Relato com desfecho pendente', 'summary': None,
            'evidence_segment_ids': [s['segment_id'] for s in window],
            'setup': _part(initial),
            'conflict': _part([conflict]),
            'development': _part(development),
            'climax': _part([conflict]),
            'payoff': _part([payoff]) if payoff else None,
            'payoff_continuity': outcome_continuity(payoff['text'], [s for s in window if s is not payoff and s.get('speaker') == speaker]) if payoff else None,
            'ending': _part([payoff]) if payoff else None,
            'narrative_structure': {'introduction': setup_ids,
                                    'development': [s['segment_id'] for s in development],
                                    'climax': [conflict['segment_id']],
                                    'resolution': [payoff['segment_id']] if payoff else [], 'ending': [payoff['segment_id']] if payoff else []},
            'interruption_segment_ids': [s['segment_id'] for s in window if s.get('speaker') not in {speaker, None}],
            'standalone_score': .8 if complete else None, 'completeness': 'supported_setup_development_payoff' if complete else 'unresolved_payoff',
            'method': 'literal_narrative_resumption_v3', 'inference': True, 'confidence': None,
            'needs_review': True, 'extension_stop_reason': None if complete else stop_reason,
            'missing_component_reasons': {} if complete else {'payoff': stop_reason}})
    return recovered
