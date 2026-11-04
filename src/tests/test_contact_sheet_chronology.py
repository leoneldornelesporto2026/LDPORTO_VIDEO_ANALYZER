"""Chronology and source-time regressions on declared synthetic decoder evidence."""
import math

import pytest

cv2 = pytest.importorskip('cv2')
np = pytest.importorskip('numpy')

from ldporto.preview_renderer import build_contact_sheet, decode_source_frame


class SyntheticCapture:
    def __init__(self, *, fps=30., count=2100, unknown_pts=False, static=False,
                 forced_pts=None, failed=False):
        self.fps, self.count = fps, count
        self.unknown_pts, self.static = unknown_pts, static
        self.forced_pts, self.failed = forced_pts, failed
        self.requested, self.index, self.released = 0., 0, False
        self.seeks = []

    def isOpened(self):
        return True

    def set(self, key, value):
        assert key == cv2.CAP_PROP_POS_MSEC
        self.requested = value/1000
        self.seeks.append(self.requested)
        return True

    def read(self):
        self.index = min(self.count-1, max(0, math.floor(self.requested*self.fps+1e-8)))
        if self.failed:
            return False, None
        frame = np.full((90, 160, 3), 75 if self.static else self.index % 200, dtype=np.uint8)
        return True, frame

    def get(self, key):
        if key == cv2.CAP_PROP_FPS:
            return self.fps
        if key == cv2.CAP_PROP_FRAME_COUNT:
            return self.count
        if key == cv2.CAP_PROP_POS_FRAMES:
            return self.index+1
        if key == cv2.CAP_PROP_POS_MSEC:
            return (self.forced_pts*1000 if self.forced_pts is not None else
                    0. if self.unknown_pts else self.index/self.fps*1000)
        return 0.

    def release(self):
        self.released = True


def run_sheet(tmp_path, monkeypatch, capture, interval, timeline=None):
    source = tmp_path/'SYNTHETIC_SOURCE_NOT_A_USER_VIDEO.bin'
    source.write_bytes(b'SYNTHETIC_DECODER_FIXTURE')
    monkeypatch.setattr(cv2, 'VideoCapture', lambda path: capture)
    output = tmp_path/'contact_sheet.jpg'
    result = build_contact_sheet(source, {'start': interval[0], 'end': interval[1]}, output, timeline)
    return result, output


def test_decoder_reports_actual_time_instead_of_requested_seek():
    frame, info = decode_source_frame(SyntheticCapture(), 40.42)
    assert frame is not None
    assert info['requested_source_time_s'] == 40.42
    assert info['source_time_s'] == pytest.approx(40.4)
    assert info['source_frame_index'] == 1212
    assert info['timestamp_provenance'] == 'opencv_decoder_reported'


def test_unsupported_zero_timestamp_is_unknown_without_frame_fps_fabrication():
    frame, info = decode_source_frame(SyntheticCapture(unknown_pts=True), 40.42)
    assert frame is not None and info['source_frame_index'] == 1212
    assert info['source_time_s'] is None and info['timestamp_provenance'] == 'unavailable'
    assert info['requested_source_time_s'] == 40.42


def test_decode_failure_is_an_explicit_absent_capture():
    frame, info = decode_source_frame(SyntheticCapture(failed=True), 1.)
    assert frame is None and info['source_time_s'] is None
    assert info['reason'] == 'source_frame_unavailable'


def test_successful_pixels_survive_unsupported_timestamp_property():
    class UnsupportedTimestampCapture(SyntheticCapture):
        def get(self, key):
            if key == cv2.CAP_PROP_POS_MSEC:
                raise cv2.error('synthetic unsupported property')
            return super().get(key)
    frame, info = decode_source_frame(UnsupportedTimestampCapture(), 1.)
    assert frame is not None and info['source_frame_index'] == 30
    assert info['source_time_s'] is None and info['timestamp_provenance'] == 'unavailable'


def test_known_midpoint_regression_has_six_distinct_ordered_source_frames(tmp_path, monkeypatch):
    from ldporto.core import stamp
    labels = []; original = cv2.putText
    def text(image, label, *args, **kwargs):
        labels.append(label)
        return original(image, label, *args, **kwargs)
    monkeypatch.setattr(cv2, 'putText', text)
    capture = SyntheticCapture()
    result, output = run_sheet(tmp_path, monkeypatch, capture, (39.65, 41.19))
    assert result['status'] == 'ok' and capture.released
    frames = result['frames']; times = [row['source_time_s'] for row in frames]
    assert times == sorted(set(times)) and len(times) == 6
    assert len({row['source_frame_index'] for row in frames}) == 6
    assert all(39.65 <= time < 41.19 for time in times)
    assert all(row['time'] == row['source_time_s'] for row in frames)
    assert any(row['requested_source_time_s'] != row['source_time_s'] for row in frames)
    assert labels == [('source ' if index == 0 else '')+stamp(time) for index, time in enumerate(times)]
    assert cv2.imread(str(output)).shape[:2] == (412, 960)
    assert result['source_and_director_framing'] and result['slot_count'] == 6


def test_sort_uses_actual_pts_after_decode_not_requested_order(tmp_path, monkeypatch):
    import ldporto.preview_renderer as renderer
    times = iter([1.8, 1.2, 1.6, 1.4, 1.1, 1.9])
    def reordered(cap, requested):
        actual = next(times)
        return np.full((90, 160, 3), round(actual*100), dtype=np.uint8), {
            'source_time_s': actual, 'source_frame_index': round(actual*30),
            'timestamp_provenance': 'opencv_decoder_reported', 'requested_source_time_s': requested}
    monkeypatch.setattr(renderer, 'decode_source_frame', reordered)
    result, _ = run_sheet(tmp_path, monkeypatch, SyntheticCapture(), (1., 2.))
    assert result['status'] == 'ok'
    assert [row['source_time_s'] for row in result['frames']] == [1.1, 1.2, 1.4, 1.6, 1.8, 1.9]


def test_short_source_never_draws_same_frame_to_fill_six_slots(tmp_path, monkeypatch):
    result, output = run_sheet(tmp_path, monkeypatch, SyntheticCapture(), (0., .02))
    assert result['status'] == 'partial' and result['frame_count'] == 1
    assert result['reason'] == 'not_enough_distinct_source_frames'
    assert result['dropped_duplicate_frames'] and result['slot_count'] == 6
    assert output.is_file()


def test_identical_pixels_at_distinct_source_pts_are_kept_and_disclosed(tmp_path, monkeypatch):
    result, _ = run_sheet(tmp_path, monkeypatch, SyntheticCapture(static=True), (1., 3.))
    assert result['status'] == 'ok' and result['frame_count'] == 6
    assert result['duplicate_content_frames_count'] == 5
    assert [row['duplicate_content'] for row in result['frames']] == [False]+[True]*5
    assert all(row['duplicate_content_of_slot'] == 0 for row in result['frames'][1:])


def test_unknown_pts_are_partial_and_labels_never_claim_requested_times(tmp_path, monkeypatch):
    labels = []; original = cv2.putText
    def text(image, label, *args, **kwargs):
        labels.append(label)
        return original(image, label, *args, **kwargs)
    monkeypatch.setattr(cv2, 'putText', text)
    result, output = run_sheet(tmp_path, monkeypatch, SyntheticCapture(unknown_pts=True), (1., 3.))
    assert result['status'] == 'partial' and result['reason'] == 'source_timestamps_unavailable'
    assert all(row['source_time_s'] is None and row['time'] is None for row in result['frames'])
    assert not result['chronology_verified_from_decoder_timestamps']
    assert labels and all('PTS unavailable' in label and '00:' not in label for label in labels)
    assert output.is_file()


def test_end_exclusive_actual_pts_are_rejected_even_if_seek_is_inside(tmp_path, monkeypatch):
    result, output = run_sheet(tmp_path, monkeypatch, SyntheticCapture(forced_pts=2.), (1., 2.))
    assert result['status'] == 'unavailable' and not output.exists()
    assert result['capture_failures']
    assert all(row['reason'] == 'decoded_frame_outside_candidate_interval' for row in result['capture_failures'])


def test_zoom_center_replaces_an_interior_normal_slot_without_adding_duplicates(tmp_path, monkeypatch):
    timeline = [{'start': 1.3, 'end': 1.7, 'camera_mode': 'SMART_ZOOM_IN', 'layout': 'full_frame'}]
    result, _ = run_sheet(tmp_path, monkeypatch, SyntheticCapture(), (0., 4.), timeline)
    assert result['status'] == 'ok' and result['frame_count'] == 6
    assert 1.5 in [row['requested_source_time_s'] for row in result['frames']]
    assert len({row['source_time_s'] for row in result['frames']}) == 6


def test_source_duration_clamps_requests_and_captures(tmp_path, monkeypatch):
    capture = SyntheticCapture(count=90)
    result, _ = run_sheet(tmp_path, monkeypatch, capture, (-5., 100.))
    assert result['status'] == 'ok'
    assert result['source_interval'] == {'start': 0., 'end': 3.}
    assert all(0 <= request < 3. for request in capture.seeks)
    assert all(0 <= row['source_time_s'] < 3. for row in result['frames'])


def test_nonfinite_candidate_interval_is_rejected_without_any_seek(tmp_path, monkeypatch):
    capture = SyntheticCapture()
    result, output = run_sheet(tmp_path, monkeypatch, capture, (math.nan, 3.))
    assert result['status'] == 'unavailable' and capture.released
    assert not capture.seeks and not output.exists()


def test_real_tiny_mjpg_roundtrip_preserves_layout_and_monotonic_decoder_times(tmp_path):
    source = tmp_path/'SYNTHETIC_CHRONOLOGY.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 10., (160, 90))
    assert writer.isOpened()
    for index in range(40):
        writer.write(np.full((90, 160, 3), 20+index*3, dtype=np.uint8))
    writer.release()
    output = tmp_path/'real_contact_sheet.jpg'
    result = build_contact_sheet(source, {'start': .5, 'end': 3.5}, output)
    assert result['status'] == 'ok', result
    assert [row['source_time_s'] for row in result['frames']] == sorted({row['source_time_s'] for row in result['frames']})
    assert result['frame_count'] == 6 and cv2.imread(str(output)).shape[:2] == (412, 960)
