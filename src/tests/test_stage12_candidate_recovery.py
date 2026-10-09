"""Offline synthetic recovery cases; no claims of replaying the S4 video."""
from copy import deepcopy

from ldporto.understanding import build_main_moments
from ldporto.story_recovery import candidate_recovery_queue
from ldporto.editorial_intelligence import select_editorial_shortlist
from ldporto.second_curation import build_second_curation_package


def seg(sid, start, end, text):
    return dict(segment_id=sid, start=start, end=end, text=text, speaker='A')


def core(mid='M', start=0, end=35, text='Uma explicação sobre a máquina.'):
    return dict(moment_id=mid, start=start, end=end, text=text,
                evidence_segment_ids=['S'], categories=[], standalone_class='excellent',
                context_requirement='none', editorial={'clarity': .95, 'hook_strength': .95})


def build(source, moments, arcs=None, cfg=None):
    return build_main_moments({'segments': source}, [], moments, [], arcs or [], [], cfg=cfg)


def test_good_candidate_without_payoff_stays_preserved_and_pending():
    source = [seg('S', 0, 10, 'Um dia eu fui consertar a máquina.'),
              seg('D', 10, 35, 'Mas a peça estava quebrada e tentei outra solução.')]
    arc = dict(story_arc_id='STORY', start=0, end=35, kind='partial_story',
               evidence_segment_ids=['S', 'D'], setup={'segment_ids': ['S']},
               development={'segment_ids': ['D']}, payoff=None, standalone_score=None)
    original = core(text=source[0]['text']); original['evidence_segment_ids'] = ['S', 'D']
    item = build(source, [original], [arc])[0]
    recovery = item['recovery']
    assert recovery['status'] == 'context_pending'
    assert recovery['prior_editorial_score'] == .95
    assert {'field': 'payoff', 'value': None, 'status': 'unresolved',
            'reason': 'story_payoff_not_grounded'} in recovery['evidence_gaps']
    assert not item['default_shortlist_eligible']
    assert item['standalone_score'] is None and item['story_completeness'] is None


def test_commercial_is_absolute_blocker_despite_high_prior_score():
    text = 'Oferecimento: o patrocinador deste programa. Use o cupom PORTO e compre agora.'
    item = build([seg('S', 0, 35, text)], [core(text=text)])[0]
    assert 'commercial_content_excluded' in item['recovery']['absolute_blockers']
    assert item['recovery']['status'] == 'blocked'
    assert not item['default_shortlist_eligible']


def test_only_boundary_extension_recovers_then_ranks_observed_context():
    source = [seg('S', 0, 30, 'Nunca contei o segredo porque'),
              seg('D', 30, 35, 'a máquina era um protótipo experimental.')]
    original = core(end=30, text=source[0]['text'])
    saved = deepcopy((source, original))
    item = build(source, [original])[0]
    assert item['ideal_end'] == 35 and item['boundary_decision'] == 'expand'
    assert item['recovery']['status'] == 'recovered_requires_review'
    assert item['recovery']['post_context_editorial_score'] == item['editorial_score_final']
    assert item['recovery']['post_context_editorial_score'] != .95
    assert item['default_shortlist_eligible']
    assert item['recovery']['publish_ready'] is False
    assert (source, original) == saved


def test_preserved_id_with_missing_hook_routes_to_review_without_promotion():
    mid = 'MOMENT_PRESERVED_00005_0000'
    item = build([seg('S', 0, 35, 'Uma explicação sobre a máquina.')], [core(mid)])[0]
    assert item['moment_id'] == mid and item['recovery']['origin'] == 'preserved'
    assert item['recovery']['status'] == 'review_pending'
    gaps = {r['field']: r for r in item['recovery']['evidence_gaps']}
    assert gaps['score_components.hook']['status'] == 'missing'
    assert gaps['score_components.hook']['value'] is None
    assert gaps['payoff']['status'] == 'not_applicable'
    assert gaps['score_components.qa_completeness']['status'] == 'not_applicable'
    assert not item['default_shortlist_eligible']
    assert candidate_recovery_queue([item])[0]['moment_id'] == mid


def test_fallback_and_dedup_alternate_keep_exact_gaps_in_curation():
    source = [seg('S', 0, 35, 'Uma explicação sobre a máquina.')]
    items = build(source, [core('MOMENT_FALLBACK_00000_0000_0000'), core('MOMENT_PRESERVED_00005_0000')])
    assert len(items) == 1 and len(items[0]['alternates']) == 1
    queue = candidate_recovery_queue(items)
    assert len(queue) == 2 and sum(q['alternate_of'] is not None for q in queue) == 1
    assert {q['recovery']['origin'] for q in queue} == {'fallback', 'preserved'}
    exported = build_second_curation_package({'main_moments': items, 'metadata': {},
                                              'transcript_segments': source})['candidates']
    assert len(exported) == 2
    assert all(row['recovery']['evidence_gaps'] for row in exported)


def test_no_minimum_shortlist_and_no_fabricated_evidence_for_missing_source():
    items = build([], [core('MOMENT_FALLBACK_00000_0000_0000')])
    selected, _ = select_editorial_shortlist(items)
    assert selected == []
    assert items[0]['clean_opening'] is None
    gaps = items[0]['recovery']['evidence_gaps']
    assert any(g['field'] == 'context.missing_segment_evidence' and g['status'] == 'missing' for g in gaps)


def test_forbidden_extension_does_not_become_recovered():
    source = [seg('S', 0, 30, 'Nunca contei o segredo porque'),
              seg('D', 30, 35, 'a máquina era um protótipo experimental.')]
    item = build(source, [core(end=30, text=source[0]['text'])], cfg={'hard_max_seconds': 32})[0]
    assert item['ideal_end'] == 30
    assert item['recovery']['status'] == 'blocked'
    assert 'duration_budget_exceeded' in item['recovery']['absolute_blockers']
    assert not item['default_shortlist_eligible']
