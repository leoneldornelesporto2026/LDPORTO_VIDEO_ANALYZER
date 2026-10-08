"""S2 negative tests: valid checksums cannot make inconsistent facts trustworthy."""
import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.analysis_quality import quality_gate
from ldporto.integrity_contracts import audit_editorial_contract, derive_review_state
from ldporto.second_curation_export import build_core_package, validate_core_package, generate_visuals_on_demand
from test_v43_handoff import analysis_fixture
from test_v48_r4_homologation import _fake_contact_sheet


def _read(package, member):
    with zipfile.ZipFile(package) as z:
        return json.loads(z.read(member))


def _tamper_with_fresh_hashes(src, dst, member, mutate):
    """Simulate a producer bug, not a corrupt ZIP: rebuild all member hashes."""
    with zipfile.ZipFile(src) as original:
        files = {name: original.read(name) for name in original.namelist()}
    data = json.loads(files[member]); mutate(data)
    files[member] = json.dumps(data, ensure_ascii=False).encode('utf-8')
    manifest = json.loads(files['SECOND_CURATION_MANIFEST.json'])
    manifest['files'] = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                         for name, raw in sorted(files.items()) if name != 'SECOND_CURATION_MANIFEST.json']
    manifest['uncompressed_bytes'] = sum(item['bytes'] for item in manifest['files'])
    manifest['file_count'] = len(files)
    files['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            z.writestr(name, raw)
    return validate_core_package(dst)


@pytest.mark.parametrize('blocked_stage', ['15_semantic', '16_understanding',
                                            '17b_broadcast_graphics', '17c_commercial_visual',
                                            '17d_targeted_asr'])
def test_blocked_upstream_never_approves_shortlist_or_stories(blocked_stage, tmp_path):
    analysis = analysis_fixture()
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'ok'},
                                blocked_stage: {'status': 'failed'}}
    analysis['social_output'] = {'stories': [{'story_id': 'ST1', 'candidate_id': 'M1'}],
                                 'story_readiness': 'READY'}
    analysis['editorial_shortlist'] = ['M1']
    output = build_core_package(analysis, output_dir=tmp_path / blocked_stage)
    assert output['state'] == 'PARTIAL'
    assert not output['readiness']['editorial_ready']
    assert _read(output['path'], 'editorial/default_shortlist.json')['candidate_ids'] == []
    assert _read(output['path'], 'social/stories_manifest.json')['stories'] == []
    assert _read(output['path'], 'social/stories_manifest.json')['story_readiness'] == 'BLOCKED'
    row = _read(output['path'], 'editorial/candidate_catalog.json')['candidates'][0]
    assert row['candidate_state'] == 'PROVISIONAL_UPSTREAM_INCOMPLETE'
    assert not row['default_shortlist_eligible'] and not row['publication_eligible']
    assert validate_core_package(output['path'])['status'] == 'valid'
    assert _read(output['path'], 'SECOND_CURATION_MANIFEST.json')['workflow']['review_state'] == 'PARTIAL'


def test_explicit_p0_quality_gate_blocks_even_when_stage_status_is_ok(tmp_path):
    analysis = analysis_fixture()
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'ok'}}
    analysis['quality_gate'] = {'status': 'P0_FAIL', 'required_missing_capabilities': ['transcription']}
    output = build_core_package(analysis, output_dir=tmp_path)
    assert output['state'] == 'PARTIAL' and not output['readiness']['editorial_ready']
    assert _read(output['path'], 'summary/final_quality_gate.json')['status'] == 'P0_FAIL'
    assert _read(output['path'], 'summary/quality_summary.json')['quality_gate']['status'] == 'P0_FAIL'


def test_missing_understanding_results_cannot_fall_back_to_semantic_as_ready():
    analysis = analysis_fixture()
    analysis['stage_status'] = {'16_understanding': {'status': 'ok'}}
    analysis['editorial_moments'] = [{'moment_id': 'M1', 'possible_start': 30, 'possible_end': 90}]
    analysis['main_moments'] = []
    report = audit_editorial_contract(analysis)
    assert report['status'] == 'blocked'
    assert any(row['path'] == 'main_moments' for row in report['errors'])


def test_malformed_nested_upstream_contract_is_path_specific():
    analysis = analysis_fixture()
    analysis['story_arcs'] = [{'story_arc_id': 'A1'}, ['not_an_arc']]
    report = audit_editorial_contract(analysis)
    assert report['status'] == 'blocked'
    assert any(row['path'] == 'story_arcs[1]' for row in report['errors'])


def test_review_ready_still_never_equals_publish_ready(tmp_path, monkeypatch):
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    analysis = analysis_fixture()
    media = tmp_path / 'mock.avi'; media.write_bytes(b'fixture')
    analysis['social_output'] = {'story_readiness': 'READY', 'stories': [{'story_id': 'ST1', 'candidate_id': 'M1'}]}
    output = build_core_package(analysis, source=media, output_dir=tmp_path / 'ready')
    assert output['state'] == 'READY'
    manifest = _read(output['path'], 'SECOND_CURATION_MANIFEST.json')
    assert manifest['workflow'] == derive_review_state(manifest['readiness'])
    assert manifest['workflow']['review_ready'] is True
    assert manifest['workflow']['review_state'] == 'READY_FOR_REVIEW'
    assert manifest['workflow']['preview_approved'] is False
    assert manifest['workflow']['publication_ready'] is False
    assert _read(output['path'], 'editorial/final_gate_report.json')['publication_ready'] is False
    assert _read(output['path'], 'social/stories_manifest.json')['publication_ready'] is False


@pytest.mark.parametrize('member,mutator,expected', [
    ('CURATION_INDEX.json', lambda obj: obj['workflow'].update(review_ready=True), 'workflow_disagreement'),
    ('editorial/final_gate_report.json', lambda obj: obj.update(excluded_commercial_count=99), 'final_gate_summary_count_disagreement'),
    ('summary/quality_summary.json', lambda obj: obj['final_package_gate'].update(publication_ready=True), 'quality_summary_disagreement'),
    ('summary/analysis_summary.json', lambda obj: obj['candidate_metrics'].update(final_shortlist_count=9), 'final_gate_summary_count_disagreement'),
    ('social/stories_manifest.json', lambda obj: obj.update(publication_ready=True), 'social_story_readiness_or_publication_gate_disagreement'),
    ('editorial/candidate_catalog.json', lambda obj: obj['candidates'][0].update(candidate_state='PROVISIONAL_UPSTREAM_INCOMPLETE'), 'candidate_invalid_eligibility'),
])
def test_validator_rejects_semantic_tampering_even_with_valid_hashes(member, mutator, expected, tmp_path):
    original = build_core_package(analysis_fixture(), output_dir=tmp_path / 'original')
    report = _tamper_with_fresh_hashes(original['path'], tmp_path / 'tampered.zip', member, mutator)
    assert report['status'] == 'failed' and report['checksums_valid']
    assert any(expected in error for error in report['errors']), report['errors']


def test_final_commercial_metrics_identical_in_every_artifact(tmp_path):
    analysis = analysis_fixture()
    ad = deepcopy(analysis['main_moments'][0]); ad['moment_id'] = 'AD'
    ad['commercial_classification'] = {'content_type': 'advertisement', 'commercial_score': .98,
                                       'eligibility': 'excluded', 'block_propagated': True}
    analysis['main_moments'].append(ad)
    analysis['editorial_shortlist'] = ['M1', 'AD']
    analysis['social_output'] = {'stories': [{'story_id': 'ST1', 'candidate_id': 'AD'}]}
    result = build_core_package(analysis, output_dir=tmp_path)
    root = lambda n: _read(result['path'], n)
    metrics = root('summary/analysis_summary.json')['candidate_metrics']
    gate = root('editorial/final_gate_report.json')
    quality = root('summary/quality_summary.json')
    assert len(root('editorial/excluded_commercials.json')) == 1
    assert metrics['excluded_commercial_count'] == gate['excluded_commercial_count'] == quality['candidate_metrics']['excluded_commercial_count'] == 1
    assert metrics['final_shortlist_count'] == gate['final_shortlist_count'] == 1
    assert metrics['final_story_count'] == gate['social_story_count'] == 0
    assert validate_core_package(result['path'])['status'] == 'valid'


def test_technical_preview_not_human_approval():
    analysis = analysis_fixture()
    analysis['preview_validation'] = {'status': 'ok', 'verifier_uses_rendered_frames': True}
    result = quality_gate(analysis, {'diarization': {'enabled': False}, 'vision': {'enabled': False}})
    assert result['preview_technical_verified'] is True
    assert result['preview_approved'] is False and result['publication_ready'] is False


def test_provided_prebuilt_package_cannot_override_a_new_upstream_failure(tmp_path):
    from ldporto.second_curation import build_second_curation_package
    analysis = analysis_fixture()
    prebuilt = build_second_curation_package(analysis)
    assert prebuilt['editorial_integrity_ready'] is True
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'failed'}}
    result = build_core_package(analysis, output_dir=tmp_path, package=prebuilt)
    assert result['state'] == 'PARTIAL'
    assert result['readiness']['editorial_ready'] is False
    assert _read(result['path'], 'editorial/default_shortlist.json')['candidate_ids'] == []


def test_visuals_on_demand_does_not_promote_a_failed_understanding(tmp_path, monkeypatch):
    from ldporto.core import file_hash
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'synthetically hashed source, no actual media required for stub')
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = file_hash(source)
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'failed'}}
    partial = build_core_package(analysis, output_dir=tmp_path / 'partial')
    replay = generate_visuals_on_demand(partial['path'], source, ['M1'], tmp_path / 'visuals')
    assert 'SECOND_CURATION_PARTIAL_ON_DEMAND' in Path(replay['path']).name
    manifest = _read(replay['path'], 'SECOND_CURATION_MANIFEST.json')
    assert manifest['readiness']['editorial_ready'] is False
    assert manifest['workflow']['review_ready'] is False
    assert validate_core_package(replay['path'])['status'] == 'valid'


def test_malformed_json_returns_structured_diagnostic_not_uncaught_exception(tmp_path):
    base = build_core_package(analysis_fixture(), output_dir=tmp_path / 'base')
    bad = tmp_path / 'invalid.zip'
    with zipfile.ZipFile(base['path']) as zin, zipfile.ZipFile(bad, 'w') as zout:
        for name in zin.namelist():
            zout.writestr(name, b'{invalid_json' if name == 'CURATION_INDEX.json' else zin.read(name))
    result = validate_core_package(bad)
    assert result['status'] == 'failed'
    assert any(row.startswith('validation_exception:') for row in result['errors'])
