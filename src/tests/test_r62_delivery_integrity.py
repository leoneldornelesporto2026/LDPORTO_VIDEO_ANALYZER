"""Small synthetic ledgers: package integrity, parent lineage and approval flags."""
import hashlib
import json
import zipfile

import pytest

from ldporto.core import file_hash
from ldporto.r62_delivery import _reindex, _zip_directory, verify_full_audit, build_visual_delivery


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')


def test_reindex_preserves_parent_and_has_no_master_self_hash_cycle(tmp_path):
    root = tmp_path/'editorial'
    parent = root/'provenance/parent_handoff_master_SNAPSHOT.json'
    write(parent, {'package_revision': 'SYNTHETIC_PARENT', 'preview_approved': False})
    parent_hash = file_hash(parent)
    write(root/'HANDOFF_MASTER.json', {'package_revision': 'SYNTHETIC_CHILD',
        'derivation': {'parent_master_ref': parent.relative_to(root).as_posix(), 'parent_master_sha256': parent_hash},
        'preview_approved': False, 'publication_ready': False})
    write(root/'SECOND_CURATION_MANIFEST.json', {'files': []})
    write(root/'camera/timeline.json', {'synthetic': True, 'render_verified': False})
    _reindex(root)
    before = {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    _reindex(root)
    assert before == {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob('*') if path.is_file()}
    master = json.loads((root/'HANDOFF_MASTER.json').read_text(encoding='utf-8'))
    manifest = json.loads((root/'SECOND_CURATION_MANIFEST.json').read_text(encoding='utf-8'))
    assert master['derivation']['parent_master_sha256'] == parent_hash == file_hash(parent)
    assert all(item['path'] not in {'HANDOFF_MASTER.json', 'SECOND_CURATION_MANIFEST.json'} for item in master['artifacts'])
    assert 'HANDOFF_MASTER.json' in {item['path'] for item in manifest['files']}
    for item in manifest['files']:
        assert file_hash(root/item['path']) == item['sha256']
    assert master['preview_approved'] is False and master['publication_ready'] is False


def test_full_audit_ledger_reopens_and_detects_changed_raw_evidence(tmp_path):
    root = tmp_path/'editorial'
    write(root/'HANDOFF_MASTER.json', {'preview_approved': False, 'publication_ready': False})
    raw = tmp_path/'synthetic_observations.json'
    write(raw, {'observations': [], 'evidence_status': 'SYNTHETIC_FIXTURE'})
    target = tmp_path/'FULL_AUDIT.zip'
    receipt = _zip_directory(root, target, [(raw, 'raw_analysis/observations.json')])
    assert receipt['sha256'] == file_hash(target)
    assert verify_full_audit(target)['status'] == 'valid'
    damaged = tmp_path/'DAMAGED.zip'
    with zipfile.ZipFile(target) as original, zipfile.ZipFile(damaged, 'w') as altered:
        for name in original.namelist():
            altered.writestr(name, b'{"tampered":true}' if name == 'raw_analysis/observations.json' else original.read(name))
    result = verify_full_audit(damaged)
    assert result['status'] == 'failed' and 'full_audit_checksum:raw_analysis/observations.json' in result['errors']
    assert result['publication_ready'] is False


@pytest.mark.parametrize('change', ['wrong_profile', 'automatic_publication', 'malformed_files'])
def test_full_audit_verifier_rejects_invalid_profile_approval_or_structure(tmp_path, change):
    data = b'{"synthetic":true}'
    manifest = {'schema_version': 'r6.2', 'profile': 'FULL_AUDIT', 'source_video_included': False,
                'preview_approved': False, 'publication_ready': False,
                'files': [{'path': 'evidence.json', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}]}
    if change == 'wrong_profile':
        manifest['profile'] = 'UNRECOGNIZED_PROFILE'
    elif change == 'automatic_publication':
        manifest['publication_ready'] = True
    else:
        manifest['files'] = None
    target = tmp_path/'INVALID_FULL.zip'
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('evidence.json', data)
        archive.writestr('FULL_AUDIT_MANIFEST.json', json.dumps(manifest))
    result = verify_full_audit(target)
    assert result['status'] == 'failed' and result['publication_ready'] is False


def test_selective_delivery_keeps_long_reel_caption_gate_separate_from_story_limit(tmp_path):
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    from test_v43_handoff import analysis_fixture
    from ldporto.second_curation_export import build_core_package, validate_core_package

    # A real, small synthetic source with a 70-second Reel. All frames are
    # generated locally; no original, model, download or external service.
    video = tmp_path/'synthetic_120_seconds.avi'
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'MJPG'), 2., (64, 48))
    assert writer.isOpened()
    for index in range(240):
        frame = np.full((48, 64, 3), 30+index % 160, dtype=np.uint8)
        cv2.rectangle(frame, (4+index % 18, 8), (28+index % 18, 36), (90, 200, 30), -1)
        writer.write(frame)
    writer.release()
    analysis = analysis_fixture()
    analysis['metadata'].update(sha256=file_hash(video), width=64, height=48, fps=2.)
    analysis['metadata']['source'].update(id='SYNTHETIC_LONG_REEL')
    analysis['main_moments'][0].update(ideal_start=20., ideal_end=90.)
    analysis['main_moments'][0]['core_moment'].update(start=20., end=90.)
    folder = tmp_path/'analysis'
    write(folder/'analysis.json', analysis)
    write(folder/'run_manifest.json', {'run_id': 'SYNTHETIC_REVISION'})
    package = build_core_package(analysis, output_dir=tmp_path/'core')
    original_hash = file_hash(package['path'])
    result = build_visual_delivery(package['path'], folder, video, tmp_path/'derived',
                                   max_frames=2, global_frames=8)
    assert result['state'] == 'PARTIAL' and result['new_model_calls'] == 0
    assert result['preview_approved'] is False and result['human_approved'] is False
    assert result['publication_ready'] is False and not result['full_pipeline_executed']
    assert original_hash == file_hash(package['path'])
    assert verify_full_audit(result['full_audit']['path'])['status'] == 'valid'
    assert validate_core_package(result['editorial']['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['editorial']['path']) as archive:
        index = json.loads(archive.read('VISUAL_FRAME_HANDOFF/index.json'))
        reviews = json.loads(archive.read('subtitles/visual_piece_caption_preflight.json'))
        reel = next(piece for piece in index['pieces'] if piece['piece_type'] == 'REEL')
        caption = reviews['reels'][reel['piece_id']]
        assert reel['caption_preflight_ref'].endswith('#/reels/'+reel['piece_id'])
        assert 'story_assembled_duration_exceeds_60_seconds' not in caption['reason_codes']
        assert caption['human_approved'] is False and caption['publication_ready'] is False
        master = json.loads(archive.read('HANDOFF_MASTER.json'))
        assert master['active_camera_ref'] == 'camera/r62_shared_camera_handoff.json'
        assert master['full_audit_ref']['sha256'] == result['full_audit']['sha256']
