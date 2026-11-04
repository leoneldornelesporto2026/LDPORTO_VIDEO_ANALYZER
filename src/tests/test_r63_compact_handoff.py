"""Integral compact export/ZIP reader/PDF on explicitly synthetic local evidence.

JPEG atlas fixtures are labeled SYNTHETIC and never claimed as source captures.
There is no source decoder, downloader, model or pipeline invocation.
"""
from copy import deepcopy
import builtins
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from ldporto.compact_handoff import build_compact_handoff, PersistedArtifacts
from ldporto.compact_handoff_reader import inspect_compact_handoff
from ldporto.core import digest, file_hash
from ldporto.second_curation_export import build_core_package
from test_v43_handoff import analysis_fixture


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def refresh_artifact_ledger(folder):
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    manifest['artifact_checksums'] = {path.name: file_hash(path) for path in folder.glob('*.json')
                                     if path.name != 'manifest.json'}
    write(folder/'manifest.json', manifest)


def synthetic_atlas(root, sha, scenes):
    image_module = pytest.importorskip('PIL.Image')
    draw_module = pytest.importorskip('PIL.ImageDraw')
    frames = []
    for index, (time, scene) in enumerate(zip([5.5, 35., 75., 100.5], scenes)):
        image = image_module.new('RGB', (320, 180), (30+index*25, 60, 80))
        draw_module.Draw(image).text((12, 12), 'SYNTHETIC TEST %s %.1fs' % (scene['scene_id'], time), fill='white')
        encoded = io.BytesIO(); image.save(encoded, format='JPEG', quality=75)
        data = encoded.getvalue(); checksum = hashlib.sha256(data).hexdigest()
        path = root/('06_VISUAL_ATLAS/frames/'+checksum+'.jpg')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        frames.append({'frame_id': 'SYNTHETIC_FRAME_'+str(index), 'source_time_s': time,
            'source_sha256': sha, 'path': path.relative_to(root).as_posix(), 'sha256': checksum,
            'width': 320, 'height': 180, 'scene_id': scene['scene_id'],
            'capture_method': 'SYNTHETIC_TEST_IMAGE_NOT_SOURCE_VIDEO',
            'timestamp_provenance': 'SYNTHETIC_CONTRACT_FIXTURE',
            'timestamp_independently_verified': False, 'final_render_frame': False})
    sheet = image_module.new('RGB', (640, 360), 'black')
    for index, frame in enumerate(frames):
        with image_module.open(root/frame['path']) as im:
            sheet.paste(im, ((index % 2)*320, (index // 2)*180))
    path = root/'06_VISUAL_ATLAS/contact_sheets/SYNTHETIC_SHEET.jpg'
    path.parent.mkdir(parents=True, exist_ok=True); sheet.save(path, 'JPEG', quality=75)
    index = {'schema_version': 'r6.3', 'source_sha256': sha, 'frames': frames,
        'contact_sheets': [{'sheet_id': 'SYNTHETIC_SHEET', 'path': path.relative_to(root).as_posix(),
                           'sha256': file_hash(path), 'scene_ids': [row['scene_id'] for row in scenes],
                           'frame_ids': [row['frame_id'] for row in frames]}],
        'missing_requests': [], 'statistics': {'unique_image_files': 4, 'frame_count': 4,
            'deduplicated_image_reuses': 0, 'synthetic_fixture': True},
        'preview_approved': False, 'publication_ready': False}
    write(root/'06_VISUAL_ATLAS/atlas_index.json', index)
    return index


@pytest.fixture
def persisted_fixture(tmp_path):
    analysis = analysis_fixture()
    sha = hashlib.sha256(b'SYNTHETIC_R63_SOURCE_IDENTITY_NO_ORIGINAL_VIDEO').hexdigest()
    analysis['metadata'].update(sha256=sha, source={'type': 'local', 'id': 'SYNTHETIC_R63',
                                                 'title': 'Evidência sintética R6.3'})
    segments = [{'segment_id': 'EXTRA_BEFORE', 'start': 5., 'end': 6., 'speaker': 'SP1', 'text': 'Antes.'},
                {'segment_id': 'S1', 'start': 30., 'end': 50., 'speaker': 'SP1', 'text': 'Primeira parte sintética.'},
                {'segment_id': 'S2', 'start': 70., 'end': 90., 'speaker': 'SP1', 'text': 'Segunda parte sintética.'},
                {'segment_id': 'EXTRA_AFTER', 'start': 100., 'end': 101., 'speaker': 'SP1', 'text': 'Depois.'}]
    words = [{'word_id': 'W_'+row['segment_id'], 'segment_id': row['segment_id'], 'start': time,
              'end': time+.3, 'word': text, 'confidence': .75, 'needs_review': True,
              'alignment_verified': False, 'audio_verified': False, 'speaker': 'SP1'}
             for row, time, text in zip(segments, [5.2, 35., 75., 100.2], ['Antes.', 'Primeira', 'Segunda', 'Depois.'])]
    analysis['transcript_segments'], analysis['words'] = segments, words
    analysis['main_moments'][0]['evidence_segment_ids'] = ['S1', 'S2']
    analysis['story_arcs'] = [{'story_arc_id': 'SYNTHETIC_ARC', 'start': 30., 'end': 90.,
        'evidence_segment_ids': ['S1', 'S2'], 'topic_id': 'T1', 'complete': False,
        'setup': {'segment_ids': ['S1']}, 'development': {'segment_ids': ['S2']}}]
    bounds = [(0., 20.), (20., 60.), (60., 95.), (95., 120.)]
    scenes = [{'scene_id': 'SCENE_'+str(i), 'start': a, 'end': b, 'duration': b-a,
               'scene_type': 'medium_shot', 'shot_type_inference': True} for i, (a, b) in enumerate(bounds)]
    shots = [{'shot_id': 'SHOT_'+str(i), 'scene_id': row['scene_id'], 'start': row['start'], 'end': row['end'],
              'shot_type': 'medium', 'transition_in': 'hard_cut' if i else None} for i, row in enumerate(scenes)]
    analysis['scenes'], analysis['shots'] = scenes, shots
    analysis['raw_tracks'] = [{'track_id': track, 'person_id': person,
                               'identity_status': 'within_track_only'} for track, person in [
        ('TRACK_SYNTHETIC', 'PERSON_SYNTHETIC'), ('TRACK_OUTSIDE', 'PERSON_OUTSIDE'),
        ('TRACK_BOUNDARY', 'PERSON_BOUNDARY'), ('TRACK_END', 'PERSON_END')]]
    analysis['tracklet_observations'] = [{'time': t, 'track_id': 'TRACK_SYNTHETIC', 'person_id': 'RAW_ONLY',
        'scene_id': 'SCENE_1', 'face_bbox': {'x': .3, 'y': .2, 'width': .08, 'height': .16},
        'face_visible': True, 'body_visible': False, 'confidence': .91, 'detection_confidence': .91,
        'sharpness': 120, 'safe_crop_possible': True} for t in [34., 35., 36.]]
    # These observations deliberately occupy the same scenes as M1, while
    # PERSON_OUTSIDE and PERSON_END are outside its [30,90) source interval.
    # The boundary track must form two singletons at the source cut at 60s.
    for time, track, scene in [(25., 'TRACK_OUTSIDE', 'SCENE_1'),
                               (59.999, 'TRACK_BOUNDARY', 'SCENE_1'),
                               (60., 'TRACK_BOUNDARY', 'SCENE_2'),
                               (90., 'TRACK_END', 'SCENE_2')]:
        analysis['tracklet_observations'].append({**analysis['tracklet_observations'][0],
            'time': time, 'track_id': track, 'scene_id': scene})
    people_by_track = {row['track_id']: row['person_id'] for row in analysis['raw_tracks']}
    analysis['people_observations'] = [{**row, 'person_id': people_by_track[row['track_id']]}
                                        for row in analysis['tracklet_observations']]
    analysis['person_identities'] = [{'person_id': person, 'identity_status': 'within_track_only'}
                                      for person in people_by_track.values()]
    analysis['camera_director_timeline'] = [{'director_id': 'SYNTHETIC_CAMERA_'+str(i),
        'source_shot_id': shot['shot_id'], 'start': shot['start'], 'end': shot['end'],
        'layout': 'full_frame', 'focus_person': None, 'camera_mode': 'SOURCE_PRESERVE',
        'crop': {'safe': False}, 'camera': {'keyframes': [
            {'time': shot['start'], 'center': [.5, .5], 'zoom': 1.},
            {'time': shot['end'], 'center': [.5, .5], 'zoom': 1.}]},
        'decision': {'reasons': ['SYNTHETIC_SOURCE_PRESERVE']}} for i, shot in enumerate(shots)]
    # Parent deliberately contains only the relevant middle transcript revision;
    # the persisted canonical source has additional literal segments and words.
    parent = deepcopy(analysis)
    parent['transcript_segments'], parent['words'] = segments[1:3], words[1:3]
    package = build_core_package(parent, output_dir=tmp_path/'parent_package', cfg={'narrative_handoff_enabled': True})
    folder = tmp_path/'persisted_analysis'
    for name, value in [('analysis_summary.json', {'metadata': analysis['metadata'], 'analysis_status': 'partial'}),
                        ('words.json', words), ('transcript_segments.json', segments),
                        ('scenes.json', scenes), ('shots.json', shots)]:
        write(folder/name, value)
    write(folder/'manifest.json', {'video_sha256': sha, 'run_id': 'SYNTHETIC_ANALYSIS_REVISION', 'artifact_checksums': {}})
    refresh_artifact_ledger(folder)
    atlas = tmp_path/'cached_atlas'
    synthetic_atlas(atlas, sha, scenes)
    return {'analysis': folder, 'package': Path(package['path']), 'atlas': atlas,
            'destination': tmp_path/'derived', 'words': words, 'segments': segments,
            'source_sha256': sha, 'scenes': scenes}


def export(fixture, **overrides):
    return build_compact_handoff(fixture['analysis'], fixture['package'],
        destination=fixture['destination'], atlas_cache=fixture['atlas'], **overrides)


def test_integral_export_reconstructs_every_scene_piece_and_full_canonical_transcript(persisted_fixture, tmp_path, monkeypatch):
    import ldporto.compact_handoff as producer
    fixture = persisted_fixture
    # Exercise multiple real shards with a tiny fixture, preserving the exact
    # production writer and coordinate payload rather than mocking its result.
    original_writer = producer._write_geometry_shards
    monkeypatch.setattr(producer, '_write_geometry_shards',
        lambda work, geometry: original_writer(work, geometry, maximum_trajectories=2))
    before = {path.name: file_hash(path) for path in fixture['analysis'].glob('*.json')}
    package_hash = file_hash(fixture['package'])
    with zipfile.ZipFile(fixture['package']) as parent:
        candidate_ids = {row['candidate_id'] for row in json.loads(parent.read('editorial/candidate_catalog.json'))['candidates']}
        units = json.loads(parent.read('editorial/story_units.json'))['units']
        standalone = json.loads(parent.read('social/stories_manifest.json'))['stories']
        series_ids = {row['sequence_id'] for row in json.loads(parent.read('editorial/story_sequence_candidates.json'))['sequences']}
        parent_word_count = len(parent.read('transcript/relevant_words.jsonl').decode('utf-8').splitlines())
    assert len(units) >= 2 and parent_word_count < len(fixture['words'])
    result = export(fixture)
    assert result['state'] == 'PARTIAL' and result['new_model_calls'] == 0
    assert not result['full_pipeline_executed'] and not result['source_artifacts_modified']
    assert package_hash == file_hash(fixture['package'])
    assert before == {path.name: file_hash(path) for path in fixture['analysis'].glob('*.json')}
    isolated = tmp_path/'zip_only_reader'/'compact.zip'
    isolated.parent.mkdir(); isolated.write_bytes(Path(result['archive']['path']).read_bytes())
    monkeypatch.setattr(PersistedArtifacts, '__init__', lambda *args: pytest.fail('reader accessed local analysis'))
    report = inspect_compact_handoff(isolated)
    assert report['status'] == 'valid', report['errors']
    assert report['zip_only'] and not report['local_analysis_accessed'] and not report['media_accessed']
    assert not report['models_executed'] and not report['approval_created']
    rebuilt = report['reconstructed']
    assert set(rebuilt['scene_index']) == {row['scene_id'] for row in fixture['scenes']}
    assert set(rebuilt['candidate_index']) == candidate_ids
    assert set(rebuilt['story_index']['parts']) == {row['unit_id'] for row in units} | {row['story_id'] for row in standalone}
    assert set(rebuilt['story_index']['series']) == series_ids
    assert list(rebuilt['transcript']['words'].values()) == fixture['words']
    assert list(rebuilt['transcript']['segments'].values()) == fixture['segments']
    assert report['counts']['word_count'] == len(fixture['words'])
    assert rebuilt['coverage']['continuous_visual_coverage_verified'] is False
    assert rebuilt['limitations']['curator_ready_package_produced'] is False
    assert rebuilt['trajectories'], 'full-frame camera must not eliminate observed person geometry'
    assert report['counts']['trajectory_shard_count'] >= 3
    m1 = rebuilt['candidate_index']['M1']
    assert set(m1['index']['person_ids']) == {'PERSON_SYNTHETIC', 'PERSON_BOUNDARY'}
    assert 'PERSON_OUTSIDE' in rebuilt['scene_index']['SCENE_1']['person_ids']
    assert 'PERSON_END' in rebuilt['scene_index']['SCENE_2']['person_ids']
    boundary = sorted((row for row in rebuilt['trajectories'].values()
                       if row['person_id'] == 'PERSON_BOUNDARY'), key=lambda row: row['start'])
    assert [(row['source_shot_id'], row['start'], row['end']) for row in boundary] == [
        ('SHOT_1', 59.999, 59.999), ('SHOT_2', 60., 60.)]
    assert all(len(row['keyframes']) == 1 for row in boundary)
    with zipfile.ZipFile(isolated) as archive:
        metadata = json.loads(archive.read('03_PEOPLE/visual_trajectories.json'))
        assert metadata['storage'] == 'indexed_shards' and 'trajectories' not in metadata
        assert set(metadata['trajectory_index']) == set(rebuilt['trajectories'])
        # A caller who has only the piece index can reach its complete geometry
        # directly. This lookup never reads the global coordinate/index file.
        reads = []
        def read_piece_json(name):
            assert name != '03_PEOPLE/visual_trajectories.json'
            reads.append(name)
            return json.loads(archive.read(name))
        piece_geometry = read_piece_json(m1['index']['camera_geometry_ref'])
        selected = {}
        for name in piece_geometry['trajectory_shard_refs']:
            selected.update({row['trajectory_id']: row for row in read_piece_json(name)['trajectories']
                             if row['trajectory_id'] in piece_geometry['trajectory_ids']})
        assert set(selected) == set(piece_geometry['trajectory_ids'])
        assert all(row['person_id'] in {'PERSON_SYNTHETIC', 'PERSON_BOUNDARY'} for row in selected.values())
        assert all(metadata['trajectory_index'][ident] in reads for ident in selected)
        assert {row['trajectory_id']: row for row in selected.values()} == {
            ident: rebuilt['trajectories'][ident] for ident in piece_geometry['trajectory_ids']}


def test_pdf_is_real_searchable_and_shared_frames_resolve_inside_zip(persisted_fixture):
    from test_r6_project_export import _pdf_text
    result = export(persisted_fixture)
    assert result['pdf']['searchable'] and result['pdf']['pdf_pages'] >= 4
    with zipfile.ZipFile(result['archive']['path']) as archive:
        pdf = archive.read('08_REPORTS/VISUAL_ATLAS.pdf')
        assert pdf.startswith(b'%PDF-') and b'/ToUnicode' in pdf
        text = _pdf_text(pdf)
        assert 'M1' in text and 'SCENE_0' in text and 'Primeira parte sintética.' in text
        index = json.loads(archive.read('06_VISUAL_ATLAS/atlas_index.json'))
        for frame in index['frames']:
            assert hashlib.sha256(archive.read(frame['path'])).hexdigest() == frame['sha256']
        assert len({row['path'] for row in index['frames']}) == 4
        assert not any(name.lower().endswith(('.mp4', '.avi', '.wav', '.zip', '.pt')) for name in archive.namelist())
        transcript = json.loads(archive.read('02_TRANSCRIPT/words_timestamps.json'))
        assert transcript['canonical_records_sha256'] == digest(persisted_fixture['words'])


def test_modified_persisted_canonical_artifact_is_rejected_before_export(persisted_fixture):
    path = persisted_fixture['analysis']/'words.json'
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError, match='persisted_artifact_checksum_mismatch:words.json'):
        export(persisted_fixture)
    assert not persisted_fixture['destination'].exists()


@pytest.mark.parametrize('kind', ['analysis_manifest', 'parent_package_identity', 'source_dimensions',
                                  'canonical_transcript_revision'])
def test_identity_or_canonical_revision_divergence_is_rejected(persisted_fixture, kind):
    folder = persisted_fixture['analysis']
    if kind == 'analysis_manifest':
        path = folder/'manifest.json'; document = json.loads(path.read_text(encoding='utf-8'))
        document['video_sha256'] = 'f'*64; write(path, document)
        reason = 'analysis_metadata_identity_disagreement'
    elif kind == 'parent_package_identity':
        other = analysis_fixture()
        other['metadata']['sha256'] = 'f'*64
        package = build_core_package(other, output_dir=folder.parent/'other_source_package')
        persisted_fixture['package'] = Path(package['path'])
        reason = 'compact_package_analysis_identity_mismatch'
    elif kind == 'source_dimensions':
        path = folder/'analysis_summary.json'; document = json.loads(path.read_text(encoding='utf-8'))
        document['metadata']['width'] = 1280
        write(path, document); refresh_artifact_ledger(folder)
        reason = 'compact_package_analysis_identity_mismatch'
    else:
        path = folder/'transcript_segments.json'; document = json.loads(path.read_text(encoding='utf-8'))
        document[1]['text'] += ' ALTERED_CANONICAL_REVISION'
        write(path, document); refresh_artifact_ledger(folder)
        reason = 'canonical_transcript_revision_conflict:S1'
    with pytest.raises(ValueError, match=reason):
        export(persisted_fixture)


def test_persisted_artifact_and_atlas_path_escape_are_rejected(persisted_fixture):
    source = PersistedArtifacts(persisted_fixture['analysis'])
    with pytest.raises(ValueError, match='unsafe_project_artifact_reference'):
        source.read('../outside.json')
    path = persisted_fixture['atlas']/'06_VISUAL_ATLAS/atlas_index.json'
    document = json.loads(path.read_text(encoding='utf-8')); document['frames'][0]['path'] = '../outside.jpg'
    write(path, document)
    with pytest.raises(ValueError, match='unsafe_project_artifact_reference'):
        export(persisted_fixture)


def test_cached_atlas_from_other_source_is_rejected(persisted_fixture):
    path = persisted_fixture['atlas']/'06_VISUAL_ATLAS/atlas_index.json'
    document = json.loads(path.read_text(encoding='utf-8')); document['source_sha256'] = 'f'*64
    write(path, document)
    with pytest.raises(ValueError, match='compact_(atlas_source_identity_mismatch|reprofile_source_identity_invalid)'):
        export(persisted_fixture)


def test_postprocessing_never_imports_model_or_download_runtime(persisted_fixture, monkeypatch):
    original_import = builtins.__import__
    forbidden = {'torch', 'ultralytics', 'faster_whisper', 'pyannote', 'transformers', 'yt_dlp'}
    def guarded(name, *args, **kwargs):
        if name.split('.')[0] in forbidden:
            pytest.fail('evidence postprocessing imported model/download runtime: '+name)
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    result = export(persisted_fixture)
    assert result['new_model_calls'] == 0 and not result['full_pipeline_executed']


def test_geometry_shard_budget_counts_json_envelope_and_preserves_oversized_singletons(tmp_path):
    from ldporto.compact_handoff import _write_geometry_shards
    # Storage-only synthetic objects: no image, identity or geometry claims.
    rows = [{'trajectory_id': 'T'+str(index), 'synthetic_storage_payload': 'x'*100}
            for index in range(3)]
    rows.append({'trajectory_id': 'OVERSIZED_SINGLETON', 'synthetic_storage_payload': 'x'*1000})
    limit = 2*len(json.dumps(rows[0], ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    lookup = _write_geometry_shards(tmp_path, {'trajectories': rows}, maximum_bytes=limit)
    index = json.loads((tmp_path/'03_PEOPLE/visual_trajectories.json').read_text(encoding='utf-8'))
    observed = {}
    for shard in index['shards']:
        raw = (tmp_path/shard['path']).read_bytes()
        content = json.loads(raw)['trajectories']
        assert shard['bytes'] == len(raw)
        assert len(raw) <= limit or len(content) == 1
        assert [row['trajectory_id'] for row in content] == shard['trajectory_ids']
        observed.update({row['trajectory_id']: row for row in content})
    assert observed == {row['trajectory_id']: row for row in rows}
    assert set(lookup) == set(observed)
