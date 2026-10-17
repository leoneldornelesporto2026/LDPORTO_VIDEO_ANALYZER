"""R6.2 dossier copies from synthetic package evidence; no real show/media."""
import json
from pathlib import Path
import zipfile

import pytest

from ldporto.core import file_hash
from ldporto.project_export import export_project, verify_project_export
from ldporto.r62_delivery import build_visual_delivery
from ldporto.visual_frame_handoff import validate_visual_frame_handoff
from test_r62_delivery_profiles import delivery_fixture


def test_r62_dossier_copies_profiles_visual_trees_and_active_camera(tmp_path, monkeypatch):
    _, package, analysis_dir, source, timeline, timeline_path = delivery_fixture(tmp_path, monkeypatch)
    delivery = build_visual_delivery(package, analysis_dir, source, tmp_path / 'delivery',
        camera_timeline_path=timeline_path, max_frames=2)
    editorial = Path(delivery['editorial']['path'])
    original_hash = file_hash(editorial)
    exported = export_project(editorial, tmp_path / 'Videos')
    root = Path(exported['path'])
    manifest = json.loads((root / 'PROJECT_MANIFEST.json').read_text(encoding='utf-8'))
    assert exported['state'] == 'PARTIAL' and exported['verification']['status'] == 'valid'
    assert manifest['r62_acceptance_state'] == 'PARTIAL'
    assert manifest['preview_approved'] is manifest['publication_ready'] is False
    assert manifest['package_ref'] == '06_SEGUNDA_CURADORIA/EDITORIAL_HANDOFF.zip'
    handoff = root / '06_SEGUNDA_CURADORIA'
    assert file_hash(handoff / 'EDITORIAL_HANDOFF.zip') == original_hash
    assert file_hash(handoff / 'FULL_AUDIT.zip') == delivery['full_audit']['sha256']
    assert len(list(root.rglob('FULL_AUDIT.zip'))) == 1
    assert not (handoff / 'SECOND_CURATION_READY.zip').exists()
    assert file_hash(editorial) == original_hash
    assert not list(root.rglob('*.mp4'))
    assert not list(root.rglob('DOSSIE_SEGUNDA_CURADORIA.pdf'))
    with zipfile.ZipFile(editorial) as archive:
        assert (root / 'MEDIA_REFERENCE.json').read_bytes() == archive.read('MEDIA_REFERENCE.json')
    copied = manifest['visual_handoff_exports']
    assert {row['piece_id'] for row in copied} == {'M1', 'M2', 'ST_FIXTURE'}
    for row in copied:
        directory = (root / row['manifest_ref']).parent
        assert validate_visual_frame_handoff(directory)['valid']
        assert (directory / 'contact_sheets/timeline.jpg').is_file()
    reels = list((root / '03_REELS').glob('*/RELATORIO_REEL.pdf'))
    assert len(reels) == 2
    assert all(b'/Subtype /Image' in path.read_bytes() for path in reels)
    story = root / '04_STORIES/AVULSOS/ST_FIXTURE'
    assert b'/Subtype /Image' in (story / 'RELATORIO_STORY.pdf').read_bytes()
    assert (story / 'caption_preflight.json').is_file()
    assert (story / 'transcricao.txt').is_file()
    for plan_path in [*list((root / '03_REELS').glob('*/camera_plan.json')), story / 'camera_plan.json']:
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        handoff_data = plan.get('camera_handoff', plan)
        assert handoff_data['segments']
        assert all(row['director_id'] == 'SYNTHETIC_REPLAY_D1' for row in handoff_data['segments'])
    assert json.loads((root / '05_CAMERAS/source_camera_timeline.json').read_text(encoding='utf-8')) == timeline
    assert verify_project_export(root)['status'] == 'valid'
    copied_frame = next((root / copied[0]['manifest_ref']).parent.glob('selected_frames/*.jpg'))
    copied_frame.write_bytes(b'SYNTHETIC TAMPER')
    assert verify_project_export(root)['status'] == 'failed'


def test_r62_dossier_rejects_full_audit_hash_mismatch(tmp_path, monkeypatch):
    _, package, analysis_dir, source, _, timeline_path = delivery_fixture(tmp_path, monkeypatch)
    delivery = build_visual_delivery(package, analysis_dir, source, tmp_path / 'delivery',
        camera_timeline_path=timeline_path, max_frames=2)
    Path(delivery['full_audit']['path']).write_bytes(b'SYNTHETIC MODIFIED AUDIT ZIP')
    with pytest.raises(ValueError, match='full_audit_sibling_integrity_failed'):
        export_project(delivery['editorial']['path'], tmp_path / 'Videos')
