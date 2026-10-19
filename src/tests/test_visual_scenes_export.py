"""Complete scene-export contracts using explicit synthetic images, never models."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from PIL import Image
import pytest

from ldporto.visual_scenes_export import (
    export_visual_scenes, plan_scene_windows, validate_visual_scene_export,
)


SOURCE_SHA = 'a' * 64


def analysis_fixture(*, duration=6., scenes=None):
    if scenes is None:
        scenes = [dict(scene_id='SCENE_A', start=0., end=duration)]
    return {
        'metadata': {'sha256': SOURCE_SHA, 'duration': duration,
                     'width': 1920, 'height': 1080, 'fps': 30., 'rotation': 0},
        'scenes': deepcopy(scenes),
        'selected_moments': [], 'candidates': [],
        'editorial_integrity': {'state': 'P1_DEGRADED'},
        'transcript_segments': [], 'words': [],
    }


class SyntheticFrames:
    """Injected fixture with truthful synthetic provenance, not real video proof."""
    def __init__(self, transform=None, *, fail=None,
                 provenance='opencv_decoder_reported'):
        self.calls = []
        self.transform = transform or (lambda timestamp: timestamp)
        self.fail = fail or (lambda timestamp: False)
        self.provenance = provenance

    def __call__(self, timestamp, output):
        self.calls.append(timestamp)
        if self.fail(timestamp):
            return {'captured': False, 'reason': 'SYNTHETIC_DECODE_FAILURE'}
        actual = self.transform(timestamp)
        # The function under test uses decoder-reported timing. These pixels and
        # timing receipts are deliberately synthetic test inputs.
        tone = int(round(max(0., actual) * 137)) % 240
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (96, 54), (tone, (tone + 31) % 255, 37)).save(path, 'JPEG')
        return {'captured': True, 'source_time_s': actual,
                'source_frame_index': round(actual * 30),
                'timestamp_provenance': self.provenance,
                'width': 96, 'height': 54,
                'source_decoded_width': 1920, 'source_decoded_height': 1080,
                'capture_method': 'SYNTHETIC_TEST_FIXTURE_NOT_SOURCE_EVIDENCE'}


def export(tmp_path, analysis=None, provider=None, *, destination=None,
           cache_directory=None, **kwargs):
    destination = destination or tmp_path / 'export'
    result = export_visual_scenes(
        analysis or analysis_fixture(), None, destination,
        frame_provider=provider or SyntheticFrames(), build_pdf=False,
        cache_directory=cache_directory, **kwargs)
    return destination, result


def assert_cover(rows, start, end):
    cursor = start
    for row in rows:
        assert row['start_ms'] == pytest.approx(cursor, abs=1e-6)
        assert row['start_ms'] < row['end_ms']
        cursor = row['end_ms']
    assert cursor == pytest.approx(end, abs=1e-6)


def test_micro_windows_cover_all_original_scenes_in_absolute_chronology():
    scenes = [dict(scene_id='LAST_UNSELECTED', start=44., end=66.194),
              dict(scene_id='FIRST', start=0., end=4.),
              dict(scene_id='MIDDLE', start=4., end=44.)]
    result = plan_scene_windows(scenes, 66.194)
    assert result['video_duration_ms'] == 66194
    assert result['original_scene_count'] == 3
    assert [row['scene_id'] for row in result['scenes']] == [
        'FIRST', 'MIDDLE', 'LAST_UNSELECTED']
    assert_cover(result['scenes'], 0., 66194.)
    for scene in result['scenes']:
        assert scene['kind'] == 'SCENE'
        assert_cover(scene['micro_windows'], scene['start_ms'], scene['end_ms'])
        assert all(0 < row['end_ms'] - row['start_ms'] <= 3000
                   for row in scene['micro_windows'])


def test_gaps_are_explicit_fallback_intervals_without_replacing_scene_identity():
    scenes = [dict(scene_id='PERSISTED_A', start=1., end=3.2),
              dict(scene_id='PERSISTED_B', start=7.1, end=8.)]
    result = plan_scene_windows(scenes, 10.)
    assert result['original_scene_count'] == 2
    assert_cover(result['scenes'], 0., 10000.)
    originals = [row for row in result['scenes'] if row['kind'] == 'SCENE']
    assert [row['scene_id'] for row in originals] == ['PERSISTED_A', 'PERSISTED_B']
    fallbacks = [row for row in result['scenes'] if row['kind'] == 'FALLBACK_INTERVAL']
    assert [(row['start_ms'], row['end_ms']) for row in fallbacks] == [
        (0., 1000.), (3200., 7100.), (8000., 10000.)]
    assert len({row['scene_id'] for row in result['scenes']}) == 5
    for scene in fallbacks:
        assert scene['scene_id'].startswith('FALLBACK_INTERVAL_')
        assert_cover(scene['micro_windows'], scene['start_ms'], scene['end_ms'])
        assert all(row['end_ms'] - row['start_ms'] <= 3000
                   for row in scene['micro_windows'])


def test_detected_internal_cuts_are_micro_window_boundaries():
    result = plan_scene_windows(
        [dict(scene_id='SCENE_WITH_CUTS', start=0., end=7.)], 7.,
        shots=[dict(shot_id='SHOT_A', start=0., end=1.1),
               dict(shot_id='SHOT_B', start=1.1, end=4.9),
               dict(shot_id='SHOT_C', start=4.9, end=7.)])
    windows = result['scenes'][0]['micro_windows']
    assert_cover(windows, 0., 7000.)
    boundaries = {row['start_ms'] for row in windows} | {row['end_ms'] for row in windows}
    assert {1100., 4900.} <= boundaries
    assert all(row['end_ms'] - row['start_ms'] <= 3000 for row in windows)


def test_microsecond_boundaries_are_not_lost_to_integer_milliseconds():
    result = plan_scene_windows([
        dict(scene_id='A', start=0., end=1.333333),
        dict(scene_id='B', start=1.333333, end=2.000001)], 2.000001)
    assert result['scenes'][0]['end_ms'] == pytest.approx(1333.333)
    assert result['scenes'][1]['start_ms'] == pytest.approx(1333.333)
    assert_cover(result['scenes'], 0., 2000.001)


@pytest.mark.parametrize('scenes,duration', [
    ([dict(scene_id='A', start=-1., end=1.)], 2.),
    ([dict(scene_id='A', start=1., end=1.)], 2.),
    ([dict(scene_id='A', start=0., end=3.)], 2.),
    ([dict(scene_id='A', start=0., end=float('nan'))], 2.),
    ([dict(scene_id='A', start=0., end=2.), dict(scene_id='B', start=1., end=3.)], 3.),
    ([dict(scene_id='A', start=0., end=1.), dict(scene_id='A', start=1., end=2.)], 2.),
    ([dict(scene_id='../ESCAPE', start=0., end=1.)], 1.),
    ([dict(scene_id='A', start=0., end=1.)], float('inf')),
])
def test_invalid_catalog_is_rejected_explicitly(scenes, duration):
    with pytest.raises(ValueError):
        plan_scene_windows(scenes, duration)


def test_complete_export_includes_scene_absent_from_editorial_candidates(tmp_path):
    analysis = analysis_fixture(duration=6., scenes=[
        dict(scene_id='SELECTED', start=0., end=1.),
        dict(scene_id='LOW_SCORE_NOT_SELECTED', start=1., end=6.)])
    analysis['selected_moments'] = [dict(candidate_id='ONLY_CANDIDATE', start=0., end=1.)]
    analysis['candidates'] = deepcopy(analysis['selected_moments'])
    directory, result = export(tmp_path, analysis)
    assert result['export_status'] == 'COMPLETE'
    assert {row['scene_id'] for row in result['scenes']} == {'SELECTED', 'LOW_SCORE_NOT_SELECTED'}
    assert_cover(result['scenes'], 0., 6000.)
    for scene in result['scenes']:
        assert scene['contact_sheet']
        with Image.open(directory / scene['contact_sheet']) as image:
            image.verify()
        for micro in scene['micro_windows']:
            assert micro['frames']
        assert scene['description'] is None
        assert scene['description_status'] == 'NOT_ANALYZED'
    validation = validate_visual_scene_export(directory)
    assert validation['status'] == 'valid', validation
    assert validation['export_status'] == 'COMPLETE'


def test_existing_transcript_references_obey_half_open_scene_boundaries(tmp_path):
    analysis = analysis_fixture(duration=6., scenes=[
        dict(scene_id='FIRST', start=0., end=3., description='Persisted synthetic description.'),
        dict(scene_id='SECOND', start=3., end=6.)])
    analysis['transcript_segments'] = [
        dict(segment_id='INSIDE_FIRST', start=1., end=2., text='Existing literal.'),
        dict(segment_id='CROSSING', start=2.5, end=3.1, text='Existing crossing.'),
        dict(segment_id='AT_SECOND_START', start=3., end=4., text='Existing boundary.')]
    analysis['words'] = [dict(word_id='WORD_BOUNDARY', segment_id='AT_SECOND_START',
                              start=3., end=3.2, text='Existing')]
    _, result = export(tmp_path, analysis)
    first, second = result['scenes']
    assert set(first['transcript_segment_ids']) == {'INSIDE_FIRST', 'CROSSING'}
    assert set(second['transcript_segment_ids']) == {'CROSSING', 'AT_SECOND_START'}
    assert first['word_ids'] == []
    assert second['word_ids'] == ['WORD_BOUNDARY']
    assert first['description'] == 'Persisted synthetic description.'
    assert first['description_status'] == 'PERSISTED_ANALYSIS'
    assert second['description'] is None
    assert second['description_status'] == 'NOT_ANALYZED'


def test_real_cpu_decoder_exports_synthetic_source_with_hash_bound_actual_pts(tmp_path):
    import cv2
    import numpy as np
    source = tmp_path / 'SYNTHETIC_SOURCE_ONLY.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 10., (160, 90))
    assert writer.isOpened()
    for index in range(20):
        image = np.full((90, 160, 3), index * 10, dtype=np.uint8)
        writer.write(image)
    writer.release()
    source_bytes = source.read_bytes()
    analysis = analysis_fixture(duration=2.)
    analysis['metadata'].update(sha256=hashlib.sha256(source_bytes).hexdigest(),
                                width=160, height=90, fps=10.)
    directory = tmp_path / 'actual_decoder_export'
    result = export_visual_scenes(analysis, source, directory, build_pdf=False)
    assert result['export_status'] == 'COMPLETE'
    assert len(result['scenes'][0]['frames']) == 2
    for frame in result['scenes'][0]['frames']:
        assert frame['capture_provenance'] == 'opencv_decoder_reported'
        assert frame['source_time_s'] == pytest.approx(frame['source_frame_index'] / 10.)
    assert source.read_bytes() == source_bytes
    assert validate_visual_scene_export(directory)['status'] == 'valid'
    foreign = deepcopy(analysis)
    foreign['metadata']['sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='source_identity_mismatch'):
        export_visual_scenes(foreign, source, tmp_path / 'foreign_source', build_pdf=False)


def test_export_sorts_and_merges_duplicate_actual_pts(tmp_path):
    # Requests are .75 and2.25. Both decode to the same actual frame at1.25.
    provider = SyntheticFrames(transform=lambda _: 1.25)
    directory, result = export(tmp_path, analysis_fixture(duration=3.), provider)
    frames = result['scenes'][0]['frames']
    assert [row['timestamp_ms'] for row in frames] == [1250.]
    assert len({row['frame_id'] for row in frames}) == len(frames)
    assert result['export_status'] == 'COMPLETE'
    assert validate_visual_scene_export(directory)['status'] == 'valid'


def test_actual_decoder_pts_are_sorted_even_when_receipts_arrive_out_of_order(tmp_path):
    _, result = export(tmp_path, analysis_fixture(duration=3.),
                       SyntheticFrames(transform=lambda time: 3. - time))
    assert [row['timestamp_ms'] for row in result['scenes'][0]['frames']] == [750., 2250.]
    assert result['export_status'] == 'COMPLETE'


def test_one_valid_capture_per_micro_window_is_sufficient(tmp_path):
    _, result = export(tmp_path, analysis_fixture(duration=3.),
                       SyntheticFrames(fail=lambda time: time < 1.5))
    assert result['export_status'] == 'COMPLETE'
    assert len(result['scenes'][0]['micro_windows'][0]['frames']) == 1


def test_export_uses_absolute_actual_time_instead_of_request_or_clip_time(tmp_path):
    analysis = analysis_fixture(duration=43., scenes=[
        dict(scene_id='LEAD', start=0., end=39.65),
        dict(scene_id='OFFSET_SCENE', start=39.65, end=43.)])
    provider = SyntheticFrames(transform=lambda time: time + .01)
    _, result = export(tmp_path, analysis, provider)
    offset = next(row for row in result['scenes'] if row['scene_id'] == 'OFFSET_SCENE')
    timestamps = [row['timestamp_ms'] for row in offset['frames']]
    assert timestamps == sorted(set(timestamps))
    assert all(39650 <= time < 43000 for time in timestamps)
    assert all(row['timestamp_ms'] == pytest.approx(row['source_time_s'] * 1000, abs=.001)
               for row in offset['frames'])
    assert result['export_status'] == 'COMPLETE'


@pytest.mark.parametrize('actual', [-.001, 3., 3.001])
def test_outside_or_end_exclusive_decoded_frame_never_counts_as_coverage(tmp_path, actual):
    _, result = export(tmp_path, analysis_fixture(duration=3.),
                       SyntheticFrames(transform=lambda _: actual))
    assert result['export_status'] in ('PARTIAL', 'FAILED')
    assert result['scenes'][0]['frames'] == []


def test_unknown_decoded_timestamp_never_creates_complete_coverage(tmp_path):
    _, result = export(tmp_path, analysis_fixture(duration=3.),
                       SyntheticFrames(provenance='seek_request_decode_timestamp_unavailable'))
    assert result['export_status'] in ('PARTIAL', 'FAILED')


def test_one_missing_micro_window_is_partial_not_complete(tmp_path):
    directory, result = export(tmp_path, analysis_fixture(duration=6.),
                               SyntheticFrames(fail=lambda time: time >= 3.))
    assert result['export_status'] == 'PARTIAL'
    windows = result['scenes'][0]['micro_windows']
    assert windows[0]['frames'] and not windows[1]['frames']
    validation = validate_visual_scene_export(directory)
    assert validation['export_status'] == 'PARTIAL'


def test_no_captures_is_failed_and_retains_explicit_scene_entries(tmp_path):
    _, result = export(tmp_path, analysis_fixture(duration=6.),
                       SyntheticFrames(fail=lambda _: True))
    assert result['export_status'] == 'FAILED'
    assert result['original_scene_count'] == 1
    assert result['scenes'][0]['scene_id'] == 'SCENE_A'
    assert not result['scenes'][0]['contact_sheet']
    assert all(not row['frames'] for row in result['scenes'][0]['micro_windows'])


def test_catalog_gaps_also_receive_valid_captures_and_contact_sheets(tmp_path):
    analysis = analysis_fixture(duration=7., scenes=[
        dict(scene_id='PERSISTED_SCENE', start=1., end=3.)])
    directory, result = export(tmp_path, analysis)
    assert result['export_status'] == 'COMPLETE'
    assert result['original_scene_count'] == 1
    assert result['fallback_interval_count'] == 2
    assert_cover(result['scenes'], 0., 7000.)
    assert all(scene['contact_sheet'] for scene in result['scenes'])
    assert all(micro['frames'] for scene in result['scenes']
               for micro in scene['micro_windows'])
    assert validate_visual_scene_export(directory)['status'] == 'valid'


def test_invalid_timestamp_receipt_is_retried_on_resume(tmp_path):
    cache = tmp_path / 'cache'
    directory, first = export(tmp_path, analysis_fixture(duration=3.),
                              SyntheticFrames(provenance='seek_request_decode_timestamp_unavailable'),
                              cache_directory=cache)
    assert first['export_status'] == 'FAILED'
    valid_decoder = SyntheticFrames()
    _, retried = export(tmp_path, analysis_fixture(duration=3.), valid_decoder,
                        destination=directory, cache_directory=cache, resume=True)
    assert valid_decoder.calls
    assert retried['export_status'] == 'COMPLETE'
    assert validate_visual_scene_export(directory)['status'] == 'valid'


def test_resume_valid_cache_never_recaptures_and_preserves_images(tmp_path):
    cache = tmp_path / 'cache'
    first = SyntheticFrames()
    directory, initial = export(tmp_path, provider=first, cache_directory=cache)
    assert initial['export_status'] == 'COMPLETE' and first.calls
    original_images = {path.relative_to(directory).as_posix():
                       (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                       for path in directory.rglob('*.jpg')}
    second = SyntheticFrames(fail=lambda _: pytest.fail('valid resumed export recaptured a frame'))
    _, resumed = export(tmp_path, provider=second, destination=directory,
                        cache_directory=cache, resume=True)
    assert resumed['export_status'] == 'COMPLETE'
    assert second.calls == []
    assert original_images == {path.relative_to(directory).as_posix():
                              (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
                              for path in directory.rglob('*.jpg')}


def test_resume_reuses_valid_receipts_and_recaptures_only_hash_mismatch(tmp_path):
    cache = tmp_path / 'cache'
    _, initial = export(tmp_path, cache_directory=cache)
    assert initial['export_status'] == 'COMPLETE'
    receipts = sorted(cache.glob('*.json'))
    assert len(receipts) >= 2
    broken = json.loads(receipts[0].read_text(encoding='utf-8'))
    (cache / broken['image']).write_bytes(b'SYNTHETIC_TAMPERED_IMAGE')
    valid_receipts = {path: (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in receipts[1:]}
    second = SyntheticFrames()
    directory, resumed = export(tmp_path, provider=second,
                                destination=tmp_path / 'resumed_export',
                                cache_directory=cache)
    assert resumed['export_status'] == 'COMPLETE'
    assert second.calls == [broken['requested_source_time_s']]
    assert validate_visual_scene_export(directory)['status'] == 'valid'
    assert all((path.read_bytes(), path.stat().st_mtime_ns) == before
               for path, before in valid_receipts.items())


def test_resume_rechecks_source_duration_instead_of_reusing_stale_coverage(tmp_path):
    analysis = analysis_fixture(duration=6.)
    cache = tmp_path / 'cache'
    directory, initial = export(tmp_path, analysis, cache_directory=cache)
    assert initial['video_duration_ms'] == 6000.
    # Same source/catalog; corrected persisted source duration exposes a tail gap.
    corrected = deepcopy(analysis)
    corrected['metadata']['duration'] = 7.
    _, resumed = export(tmp_path, corrected, destination=directory,
                        cache_directory=cache)
    assert resumed['video_duration_ms'] == 7000.
    assert_cover(resumed['scenes'], 0., 7000.)
    assert resumed['scenes'][-1]['kind'] == 'FALLBACK_INTERVAL'


def test_tampered_contact_sheet_fails_independent_validation(tmp_path):
    directory, result = export(tmp_path)
    sheet = directory / result['scenes'][0]['contact_sheet']
    sheet.write_bytes(b'SYNTHETIC_CORRUPTED_NOT_JPEG')
    validation = validate_visual_scene_export(directory)
    assert validation['status'] == 'failed'
    assert validation['errors']


@pytest.mark.parametrize('target', ['primary_sheet', 'frame_sheet'])
def test_missing_contact_sheet_references_fail_validation(tmp_path, target):
    directory, _ = export(tmp_path)
    path = directory / 'VISUAL_SCENES_INDEX.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    scene = value['scenes'][0]
    missing = 'visuals_all/SCENE_A/DOES_NOT_EXIST.jpg'
    if target == 'primary_sheet':
        scene['contact_sheet'] = missing
    else:
        scene['frames'][0]['contact_sheet'] = missing
    path.write_text(json.dumps(value), encoding='utf-8')
    validation = validate_visual_scene_export(directory)
    assert validation['status'] == 'failed'
    assert validation['errors']


def test_tampered_index_cannot_claim_complete_with_a_missing_required_window(tmp_path):
    directory, result = export(tmp_path)
    path = directory / 'VISUAL_SCENES_INDEX.json'
    value = json.loads(path.read_text(encoding='utf-8'))
    value['scenes'][0]['micro_windows'][0]['frames'] = []
    value['export_status'] = 'COMPLETE'
    path.write_text(json.dumps(value), encoding='utf-8')
    validation = validate_visual_scene_export(directory)
    assert validation['status'] == 'failed'
    assert validation['errors']
