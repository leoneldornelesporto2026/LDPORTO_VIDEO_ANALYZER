"""Offline geometric fixtures and real temporary MP4 decoding, without models."""
import numpy as np
import pytest

from ldporto.preview_verifier import (
    border_geometry_evidence, border_temporal_report, verify_preview,
    _border_crop_context,
)


def frame(bars=None, studio=False):
    image = np.full((180, 320), 5 if studio else 130, np.uint8)
    if studio:
        image[40:140, 90:230] = 100
    for side, size in (bars or {}).items():
        if side == 'top':
            image[:size] = 0
        elif side == 'bottom':
            image[-size:] = 0
        elif side == 'left':
            image[:, :size] = 0
        else:
            image[:, -size:] = 0
    return image


def samples(images, row=None, expected=None):
    row = row or {'start': 0, 'end': 10, 'layout': 'single_person',
                  'crop': {'rect_end': {'x': .2, 'y': 0, 'width': .5, 'height': 1}}}
    return [dict(frame=i, time=i / 5, segment=[row['start'], row['end']],
                 crop_context=_border_crop_context(row, i / 5, expected or {}, 320, 180),
                 **border_geometry_evidence(image, np)) for i, image in enumerate(images)]


@pytest.mark.parametrize('bars', [
    {'top': 4, 'bottom': 4}, {'top': 30, 'bottom': 30},
    {'top': 60, 'bottom': 60}, {'left': 50, 'right': 50},
    {'top': 20, 'bottom': 20, 'left': 20, 'right': 20},
])
def test_multiple_widths_and_four_sides(bars):
    report = border_temporal_report(samples([frame(bars)] * 5))
    assert report['status'] == 'proved'
    assert set(report['stable_sides']) == set(bars)
    assert report['review_required']
    assert report['render_origin_proved'] is None
    assert report['preview_approved'] is None
    assert report['publish_ready'] is False


def test_studio_subject_does_not_create_straight_rails():
    report = border_temporal_report(samples([frame(studio=True)] * 5))
    assert report['status'] == 'clear'
    assert report['unexpected_rail_samples'] == 0
    assert report['preview_approved'] is None


def test_darkness_and_missing_frames_are_unknown():
    for rows in ([], samples([np.zeros((180, 320), np.uint8)] * 5)):
        report = border_temporal_report(rows)
        assert report['status'] == 'unknown'
        assert report['review_required']


@pytest.mark.parametrize('width', [1, 80])
def test_unresolved_thin_or_extreme_bars_are_not_cleared(width):
    report = border_temporal_report(samples([frame({'top': width, 'bottom': width})] * 5))
    assert report['status'] == 'unknown'
    assert report['review_required']


def test_transient_and_changing_widths_require_review():
    for images in ([frame(), frame({'top': 10, 'bottom': 10}), frame(), frame()],
                   [frame({'top': n, 'bottom': n}) for n in (5, 15, 25, 35)]):
        report = border_temporal_report(samples(images))
        assert report['status'] == 'borderline'
        assert report['stable_sides'] == []
        assert report['review_required']


def test_one_side_and_separate_shots_do_not_prove_paired_bars():
    rows = samples([frame({'top': 15})] * 5)
    assert border_temporal_report(rows)['status'] == 'borderline'
    rows = samples([frame({'top': 15, 'bottom': 15})] * 5)
    for i, row in enumerate(rows):
        row['segment'] = [i, i + 1]
    assert border_temporal_report(rows)['stable_sides'] == []


def test_fit_padding_requires_measured_source_dimensions_and_exact_widths():
    row = {'start': 0, 'end': 10, 'layout': 'full_frame'}
    expected = {'source_width': 320, 'source_height': 120}
    report = border_temporal_report(samples([frame({'top': 30, 'bottom': 30})] * 5, row, expected))
    assert report['status'] == 'clear'
    assert report['expected_padding_rail_samples'] == 10
    for evidence in (None, {'source_width': 320, 'source_height': 180}, expected):
        wrong = border_temporal_report(samples([frame({'top': 50, 'bottom': 50})] * 5, row, evidence))
        assert wrong['status'] == 'proved'
        assert wrong['review_required']


def test_effective_crop_uses_interpolated_delivered_keyframes():
    row = {'start': 0, 'end': 10, 'layout': 'single_person',
           'camera': {'keyframes': [{'time': 0, 'zoom': 1, 'center': [.5, .5]},
                                    {'time': 10, 'zoom': 2, 'center': [.5, .5]}]}}
    context = _border_crop_context(row, 5, {'source_width': 320, 'source_height': 180}, 320, 180)
    assert context['mode'] == 'crop_resize'
    assert context['effective_crop']['width'] == pytest.approx(1 / 1.5)
    assert context['expected_rails_px']['top'] == 0


@pytest.mark.parametrize('kind,state,issue', [
    ('studio', 'clear', None), ('bars', 'proved', 'UNEXPECTED_BORDER'),
    ('dark', 'unknown', 'BORDER_REVIEW_REQUIRED'),
    ('flash', 'borderline', 'BORDER_REVIEW_REQUIRED'),
])
def test_real_mp4_report_and_probe_never_approve(tmp_path, monkeypatch, kind, state, issue):
    import cv2
    import ldporto.preview_verifier as verifier
    monkeypatch.setattr(verifier, '_ffprobe', lambda path: {'streams': [
        {'codec_type': 'video', 'duration': '1'}, {'codec_type': 'audio', 'duration': '1'}]})
    path = tmp_path / (kind + '.mp4')
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 180))
    assert writer.isOpened()
    try:
        for i in range(10):
            image = (frame(studio=True) if kind == 'studio' else
                     np.zeros((180, 320), np.uint8) if kind == 'dark' else
                     frame({'top': 30, 'bottom': 30}) if kind == 'bars' or i == 4 else frame())
            writer.write(cv2.cvtColor(image, cv2.COLOR_GRAY2BGR))
    finally:
        writer.release()
    result = verify_preview(path, {'duration': 1}, [
        {'start': 0, 'end': 1, 'layout': 'single_person',
         'crop': {'rect_end': {'x': 0, 'y': 0, 'width': 1, 'height': 1}}}])
    data = result['data']
    assert data['sampled_frames'] == 5
    assert data['border_report']['status'] == state
    if issue:
        assert result['status'] == 'partial'
        assert issue in {x['issue_type'] for x in data['issues']}
    else:
        assert 'UNEXPECTED_BORDER' not in {x['issue_type'] for x in data['issues']}
    assert data['preview_approved'] is None
    assert data['publish_ready'] is False


def test_missing_mp4_reports_unknown(tmp_path):
    result = verify_preview(tmp_path / 'missing.mp4')
    assert result['status'] == 'unavailable'
    assert result['data']['border_report']['status'] == 'unknown'


@pytest.mark.parametrize('luma,state', [(130, 'clear'), (0, 'unknown')])
def test_canary_package_real_fit_and_unknown_gate(tmp_path, monkeypatch, luma, state):
    import cv2
    from types import SimpleNamespace
    import ldporto.preview_renderer as renderer
    import ldporto.preview_verifier as verifier
    from ldporto.preview_integration import build_preview_package
    monkeypatch.setattr(renderer, 'find_media_tool', lambda name: None)
    monkeypatch.setattr(verifier, '_ffprobe', lambda path: None)
    source = tmp_path / 'synthetic_source.mp4'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 10, (320, 120))
    assert writer.isOpened()
    try:
        for _ in range(10):
            writer.write(np.full((120, 320, 3), luma, np.uint8))
    finally:
        writer.release()
    row = {'start': 0, 'end': 1, 'layout': 'full_frame'}
    package = build_preview_package(SimpleNamespace(video=source, output=tmp_path / 'out'),
                                    {'width': 320, 'height': 120, 'duration': 1},
                                    {'timeline': [row]},
                                    {'enabled': True, 'max_canaries': 1, 'canary_seconds': 1,
                                     'output_width': 320, 'output_height': 180})
    item = package['data']['canaries'][0]
    assert item['render']['source_width'] == 320
    assert item['render']['source_height'] == 120
    report = item['validation']['border_report']
    assert report['status'] == state
    assert report['preview_approved'] is None
    assert report['publish_ready'] is False
    if state == 'unknown':
        assert package['status'] == 'partial'
        assert item['accepted_preview_path'] is None
        assert not package['data']['closed_loop']['repair_accepted']
    else:
        assert report['expected_padding_rail_samples'] == 10
        assert item['accepted_preview_path'] is not None  # Technical acceptance only.
