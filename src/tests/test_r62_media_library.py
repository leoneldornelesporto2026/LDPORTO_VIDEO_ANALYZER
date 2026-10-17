"""Hash-bound original resolution/copy; all media are local synthetic test AVIs."""
import json
from pathlib import Path

import pytest

from ldporto.core import file_hash
from ldporto.media_library import register_media_copy, resolve_existing_media


@pytest.fixture
def tiny_video(tmp_path):
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    path = tmp_path/'synthetic_source.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 4., (64, 48))
    assert writer.isOpened()
    for index in range(8):
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:, :, 1] = 20 + index*20
        cv2.rectangle(frame, (4+index, 8), (24+index, 30), (255, 120, 20), -1)
        writer.write(frame)
    writer.release()
    decoder = cv2.VideoCapture(str(path))
    assert decoder.isOpened() and decoder.read()[0]
    decoder.release()
    return path


def manifest(root, **overrides):
    directory = root/'SYNTHETIC_ID'
    directory.mkdir(parents=True, exist_ok=True)
    data = {'schema_version': '1.0', 'video_id': 'SYNTHETIC_ID', 'relative_path': 'original.avi',
            'source_sha256': '0'*64, **overrides}
    (directory/'media_manifest.json').write_text(json.dumps(data), encoding='utf-8')
    return directory


def test_verified_original_is_copied_once_and_resolved_without_download_or_approval(tiny_video, tmp_path):
    expected = file_hash(tiny_video)
    before = tiny_video.read_bytes()
    library = tmp_path/'library'
    copied = register_media_copy(tiny_video, 'SYNTHETIC_ID', expected, library_root=library)
    assert copied['status'] == 'COPIED_VERIFIED' and copied['source_preserved']
    assert tiny_video.read_bytes() == before
    resolved = resolve_existing_media('SYNTHETIC_ID', expected_sha256=expected, library_root=library)
    assert resolved['status'] == 'FOUND_VERIFIED' and resolved['origin'] == 'media_library'
    assert resolved['source_sha256'] == expected and resolved['download_needed'] is False
    assert resolved['publication_ready'] is False
    again = register_media_copy(tiny_video, 'SYNTHETIC_ID', expected, library_root=library)
    assert again['status'] == 'ALREADY_VERIFIED'
    assert not list((library/'SYNTHETIC_ID').glob('*.partial'))


def test_explicit_verified_selection_has_priority_over_corrupt_lower_priority_manifest(tiny_video, tmp_path):
    library = tmp_path/'library'
    directory = library/'SYNTHETIC_ID'
    directory.mkdir(parents=True)
    (directory/'media_manifest.json').write_text('{invalid-json', encoding='utf-8')
    result = resolve_existing_media('SYNTHETIC_ID', expected_sha256=file_hash(tiny_video),
                                    explicit_path=tiny_video, library_root=library)
    assert result['status'] == 'FOUND_VERIFIED' and result['origin'] == 'explicit_selection'


def test_matching_existing_original_can_be_registered_and_resolved_after_partial_migration(tiny_video, tmp_path):
    library = tmp_path/'library'
    directory = library/'SYNTHETIC_ID'
    directory.mkdir(parents=True)
    (directory/'original.avi').write_bytes(tiny_video.read_bytes())
    register_media_copy(tiny_video, 'SYNTHETIC_ID', file_hash(tiny_video), library_root=library)
    resolved = resolve_existing_media('SYNTHETIC_ID', expected_sha256=file_hash(tiny_video), library_root=library)
    assert resolved['status'] == 'FOUND_VERIFIED' and resolved['origin'] == 'media_library'
    assert (directory/'integrity.json').is_file()


def test_mismatched_explicit_copy_never_falls_through_to_another_identity(tiny_video, tmp_path):
    library = tmp_path/'library'
    with pytest.raises(ValueError, match='selected_media_hash_mismatch'):
        resolve_existing_media('SYNTHETIC_ID', expected_sha256='0'*64,
                               explicit_path=tiny_video, library_root=library)
    assert tiny_video.is_file()


def test_wrong_copy_hash_preserves_source_and_does_not_create_library(tiny_video, tmp_path):
    library = tmp_path/'library'
    before = tiny_video.read_bytes()
    with pytest.raises(ValueError, match='media_copy_source_identity_mismatch'):
        register_media_copy(tiny_video, 'SYNTHETIC_ID', '0'*64, library_root=library)
    assert tiny_video.read_bytes() == before and not library.exists()


def test_absence_requests_selection_and_never_authorizes_download(tmp_path):
    result = resolve_existing_media('SYNTHETIC_ID', library_root=tmp_path/'missing')
    assert result['status'] == 'OPERATOR_SELECTION_REQUIRED'
    assert result['download_authorized'] is False and result['publication_ready'] is False
    assert not (tmp_path/'missing').exists()


def test_manifest_path_escape_is_rejected(tmp_path):
    library = tmp_path/'library'
    manifest(library, relative_path='../outside.avi')
    with pytest.raises(ValueError, match='unsafe_media_library_manifest'):
        resolve_existing_media('SYNTHETIC_ID', library_root=library)


def test_copy_rejects_linked_video_directory_before_writing_outside_library(tiny_video, tmp_path):
    library, outside = tmp_path/'library', tmp_path/'outside'
    library.mkdir(); outside.mkdir()
    try:
        (library/'SYNTHETIC_ID').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Windows does not permit creating a local test symlink')
    with pytest.raises(ValueError, match='unsafe_media_link_or_junction'):
        register_media_copy(tiny_video, 'SYNTHETIC_ID', file_hash(tiny_video), library_root=library)
    assert list(outside.iterdir()) == []


def test_copy_checks_reparse_status_of_video_directory_before_creating_files(tiny_video, tmp_path, monkeypatch):
    library = tmp_path/'library'
    directory = library/'SYNTHETIC_ID'
    directory.mkdir(parents=True)
    original = Path.is_symlink
    # Windows often disallows creating symlinks. Simulate only the filesystem
    # query result for this ordinary, task-owned directory; no external paths.
    monkeypatch.setattr(Path, 'is_symlink', lambda path: path == directory or original(path))
    with pytest.raises(ValueError, match='unsafe_media_link_or_junction'):
        register_media_copy(tiny_video, 'SYNTHETIC_ID', file_hash(tiny_video), library_root=library)
    assert list(directory.iterdir()) == []
