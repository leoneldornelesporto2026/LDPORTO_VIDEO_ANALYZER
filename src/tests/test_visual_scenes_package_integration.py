"""Real core ZIP + scene export + reexport on a tiny synthetic MJPG source.

No user media, models, downloaded data or full Analyzer processing is involved.
"""
from copy import deepcopy
import builtins
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

cv2 = pytest.importorskip('cv2')
np = pytest.importorskip('numpy')

from ldporto.core import file_hash
from ldporto.preview_renderer import build_contact_sheet
from ldporto.second_curation_export import build_core_package, validate_core_package
from ldporto.visual_scenes_export import reexport_all_scenes, validate_visual_scene_index
from test_v43_handoff import analysis_fixture


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')


@pytest.fixture
def source_analysis(tmp_path):
    source = tmp_path/'SYNTHETIC_120_SECONDS_SMALL.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 2., (64, 36))
    assert writer.isOpened()
    for index in range(240):
        image = np.full((36, 64, 3), 20+index % 200, dtype=np.uint8)
        cv2.rectangle(image, (index % 30, 8), (30+index % 30, 27), (30, 160, 220), -1)
        writer.write(image)
    writer.release()
    analysis = analysis_fixture()
    analysis['metadata'].update(sha256=file_hash(source), width=64, height=36, fps=2., rotation=0,
        source={'type': 'local', 'id': 'SYNTHETIC_TEST_SOURCE', 'title': 'Synthetic 120 second fixture'})
    analysis['scenes'] = [{'scene_id': 'SCENE_'+str(index), 'start': float(index*30),
        'end': float((index+1)*30), 'duration': 30.} for index in range(4)]
    analysis['shots'] = [{'shot_id': 'SHOT_'+str(index), 'scene_id': row['scene_id'],
        'start': row['start'], 'end': row['end'], 'shot_type': 'unknown'}
        for index, row in enumerate(analysis['scenes'])]
    intervals = [(5., 15.), (20., 30.), (35., 45.), (50., 60.)]
    analysis['transcript_segments'] = [{'segment_id': 'SEGMENT_'+str(index), 'start': start,
        'end': end, 'speaker': 'SP1', 'text': 'Literal synthetic segment '+str(index)+'.'}
        for index, (start, end) in enumerate(intervals)]
    prototype = deepcopy(analysis['main_moments'][0])
    analysis['main_moments'] = [{**deepcopy(prototype), 'moment_id': 'M'+str(index),
        'ideal_start': row['start'], 'ideal_end': row['end'],
        'core_moment': {'start': row['start'], 'end': row['end'], 'text': row['text']},
        'evidence_segment_ids': [row['segment_id']], 'default_shortlist_eligible': False}
        for index, row in enumerate(analysis['transcript_segments'])]
    analysis['transcript_segments'].append({'segment_id': 'SEGMENT_UNSELECTED', 'start': 100.,
        'end': 105., 'speaker': 'SP1', 'text': 'Synthetic source outside every candidate.'})
    analysis['words'] = [{'word_id': 'WORD_UNSELECTED', 'segment_id': 'SEGMENT_UNSELECTED',
        'word': 'Synthetic', 'start': 101., 'end': 101.5, 'speaker': 'SP1', 'confidence': .7,
        'needs_review': True, 'alignment_verified': False, 'audio_verified': False}]
    analysis['editorial_shortlist'] = []
    analysis['quality_gate'] = {'status': 'P1_DEGRADED', 'publication_ready': False}
    analysis['camera_director_timeline'] = [{'director_id': 'CAMERA_'+str(index),
        'source_shot_id': shot['shot_id'], 'start': shot['start'], 'end': shot['end'],
        'layout': 'full_frame', 'camera_mode': 'SOURCE_PRESERVE', 'focus_person': None,
        'crop': {'safe': False}, 'decision': {'reasons': ['SYNTHETIC_SOURCE_PRESERVE']},
        'camera': {'keyframes': [{'time': time, 'center': [.5, .5], 'zoom': 1.}
                                for time in (shot['start'], shot['end'])]}}
        for index, shot in enumerate(analysis['shots'])]
    folder = tmp_path/'persisted_analysis'
    for name, value in [('analysis_summary.json', {'metadata': analysis['metadata'], 'analysis_status': 'partial'}),
                        ('scenes.json', analysis['scenes']), ('shots.json', analysis['shots']),
                        ('transcript_segments.json', analysis['transcript_segments']), ('words.json', analysis['words'])]:
        write(folder/name, value)
    write(folder/'manifest.json', {'video_sha256': analysis['metadata']['sha256'],
        'artifact_checksums': {path.name: file_hash(path) for path in folder.glob('*.json')}})
    return source, analysis, folder


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def assert_complete_scene_catalog(files, expected_ids):
    index = json.loads(files['VISUAL_SCENES_INDEX.json'])
    assert index['export_status'] == 'COMPLETE'
    assert index['original_scene_count'] == 4
    assert {row['scene_id'] for row in index['scenes']} == expected_ids
    assert not index['editorial_selection_applied']
    assert index['video_duration_ms'] == 120000
    assert index['statistics']['micro_window_count'] == 40
    assert index['statistics']['capture_count'] == 80
    assert index['statistics']['missing_micro_windows'] == 0
    assert index['statistics']['represented_duration_ms'] == 120000
    segments = {row['segment_id'] for row in parse_jsonl(files['transcript/relevant_segments.jsonl'])}
    words = {row['word_id'] for row in parse_jsonl(files['transcript/relevant_words.jsonl'])}
    for row in index['scenes']:
        assert set(row['transcript_segment_ids']) <= segments
        assert set(row['word_ids']) <= words
        assert row['contact_sheet'] in files
        for sheet in row['contact_sheets']:
            image = cv2.imdecode(np.frombuffer(files[sheet], dtype=np.uint8), cv2.IMREAD_COLOR)
            assert image is not None and image.shape[:2] == (412, 960)
        assert all(micro['frames'] for micro in row['micro_windows'])
        assert all(frame['capture_provenance'] == 'opencv_decoder_reported' for frame in row['frames'])
    assert index['pdfs']
    assert all(files[row['path']].startswith(b'%PDF-') for row in index['pdfs'])
    manifest = json.loads(files['SECOND_CURATION_MANIFEST.json'])
    assert manifest['visual_scenes']['export_status'] == 'COMPLETE'
    assert not manifest['publication_ready'] and not manifest['preview_approved']
    return index


def parse_jsonl(blob):
    return [json.loads(line) for line in blob.decode('utf-8').splitlines() if line]


def test_normal_core_flow_exports_every_scene_with_zero_editorial_visual_limit(source_analysis, tmp_path):
    source, analysis, _ = source_analysis
    before = file_hash(source)
    result = build_core_package(analysis, source, tmp_path/'normal_packages',
        cfg={'second_curation_visual_candidate_limit': 0, 'include_candidate_previews': False})
    assert result['state'] == 'PARTIAL' and result['candidate_count'] == 4
    assert result['visual_count'] == 0
    assert file_hash(source) == before
    assert validate_core_package(result['path'])['status'] == 'valid'
    files = read_zip(result['path'])
    assert validate_visual_scene_index(json.loads(files['VISUAL_SCENES_INDEX.json']), files.__getitem__)['status'] == 'valid'
    catalog = json.loads(files['editorial/candidate_catalog.json'])['candidates']
    assert {row['candidate_id'] for row in catalog} == {'M0', 'M1', 'M2', 'M3'}
    assert all(not row['visual_refs'] for row in catalog)
    index = assert_complete_scene_catalog(files, {row['scene_id'] for row in analysis['scenes']})
    assert all(row['start_ms'] >= 60000 for row in index['scenes'][2:])
    assert all(row['end'] <= 60. for row in catalog), 'late scenes have no editorial candidate'
    assert json.loads(files['CURATION_INDEX.json'])['visual_scenes_ref'] == 'VISUAL_SCENES_INDEX.json'


def test_core_without_scene_catalog_remains_valid_and_keeps_legacy_contract(source_analysis, tmp_path):
    _, analysis, _ = source_analysis
    analysis.pop('scenes')
    result = build_core_package(analysis, output_dir=tmp_path/'legacy_packages',
                                cfg={'second_curation_visual_candidate_limit': 0})
    assert result['candidate_count'] == 4 and validate_core_package(result['path'])['status'] == 'valid'
    files = read_zip(result['path'])
    assert 'VISUAL_SCENES_INDEX.json' not in files
    assert not any(name.startswith('visuals_all/') for name in files)
    assert 'visual_scenes' not in json.loads(files['SECOND_CURATION_MANIFEST.json'])


def test_reexport_preserves_editorial_and_camera_and_corrects_legacy_moment_times(source_analysis, tmp_path, monkeypatch):
    import ldporto.second_curation_export as core_exporter
    source, analysis, folder = source_analysis
    parent_analysis = deepcopy(analysis); parent_analysis.pop('scenes')
    # Emulate the old producer's actual duplicated sixth tile and metadata.
    # This remains a synthetic MJPG fixture, not evidence from the user's video.
    def legacy_duplicate(source_path, candidate, output, timeline=None):
        info = build_contact_sheet(source_path, candidate, output, timeline)
        assert info['status'] == 'ok'
        image = cv2.imread(str(output)); image[206:412, 640:960] = image[0:206, 640:960]
        assert cv2.imwrite(str(output), image)
        info['frames'][-1] = deepcopy(info['frames'][2])
        return info
    with monkeypatch.context() as patch:
        patch.setattr(core_exporter, 'build_contact_sheet', legacy_duplicate)
        parent = build_core_package(parent_analysis, source, tmp_path/'parent_packages',
            cfg={'include_candidate_previews': False})
    before = read_zip(parent['path']); parent_hash = file_hash(Path(parent['path']))
    assert validate_core_package(parent['path'])['status'] == 'valid'
    parent_rows = json.loads(before['editorial/candidate_catalog.json'])['candidates']
    assert len(parent_rows) == 4 and all(len(row['visual_refs']) == 1 for row in parent_rows)
    assert all(row['visual_metadata']['frames'][-1]['time'] == row['visual_metadata']['frames'][2]['time']
               for row in parent_rows)
    original_import = builtins.__import__
    def guard(name, *args, **kwargs):
        if name.split('.')[0] in {'torch', 'ultralytics', 'faster_whisper', 'pyannote', 'transformers', 'yt_dlp'}:
            pytest.fail('visual-only reexport imported model/download runtime: '+name)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guard)
    result = reexport_all_scenes(folder, parent['path'], source, tmp_path/'reexport')
    assert result['export_status'] == 'COMPLETE' and result['candidate_count'] == 4
    assert result['parent_package_preserved'] and file_hash(Path(parent['path'])) == parent_hash
    assert result['new_model_calls'] == 0 and not result['camera_timeline_recomputed']
    assert not result['social_previews_rendered'] and len(result['moment_sheet_corrections']) == 4
    assert result['validation']['status'] == 'valid'
    after = read_zip(result['path'])
    assert_complete_scene_catalog(after, {row['scene_id'] for row in analysis['scenes']})
    assert parse_jsonl(after['transcript/relevant_words.jsonl']) == analysis['words']
    for name, blob in before.items():
        if name.startswith('camera/') or name == 'editorial/default_shortlist.json':
            assert after[name] == blob, name
        elif name.startswith('transcript/') and name.endswith('.jsonl'):
            old_records = parse_jsonl(blob); new_records = parse_jsonl(after[name])
            assert all(row in new_records for row in old_records), name
        elif name.startswith('transcript/'):
            assert after[name] == blob, name
    after_rows = json.loads(after['editorial/candidate_catalog.json'])['candidates']
    for old, new in zip(parent_rows, after_rows):
        assert {k: v for k, v in old.items() if k != 'visual_metadata'} == {
               k: v for k, v in new.items() if k != 'visual_metadata'}
        times = [frame['source_time_s'] for frame in new['visual_metadata']['frames']]
        assert times == sorted(set(times)) and len(times) == 6
        assert new['visual_refs'] == old['visual_refs']
        assert all(after[name] != before[name] for name in new['visual_refs'])
        stored = json.loads(after['candidates/'+new['candidate_id']+'.json'])
        assert stored == new
    # The second export must consume persisted captures and moment-sheet cache.
    import ldporto.visual_scenes_export as visual_exporter
    import ldporto.preview_renderer as renderer
    def forbidden(*args, **kwargs):
        pytest.fail('complete visual reexport attempted to decode or regenerate a valid contact sheet')
    monkeypatch.setattr(visual_exporter, '_Capture', forbidden)
    monkeypatch.setattr(renderer, 'build_contact_sheet', forbidden)
    again = reexport_all_scenes(folder, parent['path'], source, tmp_path/'reexport')
    assert again['export_status'] == 'COMPLETE'
    assert again['last_visual_execution']['new_captures'] == 0
    assert again['last_visual_execution']['reused_complete_export']
    assert validate_core_package(again['path'])['status'] == 'valid'


def test_chronological_parts_preserve_scene_crossing_ten_minute_boundary(tmp_path):
    from ldporto.editorial_pdf import EditorialPDF
    from ldporto.visual_scenes_export import _visual_parts
    assets, output = tmp_path/'synthetic_assets', tmp_path/'parts'
    assets.mkdir(); output.mkdir()
    scenes = []
    for index, (ident, start, end, sheet_count) in enumerate([
            ('SCENE_BEFORE', 0, 599000, 1),
            ('SCENE_CROSSING_600S', 599000, 601000, 2),
            ('SCENE_AFTER', 601000, 610000, 1)]):
        records = []
        for page in range(sheet_count):
            name = 'contact_sheet.jpg' if page == 0 else 'contact_sheet_002.jpg'
            relative = 'visuals_all/'+ident+'/'+name
            target = assets/relative; target.parent.mkdir(parents=True, exist_ok=True)
            image = np.full((90, 160, 3), 40+index*30+page, dtype=np.uint8)
            cv2.putText(image, 'SYNTHETIC', (5, 45), cv2.FONT_HERSHEY_SIMPLEX, .35, (250, 250, 250), 1)
            assert cv2.imwrite(str(target), image)
            records.append({'path': relative, 'sha256': file_hash(target), 'bytes': target.stat().st_size})
        scenes.append({'scene_id': ident, 'start_ms': start, 'end_ms': end,
            'contact_sheet': records[0]['path'], 'contact_sheets': [row['path'] for row in records],
            'contact_sheet_records': records, 'description': None, 'description_status': 'NOT_ANALYZED'})
    pdfs = []
    for index, (start, end) in enumerate([(0, 600000), (600000, 610000)]):
        name = 'SYNTHETIC_ATLAS_PART_'+str(index)+'.pdf'
        pdf = EditorialPDF('Synthetic partition fixture')
        pdf.text('SYNTHETIC ASSET; no source video or analysis. Interval %d..%d ms.' % (start, end))
        pdf.save(assets/name)
        pdfs.append({'path': name, 'start_ms': start, 'end_ms': end})
    index = {'source_sha256': 'c'*64, 'video_duration_ms': 610000,
             'scenes': scenes, 'pdfs': pdfs}
    before = {path.relative_to(assets).as_posix(): file_hash(path) for path in assets.rglob('*') if path.is_file()}
    original = deepcopy(index)
    parts = _visual_parts(index, assets, output)
    assert index == original
    assert len(parts) == 2
    assert [(row['start_ms'], row['end_ms']) for row in parts] == [(0, 600000), (600000, 610000)]
    assert set(parts[0]['scene_ids']) == {'SCENE_BEFORE', 'SCENE_CROSSING_600S'}
    assert set(parts[1]['scene_ids']) == {'SCENE_CROSSING_600S', 'SCENE_AFTER'}
    all_scene_ids = set()
    for number, part in enumerate(parts):
        path = output/part['filename']
        assert part['bytes'] == path.stat().st_size and part['sha256'] == file_hash(path)
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            manifest = json.loads(archive.read('VISUAL_SCENES_PART_INDEX.json'))
            assert manifest['source_sha256'] == index['source_sha256']
            assert manifest['source_scene_bounds_preserved']
            assert manifest['interval_convention'] == '[start,end)'
            assert (manifest['start_ms'], manifest['end_ms']) == (part['start_ms'], part['end_ms'])
            crossing = next(row for row in manifest['scenes'] if row['scene_id'] == 'SCENE_CROSSING_600S')
            assert crossing == scenes[1], 'cross-boundary scenes retain their original ID, bounds and sheets'
            assert (crossing['start_ms'], crossing['end_ms']) == (599000, 601000)
            all_scene_ids.update(row['scene_id'] for row in manifest['scenes'])
            expected = {row['path'] for scene in manifest['scenes'] for row in scene['contact_sheet_records']}
            expected.add(pdfs[number]['path'])
            assert set(archive.namelist()) == expected | {'VISUAL_SCENES_PART_INDEX.json'}
            assert {row['path'] for row in manifest['files']} == expected
            for record in manifest['files']:
                blob = archive.read(record['path'])
                assert record['bytes'] == len(blob)
                assert record['sha256'] == hashlib.sha256(blob).hexdigest() == before[record['path']]
    assert all_scene_ids == {row['scene_id'] for row in scenes}
    assert before == {path.relative_to(assets).as_posix(): file_hash(path) for path in assets.rglob('*') if path.is_file()}
