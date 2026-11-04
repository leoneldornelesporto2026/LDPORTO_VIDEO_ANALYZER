"""Native camera mapping contracts, using explicitly synthetic source geometry."""
from copy import deepcopy
import math

import pytest

from ldporto.core import digest
from ldporto.curator_camera_adapter import build_curator_camera_plan


META = {'duration': 200., 'width': 1920, 'height': 1080, 'fps': 24.}


def row(start=100., end=104., keys=None):
    return {'director_id': 'SYNTHETIC_DIRECTOR', 'source_shot_id': 'SYNTHETIC_SHOT',
            'start': start, 'end': end, 'layout': 'single_person', 'focus_person': 'ANONYMOUS',
            'crop': {'safe': True, 'rect_end': {'x': .35, 'y': 0., 'width': .31640625, 'height': 1.}},
            'camera': {'keyframes': keys or [
                {'time': start, 'center': [.51, .5], 'zoom': 1.},
                {'time': end, 'center': [.515, .5], 'zoom': 1.04}]}}


def test_source_times_become_relative_segments_without_mutating_evidence_or_approval():
    timeline = [row()]
    before = deepcopy(timeline)
    plan = build_curator_camera_plan(timeline, 101., 103., META)
    assert timeline == before
    assert plan['source_timeline_sha256'] == digest(timeline)
    assert plan['segments'][0]['start'] == 0 and plan['segments'][-1]['end'] == 2
    assert all(segment['source_start'] == pytest.approx(segment['start'] + 101)
               for segment in plan['segments'])
    assert all(a['end'] == pytest.approx(b['start']) for a, b in zip(plan['segments'], plan['segments'][1:]))
    assert plan['source_keyframes'][0]['camera'] == before[0]['camera']
    for field in ['consumed_by_renderer', 'final_frames_verified', 'preview_approved', 'publication_ready']:
        assert plan[field] is False


def test_unsupported_zoom_has_explicit_fallback_and_preserves_original_intensity():
    timeline = [row()]
    timeline[0]['camera']['keyframes'][-1]['zoom'] = 1.125
    plan = build_curator_camera_plan(timeline, 100., 104., META)
    assert plan['motion_segments'] == 0
    assert all(segment['mode'] == 'full_frame_blur' for segment in plan['segments'])
    assert plan['rejected'][0]['reason'] == 'renderer_zoom_envelope_exceeded_no_clamp'
    assert plan['source_keyframes'][0]['camera']['keyframes'][-1]['zoom'] == 1.125


@pytest.mark.parametrize('change', ['unsafe_crop', 'unknown_target', 'nonfinite_zoom', 'invalid_center'])
def test_unsafe_or_unknown_geometry_never_becomes_executable_individual_crop(change):
    item = row()
    if change == 'unsafe_crop':
        item['crop']['safe'] = False
    elif change == 'unknown_target':
        item['focus_person'] = None
    elif change == 'nonfinite_zoom':
        item['camera']['keyframes'][0]['zoom'] = math.nan
    else:
        item['camera']['keyframes'][0]['center'] = [1.1, .5]
    plan = build_curator_camera_plan([item], 100., 104., META)
    assert plan['rejected'] and plan['motion_segments'] == 0
    assert not plan['preview_approved'] and not plan['publication_ready']


def test_source_gaps_are_preserved_and_overlaps_rejected():
    plan = build_curator_camera_plan([row(101., 103.)], 100., 104., META)
    assert plan['segments'][0]['mode'] == plan['segments'][-1]['mode'] == 'full_frame_blur'
    assert plan['segments'][0]['source_start'] == 100 and plan['segments'][-1]['source_end'] == 104
    with pytest.raises(ValueError, match='overlapping_director_intervals'):
        build_curator_camera_plan([row(100., 103.), row(102., 104.)], 100., 104., META)


def _sample_source(keys, time):
    if time <= keys[0]['time']:
        return keys[0]['center'][1], keys[0]['zoom']
    if time >= keys[-1]['time']:
        return keys[-1]['center'][1], keys[-1]['zoom']
    for left, right in zip(keys, keys[1:]):
        if left['time'] <= time <= right['time']:
            fraction = (time-left['time'])/(right['time']-left['time'])
            return (left['center'][1] + fraction*(right['center'][1]-left['center'][1]),
                    left['zoom'] + fraction*(right['zoom']-left['zoom']))
    raise AssertionError('synthetic_fixture_time_outside_source')


def test_advertised_pixel_error_bounds_combined_center_and_zoom_crop_displacement():
    # Individually small center and scale errors add at the final crop edge.
    keys = [{'time': 0., 'center': [.5, .5], 'zoom': 1.},
            {'time': 2., 'center': [.5, .50055], 'zoom': 1.00145},
            {'time': 4., 'center': [.5, .5], 'zoom': 1.004}]
    plan = build_curator_camera_plan([row(0., 4., keys)], 0., 4., META)
    assert not plan['rejected']
    largest = 0.
    for segment in plan['segments']:
        for index in range(1001):
            fraction = index/1000
            time = segment['source_start'] + fraction*(segment['source_end']-segment['source_start'])
            center, zoom = _sample_source(keys, time)
            native_center = segment['center_y_start'] + fraction*(segment['center_y_end']-segment['center_y_start'])
            ease = fraction*fraction*(3-2*fraction)
            native_zoom = segment['zoom_start'] + ease*(segment['zoom_end']-segment['zoom_start'])
            bottom = min(1., max(0., center-.5/zoom) + 1./zoom)
            native_bottom = min(1., max(0., native_center-.5/native_zoom) + 1./native_zoom)
            largest = max(largest, abs(bottom-native_bottom)*META['height'])
    assert largest <= plan['simplification']['max_source_pixel_error'] + 1e-7
