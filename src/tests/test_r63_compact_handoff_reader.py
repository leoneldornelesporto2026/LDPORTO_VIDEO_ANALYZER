"""Independent compact ZIP reader tests; fixtures do not call the producer."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image
import pytest

from ldporto.compact_handoff_reader import inspect_compact_handoff


SOURCE = 'a' * 64
NAV = {
    'scene_index': '01_TIMELINE/scene_index.json', 'reels_index': '04_REELS/reels_index.json',
    'series_index': '05_STORIES/series_index.json', 'segments': '02_TRANSCRIPT/transcript_segments.json',
    'words': '02_TRANSCRIPT/words_timestamps.json', 'trajectories': '03_PEOPLE/visual_trajectories.json',
    'atlas_index': '06_VISUAL_ATLAS/atlas_index.json', 'camera_decisions': '07_CAMERA/camera_decisions.json',
    'safe_areas': '07_CAMERA/safe_areas.json', 'coverage': '08_REPORTS/COVERAGE_REPORT.json',
    'limitations': '08_REPORTS/LIMITATIONS.json'}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True).encode('utf8')


def fixture():
    image = io.BytesIO()
    Image.new('RGB', (64, 36), (40, 70, 110)).save(image, 'JPEG')
    picture = image.getvalue()
    counts = {'scene_count': 1, 'shot_count': 1, 'reel_count': 1, 'story_part_count': 1,
              'series_count': 1, 'frame_count': 1, 'contact_sheet_count': 0,
              'trajectory_count': 1, 'segment_count': 1, 'word_count': 1}
    documents = {
        '00_OVERVIEW/navigation_index.json': {'entries': NAV},
        NAV['scene_index']: {'scenes': [{'scene_id': 'S1', 'start': 0., 'end': 2.,
            'shot_ids': ['SHOT1'], 'frame_ids': ['F1'], 'candidate_ids': ['R1'], 'geometry_state': 'OBSERVED'}]},
        NAV['segments']: {'segments': [{'segment_id': 'SEG1', 'start': .1, 'end': .9, 'text': 'Fixture'}]},
        NAV['words']: {'words': [{'word_id': 'W1', 'segment_id': 'SEG1', 'start': .1, 'end': .9, 'word': 'Fixture'}]},
        NAV['trajectories']: {'trajectories': [{'trajectory_id': 'T1', 'person_id': 'PERSON_UNKNOWN',
            'source_shot_id': 'SHOT1', 'class': 'face', 'start': .1, 'end': .9,
            'keyframes': [{'source_time_s': .1, 'bbox': {'x': .4, 'y': .1, 'width': .1, 'height': .2}, 'confidence': .8},
                          {'source_time_s': .9, 'bbox': {'x': .5, 'y': .1, 'width': .1, 'height': .2}, 'confidence': .8}]}]},
        NAV['atlas_index']: {'frames': [{'frame_id': 'F1', 'source_time_s': .5,
            'path': '06_VISUAL_ATLAS/frames/f.jpg', 'sha256': sha(picture), 'width': 64, 'height': 36,
            'source_sha256': SOURCE}], 'contact_sheets': []},
        NAV['camera_decisions']: {'decisions': [{'decision_id': 'D1', 'start': 0., 'end': 2.,
            'source_shot_id': 'SHOT1', 'mode': 'SOURCE_FIT_BLUR', 'fallback': 'SOURCE_PRESERVE',
            'camera': {'keyframes': [{'time': 0., 'center': [.5, .5], 'zoom': 1.},
                                     {'time': 2., 'center': [.5, .5], 'zoom': 1.}]}}]},
        NAV['safe_areas']: {'regions': [{'region_id': 'A1', 'trajectory_id': 'T1',
            'kind': 'face', 'evidence_state': 'OBSERVED', 'validity': 'sampled'}]},
        NAV['coverage']: {'declared_counts': counts},
        NAV['limitations']: {'status': 'PARTIAL_VISUAL_EVIDENCE', 'items': ['Fixture, not real evidence.']},
        '07_CAMERA/camera_contract.json': {'coordinates': 'normalized_top_left_source'},
    }
    reel, part = {}, {}
    for identifier, directory, index in [('R1', '04_REELS', reel), ('P1', '05_STORIES', part)]:
        index['candidate_id' if identifier == 'R1' else 'story_id'] = identifier
        if identifier == 'P1':
            index['series_ids'] = ['SERIES1']
        for filename, ref in [('editorial', 'editorial_ref'), ('source_intervals', 'source_intervals_ref'),
                              ('visual_storyboard', 'visual_storyboard_ref'), ('camera_geometry', 'camera_geometry_ref'),
                              ('caption_evidence', 'caption_evidence_ref')]:
            index[ref] = f'{directory}/{identifier}/{filename}.json'
        documents[index['editorial_ref']] = {'piece_id': identifier, 'state': 'PARTIAL', 'human_approved': False}
        documents[index['source_intervals_ref']] = {'piece_id': identifier, 'source_sha256': SOURCE,
            'intervals': [{'start': 0., 'end': 1., 'clip_start': 0., 'clip_end': 1.}]}
        documents[index['visual_storyboard_ref']] = {'piece_id': identifier,
            'beats': [{'start': 0., 'end': 1., 'clip_start': 0., 'clip_end': 1., 'frame_ids': ['F1'],
                'scene_ids': ['S1'], 'trajectory_ids': ['T1'], 'decision_ids': ['D1'],
                'segment_ids': ['SEG1'], 'word_ids': ['W1'], 'action_evidence_state': 'UNKNOWN'}]}
        documents[index['camera_geometry_ref']] = {'piece_id': identifier, 'trajectory_ids': ['T1'],
            'decision_ids': ['D1'], 'safe_area_ids': ['A1'], 'scene_ids': ['S1'],
            'coordinate_contract_ref': '07_CAMERA/camera_contract.json'}
        documents[index['caption_evidence_ref']] = {'piece_id': identifier, 'canonical_word_ids': ['W1'],
            'canonical_segment_ids': ['SEG1'], 'status': 'ALIGNMENT_REVIEW_REQUIRED', 'publication_ready': False}
    documents[NAV['reels_index']] = {'reels': [reel]}
    documents[NAV['series_index']] = {'series': [{'series_id': 'SERIES1', 'part_ids': ['P1'],
        'status': 'CONTINUITY_UNVERIFIED'}], 'parts': [part]}
    manifest = {'schema_version': 'r6.3', 'profile': 'SECOND_CURATION_COMPACT', 'revision': 'FIXTURE1',
        'source': {'sha256': SOURCE, 'duration': 2., 'width': 1920, 'height': 1080, 'fps': 24.,
                   'video_id': None, 'title': None},
        'file_index_ref': 'FILE_INDEX.json', 'checksums_ref': 'checksums.sha256',
        'state': 'PARTIAL', 'preview_approved': False, 'human_approved': False, 'publication_ready': False,
        'declared_counts': counts}
    assets = {'06_VISUAL_ATLAS/frames/f.jpg': picture}
    return documents, manifest, assets


def package(tmp_path, documents=None, manifest=None, assets=None, *, alter_files=None):
    if documents is None:
        documents, manifest, assets = fixture()
    files = {name: encode(value) for name, value in documents.items()}
    files.update(assets or {})
    files['FILE_INDEX.json'] = encode({'files': [{'path': name, 'bytes': len(payload),
        'sha256': sha(payload), 'category': name.split('/')[0]} for name, payload in sorted(files.items())]})
    manifest = deepcopy(manifest)
    manifest['file_index_sha256'] = sha(files['FILE_INDEX.json'])
    files['MANIFEST.json'] = encode(manifest)
    files['checksums.sha256'] = ''.join(f'{sha(payload)}  {name}\n' for name, payload in sorted(files.items())).encode()
    if alter_files:
        alter_files(files)
    out = tmp_path / 'self_contained.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return out


def failed(result, error):
    assert result['status'] == 'failed'
    assert any(error in row for row in result['errors']), result['errors']
    assert 'reconstructed' not in result


def test_reconstructs_scene_candidates_stories_frames_geometry_and_words_from_zip_only(tmp_path, monkeypatch):
    archive = package(tmp_path)
    def no_local_analysis(*args, **kwargs):
        raise AssertionError('Reader attempted local data access')
    monkeypatch.setattr(Path, 'read_text', no_local_analysis)
    monkeypatch.setattr(Path, 'read_bytes', no_local_analysis)
    result = inspect_compact_handoff(archive)
    assert result['status'] == 'valid', result['errors']
    assert result['source']['video_id'] is None  # Never inferred from SHA prefix/filename.
    rebuilt = result['reconstructed']
    assert set(rebuilt['scene_index']) == {'S1'}
    assert set(rebuilt['candidate_index']) == {'R1'}
    assert set(rebuilt['story_index']['parts']) == {'P1'}
    assert rebuilt['candidate_index']['R1']['resolved']['words'][0]['word'] == 'Fixture'
    assert rebuilt['story_index']['parts']['P1']['resolved']['frames'][0]['frame_id'] == 'F1'
    assert rebuilt['candidate_index']['R1']['resolved']['trajectories'][0]['trajectory_id'] == 'T1'
    assert result['zip_only'] and not result['media_accessed'] and not result['models_executed']


def test_small_report_still_exercises_independent_reconstruction(tmp_path):
    result = inspect_compact_handoff(package(tmp_path), reconstruct=False)
    assert result['status'] == 'valid' and result['counts']['word_count'] == 1
    assert 'reconstructed' not in result


@pytest.mark.parametrize('name', ['../escape.json', '/absolute.json', 'C:/local.json', 'folder\\local.json', 'a/./b.json', ' a.json'])
def test_rejects_unsafe_zip_paths_even_when_all_checksums_are_rebuilt(tmp_path, name):
    docs, manifest, assets = fixture()
    docs[name] = {'text': 'Never extracted'}
    result = inspect_compact_handoff(package(tmp_path, docs, manifest, assets))
    assert result['status'] == 'failed'
    # Python's ZIP writer normalizes Windows backslashes in member headers;
    # the independent FILE_INDEX still contains the unsafe original reference.
    assert any('unsafe_or_duplicate_path' in e or 'invalid_index_path' in e for e in result['errors'])
    assert not (tmp_path.parent/'escape.json').exists()


def test_checks_both_integrity_layers_and_unindexed_members(tmp_path):
    result = inspect_compact_handoff(package(tmp_path, alter_files=lambda files: files.update({NAV['words']: b'{}'})))
    failed(result, 'payload_checksum')


def test_root_manifest_is_bound_by_checksums(tmp_path):
    def tamper(files):
        doc = json.loads(files['MANIFEST.json']); doc['revision'] = 'ALTERED'; files['MANIFEST.json'] = encode(doc)
    failed(inspect_compact_handoff(package(tmp_path, alter_files=tamper)), 'archive_checksum:MANIFEST.json')


def test_source_mismatch_in_nested_piece_is_not_accepted(tmp_path):
    docs, manifest, assets = fixture()
    docs['04_REELS/R1/source_intervals.json']['source_sha256'] = 'b'*64
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'source_identity')


@pytest.mark.parametrize('count', ['scene_count', 'reel_count', 'story_part_count', 'frame_count', 'word_count'])
def test_declared_complete_inventory_cannot_silently_drop_items(tmp_path, count):
    docs, manifest, assets = fixture()
    manifest['declared_counts'] = {**manifest['declared_counts'], count: 2}
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'declared_count_mismatch')


@pytest.mark.parametrize('key,missing', [('frame_ids', 'MISSING_FRAME'), ('word_ids', 'MISSING_WORD'),
    ('segment_ids', 'MISSING_SEGMENT'), ('trajectory_ids', 'MISSING_TRAJECTORY'), ('decision_ids', 'MISSING_CAMERA')])
def test_editorial_reconstruction_requires_resolved_evidence_ids(tmp_path, key, missing):
    docs, manifest, assets = fixture()
    docs['04_REELS/R1/visual_storyboard.json']['beats'][0][key] = [missing]
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'unresolved_id')


def test_missing_piece_document_cannot_be_replaced_by_a_local_path(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['reels_index']]['reels'][0]['camera_geometry_ref'] = str(tmp_path/'local_geometry.json')
    (tmp_path/'local_geometry.json').write_text('{}')
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'missing_reference')


def test_rejects_bbox_outside_source_and_out_of_order_keyframes(tmp_path):
    docs, manifest, assets = fixture()
    trajectory = docs[NAV['trajectories']]['trajectories'][0]
    trajectory['keyframes'][0]['bbox']['x'] = .99
    trajectory['keyframes'].reverse()
    result = inspect_compact_handoff(package(tmp_path, docs, manifest, assets))
    failed(result, 'invalid_bbox')
    assert any('invalid_trajectory_keyframe_time' in e for e in result['errors'])


def test_trajectory_must_not_interpolate_across_source_shot_scene(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['scene_index']]['scenes'][0]['end'] = .5
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'trajectory_crosses_shot')


def test_rejects_corrupt_image_even_with_valid_zip_checksums(tmp_path):
    docs, manifest, assets = fixture()
    assets['06_VISUAL_ATLAS/frames/f.jpg'] = b'not an image'
    docs[NAV['atlas_index']]['frames'][0]['sha256'] = sha(assets['06_VISUAL_ATLAS/frames/f.jpg'])
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'frame_decode')


def test_a_picture_timestamp_outside_piece_is_not_associated_to_it(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['atlas_index']]['frames'][0]['source_time_s'] = 1.5
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'frame_outside_piece')


def test_clip_time_mapping_cannot_bridge_source_gaps(tmp_path):
    docs, manifest, assets = fixture()
    docs['04_REELS/R1/source_intervals.json']['intervals'][0]['clip_end'] = 2.
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'invalid_clip_mapping')


def test_nested_editorial_approval_cannot_be_created_by_export(tmp_path):
    docs, manifest, assets = fixture()
    docs['04_REELS/R1/editorial.json']['human_approved'] = True
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'approval_gate')


def test_schema_mismatch_and_nonfinite_json_do_not_pass(tmp_path):
    docs, manifest, assets = fixture()
    manifest['schema_version'] = 'old'
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'invalid_schema')
    manifest['schema_version'] = 'r6.3'
    docs['04_REELS/R1/editorial.json']['score'] = float('nan')
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'invalid_json')


def test_duplicate_ids_and_casefold_paths_are_rejected(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['trajectories']]['trajectories'].append(deepcopy(docs[NAV['trajectories']]['trajectories'][0]))
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'invalid_or_duplicate_id')
    docs, manifest, assets = fixture()
    docs['08_REPORTS/limitations.json'] = {'shadow': True}
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'unsafe_or_duplicate_path')


def test_non_zip_input_reports_failure_without_writes(tmp_path):
    path = tmp_path/'corrupt.zip'; path.write_bytes(b'not ZIP')
    failed(inspect_compact_handoff(path), 'reader_error')


def test_reference_fragments_resolve_inside_zip_json_and_missing_fragment_fails(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['limitations']]['inspection_ref'] = NAV['atlas_index'] + '#frames'
    assert inspect_compact_handoff(package(tmp_path, docs, manifest, assets))['status'] == 'valid'
    docs[NAV['limitations']]['inspection_ref'] = NAV['atlas_index'] + '#/frames/0/frame_id'
    assert inspect_compact_handoff(package(tmp_path, docs, manifest, assets))['status'] == 'valid'
    docs[NAV['limitations']]['inspection_ref'] = NAV['atlas_index'] + '#missing_key'
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'unresolved_json_fragment')


def test_canonical_text_integrity_is_checked_independently_of_zip_signing(tmp_path):
    docs, manifest, assets = fixture()
    records = docs[NAV['words']]['words']
    canonical = sha(json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    manifest['canonical_transcript'] = {'words_digest': canonical}
    docs[NAV['words']]['words'][0]['word'] = 'changed'
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'canonical_transcript_digest')


def test_word_count_declaration_is_required_for_complete_transcript_claim(tmp_path):
    docs, manifest, assets = fixture()
    manifest['declared_counts'] = {k: v for k, v in manifest['declared_counts'].items() if k != 'word_count'}
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'missing_declared_count')


def test_identical_frame_bytes_must_share_one_physical_file(tmp_path):
    docs, manifest, assets = fixture()
    original = docs[NAV['atlas_index']]['frames'][0]
    duplicate = {**original, 'frame_id': 'F2', 'path': '06_VISUAL_ATLAS/frames/duplicate.jpg'}
    docs[NAV['atlas_index']]['frames'].append(duplicate)
    assets[duplicate['path']] = assets[original['path']]
    manifest['declared_counts']['frame_count'] = 2
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'duplicate_image_payload')
    duplicate['path'] = original['path']
    assets.pop('06_VISUAL_ATLAS/frames/duplicate.jpg')
    assert inspect_compact_handoff(package(tmp_path, docs, manifest, assets))['status'] == 'valid'


def test_contact_sheet_image_is_verified_too(tmp_path):
    docs, manifest, assets = fixture()
    assets['06_VISUAL_ATLAS/contact_sheets/c.jpg'] = b'not JPEG'
    docs[NAV['atlas_index']]['contact_sheets'].append({'sheet_id': 'C1',
        'path': '06_VISUAL_ATLAS/contact_sheets/c.jpg', 'sha256': sha(b'not JPEG'), 'frame_ids': ['F1']})
    manifest['declared_counts']['contact_sheet_count'] = 1
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'contact_sheet_decode')


def test_unindexed_payload_and_duplicate_checksum_lines_fail(tmp_path):
    failed(inspect_compact_handoff(package(tmp_path, alter_files=lambda f: f.update({'hidden.json': b'{}'}))),
           'file_index_completeness')
    def duplicate(files):
        files['checksums.sha256'] += files['checksums.sha256'].splitlines()[0] + b'\n'
    failed(inspect_compact_handoff(package(tmp_path, alter_files=duplicate)), 'invalid_checksum_line')


def test_coordinate_contract_bbox_declaration_is_not_a_rectangle(tmp_path):
    docs, manifest, assets = fixture()
    docs[NAV['trajectories']]['coordinate_contract'] = {'origin': 'top_left', 'bbox': 'normalized_source_xywh'}
    docs['07_CAMERA/camera_contract.json']['coordinate_contract'] = deepcopy(docs[NAV['trajectories']]['coordinate_contract'])
    assert inspect_compact_handoff(package(tmp_path, docs, manifest, assets))['status'] == 'valid'
    docs[NAV['trajectories']]['trajectories'][0]['keyframes'][0]['bbox'] = 'normalized_source_xywh'
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'invalid_bbox')


def sharded_fixture():
    docs, manifest, assets = fixture()
    rows = docs[NAV['trajectories']].pop('trajectories')
    second = deepcopy(rows[0]); second['trajectory_id'] = 'T2'; rows.append(second)
    shards = []
    for i, row in enumerate(rows):
        name = f'03_PEOPLE/trajectories/TRAJECTORIES_{i:05}.json'
        docs[name] = {'trajectories': [row]}
        payload = encode(docs[name])
        shards.append({'path': name, 'bytes': len(payload), 'sha256': sha(payload),
                       'trajectory_ids': [row['trajectory_id']]})
    docs[NAV['trajectories']].update(storage='indexed_shards', shards=shards,
        trajectory_index={row['trajectory_ids'][0]: row['path'] for row in shards})
    manifest['declared_counts']['trajectory_count'] = 2
    for name in ['04_REELS/R1/camera_geometry.json', '05_STORIES/P1/camera_geometry.json']:
        docs[name]['trajectory_shard_refs'] = [shards[0]['path']]
    return docs, manifest, assets


def test_sharded_geometry_is_hydrated_once_and_reconstructed_from_zip_only(tmp_path):
    result = inspect_compact_handoff(package(tmp_path, *sharded_fixture()))
    assert result['status'] == 'valid', result['errors']
    assert result['counts']['trajectory_count'] == 2 and result['counts']['trajectory_shard_count'] == 2
    rebuilt = result['reconstructed']
    assert set(rebuilt['trajectories']) == {'T1', 'T2'}
    assert rebuilt['candidate_index']['R1']['resolved']['trajectories'][0] is rebuilt['trajectories']['T1']


def test_shard_integrity_ledger_is_checked_in_addition_to_outer_zip_checksums(tmp_path):
    docs, manifest, assets = sharded_fixture()
    docs[NAV['trajectories']]['shards'][0]['sha256'] = 'f'*64
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'trajectory_shard_checksum')


@pytest.mark.parametrize('mutate', [
    lambda index: index['trajectory_index'].pop('T2'),
    lambda index: index['trajectory_index'].update(T1='03_PEOPLE/trajectories/TRAJECTORIES_00001.json'),
])
def test_shard_lookup_must_cover_every_id_at_its_exact_location(tmp_path, mutate):
    docs, manifest, assets = sharded_fixture()
    mutate(docs[NAV['trajectories']])
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'trajectory_index_completeness')


def test_shard_declared_inventory_and_piece_shard_references_are_exact(tmp_path):
    docs, manifest, assets = sharded_fixture()
    docs[NAV['trajectories']]['shards'][0]['trajectory_ids'] = []
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'trajectory_shard_inventory')
    docs, manifest, assets = sharded_fixture()
    docs['04_REELS/R1/camera_geometry.json']['trajectory_shard_refs'] = []
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'piece_trajectory_shard_inventory')


def test_geometry_cannot_exist_both_inline_and_in_shards(tmp_path):
    docs, manifest, assets = sharded_fixture()
    docs[NAV['trajectories']]['trajectories'] = [docs['03_PEOPLE/trajectories/TRAJECTORIES_00000.json']['trajectories'][0]]
    failed(inspect_compact_handoff(package(tmp_path, docs, manifest, assets)), 'duplicate_geometry_storage')
