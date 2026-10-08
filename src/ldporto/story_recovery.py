"""Bounded narrative resumption from literal action/conflict/outcome anchors."""
import re
from collections import Counter
from .editorial import fold_text, classify_content

ACTION = re.compile(r'\b(?:eu (?:subi|fui|recebi|tentei|lembrei|falei|pensei|continuei|estava|tava)|me chamaram|me encontrava|na epoca|um dia|certa vez|quando eu|teve uma vez|aconteceu comigo|lembro que)\b')
CONFLICT = re.compile(r'\b(?:mas|so que|problema|dificuldade|nao tenho saida|alternativas|saio correndo|sair correndo|humilhado|coracao vazio|mente perturbada|acovardado)\b')
OUTCOME = re.compile(r'\b(?:aplaudindo|aplaudiram|consegui|deu certo|ganhou o campeonato|mente se apazigou|coracao.{0,30}cheio|agora.{0,50}confianca|sabe do que voce e capaz)\b')


def recover_story_arcs(segments, topics, max_seconds=360):
    segments = sorted(segments, key=lambda s: s['start'])
    recovered = []
    for index, setup in enumerate(segments):
        # Tiny diarization fragments remain literal evidence, joined only for detection.
        initial = [s for s in segments[index:index + 4] if s['start'] < setup['start'] + 6]
        if not ACTION.search(fold_text(' '.join(s['text'] for s in initial))):
            continue
        speaker = next((s.get('speaker') for s in initial if s.get('speaker')), None)
        if not speaker:
            continue
        window = []
        conflict = payoff = None
        action_count = 0
        for s in segments[index:]:
            if s['end'] - setup['start'] > max_seconds or (window and s['start'] - window[-1]['end'] > 15):
                break
            window.append(s)
            if s.get('speaker') not in {speaker, None}:
                if s['end'] - s['start'] > 12:
                    break
                continue
            text = fold_text(s['text'])
            action_count += bool(ACTION.search(text))
            if s['start'] > initial[-1]['start'] and not conflict and CONFLICT.search(text):
                conflict = s
            if conflict and s['start'] > conflict['start'] and OUTCOME.search(text) and action_count >= 1:
                payoff = s
                break
        if not payoff or not conflict or payoff['end'] - setup['start'] < 8:
            continue
        # Literal punctuation is weak evidence of a finished ending, but a
        # dangling speech fragment must not be promoted to a complete story.
        if not payoff.get('text', '').rstrip().endswith(('.', '?', '!')):
            continue
        known = Counter()
        for s in window:
            if s.get('speaker'):
                known[s['speaker']] += s['end'] - s['start']
        if known[speaker] / max(sum(known.values()), 1e-9) < .7:
            continue
        if classify_content(' '.join(s['text'] for s in window))['eligibility'] == 'excluded':
            continue
        if any(a['start'] <= setup['start'] and a['end'] >= payoff['end'] for a in recovered):
            continue
        setup_ids = [s['segment_id'] for s in initial]
        recovered.append({'story_arc_id': f'RECOVERED_STORY_{len(recovered):04}', 'kind': 'complete_story',
            'narrative_supported': True, 'start': setup['start'], 'end': payoff['end'],
            'topic_id': next((t['topic_id'] for t in topics if setup['segment_id'] in t.get('evidence_segment_ids', [])), None),
            'topic_ids': [t['topic_id'] for t in topics if t['end'] > setup['start'] and t['start'] < payoff['end']],
            'section_id': None, 'title': 'Relato com desfecho literal', 'summary': None,
            'evidence_segment_ids': [s['segment_id'] for s in window],
            'setup': {'text': ' '.join(s['text'] for s in initial), 'segment_ids': setup_ids},
            'conflict': {'text': conflict['text'], 'segment_ids': [conflict['segment_id']]},
            'development': {'text': ' '.join(s['text'] for s in window if s not in initial and s is not payoff),
                            'segment_ids': [s['segment_id'] for s in window if s not in initial and s is not payoff]},
            'climax': {'text': conflict['text'], 'segment_ids': [conflict['segment_id']]},
            'payoff': {'text': payoff['text'], 'segment_ids': [payoff['segment_id']], 'start': payoff['start'], 'end': payoff['end']},
            'ending': {'text': payoff['text'], 'segment_ids': [payoff['segment_id']]},
            'narrative_structure': {'introduction': setup_ids,
                                    'development': [s['segment_id'] for s in window if s not in initial and s is not payoff],
                                    'climax': [conflict['segment_id']],
                                    'resolution': [payoff['segment_id']], 'ending': [payoff['segment_id']]},
            'interruption_segment_ids': [s['segment_id'] for s in window if s.get('speaker') not in {speaker, None}],
            'standalone_score': .8, 'completeness': 'supported_setup_development_payoff',
            'method': 'literal_narrative_resumption_v2', 'inference': True, 'confidence': None,
            'needs_review': True, 'missing_component_reasons': {}})
    return recovered
