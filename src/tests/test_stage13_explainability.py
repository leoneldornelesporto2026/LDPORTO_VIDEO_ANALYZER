"""Offline diagnostics: synthetic fixtures and read-only historical S4 evidence."""
import copy
import json
from pathlib import Path
import zipfile

from ldporto.editorial import rank_candidate
from ldporto.editorial_intelligence import select_editorial_shortlist, explain_shortlist


def fixture(cid, **changes):
    return rank_candidate(dict(moment_id=cid, text='Uma reflexão sobre a vida cotidiana.',
        ideal_start=0., ideal_end=40., clean_opening=True, clean_ending=True,
        hook_score=.9, standalone_score=.9, context_requirement='none', **changes))


def test_eligible_doubtful_commercial_incomplete_explained_without_mutation():
    eligible = fixture('eligible')
    doubtful = fixture('doubtful')
    doubtful.update(default_shortlist_eligible=False, commercial_classification={'eligibility': 'review'})
    commercial = fixture('commercial')
    commercial.update(default_shortlist_eligible=False, content_type='advertisement',
                      commercial_classification={'eligibility': 'excluded'})
    incomplete = fixture('incomplete', editorial_blockers=['story_payoff_not_grounded'])
    rows = [eligible, doubtful, commercial, incomplete]
    original = copy.deepcopy(rows)
    selected, report = select_editorial_shortlist(rows)
    assert [r['moment_id'] for r in selected] == ['eligible']
    assert rows == original
    diagnoses = {d['moment_id']: d for d in report['candidate_diagnostics']}
    assert 'commercial_classification:review' in diagnoses['doubtful']['blockers']
    assert diagnoses['commercial']['recovery']['status'] == 'blocked'
    assert diagnoses['incomplete']['recovery']['status'] == 'context_pending'
    assert diagnoses['eligible']['duration']['seconds'] == 40
    assert diagnoses['eligible']['render_readiness']['ready'] is None
    assert all(d['publish_ready'] is False for d in diagnoses.values())
    assert report['unique_rejected_candidates'] == 3
    assert sum(report['exclusion_counts_multilabel'].values()) > 3
    assert report == select_editorial_shortlist(list(reversed(rows)))[1]


def test_missing_proof_has_null_values_and_explicit_reasons():
    _, report = select_editorial_shortlist([{'moment_id': 'missing'}])
    d = report['candidate_diagnostics'][0]
    assert d['editorial']['final_score'] is None
    assert d['editorial']['score_status'] == 'missing'
    assert d['evidence']['confidence'] is None
    assert d['evidence']['status'] == 'missing_source_references'
    assert d['duration']['seconds'] is None
    assert 'quality_gate_details_not_recorded' in d['blockers']


def test_selection_limits_and_repetition_have_explanations():
    rows = [fixture('a'), fixture('b')]
    for r in rows:
        r['story_arc_id'] = 'same'
    _, report = select_editorial_shortlist(rows)
    assert report['exclusion_counts_multilabel']['semantic_repetition'] == 1
    _, report = select_editorial_shortlist(rows, max_items=1)
    assert report['exclusion_counts_multilabel']['shortlist_capacity'] == 1
    for r in rows:
        r['topic_id'] = 'same'
    _, report = select_editorial_shortlist(rows, max_per_topic=1)
    assert report['exclusion_counts_multilabel']['topic_diversity_limit'] == 1


def test_all_52_historical_candidates_receive_stable_diagnostics():
    # Old S4 evidence is input to current offline diagnostic code, not an updated video run.
    evidence = Path(__file__).resolve().parents[2] / 'automacao' / 'evidencias'
    with zipfile.ZipFile(evidence / 'CHATGPT_REVIEW.zip') as archive:
        member = next(p for p in archive.namelist() if p.endswith('/main_moments.json'))
        rows = json.loads(archive.read(member))
    with zipfile.ZipFile(evidence / 'SECOND_CURATION_READY.zip') as archive:
        recorded = json.loads(archive.read('editorial/selection_report_s3.json'))['selection_report']
        selected_ids = json.loads(archive.read('editorial/default_shortlist.json'))['candidate_ids']
    original = copy.deepcopy(rows)
    selected = [r for r in rows if r['moment_id'] in selected_ids]
    report = explain_shortlist(rows, selected, recorded['rejected'])
    assert len(rows) == len(report['candidate_diagnostics']) == 52
    assert len({d['moment_id'] for d in report['candidate_diagnostics']}) == 52
    assert len(selected) == 1
    assert report['unique_rejected_candidates'] == 51
    assert report['exclusion_counts_multilabel']['ineligible_by_quality_gate'] == 51
    assert report == explain_shortlist(list(reversed(rows)), selected, recorded['rejected'])
    assert rows == original
    for d in report['candidate_diagnostics']:
        assert d['selection_reasons'] and d['blocker_status']
        assert d['duration']['status'] and d['evidence']['status'] and d['recovery']['status']
    preserved = next(d for d in report['candidate_diagnostics'] if d['moment_id'] == 'MOMENT_PRESERVED_00005_0000')
    assert 'missing_required_score:hook' in preserved['blockers']
    assert preserved['editorial']['final_score'] == .854
    current_selected, current_report = select_editorial_shortlist(rows)
    assert [r['moment_id'] for r in current_selected] == selected_ids
    # Stage 16 rechecks absolute blockers independently of the old S4 flags.
    # Historical explanations stay historical; current reasons may be stricter.
    for current, historical in zip(current_report['candidate_diagnostics'], report['candidate_diagnostics']):
        assert current['moment_id'] == historical['moment_id']
        assert current['selection_status'] == historical['selection_status']
        assert set(current['blockers']) >= set(historical['blockers'])
        assert current['editorial'] == historical['editorial']


def test_empty_selection_and_invalid_duration_remain_explicit():
    assert select_editorial_shortlist([])[1]['unique_rejected_candidates'] == 0
    rows = [{'moment_id': 'invalid', 'ideal_start': float('nan'), 'ideal_end': 20}]
    _, report = select_editorial_shortlist(rows)
    assert report['candidate_diagnostics'][0]['duration']['seconds'] is None
