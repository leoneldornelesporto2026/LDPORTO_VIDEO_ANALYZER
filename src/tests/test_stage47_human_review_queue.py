"""Stage 47: synthetic offline review queue; never real commercial/human evidence."""
from copy import deepcopy
import json
import zipfile
import pytest
from test_v43_handoff import analysis_fixture
from test_stage43_capability_contract import disabled_analysis, read
from ldporto.second_curation_export import build_core_package, validate_core_package
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_decisions import compile_decisions
from test_v44_second_curation import decisions, catalog


def test_optional_failed_ocr_keeps_grounded_provisional_queue(tmp_path):
    analysis = disabled_analysis()
    analysis['stage_status']['17c_commercial_visual'] = {'status': 'failed', 'reason': 'optional_ocr_failure'}
    result = build_core_package(analysis, output_dir=tmp_path)
    queue = read(result['path'], 'editorial/human_review_queue.json')
    assert queue['candidate_ids'] == ['M1']
    entry = queue['entries'][0]
    assert entry['human_review_provisional'] and entry['priority'] == 'commercial_review'
    assert entry['segment_ids'] == ['S1']
    assert read(result['path'], 'editorial/default_shortlist.json')['candidate_ids'] == []
    assert read(result['path'], 'social/stories_manifest.json')['stories'] == []
    with zipfile.ZipFile(result['path']) as archive:
        assert entry['transcript_ref'] in archive.namelist()
        assert entry['candidate_ref'] in archive.namelist()
    assert validate_core_package(result['path'])['status'] == 'valid'
    metrics = read(result['path'], 'summary/analysis_summary.json')['candidate_metrics']
    assert {k: metrics[k] for k in ('discovered', 'review_queue', 'shortlist', 'approved', 'rendered')} == {
        'discovered': 1, 'review_queue': 1, 'shortlist': 0, 'approved': 0, 'rendered': None}


@pytest.mark.parametrize('explicit', [False, True])
def test_preserved_alternatives_share_one_editorial_slot(tmp_path, explicit):
    analysis = analysis_fixture()
    first = analysis['main_moments'][0]
    first['moment_id'] = 'MOMENT_PRESERVED_00032_0002'
    second = deepcopy(first)
    second['moment_id'] = 'MOMENT_PRESERVED_00032_0005'
    if explicit:
        second.update(ideal_start=31, alternate_of=first['moment_id'])
    analysis['main_moments'].append(second)
    analysis['editorial_shortlist'] = [first['moment_id'], second['moment_id']]
    result = build_core_package(analysis, output_dir=tmp_path)
    queue = read(result['path'], 'editorial/human_review_queue.json')
    assert queue['candidate_ids'] == [first['moment_id']]
    assert queue['entries'][0]['alternative_ids'] == [second['moment_id']]
    assert read(result['path'], 'editorial/default_shortlist.json')['candidate_ids'] == [first['moment_id']]
    assert validate_core_package(result['path'])['status'] == 'valid'


def test_replay_and_manual_proposal_never_inherit_human_approval():
    analysis = disabled_analysis()
    analysis['main_moments'][0].update(human_approved=True, publication_ready=True)
    row = build_second_curation_package(analysis)['candidates'][0]
    assert not row['human_approved'] and not row['publication_ready']
    proposal = compile_decisions(decisions(), catalog(), {'sha256': 'HASH', 'duration': 100})[0]
    assert proposal['needs_review'] and not proposal['human_approved'] and not proposal['publication_ready']
    assert compile_decisions(decisions('reject'), catalog(), {'sha256': 'HASH', 'duration': 100}) == []


def test_queue_tampering_rejected_even_with_updated_checksums(tmp_path):
    from test_s2_pipeline_integrity import _tamper_with_fresh_hashes
    result = build_core_package(disabled_analysis(), output_dir=tmp_path / 'original')
    report = _tamper_with_fresh_hashes(result['path'], tmp_path / 'tampered.zip',
        'editorial/human_review_queue.json', lambda obj: obj.update(candidate_ids=[]))
    assert report['status'] == 'failed' and report['checksums_valid']
    assert 'human_review_queue_disagreement' in report['errors']


def test_transcription_failure_does_not_create_review_evidence(tmp_path):
    analysis = disabled_analysis()
    analysis['stage_status']['04_transcription'] = {'status': 'failed'}
    result = build_core_package(analysis, output_dir=tmp_path)
    assert read(result['path'], 'editorial/human_review_queue.json')['candidate_ids'] == []
