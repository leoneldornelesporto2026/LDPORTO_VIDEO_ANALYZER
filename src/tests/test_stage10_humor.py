"""Synthetic offline humor boundaries; no claim about audiovisual humor quality."""
from copy import deepcopy

import pytest

from ldporto.editorial import optimize_boundaries, rank_candidate
from ldporto.editorial_intelligence import humor_integrity
from ldporto.understanding import build_main_moments


def seg(sid, start, end, text, speaker='A'):
    return dict(segment_id=sid, start=start, end=end, text=text, speaker=speaker)


@pytest.fixture
def joke():
    return [seg('S', 10, 14, 'Eu fui ao banco pedir dinheiro.'),
            seg('P', 14, 18, 'Só que o gerente pediu dinheiro para mim.'),
            seg('R', 18, 21, '[risos]', 'B')]


def moment(start=14, end=18, ids=None):
    return dict(moment_id='M', start=start, end=end, evidence_segment_ids=ids or ['P'],
                categories=['humor'], text='Só que o gerente pediu dinheiro para mim.',
                context_requirement='none', standalone_class='excellent')


def test_joke_preserves_literal_roles_and_reaction(joke):
    before = deepcopy(joke)
    b = optimize_boundaries(moment(), joke)
    assert (b['ideal_start'], b['ideal_end']) == (10, 21)
    assert b['boundary_segment_ids'] == ['S', 'P', 'R']
    assert b['context_added_before'] == 4 and b['context_added_after'] == 3
    h = humor_integrity(joke, 10, 21, True)
    assert h['blockers'] == []
    assert h['setup']['text'] == joke[0]['text']
    assert h['punchline_candidate']['segment_ids'] == ['P']
    assert h['reaction']['segment_ids'] == ['R']
    assert h['punchline'] is None and h['humor_confirmed'] is None
    assert h['requires_review'] and joke == before


def test_candidate_without_laughter_is_supported_for_review(joke):
    h = humor_integrity(joke[:2], 10, 18, True)
    assert h['blockers'] == [] and h['punchline_candidate']['segment_ids'] == ['P']
    assert h['reaction'] is None and h['humor_confirmed'] is None


def test_interruption_before_grace_remains_blocked():
    rows = [seg('S', 0, 4, 'Eu fui ao banco.'),
            seg('I', 4, 7, 'Pera aí, deixa eu falar.', 'B'),
            seg('P', 7, 11, 'Só que o gerente pediu dinheiro para mim.')]
    h = humor_integrity(rows, 0, 7, True)
    assert 'interruption_before_payoff' in h['blockers']
    assert 'potential_punchline_after_clip' in h['blockers']
    assert h['interruption']['segment_ids'] == ['I']
    assert h['punchline_candidate'] is None


@pytest.mark.parametrize('hinted', [False, True])
def test_audience_laughter_is_reaction_not_joke(hinted):
    h = humor_integrity([seg('R', 0, 3, '[risos]', None)], 0, 3, hinted)
    assert h['classification'] == 'reaction_without_joke_evidence'
    assert h['punchline_candidate'] is None and h['setup'] is None
    assert h['humor_confirmed'] is None
    if hinted:
        assert 'punchline_not_grounded' in h['blockers']


@pytest.mark.parametrize('text', ['[inaudível] [risos]', '[ininteligível]', ''])
def test_missing_asr_does_not_invent_punchline(text):
    h = humor_integrity([seg('X', 0, 4, text)], 0, 4, True)
    assert 'punchline_not_grounded' in h['blockers']
    assert h['punchline_candidate'] is None and h['punchline'] is None
    if text:
        assert h['classification'] == 'asr_phrase_unresolved'


def test_earlier_laughter_does_not_mask_later_payoff():
    rows = [seg('R', 0, 3, '[risos]'), seg('P', 3, 7, 'Só que o gerente pediu dinheiro para mim.')]
    h = humor_integrity(rows, 0, 3, True)
    assert 'potential_punchline_after_clip' in h['blockers']
    assert 'punchline_not_grounded' in h['blockers']


@pytest.mark.parametrize('start,end', [(10, 16), (15, 21)])
def test_source_fragment_is_blocked(joke, start, end):
    assert 'humor_source_segment_truncated' in humor_integrity(joke, start, end, True)['blockers']


@pytest.mark.parametrize('topic,shots', [
    (dict(start=14, end=18), []),
    (None, [dict(start=14, end=18)]),
    (dict(start=0, end=20), []),
])
def test_context_does_not_cross_topic_or_shot(joke, topic, shots):
    b = optimize_boundaries(moment(), joke, topic=topic, shots=shots)
    assert b['ideal_start'] >= (topic['start'] if topic else 14)
    assert b['ideal_end'] <= (topic['end'] if topic else 18)
    assert 'reaction_after_clip' in humor_integrity(joke, b['ideal_start'], b['ideal_end'], True)['blockers']


def test_context_more_than_five_seconds_remains_unresolved(joke):
    joke[-1]['end'] = 24
    b = optimize_boundaries(moment(), joke)
    assert b['ideal_end'] == 18
    assert 'reaction_after_clip' in humor_integrity(joke, 10, 18, True)['blockers']


def test_theme_change_prevents_cue_association(joke):
    joke.insert(2, seg('T', 18, 19, 'Mudando de assunto agora.'))
    joke[-1].update(start=19, end=22)
    b = optimize_boundaries(moment(), joke)
    assert b['ideal_end'] == 18 and b['humor_boundary_proposal']['expansion_unresolved']


def test_source_order_is_deterministic(joke):
    assert humor_integrity(joke, 10, 21, True) == humor_integrity(joke[::-1], 10, 21, True)


def test_main_moments_integrates_bounded_context_and_blocks_ending(joke):
    rows = build_main_moments({'segments': joke}, [], [moment()], [], [], [])
    assert rows[0]['ideal_start'] == 10 and rows[0]['ideal_end'] == 21
    assert rows[0]['humor_integrity']['blockers'] == []
    topic = dict(topic_id='T', start=10, end=18)
    rows = build_main_moments({'segments': joke}, [topic], [moment()], [], [], [])
    assert rows[0]['ideal_end'] == 18
    assert 'reaction_after_clip' in rows[0]['editorial_blockers']
    assert not rows[0]['default_shortlist_eligible']


def test_core_crossing_shot_is_pending(joke):
    shots = [dict(start=10, end=16), dict(start=16, end=25)]
    rows = build_main_moments({'segments': joke}, [], [moment()], [], [], shots)
    assert 'humor_context_exceeds_topic_shot_or_duration' in rows[0]['editorial_blockers']
    assert not rows[0]['default_shortlist_eligible']


def test_high_score_cannot_approve_before_payoff(joke):
    h = humor_integrity(joke, 10, 14, True)
    raw = dict(ideal_start=10, ideal_end=14, text=joke[0]['text'],
               clean_opening=True, clean_ending=True, hook_score=1., standalone_score=1.,
               editorial_blockers=h['blockers'], context_requirement='none')
    assert not rank_candidate(raw)['default_shortlist_eligible']


@pytest.mark.parametrize('text', ['Só que...', 'Mas aí ele disse que',
                                 'Adivinha?', 'Sabe o que aconteceu?'])
def test_teaser_or_truncated_asr_is_not_payoff(text):
    h = humor_integrity([seg('X', 0, 4, text), seg('R', 4, 6, '[risos]')], 0, 6, True)
    assert 'punchline_not_grounded' in h['blockers']
    assert h['punchline_candidate'] is None


def test_interruption_after_candidate_needs_review(joke):
    joke.append(seg('I', 21, 23, 'Não terminei.'))
    h = humor_integrity(joke, 10, 23, True)
    assert 'interruption_after_candidate_unresolved' in h['blockers']


def test_hard_duration_limit_is_preserved(joke):
    b = optimize_boundaries(moment(), joke, cfg={'hard_max_seconds': 5})
    assert (b['ideal_start'], b['ideal_end']) == (14, 18)
    assert b['humor_boundary_proposal']['expansion_unresolved']
