"""Stage 30 synthetic offline evidence; no source video or rendered zoom."""
from copy import deepcopy

import pytest

from ldporto.shots import build_shots
from ldporto.person_motion import build_person_motion
from ldporto.camera_timeline import build_camera_timeline
from ldporto.visual_sampling import ShotBoundarySamplingPlan, ShortShotSamplingPlan


def fixture():
    scenes = [dict(scene_id='S0', start=0., end=1.),
              dict(scene_id='S1', start=1., end=1.4),
              dict(scene_id='S2', start=1.4, end=2.4)]
    vision = {'frames': [], 'observations': []}
    for scene, person, times, x in zip(scenes, ['A', 'B', 'A'],
            [[.1, .9], [1.05, 1.35], [1.5, 2.3]], [.2, .8, .7]):
        for t in times:
            vision['frames'].append(dict(time=t, scene_id=scene['scene_id'],
                visible_people=[person], boundary_difference=.4))
            vision['observations'].append(dict(time=t, scene_id=scene['scene_id'],
                person_id=person, track_id=scene['scene_id']+'T', face_visible=True,
                face_height=.5, face_area=.1, center={'x': x, 'y': .5},
                safe_crop_possible=True))
    return scenes, vision


def test_reaction_return_links_identity_without_linking_crop_geometry():
    scenes, vision = fixture()
    for o in vision['observations']:
        if o['person_id'] == 'B':
            o.update(reaction_detected=True, reaction_type='nodding')
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    assert [s['shot_role'] for s in shots] == ['main_person', 'reaction', 'main_person']
    assert shots[1]['reaction_people'] == ['B']
    assert shots[2]['participant_links'] == [dict(person_id='A', previous_observed_shot_id='SHOT_00000',
        track_ids=['S2T'], method='upstream_person_id', geometry_continuity=False)]
    assert all(s['shot_type'] == 'close_up' for s in shots)
    assert all(s['sampling_coverage']['start_observed'] and s['sampling_coverage']['end_observed'] for s in shots)


def test_shot_samples_sorted_and_end_is_exclusive():
    scenes, vision = fixture()
    vision['frames'].reverse()
    vision['frames'].append(dict(time=1., scene_id='S0', visible_people=['STALE']))
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    assert shots[0]['sampling_coverage']['first_sample_at'] == .1
    assert shots[0]['sample_count'] == 2
    assert shots[0]['primary_visual_person'] == 'A'


def test_missing_edge_samples_are_reported_without_synthetic_observations():
    scene = dict(scene_id='S', start=0., end=10.)
    data = build_shots([scene], {'frames': [dict(time=5., scene_id='S', visible_people=[])],
                              'observations': []}, {}, {})['data']['shots'][0]
    assert data['sampling_coverage']['start_observed'] is False
    assert data['sampling_coverage']['end_observed'] is False
    assert data['face_visibility_score'] is None
    assert data['primary_visual_person'] is None


def test_explicit_tv_cut_preserves_source_and_does_not_claim_local_speech():
    scenes, vision = fixture()
    scenes[1]['tv_cut_verified'] = True
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    active = [dict(start=0., end=2.4, active_person='B', active_speaker_state='CONFIRMED')]
    timeline = build_camera_timeline({'duration': 2.4}, vision, shots, active, [], {})['data']['timeline']
    assert shots[1]['shot_role'] == 'tv_cut'
    assert shots[0]['tv_cut_verified'] is None
    tv = [r for r in timeline if r['shot_id'] == shots[1]['shot_id']]
    assert tv and all(r['active_person'] is None and not r['vertical_crop']['safe'] for r in tv)
    assert all(r['vertical_crop']['center_x'] == .5 for r in tv)


def test_fast_cuts_reset_crop_and_motion_but_keep_participant_return():
    scenes, vision = fixture()
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    people = build_person_motion(vision, {})['data']['people']
    a = next(p for p in people if p['person_id'] == 'A')['samples']
    assert a[2]['reset_reason'] == 'source_boundary'
    assert a[2]['center_x'] == .7
    assert a[2]['velocity_x'] is None and a[2]['acceleration_x'] is None
    active = [dict(start=s['start'], end=s['end'], active_person=p, active_speaker_state='CONFIRMED')
              for s, p in zip(scenes, ['A', 'B', 'A'])]
    rows = build_camera_timeline({'duration': 2.4}, vision, shots, active, people, {})['data']['timeline']
    for shot in shots[1:]:
        first = next(r for r in rows if r['shot_id'] == shot['shot_id'])
        assert first['crop_continuity'] == 'reset_at_source_boundary'
        assert first['vertical_crop']['recommended_layout'] == 'full_frame'
        assert first['vertical_crop']['center_x'] == .5
        assert first['vertical_crop']['recommended_zoom'] == 1.
        assert first['movement']['velocity_x'] is None


def test_missing_face_never_implies_occlusion_or_safe_crop():
    scenes, vision = fixture()
    for o in vision['observations']:
        o['face_visible'] = False
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    assert all(s['shot_type'] == 'unknown' for s in shots)
    active = [dict(start=0., end=2.4, active_person='A', active_speaker_state='CONFIRMED')]
    rows = build_camera_timeline({'duration': 2.4}, vision, shots, active, [], {})['data']['timeline']
    assert all(r['face_presence'] == 'unknown' and not r['vertical_crop']['safe'] for r in rows)
    assert all('occluded' not in str(r) for r in rows)


@pytest.mark.parametrize('change,reason', [('scene_id', 'source_boundary'), ('track_id', 'track_change'),
                                        ('time', 'observation_gap')])
def test_motion_resets_and_does_not_smooth_across_break(change, reason):
    scenes, vision = fixture()
    first = vision['observations'][0]
    second = dict(first, time=.5, center={'x': .8, 'y': .5})
    second[change] = 3. if change == 'time' else 'NEW'
    rows = build_person_motion({'observations': [first, second]}, {})['data']['people'][0]['samples']
    assert rows[1]['reset_reason'] == reason
    assert rows[1]['center_x'] == .8 and rows[1]['velocity_x'] is None


def test_duplicate_motion_frames_do_not_bias_velocity_or_acceleration():
    _, vision = fixture()
    observations = vision['observations'][:2]
    original = build_person_motion({'observations': observations}, {})
    duplicated = build_person_motion({'observations': observations + deepcopy(observations)}, {})
    assert duplicated == original
    assert original['data']['people'][0]['samples'][1]['acceleration_x'] is None


def test_timeline_rejects_motion_from_another_track():
    scenes, vision = fixture()
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    people = build_person_motion(vision, {})['data']['people']
    for p in people:
        for s in p['samples']:
            s['track_id'] = 'STALE'
    active = [dict(start=0., end=2.4, active_person='A', active_speaker_state='CONFIRMED')]
    rows = build_camera_timeline({'duration': 2.4}, vision, shots, active, people, {})['data']['timeline']
    assert all(r['movement'] is None for r in rows)


def test_open_plan_does_not_assign_principal_or_reaction_from_motion():
    scenes, vision = fixture()
    for f in vision['frames']:
        f['visible_people'] = ['A', 'B', 'C']
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    assert all(s['shot_type'] == 'group' and s['primary_visual_person'] is None and
               s['reaction_people'] == [] and s['shot_role'] == 'unknown' for s in shots)


def test_existing_boundary_plans_cover_long_and_short_shots_without_replay():
    scenes = [dict(start=0., end=8.), dict(start=8., end=8.4), dict(start=8.4, end=20.)]
    long = ShotBoundarySamplingPlan(scenes)
    short = ShortShotSamplingPlan(scenes)
    assert long.times == [.12, 7.88, 8.52, 19.88]
    assert all(8. < t < 8.4 for t in short.times)
    resumed = ShotBoundarySamplingPlan(scenes, start_time=8.6)
    assert resumed.times == [19.88]
    assert not resumed.due(8.6)


def test_measured_motion_reaches_timeline_with_track_and_compensation_provenance():
    scenes, vision = fixture()
    vision['observations'][1]['center'] = {'x': .4, 'y': .5}
    shots = build_shots(scenes, vision, {}, {})['data']['shots']
    people = build_person_motion(vision, {})['data']['people']
    active = [dict(start=0., end=1., active_person='A', active_speaker_state='CONFIRMED')]
    rows = build_camera_timeline({'duration': 2.4}, vision, shots, active, people, {})['data']['timeline']
    moving = next(r['movement'] for r in rows if r['movement'] and r['movement']['velocity_x'] is not None)
    assert moving['velocity_x'] == pytest.approx(.0875)
    assert moving['movement_direction'] == 'right'
    assert moving['scene_id'] == 'S0' and moving['track_id'] == 'S0T'
    assert moving['camera_compensation_measured'] is False
    assert all(r['vertical_crop']['recommended_zoom'] == 1. for r in rows)


def test_no_visual_frames_preserves_unknown_face_and_focus():
    rows = build_camera_timeline({'duration': 2.}, {}, [], [], [], {})['data']['timeline']
    assert rows[0]['face_presence'] == 'unknown'
    assert rows[0]['active_person'] is None and rows[0]['movement'] is None
    assert rows[0]['vertical_crop']['recommended_layout'] == 'full_frame'
