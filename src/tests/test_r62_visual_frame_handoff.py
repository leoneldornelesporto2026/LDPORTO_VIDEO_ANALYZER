"""Focused synthetic handoff contracts; these do not homologate the real show."""
from copy import deepcopy
import json
from pathlib import Path

import cv2
import jsonschema
import numpy as np
import pytest

from ldporto.core import file_hash
from ldporto.visual_frame_handoff import (SparseFrameProvider, VisualEvidenceIndex,
    build_visual_frame_handoff, plan_frame_times, project_source_bbox,
    validate_visual_frame_handoff, visual_handoff_schema)


SOURCE_HASH, PACKAGE_HASH = 'a' * 64, 'b' * 64


def analysis_fixture():
    def camera(a, b, shot, center):
        return {'director_id': 'D_' + shot, 'source_shot_id': shot, 'start': a, 'end': b,
            'layout': 'single_person', 'focus_person': 'ANONYMOUS_001',
            'camera_mode': 'HOLD', 'crop': {'safe': True,
                'rect_end': {'x': .3, 'y': 0., 'width': .3, 'height': 1.}, 'preflight_sample_count': 2},
            'camera': {'keyframes': [{'time': a, 'center': center, 'zoom': 1.},
                                     {'time': b, 'center': [.6, .5], 'zoom': 1.1}]}}
    return {'metadata': {'duration': 20., 'width': 1920, 'height': 1080, 'fps': 24.,
                         'rotation': 0, 'sha256': SOURCE_HASH},
        'camera_director_timeline': [camera(0., 12., 'S1', [.4, .5]), camera(12., 20., 'S2', [.5, .5])],
        'person_tracks': [{'track_id': 'T1', 'first_seen': 1., 'last_seen': 18.,
                           'identity_status': 'within_track_only'}],
        'person_appearances': [{'appearance_id': 'A_' + str(t), 'observed_at': t,
            'track_id': 'T1', 'person_id': 'ANONYMOUS_001', 'scene_id': 'SC1' if t < 12 else 'SC2',
            'body_bbox': {'x': .4, 'y': .2, 'width': .2, 'height': .7},
            'face_bbox': {'x': .45, 'y': .2, 'width': .08, 'height': .12},
            'face_visible': True, 'body_visible': True, 'confidence': .8}
            for t in (1., 10.25, 10.75, 13., 15.5, 19.)]}


def candidate_fixture():
    return {'candidate_id': 'REEL_SYNTHETIC', 'start': 10., 'end': 17.,
            'transcript_literal': 'Synthetic fixture literal text.', 'segment_ids': ['SYNTHETIC_SEGMENT']}


def captured_fixture(timestamp, output):
    # A real decoded image artifact, with synthetic pixels and explicit provenance.
    image = np.full((36, 64, 3), 80, dtype=np.uint8)
    image[8:22, 24:38] = 180
    got, encoded = cv2.imencode('.jpg', image)
    assert got
    encoded.tofile(str(output))
    return {'captured': True, 'source_time_s': timestamp, 'source_frame_index': None,
        'timestamp_provenance': 'synthetic_fixture_time', 'width': 64, 'height': 36,
        'source_decoded_width': 1920, 'source_decoded_height': 1080,
        'capture_method': 'synthetic_fixture_image', 'quality': 'fixture_only'}


def build(tmp_path, **kwargs):
    analysis = kwargs.pop('analysis', analysis_fixture())
    candidate = kwargs.pop('candidate', candidate_fixture())
    directory = tmp_path / 'handoff'
    manifest = build_visual_frame_handoff(analysis, candidate, directory,
        source_sha256=SOURCE_HASH, package_sha256=PACKAGE_HASH, revision='SYNTHETIC_REV_1', **kwargs)
    return directory, manifest


def read(directory, name):
    return json.loads((directory / name).read_text(encoding='utf-8'))


def rehash(directory, name):
    path = directory / 'visual_handoff_manifest.json'
    value = read(directory, path.name)
    for row in value['files']:
        if row['path'] == name:
            row['sha256'], row['bytes'] = file_hash(directory / name), (directory / name).stat().st_size
    path.write_text(json.dumps(value), encoding='utf-8')


def test_complete_artifacts_are_source_bound_and_never_approval(tmp_path):
    analysis = analysis_fixture()
    previous = deepcopy(analysis)
    directory, manifest = build(tmp_path, analysis=analysis, frame_provider=captured_fixture)
    assert analysis == previous
    assert validate_visual_frame_handoff(directory)['valid'] is True
    jsonschema.Draft202012Validator(visual_handoff_schema()).validate(manifest)
    assert manifest['source_sha256'] == SOURCE_HASH
    assert manifest['input_package_sha256'] == PACKAGE_HASH
    assert manifest['editorial_state'] == 'PARTIAL'
    assert manifest['preview_approved'] is manifest['publish_ready'] is False
    assert len(manifest['files']) >= 10
    sheet = read(directory, 'contact_sheets/index.json')
    assert cv2.imread(str(directory / sheet['path'])) is not None
    assert all(row['score'] is None and row['eligibility'] == 'UNVERIFIED'
               for row in read(directory, 'thumbnail_candidates.json')['candidates'])


def test_non_contiguous_story_uses_concatenated_clip_time_and_preserves_gaps(tmp_path):
    candidate = {**candidate_fixture(), 'story_id': 'STORY_SYNTHETIC_PART_01'}
    directory, manifest = build(tmp_path, candidate=candidate, frame_provider=captured_fixture,
        intervals=[{'start': 10., 'end': 12.}, {'start': 15., 'end': 17.}])
    assert manifest['candidate_id'] == 'STORY_SYNTHETIC_PART_01'
    assert manifest['parent_candidate_id'] == 'REEL_SYNTHETIC'
    assert manifest['source_intervals'][1]['clip_start'] == 2.
    points = [point for row in read(directory, 'visual_tracks.json')['tracks'] for point in row['observations']]
    assert [point['source_time_s'] for point in points] == [10.25, 10.75, 15.5]
    assert points[-1]['clip_time_s'] == 2.5
    assert all(row['interpolation_allowed'] is False and row['cross_cut_identity_propagation'] is False
               for row in read(directory, 'visual_tracks.json')['tracks'])
    assert all(not 12. <= frame['source_time_s'] < 15.
               for frame in read(directory, 'frame_index.json')['frames'])


def test_missing_provider_is_explicit_not_a_captured_frame(tmp_path):
    directory, manifest = build(tmp_path)
    assert manifest['coverage']['captured_frames'] == 0
    assert manifest['coverage']['missing_frames'] > 0
    assert read(directory, 'frame_index.json')['frames'] == []
    assert list((directory / 'selected_frames').iterdir()) == []
    assert read(directory, 'contact_sheets/index.json')['status'] == 'unavailable'
    assert validate_visual_frame_handoff(directory)['valid']


def test_safe_areas_are_observed_projection_and_unknown_overlay(tmp_path):
    directory, _ = build(tmp_path)
    safe = read(directory, 'safe_areas.json')
    assert safe['platform_margins_status'] == 'unknown'
    assert safe['overlay_approval'] is False
    assert all(zone == {'status': 'unknown', 'rect': None} for zone in safe['overlay_zones'].values())
    assert safe['protected_regions']
    assert all(region['output_projection']['final_render_verified'] is False
               for region in safe['protected_regions'])
    assert 'head_full_extent' in safe['unobserved_region_types']
    assert all(region['region_type'] != 'head_full_extent' for region in safe['protected_regions'])


def test_bbox_projection_uses_crop_or_source_contain_and_rejects_clipping():
    face = {'x': .4, 'y': .2, 'width': .1, 'height': .1}
    crop = {'x': .25, 'y': .1, 'width': .5, 'height': .8}
    output = project_source_bbox(face, crop=crop)
    assert output['bbox_final_normalized'] == pytest.approx({'x': .3, 'y': .125, 'width': .2, 'height': .125})
    fitted = project_source_bbox(face)
    assert fitted['bbox_final_normalized']['height'] == pytest.approx(.1 * 1080 * (1080 / 1920) / 1920)
    clipped = project_source_bbox(face, crop={'x': .45, 'y': 0., 'width': .3, 'height': 1.})
    assert clipped['status'] == 'clipped_by_proposed_crop'
    assert project_source_bbox({'x': -1., 'y': 0., 'width': .1, 'height': .1})['status'] == 'unknown'


def test_adaptive_sampling_preserves_shared_first_last_anchors():
    analysis, candidate = analysis_fixture(), candidate_fixture()
    index = VisualEvidenceIndex(analysis)
    anchors = plan_frame_times(analysis, candidate, evidence_index=index, max_frames=2)['requests']
    adaptive = plan_frame_times(analysis, candidate, evidence_index=index, max_frames=6)['requests']
    assert [row['requested_source_time_s'] for row in anchors] == [adaptive[0]['requested_source_time_s'], adaptive[-1]['requested_source_time_s']]
    assert all(candidate['start'] <= row['requested_source_time_s'] < candidate['end'] for row in adaptive)


def test_candidate_trim_is_not_claimed_as_a_real_source_cut(tmp_path):
    directory, _ = build(tmp_path)
    transitions = read(directory, 'scene_transitions.json')['transitions']
    assert transitions[0]['source_time_s'] == 10.
    assert transitions[0]['event'] == 'selected_interval_start_inside_shot'
    assert transitions[0]['source_shot_start_s'] == 0.
    assert transitions[1]['source_time_s'] == 12.
    assert transitions[1]['event'] == 'source_shot_boundary'


def test_revised_camera_artifact_reference_and_hash_are_explicit(tmp_path):
    analysis = analysis_fixture()
    analysis['camera_timeline_artifact_ref'] = 'camera/r62_camera_timeline.json'
    directory, manifest = build(tmp_path, analysis=analysis)
    assert manifest['dependencies'][0]['path'] == 'camera/r62_camera_timeline.json'
    camera = read(directory, 'camera_keyframes.json')
    assert camera['source_timeline_ref'] == 'camera/r62_camera_timeline.json'
    assert camera['timeline_sha256'] == manifest['dependencies'][0]['content_sha256']
    assert all(row['source_timeline_ref'] == 'camera/r62_camera_timeline.json' for row in camera['segments'])


def test_story_unit_canonical_literal_and_segment_ids_are_preserved(tmp_path):
    story = {'story_id': 'UNIT_SYNTHETIC', 'start': 10., 'end': 11.,
             'literal_text': 'Literal unit fixture.', 'source_segment_ids': ['SEG_UNIT_01']}
    directory, _ = build(tmp_path, candidate=story)
    storyboard = read(directory, 'storyboard.json')
    assert storyboard['transcript_literal'] == 'Literal unit fixture.'
    assert storyboard['source_segment_ids'] == ['SEG_UNIT_01']
    assert storyboard['transcript_gaps_status'] == 'unknown'


def test_integrity_and_paths_are_reopened_and_checked(tmp_path):
    directory, _ = build(tmp_path, frame_provider=captured_fixture)
    (directory / 'storyboard.json').write_text('{}', encoding='utf-8')
    result = validate_visual_frame_handoff(directory)
    assert result['valid'] is False
    assert 'visual_integrity_mismatch:storyboard.json' in result['errors']
    manifest = read(directory, 'visual_handoff_manifest.json')
    manifest['files'].append({'path': '../outside.json', 'sha256': SOURCE_HASH, 'bytes': 0})
    (directory / 'visual_handoff_manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert 'visual_unsafe_or_duplicate_path:../outside.json' in validate_visual_frame_handoff(directory)['errors']


def test_temporal_and_bbox_semantics_are_checked_after_rehash(tmp_path):
    directory, _ = build(tmp_path)
    path = directory / 'visual_tracks.json'
    tracks = read(directory, path.name)
    tracks['tracks'][0]['observations'][0]['clip_time_s'] += 5.
    tracks['tracks'][0]['observations'][0]['bboxes']['person']['width'] = 2.
    path.write_text(json.dumps(tracks), encoding='utf-8')
    rehash(directory, path.name)
    result = validate_visual_frame_handoff(directory)
    assert any('visual_time_basis_mismatch' in error for error in result['errors'])
    assert any('visual_invalid_bbox' in error for error in result['errors'])


def test_budget_and_existing_revision_fail_without_overwriting(tmp_path):
    with pytest.raises(ValueError, match='candidate_byte_budget'):
        build(tmp_path, max_bytes=30)
    assert not (tmp_path / 'handoff').exists()
    assert not list(tmp_path.glob('.visual_handoff_*'))
    directory, _ = build(tmp_path)
    prior_hash = file_hash(directory / 'visual_handoff_manifest.json')
    with pytest.raises(FileExistsError):
        build(tmp_path)
    assert file_hash(directory / 'visual_handoff_manifest.json') == prior_hash


def test_source_mismatch_and_bad_intervals_are_rejected(tmp_path):
    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = 'c' * 64
    with pytest.raises(ValueError, match='sha256_mismatch'):
        build(tmp_path, analysis=analysis)
    with pytest.raises(ValueError, match='overlapping_or_unordered'):
        build(tmp_path, intervals=[{'start': 10., 'end': 15.}, {'start': 14., 'end': 17.}])


def test_shared_decoder_warms_real_synthetic_frames_and_obeys_global_cap(tmp_path):
    source = tmp_path / 'synthetic.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 10., (80, 60))
    assert writer.isOpened()
    for index in range(20):
        frame = np.full((60, 80, 3), index * 7, dtype=np.uint8)
        frame[10:30, 10 + index:30 + index] = 240
        writer.write(frame)
    writer.release()
    prior_hash = file_hash(source)
    with SparseFrameProvider(source, max_frames=2) as provider:
        assert provider.get(.2)['captured'] is True
        decoded = provider.decoded_frames
        output = tmp_path / 'warm.jpg'
        assert provider(.2, output)['captured'] is True
        assert provider.decoded_frames == decoded
        assert cv2.imread(str(output)) is not None
        assert provider.get(.7)['captured'] is True
        assert provider.get(1.) == {'captured': False, 'reason': 'global_frame_budget_exhausted'}
        assert len(provider.cache) == 2
    assert file_hash(source) == prior_hash
    with pytest.raises(ValueError, match='source_sha256_mismatch'):
        with SparseFrameProvider(source, metadata={'sha256': 'f' * 64}):
            pass
