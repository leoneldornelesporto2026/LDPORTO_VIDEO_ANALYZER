"""Only isolated synthetic projects: no original media, GPU, services or deletion."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ldporto import storage


def project(tmp_path):
    root = tmp_path / 'synthetic_project'
    (root / 'audio').mkdir(parents=True)
    (root / 'audio' / 'original.wav').write_bytes(b'regenerable-audio')
    (root / 'analysis.json').write_text(json.dumps({
        'metadata': {'source': {'title': 'Synthetic show', 'id': 'synthetic-id'}}
    }), encoding='utf-8')
    (root / 'run_manifest.json').write_text(json.dumps({
        'analysis_status': 'partial', 'created_at': '2026-10-16T00:00:00Z'
    }), encoding='utf-8')
    return root


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('inside', [False, True])
def test_original_video_never_enters_cleanup_even_with_legacy_include_source(tmp_path, inside):
    root = project(tmp_path)
    source = (root if inside else tmp_path) / 'source.mp4'
    source.write_bytes(b'ORIGINAL')
    preview = storage.cleanup_preview(root, source, include_source=True)
    assert preview['optional_source'] is None
    assert preview['include_source_allowed'] is False
    assert str(source) not in {row['path'] for row in preview['removable']}
    storage.execute_cleanup(preview, confirmed=True)
    assert source.read_bytes() == b'ORIGINAL'


def test_original_audio_supplied_as_source_is_protected(tmp_path):
    root = project(tmp_path)
    source = root / 'audio' / 'original.wav'
    preview = storage.cleanup_preview(root, source, include_source=True)
    assert preview['removable'] == []
    assert storage.execute_cleanup(preview, confirmed=True)['removed_bytes'] == 0
    assert source.exists()


def test_default_inventory_and_preview_are_read_only_and_confirmation_is_exact(tmp_path):
    root = project(tmp_path)
    before = snapshot(root)
    preview = storage.cleanup_preview(root)
    rows = storage.list_projects(tmp_path)
    assert rows[0]['name'] == 'Synthetic show'
    assert rows[0]['video_id'] == 'synthetic-id'
    assert rows[0]['status'] == 'partial'
    assert rows[0]['read_only'] is True
    assert rows[0]['last_used_basis'] == 'latest_artifact_modification_not_access_time'
    for invalid in (False, None, 1, 'yes'):
        with pytest.raises(ValueError):
            storage.execute_cleanup(preview, confirmed=invalid)
    assert snapshot(root) == before
    assert not (root / storage.QUARANTINE_DIR).exists()


def test_quarantine_and_restore_round_trip_preserves_protected_artifacts(tmp_path):
    root = project(tmp_path)
    for name in ('transcript.txt', 'transcript.srt', 'words.json', 'camera_plan.json',
                 'SECOND_CURATION_READY.zip', 'PREVIEW_APPROVED.json', 'FINAL.mp4'):
        (root / name).write_bytes(b'PROTECTED ' + name.encode())
    before = snapshot(root)
    preview = storage.cleanup_preview(root)
    result = storage.execute_cleanup(preview, confirmed=True)
    assert result['quarantined_bytes'] == len(b'regenerable-audio')
    assert result['reclaimed_bytes'] == 0
    assert result['errors'] == []
    assert not (root / 'audio' / 'original.wav').exists()
    assert storage.cleanup_preview(root)['removable'] == []
    assert storage.list_quarantines(root)[0]['quarantine_id'] == result['quarantine_id']
    plan = storage.restore_preview(root, result['quarantine_id'])
    assert plan['restorable_bytes'] == result['quarantined_bytes']
    with pytest.raises(ValueError):
        storage.restore_quarantine(root, result['quarantine_id'])
    restored = storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)
    assert restored['restored_bytes'] == result['quarantined_bytes']
    assert restored['skipped'] == []
    after = snapshot(root)
    assert all(after[name] == checksum for name, checksum in before.items())
    assert storage.list_quarantines(root)[0]['file_count'] == 0


def test_same_size_same_mtime_content_change_is_rejected_by_hash(tmp_path):
    root = project(tmp_path)
    path = root / 'audio' / 'original.wav'
    preview = storage.cleanup_preview(root)
    stat = path.stat()
    path.write_bytes(b'X' * stat.st_size)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    result = storage.execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0
    assert path.read_bytes() == b'X' * stat.st_size


@pytest.mark.parametrize('owner', [str(os.getpid()), '0', '-1', 'unknown-owner'])
def test_live_or_unknown_project_ownership_blocks_cleanup(tmp_path, owner):
    root = project(tmp_path)
    preview = storage.cleanup_preview(root)
    (root / 'RUNNING.lock').write_text(owner, encoding='utf-8')
    assert storage.cleanup_preview(root)['removable'] == []
    assert storage.execute_cleanup(preview, confirmed=True)['removed_bytes'] == 0
    assert (root / 'audio' / 'original.wav').exists()


def test_corrupt_lease_is_not_treated_as_safe(tmp_path):
    root = project(tmp_path)
    path = root / 'audio' / 'original.wav'
    (path.parent / '.ldporto_media_use_unknown.json').write_text('{broken', encoding='utf-8')
    assert storage.media_in_use(path) is True
    assert storage.cleanup_preview(root)['removable'] == []


def test_lease_acquired_after_preview_blocks_move(tmp_path):
    root = project(tmp_path)
    preview = storage.cleanup_preview(root)
    path = root / 'audio' / 'original.wav'
    with storage.media_lease(path):
        result = storage.execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0 and path.exists()


def test_cancellation_keeps_all_files_and_creates_no_quarantine(tmp_path):
    root = project(tmp_path)
    preview = storage.cleanup_preview(root)
    before = snapshot(root)
    result = storage.execute_cleanup(preview, confirmed=True, cancel=lambda: True)
    assert result['cancelled'] is True
    assert result['removed_bytes'] == 0 and snapshot(root) == before


def test_forged_external_candidate_is_skipped(tmp_path):
    root = project(tmp_path)
    outside = tmp_path / 'outside.wav'
    outside.write_bytes(b'other-project')
    preview = storage.cleanup_preview(root)
    preview['removable'] = [{'path': str(outside), 'bytes': outside.stat().st_size,
                             'mtime_ns': outside.stat().st_mtime_ns, 'sha256': storage._hash(outside)}]
    result = storage.execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0 and outside.read_bytes() == b'other-project'


def test_traversal_and_application_root_are_rejected(tmp_path):
    root = project(tmp_path)
    with pytest.raises(ValueError):
        storage.cleanup_preview(root / '..')
    from ldporto.paths import PROJECT_ROOT
    with pytest.raises(ValueError):
        storage.cleanup_preview(PROJECT_ROOT)
    with pytest.raises(ValueError):
        storage.restore_preview(root, '../outside')


def test_reparse_ancestor_is_rejected_before_resolve(tmp_path, monkeypatch):
    root = project(tmp_path)
    original_lstat = Path.lstat
    def reparse_stat(path, *args, **kwargs):
        stat = original_lstat(path, *args, **kwargs)
        if path == root / 'audio':
            return SimpleNamespace(st_file_attributes=0x400, st_mode=stat.st_mode)
        return stat
    monkeypatch.setattr(Path, 'lstat', reparse_stat)
    with pytest.raises(ValueError):
        storage._safe_path(root / 'audio' / 'original.wav')
    assert storage.cleanup_preview(root)['removable'] == []


def test_symbolic_link_ancestor_cannot_reach_another_project(tmp_path):
    root = project(tmp_path)
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'external.wav').write_bytes(b'not-owned')
    link = root / 'audio' / 'external_link'
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip('Windows symlink privilege unavailable: ' + str(exc))
    before = (external / 'external.wav').read_bytes()
    preview = storage.cleanup_preview(root)
    assert str(link / 'external.wav') not in {row['path'] for row in preview['removable']}
    storage.execute_cleanup(preview, confirmed=True)
    assert (external / 'external.wav').read_bytes() == before
    with pytest.raises(ValueError):
        storage.cleanup_preview(link)


@pytest.mark.parametrize('subdirectory', ['revisions/r1', 'approved', 'approvals', 'final_renders'])
def test_protected_revisions_and_approvals_remain_outside_whitelist(tmp_path, subdirectory):
    root = project(tmp_path)
    protected = root / 'audio' / subdirectory / 'protected.wav'
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b'protected')
    preview = storage.cleanup_preview(root)
    assert str(protected) not in {row['path'] for row in preview['removable']}
    storage.execute_cleanup(preview, confirmed=True)
    assert protected.read_bytes() == b'protected'


def test_move_or_disk_failure_preserves_original_and_pending_receipt(tmp_path, monkeypatch):
    root = project(tmp_path)
    preview = storage.cleanup_preview(root)
    def fail_move(*args, **kwargs):
        raise OSError(28, 'synthetic disk failure')
    monkeypatch.setattr(storage, '_move_no_replace', fail_move)
    result = storage.execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0 and result['errors']
    assert (root / 'audio' / 'original.wav').read_bytes() == b'regenerable-audio'
    assert storage.restore_preview(root, result['quarantine_id'])['restorable_bytes'] == 0


def test_receipt_write_failure_preserves_original(tmp_path, monkeypatch):
    root = project(tmp_path)
    preview = storage.cleanup_preview(root)
    def fail_replace(*args, **kwargs):
        raise OSError(28, 'synthetic disk full before move')
    monkeypatch.setattr(os, 'replace', fail_replace)
    result = storage.execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0 and result['errors']
    assert (root / 'audio' / 'original.wav').read_bytes() == b'regenerable-audio'


def test_restore_collision_and_quarantine_tampering_preserve_both_files(tmp_path):
    root = project(tmp_path)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    path = root / 'audio' / 'original.wav'
    path.write_bytes(b'new-regenerable-audio')
    restored = storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)
    assert restored['restored_bytes'] == 0
    assert restored['skipped'][0]['reason'] == 'destination_exists'
    assert path.read_bytes() == b'new-regenerable-audio'
    stored = Path(result['quarantine_path']) / 'files' / 'audio' / 'original.wav'
    stored.write_bytes(b'changed')
    assert storage.restore_preview(root, result['quarantine_id'])['restorable_bytes'] == 0


def test_restore_tampered_relative_reference_never_reaches_outside_project(tmp_path):
    root = project(tmp_path)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    receipt_path = Path(result['quarantine_path']) / 'manifest.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    receipt['files'][0]['relative_path'] = '../../outside.wav'
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    restored = storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)
    assert restored['restored_bytes'] == 0 and restored['skipped']
    assert not (tmp_path / 'outside.wav').exists()


def test_project_export_exists_does_not_claim_verified_without_validator(tmp_path):
    root = project(tmp_path)
    external = tmp_path / 'organized-export'
    external.mkdir()
    (root / 'project_export.json').write_text(json.dumps({'path': str(external)}), encoding='utf-8')
    before = snapshot(tmp_path)
    row = storage.list_projects(tmp_path)[0]
    assert row['export_exists'] is True and row['export_integrity'] == 'not_verified'
    checked = storage.list_projects(tmp_path, export_verifier=lambda path: {'status': 'valid'})[0]
    assert checked['export_integrity'] == 'valid'
    assert snapshot(tmp_path) == before


def test_quarantine_uuid_collision_does_not_replace_an_existing_receipt(tmp_path, monkeypatch):
    root = project(tmp_path)
    monkeypatch.setattr(storage.uuid, 'uuid4', lambda: SimpleNamespace(hex='a' * 32))
    first = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    (root / 'audio' / 'another.wav').write_bytes(b'another')
    before = snapshot(root)
    second = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    assert second['removed_bytes'] == 0 and second['errors']
    assert snapshot(root) == before
    assert storage.restore_preview(root, first['quarantine_id'])['restorable_bytes'] > 0


def test_cancel_after_first_move_keeps_remaining_files(tmp_path, monkeypatch):
    root = project(tmp_path)
    (root / 'audio' / 'second.wav').write_bytes(b'second')
    cancelled = False
    original_move = storage._move_no_replace
    def move_and_cancel(*args):
        nonlocal cancelled
        original_move(*args)
        cancelled = True
    monkeypatch.setattr(storage, '_move_no_replace', move_and_cancel)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True, cancel=lambda: cancelled)
    assert result['cancelled'] is True and len(result['removed']) == 1
    assert len(result['skipped']) == 1
    assert len(list((root / 'audio').glob('*.wav'))) == 1
    assert storage.restore_preview(root, result['quarantine_id'])['restorable_bytes'] > 0


def test_changed_quarantine_hash_is_blocked_without_destination_collision(tmp_path):
    root = project(tmp_path)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    stored = Path(result['quarantine_path']) / 'files' / 'audio' / 'original.wav'
    stat = stored.stat()
    stored.write_bytes(b'X' * stat.st_size)
    os.utime(stored, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    plan = storage.restore_preview(root, result['quarantine_id'])
    assert plan['files'][0]['reason'] == 'missing_or_changed_quarantine_file'
    assert storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)['restored_bytes'] == 0
    assert not (root / 'audio' / 'original.wav').exists()
    assert stored.exists()


def test_pending_receipt_remains_restorable_after_final_receipt_write_failure(tmp_path, monkeypatch):
    root = project(tmp_path)
    original_write = storage._write_receipt
    calls = 0
    def fail_second_write(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError(28, 'synthetic disk full after move')
        original_write(*args)
    monkeypatch.setattr(storage, '_write_receipt', fail_second_write)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    assert result['quarantined_bytes'] > 0 and result['errors']
    assert result['skipped'] == []
    assert storage.restore_preview(root, result['quarantine_id'])['restorable_bytes'] > 0
    assert storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)['restored_bytes'] > 0


def test_cleanup_cannot_be_retargeted_into_quarantine_or_protected_revision(tmp_path):
    root = project(tmp_path)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    for forbidden in (Path(result['quarantine_path']) / 'files', root / 'revisions' / 'r1'):
        forbidden.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            storage.cleanup_preview(forbidden)


def test_export_pointer_hash_mismatch_is_not_verified_as_valid(tmp_path):
    root = project(tmp_path)
    external = tmp_path / 'organized-export'
    external.mkdir()
    (external / 'PROJECT_MANIFEST.json').write_text('{}', encoding='utf-8')
    (root / 'project_export.json').write_text(json.dumps({
        'path': str(external), 'manifest_sha256': '0' * 64, 'state': 'PARTIAL'
    }), encoding='utf-8')
    row = storage.list_projects(tmp_path, export_verifier=lambda path: {'status': 'valid'})[0]
    assert row['export_integrity'] == 'failed' and row['export_state'] == 'PARTIAL'


def test_restore_receipt_failure_reports_real_move_without_counting_it_as_skipped(tmp_path, monkeypatch):
    root = project(tmp_path)
    result = storage.execute_cleanup(storage.cleanup_preview(root), confirmed=True)
    def fail_write(*args):
        raise OSError(28, 'synthetic receipt failure after restore')
    monkeypatch.setattr(storage, '_write_receipt', fail_write)
    restored = storage.restore_quarantine(root, result['quarantine_id'], confirmed=True)
    assert restored['restored_bytes'] > 0 and restored['errors']
    assert restored['skipped'] == []
    assert (root / 'audio' / 'original.wav').read_bytes() == b'regenerable-audio'
