"""Synthetic offline stories; these are not transcripts of Joao Gordo."""
from copy import deepcopy

import pytest

from ldporto.story_recovery import recover_story_arcs
from ldporto.understanding import build_story_arcs, _validate_story_arcs_contract
from ldporto.editorial_intelligence import narrative_integrity
from ldporto.editorial import _complete_story, optimize_boundaries


def fixture():
    texts = ['Um dia eu fui gravar um disco no estudio.',
             'Mas o disco ficou parado por um problema no estudio.',
             'Eu continuei a gravar o disco com outros musicos.',
             'No final consegui terminar o disco']
    rows = [dict(segment_id=f'S{i}', start=i * 10, end=(i + 1) * 10,
                 speaker='A', text=text) for i, text in enumerate(texts)]
    topics = [dict(topic_id=f'T{i}', start=i * 20, end=(i + 1) * 20,
                   evidence_segment_ids=[f'S{i * 2}', f'S{i * 2 + 1}']) for i in range(2)]
    return rows, topics


def complete(arcs):
    return [a for a in arcs if a['kind'] == 'complete_story']


def test_two_chunks_later_payoff_without_asr_punctuation():
    rows, topics = fixture()
    original = deepcopy((rows, topics))
    arcs = build_story_arcs({'segments': rows}, topics)
    arc = complete(arcs)[0]
    assert arc['topic_ids'] == ['T0', 'T1']
    for key, ids in [('setup', ['S0']), ('development', ['S1', 'S2']),
                     ('climax', ['S1']), ('payoff', ['S3'])]:
        assert arc[key]['segment_ids'] == ids
        assert arc[key]['text'] == ' '.join(r['text'] for r in rows if r['segment_id'] in ids)
        assert arc[key]['start'] == next(r['start'] for r in rows if r['segment_id'] == ids[0])
    assert arc['start'] == 0 and arc['end'] == 40
    assert _complete_story(arc, ['S0', 'S1', 'S2', 'S3'])
    assert narrative_integrity(arc, ['S0', 'S1', 'S2'])['status'] == 'incomplete'
    assert _validate_story_arcs_contract(arcs, rows)[1] == []
    assert (rows, topics) == original
    boundary = optimize_boundaries({'start': 10, 'end': 30}, rows, {}, arc, [])
    assert boundary['ideal_start'] == 0 and boundary['ideal_end'] == 40


def test_no_ending_remains_partial_even_with_high_score():
    rows, topics = fixture()
    arcs = recover_story_arcs(rows[:-1], topics)
    assert arcs and not complete(arcs)
    arc = arcs[0]
    assert arc['payoff'] is None and arc['ending'] is None
    assert arc['standalone_score'] is None and arc['confidence'] is None
    assert arc['missing_component_reasons']['payoff'] == 'outcome_not_observed'
    arc['standalone_score'] = 1
    assert not _complete_story(arc, arc['evidence_segment_ids'])
    assert narrative_integrity(arc, arc['evidence_segment_ids'])['status'] == 'incomplete'


@pytest.mark.parametrize('text', [
    'No final.', 'O resultado.', 'Acabou.', 'Nao consegui terminar o disco.',
    'Talvez consegui terminar o disco.', 'Se deu certo o disco, vamos ver.',
    'Consegui terminar o disco?', 'Consegui terminar o disco e',
])
@pytest.mark.parametrize('single_topic', [False, True])
def test_generic_negated_hypothetical_or_dangling_ending_is_not_payoff(text, single_topic):
    rows, topics = fixture()
    rows[-1]['text'] = text
    if single_topic:
        topics = [dict(topic_id='T', start=0, end=40, evidence_segment_ids=[r['segment_id'] for r in rows])]
    assert not complete(build_story_arcs({'segments': rows}, topics))


@pytest.mark.parametrize('single_topic', [False, True])
def test_explicit_topic_change_blocks_outcome_even_with_shared_word(single_topic):
    rows, topics = fixture()
    rows[2]['text'] = 'Mudando de assunto, vamos falar de outro disco.'
    if single_topic:
        topics = [dict(topic_id='T', start=0, end=40, evidence_segment_ids=[r['segment_id'] for r in rows])]
    assert not complete(build_story_arcs({'segments': rows}, topics))
    arc = recover_story_arcs(rows, topics)[0]
    assert arc['extension_stop_reason'] == 'topic_change_observed'
    assert 'S2' not in arc['evidence_segment_ids']


def test_unrelated_chunk_cannot_supply_payoff():
    rows, topics = fixture()
    rows[2]['text'] = 'A cozinha recebeu panelas novas.'
    rows[3]['text'] = 'Consegui cozinhar o jantar.'
    arc = recover_story_arcs(rows, topics)[0]
    assert arc['payoff'] is None
    assert arc['extension_stop_reason'] == 'cross_chunk_continuity_unresolved'


@pytest.mark.parametrize('shift,max_seconds,reason', [
    (16, 360, 'story_pause_exceeds_window'),
    (0, 35, 'story_time_window_exhausted'),
])
def test_time_limits_leave_explicit_partial(shift, max_seconds, reason):
    rows, topics = fixture()
    for row in rows[2:]:
        row['start'] += shift
        row['end'] += shift
    arc = recover_story_arcs(rows, topics, max_seconds=max_seconds)[0]
    assert arc['payoff'] is None and arc['extension_stop_reason'] == reason


@pytest.mark.parametrize('speaker', [None, 'B'])
def test_outcome_from_unknown_or_other_speaker_is_not_narrator_payoff(speaker):
    rows, topics = fixture()
    rows[-1]['speaker'] = speaker
    assert not complete(build_story_arcs({'segments': rows}, topics))


def test_interruption_is_evidence_but_not_development():
    rows, topics = fixture()
    rows.insert(2, dict(segment_id='I', start=20, end=22, speaker='B', text='Nossa!'))
    rows[3]['start'] = 22
    arc = complete(recover_story_arcs(rows, topics))[0]
    assert arc['interruption_segment_ids'] == ['I']
    assert 'I' in arc['evidence_segment_ids']
    assert 'I' not in arc['development']['segment_ids']


def test_out_of_order_topic_ids_do_not_reverse_components():
    rows, _ = fixture()
    topics = [dict(topic_id='T', start=0, end=40, evidence_segment_ids=['S3', 'S2', 'S1', 'S0'])]
    arc = complete(build_story_arcs({'segments': rows}, topics))[0]
    assert arc['setup']['segment_ids'] == ['S0']
    assert arc['payoff']['segment_ids'] == ['S3']


@pytest.mark.parametrize('speaker', [None, 'B'])
def test_single_topic_cannot_borrow_other_speakers_conflict(speaker):
    rows, _ = fixture()
    rows[1]['speaker'] = speaker
    topics = [dict(topic_id='T', start=0, end=40, evidence_segment_ids=[r['segment_id'] for r in rows])]
    assert not complete(build_story_arcs({'segments': rows}, topics))
