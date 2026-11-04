"""Offline synthetic contracts; no commercial truth or human approval fabricated."""
from copy import deepcopy
import json
import zipfile

import pytest

from ldporto.integrity_contracts import audit_editorial_contract, stage_capability, derive_review_state
from ldporto.commercial_gate import apply_commercial_refinement, targeted_ocr
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


def read(path, name):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read(name))


def disabled_analysis():
    analysis = analysis_fixture()
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'ok'},
        '17c_commercial_visual': {'status': 'skipped', 'reason': 'ocr_disabled'}}
    analysis['commercial_visual_s8'] = targeted_ocr('never_opened.mp4', [], {'enabled': False})
    analysis['quality_gate'] = {'status': 'P0_FAIL',
        'required_missing_capabilities': ['visual_tracking_unavailable', 'ocr_disabled']}
    return analysis


@pytest.mark.parametrize('row,state', [
    ({'status': 'ok'}, 'measured_ok'),
    ({'status': 'partial'}, 'measured_partial'),
    ({'status': 'skipped', 'reason': 'ocr_disabled'}, 'not_measured_disabled'),
    ({'status': 'unavailable', 'reason': 'missing_dependency'}, 'unavailable_dependency'),
    ({'status': 'failed'}, 'failed'),
    ({'status': 'partial', 'measured_frames': 0, 'failed_frames_or_ocr': 3}, 'failed'),
])
def test_v1_status_and_reason_are_preserved(row, state):
    original = deepcopy(row)
    result = stage_capability(row)
    assert result['state'] == state and result['legacy_status'] == row['status']
    if row.get('reason'):
        assert result['reason'] == row['reason']
    assert row == original


def test_disabled_ocr_keeps_editorial_queue_and_blocks_commercial_release(tmp_path):
    analysis = disabled_analysis()
    analysis['social_output'] = {'stories': [{'story_id': 'ST1', 'candidate_id': 'M1'}]}
    contract = audit_editorial_contract(analysis)
    assert contract['editorial_integrity_ready']
    assert '17c_commercial_visual' in contract['capability_contract']['unmeasured_capabilities']
    package = build_second_curation_package(analysis)
    row = package['candidates'][0]
    assert row['eligible_for_human_review'] and not row['publication_ready']
    assert row['commercial_classification']['eligibility'] == 'review'
    result = build_core_package(analysis, output_dir=tmp_path)
    assert result['readiness']['editorial_ready']
    assert result['readiness']['commercial_ready'] is False
    manifest = read(result['path'], 'SECOND_CURATION_MANIFEST.json')
    assert manifest['workflow']['provisional_review_ready']
    assert manifest['workflow']['publication_ready'] is False
    assert manifest['readiness_reasons']['commercial_ready'] == 'commercial_visual_not_measured_disabled'
    assert read(result['path'], 'editorial/provisional_review_queue.json')['candidate_ids'] == ['M1']
    assert read(result['path'], 'editorial/default_shortlist.json')['candidate_ids'] == []
    assert read(result['path'], 'social/stories_manifest.json')['stories'] == []
    assert validate_core_package(result['path'])['status'] == 'valid'


@pytest.mark.parametrize('structural', ['16_understanding', '04_transcription'])
def test_disabled_ocr_never_masks_required_failure(structural):
    analysis = disabled_analysis()
    analysis['stage_status'][structural] = {'status': 'failed'}
    assert audit_editorial_contract(analysis)['editorial_integrity_ready'] is False


def test_structural_p0_cannot_be_relabeled_as_capacity_gap():
    analysis = disabled_analysis()
    analysis['quality_gate']['required_missing_capabilities'].append('transcription')
    assert not audit_editorial_contract(analysis)['editorial_integrity_ready']


def test_known_commercial_exclusion_dominates_disabled_ocr(tmp_path):
    analysis = disabled_analysis()
    analysis['main_moments'][0]['commercial_classification'] = {
        'content_type': 'advertisement', 'commercial_score': .98, 'eligibility': 'excluded'}
    result = build_core_package(analysis, output_dir=tmp_path)
    row = read(result['path'], 'editorial/candidate_catalog.json')['candidates'][0]
    assert row['commercial_classification']['eligibility'] == 'excluded'
    assert not row['eligible_for_human_review']
    assert read(result['path'], 'editorial/provisional_review_queue.json')['candidate_ids'] == []


@pytest.mark.parametrize('visual', [
    {'status': 'partial', 'measured_frames': 0, 'failed_frames_or_ocr': 3, 'texts': []},
    {'status': 'unavailable', 'reason': 'optional_tesseract_missing', 'texts': []},
    {'status': 'measured', 'inspected_candidate_ids': ['OTHER'], 'texts': []},
])
def test_ocr_error_dependency_or_uninspected_candidate_never_eligible(visual, tmp_path):
    analysis = analysis_fixture()
    analysis['commercial_visual_s8'] = visual
    refined = apply_commercial_refinement(analysis, analysis['transcript_segments'], [], {}, commercial_visual=visual)
    assert refined['main_moments'][0]['commercial_classification']['eligibility'] == 'review'
    assert not refined['editorial_shortlist']
    result = build_core_package(analysis, output_dir=tmp_path)
    row = read(result['path'], 'editorial/candidate_catalog.json')['candidates'][0]
    assert row['commercial_classification']['eligibility'] == 'review'
    assert not row['publication_eligible'] and not row['publication_ready']


def test_legacy_schema_retains_editorial_behavior_and_unknown_visual_readiness(tmp_path):
    result = build_core_package(analysis_fixture(), output_dir=tmp_path)
    assert result['readiness']['editorial_ready']
    assert result['readiness']['commercial_ready'] is None
    manifest = read(result['path'], 'SECOND_CURATION_MANIFEST.json')
    assert manifest['schema_version'] == '1.0'
    assert not manifest['workflow']['publication_ready']
    assert validate_core_package(result['path'])['status'] == 'valid'


def test_v1_workflow_without_new_readiness_field_keeps_old_shape():
    workflow = derive_review_state({'editorial_ready': True, 'transcript_ready': True, 'visual_ready': True})
    assert workflow['review_ready'] and workflow['publication_ready'] is False
    assert 'provisional_review_ready' not in workflow


@pytest.mark.parametrize('status,state', [('failed', 'failed'), ('unavailable', 'unavailable_dependency')])
def test_payload_cannot_clear_explicit_stage_loss(status, state):
    analysis = disabled_analysis()
    analysis['stage_status']['17c_commercial_visual'] = {'status': status, 'reason': 'real_stage_loss'}
    analysis['commercial_visual_s8'] = {'status': 'measured', 'measured_frames': 3}
    report = audit_editorial_contract(analysis)
    capability = report['capability_contract']['stages']['17c_commercial_visual']
    assert capability['state'] == state and capability['reason'] == 'real_stage_loss'
    assert not report['editorial_integrity_ready']


def test_wrapper_status_and_payload_loss_reason_both_survive():
    analysis = disabled_analysis()
    analysis['stage_status']['17c_commercial_visual'] = {'status': 'skipped'}
    capability = audit_editorial_contract(analysis)['capability_contract']['stages']['17c_commercial_visual']
    assert capability['legacy_status'] == 'skipped'
    assert capability['reason'] == 'ocr_disabled'
    assert capability['state'] == 'not_measured_disabled'


def test_missing_reference_blocks_provisional_queue(tmp_path):
    analysis = disabled_analysis()
    analysis['main_moments'][0]['topic_id'] = 'BROKEN'
    result = build_core_package(analysis, output_dir=tmp_path)
    assert not result['readiness']['editorial_ready']
    assert read(result['path'], 'editorial/provisional_review_queue.json')['candidate_ids'] == []


def test_validator_rejects_clearing_unknown_commercial_with_fresh_hashes(tmp_path):
    from test_s2_pipeline_integrity import _tamper_with_fresh_hashes
    result = build_core_package(disabled_analysis(), output_dir=tmp_path / 'original')
    report = _tamper_with_fresh_hashes(result['path'], tmp_path / 'tampered.zip',
        'editorial/candidate_catalog.json', lambda obj:
        obj['candidates'][0]['commercial_classification'].update(eligibility='eligible'))
    assert report['status'] == 'failed' and report['checksums_valid']
    assert 'commercial_unknown_eligible:M1' in report['errors']
