"""Offline capability and transition fixtures; no real render or human approval."""
import pytest

from ldporto.analysis_quality import quality_gate
from ldporto.core import file_hash
from ldporto.integrity_contracts import preview_technical_readiness
from ldporto.second_curation_export import build_core_package, generate_visuals_on_demand, validate_core_package
from test_s2_pipeline_integrity import _read, _tamper_with_fresh_hashes
from test_v43_handoff import analysis_fixture
from test_v48_r4_homologation import _fake_contact_sheet


@pytest.mark.parametrize('evidence,expected', [
    ({}, None),
    ({'status': 'ok', 'verifier_uses_rendered_frames': True}, None),
    ({'status': 'ok', 'verifier_uses_rendered_frames': True, 'sampled_frames': 0}, False),
    ({'status': 'ok', 'verifier_uses_rendered_frames': False, 'sampled_frames': 3}, False),
    ({'status': 'failed', 'verifier_uses_rendered_frames': True, 'sampled_frames': 3}, False),
    ({'status': 'ok', 'verifier_uses_rendered_frames': True, 'sampled_frames': 3}, True),
])
def test_preview_requires_sampled_render_evidence(evidence, expected, tmp_path):
    analysis = analysis_fixture()
    analysis['preview_validation'] = evidence
    assert preview_technical_readiness(evidence) is expected
    assert quality_gate(analysis)['preview_technical_verified'] is expected
    output = build_core_package(analysis, output_dir=tmp_path)
    assert output['readiness']['preview_ready'] is expected
    workflow = _read(output['path'], 'SECOND_CURATION_MANIFEST.json')['workflow']
    assert workflow['preview_technical_ready'] is (expected is True)
    assert workflow['preview_approved'] is False
    assert workflow['publication_ready'] is False


@pytest.mark.parametrize('quality_status,missing', [
    ('P1_DEGRADED', []), ('P0_FAIL', ['visual_tracking_unavailable']),
])
def test_camera_failure_and_absent_face_allow_evidenced_editorial_review(quality_status, missing, tmp_path, monkeypatch):
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    source = tmp_path / 'fixture.mp4'
    source.write_bytes(b'synthetic source for contact sheet stub')
    analysis = analysis_fixture()
    analysis['stage_status'] = {'15_semantic': {'status': 'ok'}, '16_understanding': {'status': 'ok'},
                                '08_person_reid': {'status': 'failed'}, '19_camera_director': {'status': 'failed'}}
    analysis['quality_gate'] = {'status': quality_status, 'required_missing_capabilities': missing}
    analysis['analysis_quality']['resolved_focus_coverage'] = 0
    output = build_core_package(analysis, source=source, output_dir=tmp_path / 'export')
    manifest = _read(output['path'], 'SECOND_CURATION_MANIFEST.json')
    assert analysis['analysis_status'] == 'partial'
    assert manifest['readiness']['editorial_ready'] is True
    assert manifest['readiness']['camera_ready'] is False
    assert manifest['workflow']['review_state'] == 'READY_FOR_REVIEW'
    assert manifest['workflow']['publication_ready'] is False
    assert manifest['workflow']['preview_approved'] is False
    assert manifest['readiness']['preview_ready'] is None


@pytest.mark.parametrize('status', ['failed', 'pending', 'unknown', 'skipped'])
def test_semantic_failure_or_unknown_cannot_be_review_ready(status, tmp_path):
    analysis = analysis_fixture()
    analysis['stage_status'] = {'15_semantic': {'status': status}}
    output = build_core_package(analysis, output_dir=tmp_path)
    assert output['state'] == 'PARTIAL'
    assert output['readiness']['editorial_ready'] is False


def test_missing_artifact_upload_requires_fresh_preview_verification(tmp_path, monkeypatch):
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', lambda *args: {'status': 'unavailable'})
    source = tmp_path / 'fixture.mp4'
    source.write_bytes(b'synthetic source for offline upload transition')
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = file_hash(source)
    analysis['preview_validation'] = {'status': 'ok', 'verifier_uses_rendered_frames': True, 'sampled_frames': 3}
    initial = build_core_package(analysis, output_dir=tmp_path / 'initial')
    assert initial['readiness']['visual_ready'] is False
    monkeypatch.setattr('ldporto.second_curation_export.build_contact_sheet', _fake_contact_sheet)
    replay = generate_visuals_on_demand(initial['path'], source, ['M1'], tmp_path / 'replay')
    manifest = _read(replay['path'], 'SECOND_CURATION_MANIFEST.json')
    assert manifest['readiness']['visual_ready'] is True
    assert manifest['readiness']['preview_ready'] is None
    assert manifest['workflow']['review_state'] == 'READY_FOR_REVIEW'
    assert manifest['workflow']['preview_approved'] is False
    assert manifest['workflow']['publication_ready'] is False
    assert validate_core_package(replay['path'])['status'] == 'valid'


def test_preview_flags_cannot_override_missing_frames_with_fresh_checksums(tmp_path):
    analysis = analysis_fixture()
    analysis['preview_validation'] = {'status': 'ok', 'verifier_uses_rendered_frames': True, 'sampled_frames': 3}
    output = build_core_package(analysis, output_dir=tmp_path / 'initial')
    report = _tamper_with_fresh_hashes(output['path'], tmp_path / 'tampered.zip',
                                     'summary/preview_validation.json', lambda obj: obj.update(sampled_frames=0))
    assert report['checksums_valid'] and report['status'] == 'failed'
    assert 'preview_ready_without_rendered_frame_evidence' in report['errors']


@pytest.mark.parametrize('change', ['approval_missing', 'decision', 'source', 'package', 'preview'])
def test_existing_human_hash_gate_rejects_missing_or_stale_approval(change, tmp_path):
    from ldporto.curator_delivery import canonical_hash, verify_approval
    # Arbitrary bytes test hash invalidation only, never MP4 validity or approval.
    paths = {}
    for name in ('source', 'package', 'preview'):
        paths[name] = tmp_path / name
        paths[name].write_bytes(('synthetic ' + name).encode())
    plan = {'source_video': str(paths['source']), 'source_sha256': file_hash(paths['source']),
            'package_path': str(paths['package']), 'package_sha256': file_hash(paths['package']),
            'clips': [{'id': 'SYNTHETIC', 'duration': 1}]}
    plan['plan_sha256'] = canonical_hash(plan)
    approval = {'batch_authorized': True, 'plan_sha256': plan['plan_sha256'],
                'source_sha256': plan['source_sha256'], 'package_sha256': plan['package_sha256'],
                'canary_sha256': file_hash(paths['preview']),
                'checklist': {key: True for key in ('editorial', 'commercial', 'subtitles', 'camera', 'audio', 'safe_area', 'payoff')}}
    if change == 'approval_missing':
        approval = {}
    elif change == 'decision':
        plan['clips'][0]['duration'] = 2
    else:
        paths[change].write_bytes(b'changed synthetic artifact')
    with pytest.raises(ValueError, match='TAMPERED|MODIFIED|INVALIDATED_OR_INCOMPLETE'):
        verify_approval(plan, approval, {'file': str(paths['preview'])})
