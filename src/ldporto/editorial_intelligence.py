"""Session 3: evidence-grounded editorial judgments, never publication approval.

Only observed transcript segment IDs/times establish narrative events.  Scores are
review heuristics; an applause/laughter cue in ASR is not proof of a funny joke.
"""
import re
import math
import unicodedata


def _fold(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '').casefold())
                   if unicodedata.category(c) != 'Mn')


def _ids(part):
    ids = part.get('segment_ids', []) if isinstance(part, dict) else []
    return ids if isinstance(ids, list) and all(isinstance(s, str) for s in ids) else []


def narrative_integrity(arc, selection_ids):
    """Detect when a selected clip intersects a known story but omits its ending.

    This is a conservative evidence check, not a semantic assertion that the
    outcome is satisfying. A non-narrative discussion has no story obligation.
    """
    if not isinstance(arc, dict) or arc.get('kind') not in {'complete_story', 'partial_story', 'anecdote'}:
        return {'status': 'not_applicable', 'blockers': [], 'evidence_segment_ids': []}
    selected = set(selection_ids or [])
    covered = set(arc.get('evidence_segment_ids') or [])
    if not (selected & covered):
        return {'status': 'not_applicable', 'blockers': [], 'evidence_segment_ids': []}
    required = ('setup', 'development', 'payoff')
    components = {name: _ids(arc.get(name)) for name in required}
    reasons = []
    # A partial story has no grounded outcome. It cannot be sold as complete.
    if arc.get('kind') != 'complete_story' or not all(components.values()):
        reasons.append('story_payoff_not_grounded')
    for name in required:
        if components[name] and not set(components[name]).issubset(selected):
            reasons.append('missing_story_' + name)
    ending = _ids(arc.get('ending'))
    if ending and (arc.get('kind') == 'complete_story' and not set(ending).issubset(selected)):
        reasons.append('missing_story_ending')
    return {'status': 'incomplete' if reasons else 'complete_candidate',
            'blockers': list(dict.fromkeys(reasons)),
            'evidence_segment_ids': sorted(selected & covered),
            'requires_review': True}


_LAUGHTER = re.compile(r'\[(?:risos?|gargalhadas?|laugh(?:ter|s)?)\]|\((?:risos?|gargalhadas?|laugh(?:ter|s)?)\)|\b(?:kkkk+|haha(?:ha)+|plateia ri|todos riem|gargalhadas?|risadas?)\b', re.I)
_PUNCHLINE = re.compile(r'\b(?:so que|mas ai|e no final|ai eu falei|e ele disse|e ela disse|pior que|ate que|adivinha|sabe o que aconteceu)\b', re.I)
_INTERRUPT = re.compile(r'\b(?:pera ai|calma ai|deixa eu falar|nao terminei|espera um pouco|interromp)\b', re.I)


_SETUP = re.compile(r"\b(?:uma piada|contar uma piada|um dia|quando eu|eu fui|eu estava|era uma vez)\b", re.I)
_ASR_GAP = re.compile(r"\[(?:inaudivel|ininteligivel|unintelligible)\]|\bnao entendi (?:a frase|o que)\b", re.I)


def _speech(row):
    text = _LAUGHTER.sub('', _fold(row.get('text', '')))
    text = _ASR_GAP.sub('', text)
    return bool(re.search(r'\w', text))


def _payoff_candidate(row):
    text = _fold(row.get('text', '')).strip()
    if not _PUNCHLINE.search(text) or _ASR_GAP.search(text):
        return False
    # A teaser or an unfinished connective is setup, not a captured outcome.
    if re.search(r'\b(?:adivinha|sabe o que aconteceu)\b', text):
        return False
    remainder = _PUNCHLINE.sub('', _LAUGHTER.sub('', text))
    if len(re.findall(r'\w+', remainder)) < 2:
        return False
    return not re.search(r'\b(?:que|e|mas|porque|quando|se|o|a|um|uma)\W*$', text)


def humor_integrity(segments, start, end, hinted=False):
    """Literal roles are candidates for review, never semantic proof of humor."""
    rows = sorted(segments, key=lambda s: (s['start'], s['end'], s['segment_id']))
    inside = [s for s in rows if s['end'] > start and s['start'] < end]
    following = [s for s in rows if end <= s['start'] <= end + 16]
    preceding = [s for s in rows if start - 5 <= s['start'] and s['end'] <= start]
    def hits(rows, regex):
        return [s['segment_id'] for s in rows if regex.search(_fold(s.get('text', '')))]
    laughs = hits(inside, _LAUGHTER)
    after_laughs = hits(following, _LAUGHTER)
    turns = [s['segment_id'] for prev, s in zip(inside, inside[1:])
             if prev.get('speaker') and s.get('speaker') and prev['speaker'] != s['speaker']]
    interruptions = hits(inside, _INTERRUPT)
    punchline_cues = hits([s for s in inside if _speech(s)], _PUNCHLINE)
    candidates = [s['segment_id'] for s in inside if _payoff_candidate(s)]
    later_payoff = hits([s for s in following if _speech(s)], _PUNCHLINE)
    setups = hits(inside, _SETUP)
    probable_humor = bool(hinted or laughs or after_laughs)
    blockers = []
    if probable_humor and after_laughs:
        blockers.append('reaction_after_clip')
    if probable_humor and later_payoff:
        blockers.append('potential_punchline_after_clip')
    if hinted and not candidates:
        blockers.append('punchline_not_grounded')
    if hinted and hits(preceding, _SETUP) and not setups:
        blockers.append('setup_begins_before_clip')
    if hinted and interruptions and not candidates:
        blockers.append('interruption_before_payoff')
    if hinted and interruptions and candidates:
        last_payoff = max(s['end'] for s in inside if s['segment_id'] in candidates)
        if any(s['start'] >= last_payoff for s in inside if s['segment_id'] in interruptions):
            blockers.append('interruption_after_candidate_unresolved')
    if probable_humor and any(s['start'] < start or s['end'] > end for s in inside):
        blockers.append('humor_source_segment_truncated')
    gaps = hits(inside, _ASR_GAP)
    if hinted and gaps:
        blockers.append('asr_phrase_unresolved')
    classification = ('asr_phrase_unresolved' if gaps else
                      'punchline_candidate' if candidates and hinted else
                      'reaction_without_joke_evidence' if laughs else
                      'unresolved_humor' if hinted else 'not_applicable')
    def part(ids):
        sources = [s for s in inside if s['segment_id'] in ids]
        return ({'segment_ids': ids, 'start': sources[0]['start'], 'end': sources[-1]['end'],
                 'text': ' '.join(s.get('text', '') for s in sources), 'inference': True}
                if sources else None)
    return {'status': 'incomplete' if blockers else 'observed_reaction' if laughs else 'unresolved' if hinted else 'not_applicable',
            'classification': classification, 'blockers': list(dict.fromkeys(blockers)),
            'laughter_segment_ids': laughs, 'reaction_after_end_segment_ids': after_laughs,
            'punchline_cue_segment_ids': punchline_cues,
            'interruption_segment_ids': interruptions, 'speaker_turn_segment_ids': turns,
            'setup': part(setups), 'incongruity': part(punchline_cues),
            'punchline_candidate': part(candidates) if hinted else None,
            'punchline': None, 'humor_confirmed': None,
            'reaction': part(laughs), 'interruption': part(interruptions),
            'method': 'literal_asr_laughter_and_turn_cues_not_acoustic_proof',
            'requires_review': probable_humor}


def propose_humor_boundaries(segments, start, end, lower=0., upper=None):
    """Suggest whole source segments within five seconds and supplied hard limits.

    Two seconds is the preferred context minimum, not permission to fabricate
    padding or cross a topic/shot. Longer required continuation remains blocked.
    """
    upper = upper if upper is not None else max((s['end'] for s in segments), default=end)
    rows = sorted(segments, key=lambda s: (s['start'], s['end'], s['segment_id']))
    before = [s for s in rows if lower <= s['start'] >= start - 5 and s['end'] <= start
              and _SETUP.search(_fold(s.get('text', '')))]
    after = [s for s in rows if end <= s['start'] and s['end'] <= min(end + 5, upper)
             and (_PUNCHLINE.search(_fold(s.get('text', ''))) or _LAUGHTER.search(_fold(s.get('text', ''))))]
    proposed_start = before[-1]['start'] if before else start
    proposed_end = after[-1]['end'] if after else end
    # Do not associate cues through an intervening topic change or long gap.
    span = [s for s in rows if s['end'] > proposed_start and s['start'] < proposed_end]
    change = re.compile(r"\b(?:mudando de assunto|outro assunto|agora vamos falar)\b")
    unsafe = (any(change.search(_fold(s.get('text', ''))) for s in span)
              or any(b['start'] - a['end'] > 5 for a, b in zip(span, span[1:]))
              or any(s['start'] < lower or s['end'] > upper for s in span))
    if unsafe:
        proposed_start, proposed_end = start, end
    return {'start': proposed_start, 'end': proposed_end,
            'context_target_seconds': [2, 5], 'inference': True, 'requires_review': True,
            'method': 'whole_asr_segments_bounded_by_topic_and_shot',
            'expansion_unresolved': unsafe}


def absolute_selection_blockers(row):
    """Recheck recorded safety evidence even when an eligibility flag is stale."""
    from .editorial import COMMERCIAL_TYPES, finite_score
    reasons = list(row.get('editorial_blockers') or []) + list(row.get('boundary_blockers') or [])
    commercial = row.get('commercial_classification') or {}
    score = finite_score(commercial.get('commercial_score', commercial.get('score', row.get('commercial_score'))))
    if (row.get('content_type') in COMMERCIAL_TYPES or commercial.get('content_type') in COMMERCIAL_TYPES
            or commercial.get('eligibility') in {'excluded', 'exclude', 'review'}
            or score is not None and score >= .7):
        reasons.append('commercial_selection_gate')
    for field in ('clean_opening', 'clean_ending'):
        if row.get(field) is False:
            reasons.append(field + ':false')
    for field in ('narrative_integrity', 'humor_integrity'):
        assessment = row.get(field) or {}
        reasons.extend(assessment.get('blockers') or [])
        if assessment.get('status') == 'incomplete':
            reasons.append(field + ':incomplete')
    return sorted(set(reasons))


def _selection_time(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def diversity_features(row, window_seconds=600):
    """Only recorded labels/IDs; missing dimensions stay null, never inferred."""
    start = _selection_time(row.get('ideal_start', row.get('start')))
    participants = (row.get('editorial_participant_ids') or row.get('person_ids')
                    or row.get('speaker_ids') or [])
    format_label = row.get('editorial_format')
    if not format_label:
        format_label = ('pergunta' if row.get('question_answer_linkage') or row.get('qa_integrity_status') == 'complete_candidate' else
                        'piada' if row.get('content_type') in {'humor', 'joke'} or 'humor' in (row.get('categories') or []) else
                        'relato' if row.get('story_type') in {'complete_story', 'partial_story', 'anecdote'} else None)
    return {'topic': row.get('topic_id') or row.get('primary_topic_id') or row.get('program_section_id') or row.get('topic'),
            'temporal_segment': int(start // max(1., window_seconds)) if start is not None else None,
            'participants': sorted(set(participants)) or None,
            'format': format_label}


def diversity_next(rows, selected, score_key, window_seconds=600, score_band=.08):
    """Quality first; balance four dimensions only within a close score band."""
    from .editorial import finite_score
    def score(row):
        return finite_score(row.get(score_key)) or 0.
    ordered = sorted(rows, key=lambda r: (-score(r), _selection_time(r.get('ideal_start', r.get('start'))) or 0.,
                                         r.get('moment_id', r.get('candidate_id', ''))))
    if not selected:
        return ordered[0]
    observed = [diversity_features(r, window_seconds) for r in selected]
    def novelty(row):
        features = diversity_features(row, window_seconds)
        return sum(not any(
            set(value) & set(prior[key] or []) if key == 'participants' else value == prior[key]
            for prior in observed) for key, value in features.items() if value is not None)
    close = [r for r in ordered if score(r) >= score(ordered[0]) - score_band]
    return max(close, key=novelty)


def selection_disposition(row, reasons, selected=False):
    if selected:
        return 'chosen'
    if reasons and all(r in {'shortlist_capacity', 'topic_diversity_limit', 'semantic_repetition',
                             'diversity_or_repetition_limit'} for r in reasons):
        return 'alternative'
    if (row.get('commercial_classification') or {}).get('eligibility') == 'review':
        return 'pending'
    if absolute_selection_blockers(row):
        return 'excluded'
    from .editorial import finite_score
    return 'pending' if finite_score(row.get('editorial_score_final', row.get('editorial_quality_score'))) is None else 'excluded'


def explain_shortlist(candidates, selected, rejected):
    """Explain recorded selection without reranking, adding proof or opening gates."""
    from collections import Counter
    from .editorial import finite_score
    from .story_recovery import candidate_recovery

    selected_ids = {r['moment_id'] for r in selected}
    rejection = {r['moment_id']: r['reasons'] for r in rejected}
    diagnostics = []
    for row in sorted(candidates, key=lambda r: r.get('moment_id', '')):
        rid = row.get('moment_id')
        reasons = sorted(set(rejection.get(rid, [])))
        details = set(row.get('editorial_blockers') or [])
        details.update(row.get('boundary_blockers') or [])
        uncertainty = row.get('ranking_uncertainty') or {}
        missing = sorted(set(uncertainty.get('missing_required_components') or []))
        details.update('missing_required_score:' + key for key in missing)
        classification = row.get('commercial_classification') or {}
        if classification.get('eligibility') in {'excluded', 'review'}:
            details.add('commercial_classification:' + classification['eligibility'])
        for field in ('clean_opening', 'clean_ending', 'duration_default_eligible'):
            if row.get(field) is False:
                details.add(field + ':false')
        if 'ineligible_by_quality_gate' in reasons and not details:
            details.add('quality_gate_details_not_recorded')
        start, end = row.get('ideal_start'), row.get('ideal_end')
        valid_interval = (isinstance(start, (int, float)) and isinstance(end, (int, float))
                          and not isinstance(start, bool) and not isinstance(end, bool)
                          and math.isfinite(start) and math.isfinite(end)
                          and end > start)
        ids = sorted(set(row.get('evidence_segment_ids') or []))
        recovery = row.get('recovery') or candidate_recovery(row)
        diagnostics.append({
            'moment_id': rid, 'selection_status': 'selected' if rid in selected_ids else 'rejected',
            'selection_disposition': selection_disposition(row, reasons, rid in selected_ids),
            'diversity_features': diversity_features(row),
            'selection_reasons': reasons or ['passed_recorded_selection_gates'],
            'blockers': sorted(set(reasons) | details),
            'blocker_status': 'recorded' if reasons or details else 'none_recorded',
            'editorial': {'raw_score': row.get('editorial_score_raw'),
                          'raw_score_status': 'recorded' if row.get('editorial_score_raw') is not None else 'not_recorded',
                          'final_score': row.get('editorial_score_final'),
                          'score_status': 'observed' if row.get('editorial_score_final') is not None else 'missing',
                          'penalties': dict(row.get('penalties') or {}),
                          'penalty_status': 'recorded' if row.get('penalties') else 'not_recorded',
                          'score_is_probability': False},
            'evidence': {'segment_ids': ids, 'status': 'referenced_not_revalidated' if ids else 'missing_source_references',
                         'coverage': finite_score(row.get('evidence_coverage')),
                         'coverage_status': 'recorded' if finite_score(row.get('evidence_coverage')) is not None else 'missing_or_invalid',
                         'confidence': row.get('ranking_confidence'),
                         'confidence_status': 'recorded' if row.get('ranking_confidence') else 'not_recorded',
                         'missing_required_components': missing,
                         'component_status': 'recorded' if 'ranking_uncertainty' in row else 'not_recorded'},
            'duration': {'start': start, 'end': end, 'seconds': round(end - start, 6) if valid_interval else None,
                         'status': 'recorded_interval' if valid_interval else 'missing_or_invalid_interval',
                         'default_eligible': row.get('duration_default_eligible'),
                         'gate_status': 'recorded' if row.get('duration_default_eligible') is not None else 'not_recorded',
                         'exception': row.get('duration_exception'),
                         'exception_status': 'recorded' if row.get('duration_exception') is not None else 'not_recorded',
                         'reason': row.get('duration_exception_reason') or 'see_recorded_duration_gate'},
            'recovery': recovery,
            'render_readiness': {'ready': None, 'status': 'not_assessed_by_editorial_selection',
                                 'reason': 'requires_downstream_media_and_preview_validation'},
            'publish_ready': False})
    counts = Counter(reason for d in diagnostics for reason in set(d['blockers'])
                     if d['selection_status'] == 'rejected')
    return {'candidate_diagnostics': diagnostics,
            'exclusion_counts_multilabel': dict(sorted(counts.items())),
            'unique_rejected_candidates': sum(d['selection_status'] == 'rejected' for d in diagnostics),
            'counting_method': 'one_per_candidate_per_label_labels_overlap_do_not_sum',
            'diagnostic_version': 'stage13_v1'}


def select_editorial_shortlist(candidates, max_items=12, min_score=.50, max_per_topic=2):
    """No fixed quota: high quality and distinct subject matter take precedence.

    Temporal duplicates are already collapsed by upstream dedup. This stage
    prevents topical monopolies, repetitive takes, and incomplete narratives.
    """
    from .editorial import terms, finite_score
    try:
        max_items = max(0, int(max_items))
    except (TypeError, ValueError):
        max_items = 12
    selected, topic_counts, eliminated = [], {}, []
    eligible = []
    for row in candidates:
        rid = row.get('moment_id')
        blockers = absolute_selection_blockers(row)
        score = finite_score(row.get('editorial_score_final'))
        if not row.get('default_shortlist_eligible', False):
            blockers.append('ineligible_by_quality_gate')
        if score is None or score < min_score:
            blockers.append('below_editorial_quality_floor')
        if blockers:
            eliminated.append({'moment_id': rid, 'reasons': sorted(set(blockers))})
            continue
        eligible.append(row)
    while eligible:
        row = diversity_next(eligible, selected, 'editorial_score_final')
        eligible.remove(row)
        rid = row.get('moment_id')
        if len(selected) >= max_items:
            eliminated.append({'moment_id': rid, 'reasons': ['shortlist_capacity']})
            continue
        topic = row.get('topic_id') or row.get('program_section_id')
        if topic and topic_counts.get(topic, 0) >= max_per_topic:
            eliminated.append({'moment_id': rid, 'reasons': ['topic_diversity_limit']})
            continue
        text = terms((row.get('core_moment') or {}).get('text') or row.get('text', ''))
        duplicate = False
        for earlier in selected:
            if row.get('story_arc_id') and row['story_arc_id'] == earlier.get('story_arc_id'):
                duplicate = True
                break
            earlier_terms = terms((earlier.get('core_moment') or {}).get('text') or earlier.get('text', ''))
            if len(text) >= 4 and len(earlier_terms) >= 4 and len(text & earlier_terms) / max(1, len(text | earlier_terms)) >= .75:
                duplicate = True
                break
        if duplicate:
            eliminated.append({'moment_id': rid, 'reasons': ['semantic_repetition']})
            continue
        selected.append(row)
        if topic:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
    selected.sort(key=lambda r: (-finite_score(r['editorial_score_final']), _selection_time(r.get('ideal_start')) or 0., r.get('moment_id', '')))
    eliminated.sort(key=lambda r: r.get('moment_id', ''))
    return selected, {**explain_shortlist(candidates, selected, eliminated),
                      'candidates_evaluated': len(candidates), 'shortlist_count': len(selected),
                      'rejected': eliminated, 'min_score': min_score,
                      'max_per_topic': max_per_topic, 'fixed_quota': False,
                      'method': 'absolute_gates_quality_band_four_dimension_diversity',
                      'diversity_policy': {'version': '16.1', 'score_band': .08, 'temporal_window_seconds': 600,
                                           'dimensions': ['topic', 'temporal_segment', 'participants', 'format']},
                      'unfilled_slots_are_intentional': len(selected) < max_items}
