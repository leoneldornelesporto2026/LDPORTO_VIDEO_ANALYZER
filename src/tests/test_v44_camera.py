import numpy as np
from director_fixtures import fixture, turn
from ldporto.camera_director import build_camera_director


def test_dominant_face_fallback_can_crop_without_claiming_speaker_identity():
    metadata, vision, shots = fixture(12)
    result = build_camera_director(metadata, vision, shots, [turn(0, 12, person=None)], [],
                                   {'dominant_face_fallback': True})['data']
    rows = [row for row in result['timeline'] if row['layout'] == 'single_person']
    assert rows and min(row['start'] for row in rows) >= 2
    assert all(row['camera_evidence_role'] == 'DOMINANT_FACE' for row in rows)
    assert all(row['speaker_identity_confirmed'] is False for row in rows)
    assert result['metrics']['dominant_face_coverage'] > .5


def test_ambiguous_equal_faces_do_not_pick_a_visual_target():
    metadata, vision, shots = fixture(12, pair=True)
    result = build_camera_director(metadata, vision, shots, [turn(0, 12, person=None)], [],
                                   {'dominant_face_fallback': True})['data']
    assert not any(row['focus_person'] for row in result['timeline'])


def test_dominant_target_resets_at_source_cut_and_missing_face():
    metadata, vision, shots = fixture(12, cuts=(6,))
    vision['observations'] = [row for row in vision['observations'] if row['time'] < 9]
    result = build_camera_director(metadata, vision, shots, [turn(0, 12, person=None)], [],
                                   {'dominant_face_fallback': True})['data']
    assert all(row['layout'] == 'full_frame' for row in result['timeline'] if 6 <= row['start'] < 8 or row['start'] >= 9.5)
    assert all(row['camera_state'] in {'HOLD', 'RECENTER', 'ZOOM_IN', 'ZOOM_OUT', 'SHOT_SWITCH',
                                      'TARGET_SWITCH', 'RETURN_SOURCE', 'REACTION', 'TWO_SHOT', 'SPLIT'}
               for row in result['timeline'])


def test_broadcast_detection_requires_temporal_text_evidence_not_plain_static_image():
    import cv2
    from ldporto.broadcast_graphics import detect_graphics
    plain = np.full((180, 320, 3), 100, dtype=np.uint8)
    assert detect_graphics([plain] * 8, fps=2)['regions'] == []
    samples = []
    for index in range(8):
        frame = plain.copy()
        cv2.rectangle(frame, (0, 132), (319, 174), (20, 30, 180), -1)
        cv2.putText(frame, 'NEWS LIVE 69,99', (10, 156), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
        samples.append(frame)
    result = detect_graphics(samples, fps=2)
    assert any(row['kind'] == 'lower_third' and row['y_start'] < .85 for row in result['regions'])
    assert all(row['evidence']['edge_density'] > 0 for row in result['regions'])


def test_interview_layout_needs_two_relevant_targets_and_safe_union():
    from ldporto.interview_layout import choose_layout
    faces = [{'person_id': 'A', 'face_bbox': {'x': .25, 'y': .2, 'width': .1, 'height': .2}},
             {'person_id': 'B', 'face_bbox': {'x': .65, 'y': .2, 'width': .1, 'height': .2}}]
    assert choose_layout(faces, ['A'])['layout'] == 'single_speaker'
    assert choose_layout(faces, ['A', 'B'], union_safe=True)['layout'] == 'two_shot'
    assert choose_layout(faces, ['A', 'B'], union_safe=False)['layout'] == 'split_screen'
    assert choose_layout(faces, ['A'], reaction_person='B', reaction_evidence=False)['layout'] == 'single_speaker'


def test_runtime_defaults_enable_visual_fallback_and_keep_identity_metrics_separate():
    from ldporto.config import load_config
    from ldporto.analysis_quality import camera_quality_metrics
    assert load_config()['camera_director']['dominant_face_fallback'] is True
    row = {'start': 0, 'end': 10, 'layout': 'single_person', 'focus_person': 'A',
           'focus_confidence': .95, 'camera_evidence_role': 'DOMINANT_FACE'}
    metrics = camera_quality_metrics([row], 10)
    assert metrics['resolved_focus_coverage'] == 1
    assert metrics['known_speaker_focus_fraction'] == 0


def test_targeted_graphics_reads_only_candidate_windows(tmp_path):
    import cv2
    from ldporto.broadcast_graphics import inspect_candidate_graphics
    path = tmp_path / 'broadcast.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (320, 180))
    assert writer.isOpened()
    for _ in range(60):
        frame = np.full((180, 320, 3), 100, dtype=np.uint8)
        cv2.putText(frame, 'NEWS LIVE 69,99', (10, 156), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 1)
        writer.write(frame)
    writer.release()
    result = inspect_candidate_graphics(path, [{'moment_id': 'M', 'start': 1, 'end': 5}], limit=1)
    assert result['sampled_frames'] == 8
    assert result['intervals'][0]['start'] == 1
    assert result['intervals'][0]['regions'][0]['kind'] == 'lower_third'
