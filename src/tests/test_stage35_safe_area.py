"""Offline fixtures: no source media, detector, GPU or final render approval."""
from copy import deepcopy
import pytest
from ldporto.config import DEFAULTS
from ldporto.safe_area import plan_safe_area, rect, intersects, _transform
from ldporto.social_output import ASPECT_RATIOS, build_social_output
from test_v44_social_output import candidate


def fixture():
    c = candidate('A', 0)
    analysis = {
        'metadata': {'width': 1080, 'height': 1920},
        'camera_timeline': [{'start': 0, 'end': 40, 'crop': {
            'rect_end': {'x': 0, 'y': 0, 'width': 1, 'height': 1}}}],
        'people_observations': [{'time': 5, 'face_bbox': {
            'x': .3, 'y': .06, 'width': .4, 'height': .36}, 'confidence': .8}],
        'broadcast_graphics': {'intervals': [{'start': 0, 'end': 40, 'regions': [{
            'kind': 'lower_third', 'persistent': True,
            'x_start': 0, 'x_end': 1, 'y_start': .74, 'y_end': .98, 'confidence': .9}]}]},
    }
    return analysis, c


def plan(analysis, c):
    return plan_safe_area(analysis, c, ASPECT_RATIOS['9:16'], 'upper_middle',
                          {'x': .1, 'y': .08, 'width': .8, 'height': .12})


def test_central_face_and_lower_gc_jointly_move_title_and_caption():
    analysis, c = fixture()
    output = build_social_output(analysis, deepcopy(DEFAULTS), {'candidates': [c]})
    story = output['stories'][0]
    visual, captions = story['visual_plan'], story['caption_plan']
    safe = visual['safe_area_plan']
    s = safe['segments'][0]
    assert visual['title_position'] == 'center_upper'
    assert captions['preferred_position'] == 'center_low'
    assert not intersects(s['title_rect'], s['caption_rect'])
    assert all(not intersects(s[k], o['rect']) for k in ('title_rect', 'caption_rect') for o in s['obstacles'])
    assert safe['confidence'] == .8  # minimum supplied evidence, not accuracy
    assert safe['reposition_required'] and 'conflict_reposition_required' in ' '.join(safe['reposition_reasons'])
    assert safe['safe_area_approved'] is None and safe['post_render_validation_required']
    assert visual['safe_area_verified'] is False and captions['final_safe_area_verified'] is False
    assert safe['max_title_lines'] == captions['max_lines'] == 2
    assert 'no_text_transition_over_punchline' in safe['transition_policy']
    assert story['publication_ready'] is False


def test_missing_geometry_preserves_null_and_manual_fallback():
    c = candidate('A', 0)
    safe = plan({}, c)
    assert safe['confidence'] is None and safe['safe_area_approved'] is None
    assert safe['fallback'] == 'manual_layout_and_final_render_review'
    assert 'camera_interval_missing_or_ambiguous' in safe['reposition_reasons']
    assert 'face_geometry_missing_not_proof_of_absence' in safe['reposition_reasons']


@pytest.mark.parametrize('box', [None, {}, {'x': float('nan'), 'y': 0, 'width': 1, 'height': 1},
                                      {'x': 0, 'y': 0, 'width': -1, 'height': 1},
                                      {'x': .9, 'y': 0, 'width': .2, 'height': 1}])
def test_invalid_boxes_never_become_safe_evidence(box):
    assert rect(box) is None
    analysis, c = fixture()
    analysis['people_observations'][0]['face_bbox'] = box
    safe = plan(analysis, c)
    assert safe['confidence'] is None
    assert 'face_geometry_missing_or_invalid' in safe['reposition_reasons']


def test_no_joint_zone_keeps_positions_null_instead_of_claiming_success():
    analysis, c = fixture()
    analysis['people_observations'][0]['face_bbox'] = dict(x=0, y=0, width=1, height=1)
    safe = plan(analysis, c)
    assert safe['segments'][0]['title_rect'] is None
    assert safe['segments'][0]['caption_rect'] is None
    assert safe['confidence'] is None
    assert 'no_joint_title_caption_zone_manual_layout_required' in safe['reposition_reasons']
    story = build_social_output(analysis, deepcopy(DEFAULTS), {'candidates':[c]})['stories'][0]
    assert story['visual_plan']['title_candidate_rect_normalized'] is None
    assert story['caption_plan']['preferred_position'] == 'dynamic_safe_zone'


def test_crop_projection_and_fit_with_padding_use_output_coordinates():
    profile = ASPECT_RATIOS['9:16']
    metadata = dict(width=1920, height=1080)
    row = {'crop': {'rect_end': dict(x=.25, y=0, width=.5, height=1)}}
    projected, reason = _transform(dict(x=.4, y=.2, width=.1, height=.3), row, 5, metadata, profile)
    assert reason is None
    assert projected['x'] == pytest.approx(.3)
    assert projected['width'] == pytest.approx(.2)
    outside, reason = _transform(dict(x=0, y=0, width=.1, height=.1), row, 5, metadata, profile)
    assert outside is None and reason is None
    fitted, reason = _transform(dict(x=0, y=0, width=1, height=1), {'layout':'full_frame'}, 5, metadata, profile)
    assert reason is None and fitted['y'] > .3 and fitted['height'] < .4


def test_multiple_intervals_hold_pair_and_ignore_outside_cut_ocr_faces():
    analysis, c = fixture()
    row = analysis['camera_timeline'][0]
    row['end'] = 20
    analysis['camera_timeline'].append({**deepcopy(row), 'start':20, 'end':40})
    analysis['people_observations'].append({**deepcopy(analysis['people_observations'][0]), 'time':25})
    analysis['people_observations'].append({'time': 50, 'face_bbox': dict(x=0,y=0,width=1,height=1)})
    analysis['commercial_visual_s8'] = {'texts': [
        {'observed_at': 5, 'moment_id': 'OTHER', 'bbox':dict(x=0,y=0,width=1,height=1)},
        {'observed_at': 50, 'bbox':dict(x=0,y=0,width=1,height=1)}]}
    safe = plan(analysis, c)
    assert len(safe['segments']) == 2
    assert safe['segments'][0]['title_rect'] == safe['segments'][1]['title_rect']
    assert safe['segments'][0]['caption_rect'] == safe['segments'][1]['caption_rect']
    assert safe['confidence'] == .8


def test_split_and_missing_confidence_are_not_approved():
    analysis, c = fixture()
    analysis['camera_timeline'][0]['split'] = {'panels': []}
    # A truthy actual split is deliberately unsupported by this compositor plan.
    safe = plan(analysis, c)
    assert 'split_geometry_requires_final_compositor' in safe['reposition_reasons']
    assert safe['confidence'] is None
    del analysis['camera_timeline'][0]['split']
    del analysis['people_observations'][0]['confidence']
    assert plan(analysis, c)['confidence'] is None


def test_ocr_is_an_obstacle_without_assuming_persistence():
    analysis, c = fixture()
    analysis['commercial_visual_s8'] = {'texts':[{'observed_at': 5, 'moment_id':'A',
        'bbox': dict(x=0, y=.45, width=1, height=.28), 'confidence':.7}]}
    safe = plan(analysis, c)
    assert safe['segments'][0]['caption_rect'] is None
    assert any(o['kind'] == 'ocr' and o['observed_at'] == 5 for o in safe['segments'][0]['obstacles'])


def test_delivered_keyframe_crop_is_used_instead_of_end_rect():
    metadata = dict(width=1920, height=1080)
    row = {'start':0, 'camera':{'keyframes':[
        {'time':0, 'center':[.3,.5], 'zoom':1},
        {'time':10, 'center':[.7,.5], 'zoom':1}]},
        'crop':{'rect_end':dict(x=0,y=0,width=1,height=1)}}
    box = dict(x=.25,y=.1,width=.1,height=.2)
    first, reason = _transform(box, row, 0, metadata, ASPECT_RATIOS['9:16'])
    last, reason2 = _transform(box, row, 10, metadata, ASPECT_RATIOS['9:16'])
    assert reason is reason2 is None
    assert first is not None and last is None


def test_invalid_keyframe_and_unknown_face_time_use_fallback():
    analysis, c = fixture()
    analysis['people_observations'][0]['time'] = None
    assert plan(analysis, c)['confidence'] is None
    row = {'start':0, 'camera':{'keyframes':[{'time':0, 'center':[float('nan'), .5]}]}}
    box = dict(x=.25,y=.1,width=.1,height=.2)
    projected, reason = _transform(box, row, 0, analysis['metadata'], ASPECT_RATIOS['9:16'])
    assert projected is None and reason == 'crop_or_source_geometry_missing_or_invalid'


def test_inspected_technical_render_does_not_approve_social_safe_area(tmp_path):
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    from ldporto.preview_verifier import verify_preview
    path = tmp_path / 'technical_fixture.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (96, 160))
    assert writer.isOpened()
    try:
        for _ in range(10):
            writer.write(np.full((160,96,3), 80, dtype=np.uint8))
    finally:
        writer.release()
    data = verify_preview(path, {'width':96, 'height':160, 'duration':1})['data']
    assert data['sampled_frames'] > 0 and data['verifier_uses_rendered_frames'] is True
    assert data['safe_area_approved'] is None
    assert data['social_safe_area_post_render_validation_required'] is True
    assert data['safe_area_validation_scope'] == 'technical_camera_preview_without_social_overlays'
