"""Session 3: evidence-grounded editorial judgments, never publication approval.

Only observed transcript segment IDs/times establish narrative events.  Scores are
review heuristics; an applause/laughter cue in ASR is not proof of a funny joke.
"""
import re
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


def humor_integrity(segments, start, end, hinted=False):
    """Locate observable laughter/turns and flag unfinished potential jokes.

    A laugh marker does not alone establish that a particular joke landed.
    No punchline text is fabricated from confidence or classifier categories.
    """
    inside = [s for s in segments if s.get('end', 0) > start and s.get('start', 0) < end]
    following = [s for s in segments if end <= s.get('start', 0) <= end + 16]
    preceding = [s for s in segments if start - 12 <= s.get('end', 0) <= start]
    def hits(rows, regex):
        return [s['segment_id'] for s in rows if regex.search(_fold(s.get('text', '')))]
    laughs = hits(inside, _LAUGHTER)
    after_laughs = hits(following, _LAUGHTER)
    turns = [s['segment_id'] for prev, s in zip(inside, inside[1:])
             if prev.get('speaker') and s.get('speaker') and prev['speaker'] != s['speaker']]
    interruptions = hits(inside, _INTERRUPT)
    punchline_cues = hits(inside, _PUNCHLINE)
    later_payoff = hits(following, _PUNCHLINE)
    probable_humor = bool(hinted or laughs or after_laughs)
    blockers = []
    if probable_humor and after_laughs and not laughs:
        blockers.append('reaction_after_clip')
    if probable_humor and later_payoff and not punchline_cues and not laughs:
        blockers.append('potential_punchline_after_clip')
    if hinted and not (laughs or punchline_cues):
        blockers.append('punchline_not_grounded')
    if hinted and preceding and not (punchline_cues or laughs) and _PUNCHLINE.search(_fold(preceding[-1].get('text', ''))):
        blockers.append('setup_begins_before_clip')
    return {'status': 'incomplete' if blockers else 'observed_reaction' if laughs else 'unresolved' if hinted else 'not_applicable',
            'blockers': list(dict.fromkeys(blockers)), 'laughter_segment_ids': laughs,
            'reaction_after_end_segment_ids': after_laughs,
            'punchline_cue_segment_ids': punchline_cues,
            'interruption_segment_ids': interruptions, 'speaker_turn_segment_ids': turns,
            'method': 'literal_asr_laughter_and_turn_cues_not_acoustic_proof',
            'requires_review': probable_humor}


def select_editorial_shortlist(candidates, max_items=12, min_score=.50, max_per_topic=2):
    """No fixed quota: high quality and distinct subject matter take precedence.

    Temporal duplicates are already collapsed by upstream dedup. This stage
    prevents topical monopolies, repetitive takes, and incomplete narratives.
    """
    from .editorial import terms
    try:
        max_items = max(0, int(max_items))
    except (TypeError, ValueError):
        max_items = 12
    selected, topic_counts, eliminated = [], {}, []
    sorted_rows = sorted(candidates, key=lambda r: (-(r.get('editorial_score_final') or 0), r.get('ideal_start', 0), r.get('moment_id', '')))
    for row in sorted_rows:
        rid = row.get('moment_id')
        blockers = list(row.get('editorial_blockers') or [])
        score = row.get('editorial_score_final')
        if not row.get('default_shortlist_eligible', False):
            blockers.append('ineligible_by_quality_gate')
        if score is None or score < min_score:
            blockers.append('below_editorial_quality_floor')
        if blockers:
            eliminated.append({'moment_id': rid, 'reasons': sorted(set(blockers))})
            continue
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
    return selected, {'candidates_evaluated': len(candidates), 'shortlist_count': len(selected),
                      'rejected': eliminated, 'min_score': min_score,
                      'max_per_topic': max_per_topic, 'fixed_quota': False,
                      'method': 'evidence_gates_score_floor_topical_diversity'}
