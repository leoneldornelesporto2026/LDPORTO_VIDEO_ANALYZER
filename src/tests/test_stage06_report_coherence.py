import json
from copy import deepcopy
from types import SimpleNamespace
import pytest
from ldporto.core import read_json
from ldporto.reports import ReportEngine
from ldporto.second_curation_export import build_core_package, validate_core_package
from ldporto.integrity_contracts import canonical_report_metrics
from test_v43_handoff import analysis_fixture
from test_s2_pipeline_integrity import _tamper_with_fresh_hashes


def fixture():
    a = analysis_fixture()
    for key in ('editorial_moments questions_answers candidate_hooks candidate_endings timeline speaker_person_mapping silences audio_events ocr_text low_confidence_words transcription_alternatives people_observations scenes person_motion active_speaker speaker_person_summary entities story_arcs camera_timeline master_timeline thumbnail_candidates unaligned_segments').split():
        a.setdefault(key, [])
    a.update(video_understanding={'about': None, 'main_topics': []},
             subtitle_review_s7={'selected_candidate_count': 0, 'total_words': 10,
                'originally_flagged_for_review': 2, 'words_flagged_for_review': 3,
                'candidates': {}, 'audio_verification_performed': False})
    a['metadata']['filename'] = 'synthetic.mp4'
    a['topics'][0]['method'] = 'heuristic'
    a['candidate_metrics'] = {'candidates_before_dedup': 2, 'candidates_after_dedup': 1,
                              'excluded_commercial_count': 999, 'final_shortlist_count': 999}
    return a


@pytest.mark.parametrize('status', ['P0_FAIL', 'P1_DEGRADED'])
def test_offline_report_export_consumers_agree(tmp_path, status):
    a = fixture()
    if status == 'P1_DEGRADED':
        a['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'ok'}}
        a['analysis_quality'].update(diarization_availability=True, micro_track_ratio=.6,
                                     resolved_focus_coverage=0)
        a['people_observations'] = [{'time': 1, 'track_id': 'SYNTHETIC_TRACK', 'person_id': None}]
        a['qa_metrics'] = {'unresolved_question_count': 1}
        a['preview_validation'] = {'status': 'ok', 'verifier_uses_rendered_frames': True, 'sampled_frames': 1}
    ctx = SimpleNamespace(output=tmp_path / 'reports', signature='fixture',
        config={'strict': False, 'export': {'second_curation_output_dir': str(tmp_path / 'packages')}})
    ReportEngine().run(ctx, a, [])
    final = a['final_package_gate']
    assert final['status'] == status
    if status == 'P1_DEGRADED':
        assert {r['code'] for r in final['issues']} == {
            'active_speaker_unavailable', 'fragmented_tracking', 'qa_unresolved', 'unresolved_camera_focus'}
    assert final['publication_ready'] is False
    summary = read_json(ctx.output / 'analysis_summary.json')
    compact = read_json(ctx.output / 'CHATGPT_ANALYSIS_HANDOFF.compact.json')['analysis_summary']
    full = read_json(ctx.output / 'CHATGPT_ANALYSIS_HANDOFF.json')
    video = read_json(ctx.output / 'video_summary.json')
    for doc in (summary, compact, full, video):
        assert doc['candidate_metrics'] == a['candidate_metrics']
        assert doc['quality_gate'] == a['quality_gate']
        assert doc['subtitle_review_metrics'] == a['subtitle_review_metrics']
        assert doc['final_package_gate'] == final
    assert a['analysis_quality']['quality_status'] == final['status']
    assert a['candidate_metrics']['final_shortlist_count'] == len(a['editorial_shortlist'])
    assert a['candidate_metrics']['excluded_commercial_count'] == 0
    from ldporto.compact_artifacts import load_analysis_artifacts
    assert load_analysis_artifacts(ctx.output)['candidate_metrics'] == a['candidate_metrics']


@pytest.mark.parametrize('member,field', [
    ('summary/analysis_summary.json', 'subtitle_review_metrics'),
    ('summary/quality_summary.json', 'subtitle_review_metrics'),
    ('summary/final_quality_gate.json', 'commercial_review_count'),
    ('editorial/final_gate_report.json', 'commercial_review_count'),
])
def test_fresh_checksums_do_not_hide_field_divergences(tmp_path, member, field):
    result = build_core_package(fixture(), output_dir=tmp_path / 'export')
    report = _tamper_with_fresh_hashes(result['path'], tmp_path / 'tampered.zip', member,
                                     lambda obj: obj.update({field: 999}))
    assert report['checksums_valid'] and report['status'] == 'failed'
    assert any('report_field_disagreement:' + member + '.' + field in e for e in report['errors'])


def test_counts_are_unique_and_unknown_review_stays_null():
    candidate = {'candidate_id': 'C1', 'commercial_classification': {'eligibility': 'excluded'}}
    metrics, review = canonical_report_metrics({}, [candidate, deepcopy(candidate)], ['C1', 'C1'],
                                               [{'story_id': 'S1'}, {'story_id': 'S1'}])
    assert metrics['final_candidate_count'] == metrics['excluded_commercial_count'] == 1
    assert metrics['final_shortlist_count'] == metrics['final_story_count'] == 1
    assert review['words_flagged_for_review'] is None
    assert review['audio_verification_performed'] is None
