"""Synthetic source-scene atlas: existing JPEGs, literal text and safe reuse."""
from copy import deepcopy
import json

from PIL import Image, ImageDraw
import pytest

from ldporto.core import file_hash
from ldporto.visual_scenes_atlas import build_visual_scenes_atlas, RECEIPT_REF
from test_r6_project_export import _pdf_text


def _sheet(root, relative, label):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (960, 412), (32, 45, 57))
    ImageDraw.Draw(image).text((20, 20), 'SYNTHETIC TEST PIXELS ' + label, fill='white')
    image.save(path, 'JPEG', quality=78)
    return relative


def _scene(root, sid, start, end, *, kind='SCENE', description=None, segments=()):
    windows = []
    frames = []
    cursor = start
    while cursor < end:
        stop = min(cursor + 3000, end)
        timestamp = cursor + (stop - cursor) / 4
        frame = {'frame_id': sid + '_F_%03d' % len(frames), 'timestamp_ms': timestamp,
                 'source_time_s': timestamp / 1000, 'sha256': '1' * 64,
                 'capture_provenance': 'SYNTHETIC_FIXTURE_NOT_SOURCE_EVIDENCE'}
        windows.append({'micro_id': sid + '_M_%03d' % len(windows),
                        'start_ms': cursor, 'end_ms': stop, 'frames': [frame]})
        frames.append(frame)
        cursor = stop
    sheets = [_sheet(root, 'visuals_all/' + sid + '/contact_sheet_%03d.jpg' % offset, sid)
              for offset in range((len(frames) + 5) // 6)]
    return {'scene_id': sid, 'start_ms': start, 'end_ms': end, 'duration_ms': end - start,
            'kind': kind, 'contact_sheet': sheets[0], 'contact_sheets': sheets,
            'frames': frames, 'micro_windows': windows, 'description': description,
            'description_status': 'PERSISTED_ANALYSIS' if description else 'NOT_ANALYZED',
            'transcript_segment_ids': list(segments)}


def _index(scenes, duration):
    return {'source_sha256': 'a' * 64, 'video_duration_ms': duration,
            'original_scene_count': sum(row['kind'] == 'SCENE' for row in scenes),
            'export_status': 'COMPLETE', 'scenes': scenes,
            'preview_approved': False, 'publication_ready': False}


def test_short_atlas_keeps_every_scene_searchable_literal_and_existing_images(tmp_path):
    scenes = [_scene(tmp_path, 'SCENE_NOT_AN_EDITORIAL_CANDIDATE', 3000, 66194,
                     description='Descrição já existente: palco azul.', segments=['SEG_1']),
              _scene(tmp_path, 'FALLBACK_INTERVAL_0001', 2000, 3000, kind='FALLBACK_INTERVAL'),
              _scene(tmp_path, 'SCENE_ORIGINAL_001', 0, 2000)]
    index = _index(scenes, 66194)
    before = deepcopy(index)
    literal = 'Ação, coração e música: café às três.'
    result = build_visual_scenes_atlas(tmp_path, index, [{'segment_id': 'SEG_1', 'text': literal}])
    assert index == before
    assert result['export_status'] == 'COMPLETE'
    assert result['preview_approved'] is False and result['publication_ready'] is False
    assert len(result['pdfs']) == 1
    row = result['pdfs'][0]
    assert row['path'] == 'VISUAL_SCENES_ATLAS.pdf'
    assert row['scene_ids'] == ['SCENE_ORIGINAL_001', 'FALLBACK_INTERVAL_0001', 'SCENE_NOT_AN_EDITORIAL_CANDIDATE']
    path = tmp_path / row['path']
    assert row['sha256'] == file_hash(path) and row['bytes'] == path.stat().st_size
    data = path.read_bytes()
    text = _pdf_text(data)
    assert '00:01:06.194' in text and 'NOT_ANALYZED' in text
    assert literal in text and 'Descrição já existente: palco azul.' in text
    assert all(scene['scene_id'] in text for scene in scenes)
    assert text.index('SCENE_ORIGINAL_001', text.index('Índice de leitura')) < text.index('FALLBACK_INTERVAL_0001', text.index('Índice de leitura'))
    assert b'/Subtype /Image' in data and row['searchable'] is True


def test_long_atlas_splits_ten_minutes_without_changing_crossing_scene_id(tmp_path):
    first = _scene(tmp_path, 'SCENE_FIRST', 0, 599000)
    crossing = _scene(tmp_path, 'SCENE_CROSSING', 599000, 600500, segments=['SEG_CROSS'])
    result = build_visual_scenes_atlas(tmp_path, _index([first, crossing], 600500),
                                     [{'segment_id': 'SEG_CROSS', 'text': 'Fala literal na transição.'}])
    assert result['export_status'] == 'COMPLETE'
    assert [(row['start_ms'], row['end_ms']) for row in result['pdfs']] == [(0, 600000), (600000, 600500)]
    assert [row['path'] for row in result['pdfs']] == [
        'VISUAL_SCENES_ATLAS_000_010_MIN.pdf', 'VISUAL_SCENES_ATLAS_010_011_MIN.pdf']
    assert all('SCENE_CROSSING' in row['scene_ids'] for row in result['pdfs'])
    for row in result['pdfs']:
        text = _pdf_text((tmp_path / row['path']).read_bytes())
        assert 'SCENE_CROSSING' in text and '00:10:00.500' in text
        assert 'Fala literal na transição.' in text
        assert 'O ID original permanece o mesmo.' in text


def test_fractional_millisecond_capture_preserves_its_actual_timestamp(tmp_path):
    scene = _scene(tmp_path, 'SCENE_MICROSECOND', 0, 1000.004)
    result = build_visual_scenes_atlas(tmp_path, _index([scene], 1000.004))
    text = _pdf_text((tmp_path / result['pdfs'][0]['path']).read_bytes())
    assert '00:00:01.000004' in text
    assert '00:00:00.250001' in text


def test_normalized_microsecond_duration_tolerates_binary_float_subtraction(tmp_path):
    scene = _scene(tmp_path, 'SCENE_FLOAT_PRECISION', 3866.667, 4600.0)
    scene['duration_ms'] = 733.333  # Persisted integer-microsecond normalization.
    assert scene['duration_ms'] != scene['end_ms'] - scene['start_ms']
    result = build_visual_scenes_atlas(tmp_path, _index([scene], 4600))
    assert result['export_status'] == 'COMPLETE'
    text = _pdf_text((tmp_path / result['pdfs'][0]['path']).read_bytes())
    assert '00:00:03.866667' in text and 'duração 733.333 ms.' in text
    scene['duration_ms'] += 0.001
    with pytest.raises(ValueError, match='scene_identity_or_interval_invalid'):
        build_visual_scenes_atlas(tmp_path, _index([scene], 4600))


def test_missing_sheet_and_capture_remain_partial_without_invented_evidence(tmp_path):
    scene = _scene(tmp_path, 'SCENE_MISSING', 0, 1000, segments=['NOT_AVAILABLE'])
    (tmp_path / scene['contact_sheet']).unlink()
    scene['micro_windows'][0]['frames'] = []
    result = build_visual_scenes_atlas(tmp_path, _index([scene], 1000))
    assert result['export_status'] == 'PARTIAL'
    assert {row['reason'] for row in result['failures']} >= {
        'micro_window_without_valid_capture', 'contact_sheet_missing', 'no_valid_contact_sheet_for_interval'}
    data = (tmp_path / result['pdfs'][0]['path']).read_bytes()
    assert b'/Subtype /Image' not in data
    text = _pdf_text(data)
    assert 'NOT_AVAILABLE | texto não fornecido' in text
    assert 'NOT_ANALYZED' in text


def test_unchanged_merged_index_reuses_pdf_and_owned_partial_can_be_repaired(tmp_path):
    scene = _scene(tmp_path, 'SCENE_RESUME', 0, 1000)
    index = _index([scene], 1000)
    first = build_visual_scenes_atlas(tmp_path, index)
    path = tmp_path / first['pdfs'][0]['path']
    before = path.stat().st_mtime_ns
    index.update(first)
    reused = build_visual_scenes_atlas(tmp_path, index)
    assert reused['reused_unchanged'] is True and path.stat().st_mtime_ns == before
    index['scenes'][0]['description'] = 'Texto canônico restaurado.'
    repaired = build_visual_scenes_atlas(tmp_path, index)
    assert repaired['reused_unchanged'] is False
    assert 'Texto canônico restaurado.' in _pdf_text(path.read_bytes())
    assert json.loads((tmp_path / RECEIPT_REF).read_text(encoding='utf-8'))['pdfs'][0]['sha256'] == file_hash(path)


def test_foreign_existing_pdf_is_preserved(tmp_path):
    scene = _scene(tmp_path, 'SCENE_SAFE', 0, 1000)
    target = tmp_path / 'VISUAL_SCENES_ATLAS.pdf'
    target.write_bytes(b'FOREIGN FILE MUST REMAIN')
    with pytest.raises(FileExistsError, match='requires_new_revision'):
        build_visual_scenes_atlas(tmp_path, _index([scene], 1000))
    assert target.read_bytes() == b'FOREIGN FILE MUST REMAIN'


def test_failed_visual_coverage_remains_failed_even_with_a_textual_pdf(tmp_path):
    scene = _scene(tmp_path, 'SCENE_FAILED', 0, 1000)
    scene['frames'] = []
    scene['micro_windows'][0]['frames'] = []
    scene['contact_sheets'] = []
    scene['contact_sheet'] = None
    index = _index([scene], 1000)
    index['export_status'] = 'FAILED'
    result = build_visual_scenes_atlas(tmp_path, index)
    assert result['pdfs'] and result['export_status'] == 'FAILED'
    assert result['source_export_status'] == 'FAILED'


@pytest.mark.parametrize('mutation,reason', [
    (lambda row: row.update(end_ms=True), 'scene_identity_or_interval_invalid'),
    (lambda row: row['frames'][0].update(timestamp_ms=1000), 'frame_outside_scene'),
    (lambda row: row['micro_windows'][0].update(end_ms=float('nan')), 'micro_window_invalid'),
    (lambda row: row.update(contact_sheets=['../outside.jpg']), 'unsafe'),
])
def test_invalid_scene_timestamp_and_unsafe_contact_references_fail(tmp_path, mutation, reason):
    scene = _scene(tmp_path, 'SCENE_INVALID', 0, 1000)
    mutation(scene)
    with pytest.raises(ValueError, match=reason):
        build_visual_scenes_atlas(tmp_path, _index([scene], 1000))
