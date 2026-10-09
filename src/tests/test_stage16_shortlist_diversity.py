"""Controlled offline benchmark; labels are synthetic, never media findings."""
from copy import deepcopy
import pytest

from ldporto.editorial_intelligence import select_editorial_shortlist
from ldporto.social_output import select_story_set


def candidate(cid, start=0, score=.9, **changes):
    return dict(moment_id=cid, candidate_id=cid, ideal_start=start, ideal_end=start+40,
                start=start, end=start+40, duration=40, editorial_score_final=score,
                editorial_quality_score=score, default_shortlist_eligible=True,
                topic_id='T', primary_topic_id='T', speaker_ids=['S1'],
                editorial_format='relato', clean_opening=True, clean_ending=True,
                core_moment={'text': cid}, hook_strength=.9, visual_viability=.8,
                score_components={'standalone_clarity': .9}, **changes)


@pytest.mark.parametrize('dimension,change', [
    ('topic', {'topic_id': 'OTHER', 'primary_topic_id': 'OTHER'}),
    ('temporal_segment', {'ideal_start': 1200, 'start': 1200, 'ideal_end': 1240, 'end': 1240}),
    ('participants', {'speaker_ids': ['S2']}),
    ('format', {'editorial_format': 'pergunta'}),
])
def test_each_dimension_breaks_close_quality_ties_after_best(dimension, change):
    a, b, c = candidate('A'), candidate('B', 100, .89), candidate('C', 200, .87)
    c.update(change)
    rows = [a, b, c]
    before = deepcopy(rows)
    selected, report = select_editorial_shortlist(rows, max_items=2, max_per_topic=3)
    assert [r['moment_id'] for r in selected] == ['A', 'C']
    assert rows == before
    assert report == select_editorial_shortlist(list(reversed(rows)), max_items=2, max_per_topic=3)[1]
    d = {d['moment_id']: d for d in report['candidate_diagnostics']}
    assert d['B']['selection_disposition'] == 'alternative'
    assert d['C']['diversity_features'][dimension] != d['A']['diversity_features'][dimension]
    stories, metrics = select_story_set(rows, {'max_stories': 2, 'max_per_topic': 3})
    assert [r['candidate_id'] for r in stories] == ['A', 'C']
    assert next(r for r in metrics['candidate_decisions'] if r['candidate_id'] == 'B')['disposition'] == 'alternative'


def test_controlled_benchmark_no_redundancy_no_twelve_and_quality_first():
    a = candidate('A', score=.98, story_arc_id='ARC')
    duplicate = candidate('COPY', 100, .97, story_arc_id='ARC')
    strong = candidate('STRONG', 200, .92)
    weak = candidate('WEAK', 1200, .3, person_ids=['P2'])
    selected, report = select_editorial_shortlist([a, duplicate, strong, weak])
    assert [r['moment_id'] for r in selected] == ['A', 'STRONG']
    assert report['fixed_quota'] is False and report['unfilled_slots_are_intentional']
    assert report['shortlist_count'] == 2
    assert any('semantic_repetition' in r['reasons'] for r in report['rejected'])
    for selector in (lambda r: select_editorial_shortlist(r), lambda r: select_story_set(r, {})):
        assert [r['candidate_id'] for r in selector([a])[0]] == ['A']


@pytest.mark.parametrize('changes', [
    {'content_type': 'advertisement'},
    {'commercial_classification': {'eligibility': 'excluded'}},
    {'commercial_classification': {'eligibility': 'review'}},
    {'commercial_score': .95},
    {'clean_ending': False},
    {'boundary_blockers': ['confirmed_truncation']},
    {'narrative_integrity': {'status': 'incomplete', 'blockers': ['missing_story_ending']}},
    {'humor_integrity': {'status': 'incomplete', 'blockers': ['reaction_after_clip']}},
])
def test_absolute_blockers_win_over_stale_true_flag_and_diversity(changes):
    unsafe = candidate('UNSAFE', 1200, .99)
    unsafe.update(changes)
    safe = candidate('SAFE')
    rows = [unsafe, safe]
    original = deepcopy(rows)
    selected, report = select_editorial_shortlist(rows)
    assert [r['moment_id'] for r in selected] == ['SAFE']
    assert next(r for r in report['candidate_diagnostics'] if r['moment_id'] == 'UNSAFE')['selection_reasons']
    stories, metrics = select_story_set(rows, {})
    assert [r['candidate_id'] for r in stories] == ['SAFE']
    assert next(r for r in metrics['candidate_decisions'] if r['candidate_id'] == 'UNSAFE')['reasons']
    assert rows == original


def test_missing_proof_and_nonfinite_scores_never_fill_shortlist():
    rows = [{'moment_id': 'MISSING'}, candidate('NAN', score=float('nan'))]
    selected, report = select_editorial_shortlist(rows)
    assert selected == []
    missing = next(d for d in report['candidate_diagnostics'] if d['moment_id'] == 'MISSING')
    assert missing['selection_disposition'] == 'pending'
    assert all(v is None for v in missing['diversity_features'].values())
    assert missing['editorial']['final_score'] is None
    assert missing['publish_ready'] is False


def test_diversity_does_not_displace_clearly_better_material():
    a, b, c = candidate('A', score=.99), candidate('B', 100, .95), candidate('C', 1800, .6)
    c.update(speaker_ids=['S2'], topic_id='NEW', primary_topic_id='NEW', editorial_format='piada')
    assert [r['moment_id'] for r in select_editorial_shortlist([a, b, c], max_items=2)[0]] == ['A', 'B']
    assert [r['candidate_id'] for r in select_story_set([a, b, c], {'max_stories': 2})[0]] == ['A', 'B']


def test_social_quality_floor_capacity_and_unknown_topics_are_not_quotas():
    a, b, c = candidate('A'), candidate('B', 800, .89), candidate('C', 1600, .87)
    b['speaker_ids'] = ['S2']
    c['editorial_format'] = 'pergunta'
    for row in (a, b, c):
        row['topic_id'] = row['primary_topic_id'] = None
    low = candidate('LOW', 2400, .01)
    low.update(hook_strength=0, visual_viability=0, score_components={})
    out, metrics = select_story_set([a, b, c, low], {'max_per_topic': 1})
    assert {r['candidate_id'] for r in out} == {'A', 'B', 'C'}
    assert metrics['selected_count'] == 3 and metrics['fixed_quota'] is False
    assert metrics['rejection_reasons']['below_story_quality_floor'] == 1
    assert select_story_set([a], {'max_stories': 0})[0] == []
    empty, metrics = select_story_set([low], {})
    assert empty == [] and len(metrics['candidate_decisions']) == 1
