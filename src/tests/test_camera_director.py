import copy
import json
import math
from pathlib import Path
import pytest
from director_fixtures import fixture, turn
from ldporto.camera_director import build_camera_director
from ldporto.camera_motion import Axis, CameraMotion
from ldporto.director_config import resolve_config, PROFILES
from ldporto.config import load_config
from ldporto.person_motion import build_person_motion
from ldporto.active_speaker import build_active_speaker


def run(data, active=None, cfg=None, **kwargs):
    m, v, shots = data
    return build_camera_director(m, v, shots, active or [turn(0, m['duration'])],
        kwargs.pop('motion', []), cfg, **kwargs)['data']


def focuses(data):
    return [r['focus_person'] for r in data['timeline'] if r['focus_person']]


def test_long_monologue_stable_and_compacted():
    d = run(fixture(60))
    assert set(focuses(d)) == {'PERSON_A'}
    assert len(d['timeline']) < 10
    assert d['metrics']['director_switches_per_minute'] <= 2


def test_brief_interruption_does_not_switch():
    d = run(fixture(20, pair=True), [turn(0, 8), turn(8, 8.4, 'PERSON_B'), turn(8.4, 20)])
    assert 'PERSON_B' not in focuses(d)
    assert d['metrics']['switches_suppressed'] > 0


def test_stable_challenger_eventually_gets_focus():
    d = run(fixture(25, pair=True), [turn(0, 8), turn(8, 25, 'PERSON_B')])
    assert 'PERSON_B' in focuses(d)
    assert next(r['start'] for r in d['timeline'] if r['focus_person'] == 'PERSON_B') >= 8.9


def test_quick_exchange_prefers_two_shot_no_pinball():
    turns = [turn(i, i+1, 'PERSON_A' if i%2 == 0 else 'PERSON_B') for i in range(20)]
    d = run(fixture(20, pair=True), turns)
    assert any(r['layout'] == 'two_shot' for r in d['timeline'])
    assert d['metrics']['director_switches_per_minute'] < 12


@pytest.mark.parametrize('distant,expected', [(False, 'two_shot'), (True, 'split_candidate')])
def test_overlap_layout(distant, expected):
    d = run(fixture(12, pair=True, distant=distant), [turn(0, 12, overlap=True), turn(0, 12, 'PERSON_B', overlap=True)])
    assert any(r['layout'] == expected for r in d['timeline'])
    assert not any(r['layout'] == 'single_person' for r in d['timeline'])


def test_split_rejects_invisible_second_person():
    d = run(fixture(12), [turn(0, 12, overlap=True), turn(0, 12, 'PERSON_B', overlap=True)])
    assert all(r['layout'] != 'split_candidate' for r in d['timeline'])


def test_split_side_stability():
    d = run(fixture(20, pair=True, distant=True), [turn(0, 20, overlap=True), turn(0, 20, 'PERSON_B', overlap=True)])
    assert {r['split']['left_person'] for r in d['timeline'] if r['split']} == {'PERSON_A'}


def test_unknown_voice_never_invents_person():
    d = run(fixture(12), [turn(0, 12, person=None)])
    assert not focuses(d)
    assert all(r['layout'] == 'full_frame' for r in d['timeline'])


@pytest.mark.parametrize('kind', ['broll', 'b_roll', 'logo', 'empty', 'screen_capture', 'title_card'])
def test_preserve_source_content(kind):
    d = run(fixture(10, kind=kind))
    assert not focuses(d)
    assert all(r['camera']['zoom_end'] == 1 for r in d['timeline'])


def test_slow_walk_pan_is_smooth():
    data = fixture(30, moving=True)
    motion = build_person_motion(data[1], {})['data']['people']
    d = run(data, motion=motion)
    keys = [k for r in d['timeline'] if r['focus_person'] for k in r['camera']['keyframes']]
    assert keys[-1]['center'][0] > keys[0]['center'][0]+.1
    assert max(abs(k['velocity'][0]) for k in keys) <= .12+1e-9
    assert max(abs(k['acceleration'][0]) for k in keys) <= .18+1e-9


def test_jitter_stays_in_deadzone():
    d = run(fixture(15, jitter=True))
    keys = [k for r in d['timeline'] if r['focus_person'] for k in r['camera']['keyframes']]
    assert max(k['center'][0] for k in keys)-min(k['center'][0] for k in keys) < .001
    assert d['metrics']['deadzone_suppressed_moves'] > 0


def test_target_jump_cannot_teleport_controller():
    c = CameraMotion(.2, .5, 1.)
    cfg = resolve_config({'movement_confirm_seconds': 0.})
    for i in range(20):
        before, after, _ = c.move([.9, .5, 1.3], i*.25, .25, cfg)
        assert abs(after[0]-before[0]) <= cfg['max_pan_speed']*.25+1e-9
        assert abs(after[2]-before[2]) <= cfg['max_zoom_speed']*.25+1e-9


def test_zoom_quality_resolution_limit():
    data = fixture(30)
    data[0].update(width=1920, height=1080)
    d = run(data)
    assert all(k['zoom'] <= 1.+1e-8 for r in d['timeline'] for k in r['camera']['keyframes'])


def test_zoom_no_window_oscillation():
    d = run(fixture(18, jitter=True))
    z = [k['zoom'] for r in d['timeline'] if r['focus_person'] for k in r['camera']['keyframes']]
    assert all(b >= a-1e-5 for a, b in zip(z, z[1:]))


def test_long_speech_breathing_is_contextual():
    d = run(fixture(45))
    assert any('long_speech_visual_breathing' in r['decision']['reasons'] for r in d['timeline'])
    early = next(r for r in d['timeline'] if r['focus_person'])
    late = d['timeline'][-1]
    assert late['camera']['zoom_end'] < max(k['zoom'] for k in early['camera']['keyframes'])


def test_hard_cut_reset_no_lookahead_leak():
    d = run(fixture(20, cuts=(10,)), [turn(0, 10), turn(10, 20, 'PERSON_B')])
    assert all(not (r['start'] < 10 < r['end']) for r in d['timeline'])
    assert next(r for r in d['timeline'] if r['start'] == 10)['camera']['transition_in'] == 'source_cut'
    assert all(e['lookahead_horizon'] <= 10 for e in d['debug']['events'] if e['time'] < 10)
    assert all(e['future_speaker'] is None for e in d['debug']['events'] if e['time'] < 10)


def test_reaction_is_objective_without_emotion():
    data = fixture(25, pair=True)
    motion = [{'person_id': 'PERSON_B', 'samples': [{'time': i/4, 'movement_intensity': .9 if 8 <= i/4 <= 8.5 else 0} for i in range(100)]}]
    d = run(data, motion=motion)
    reactions = [r for r in d['timeline'] if r['reaction']]
    assert reactions and all(r['reaction']['emotion'] is None for r in reactions)
    assert d['timeline'][-1]['focus_person'] == 'PERSON_A'


def test_low_confidence_is_null():
    d = run(fixture(10), [turn(0, 10, confidence=.2)])
    assert not focuses(d)


def test_nan_inf_rejected_in_config():
    for value in (float('nan'), float('inf'), True, -1):
        with pytest.raises(ValueError):
            resolve_config({'max_zoom_default': value})


@pytest.mark.parametrize('profile', list(PROFILES))
def test_profiles_share_engine(profile):
    d = run(fixture(10), cfg={'profile': profile})
    assert d['config']['profile'] == profile
    json.dumps(d, allow_nan=False)


def test_one_mapping_window_never_becomes_consensus():
    _, v, _ = fixture(10)
    raw = [{'start': 0, 'end': 5, 'speaker': 'S', 'person_id': 'PERSON_A', 'confidence': .99}]
    d = build_active_speaker({'turns': [{'start': 0, 'end': 10, 'speaker': 'S'}]}, v, raw, {})['data']
    assert all(r['person_id'] is None for r in d['intervals'])


def test_consensus_visibility_is_local_and_manual_scoped():
    _, v, _ = fixture(10)
    v['observations'] = [o for o in v['observations'] if o['time'] < 4]
    raw = [{'start': 0, 'end': 3, 'speaker': 'S', 'person_id': 'PERSON_A', 'method': 'user_verified'}]
    d = build_active_speaker({'turns': [{'start': 0, 'end': 10, 'speaker': 'S'}]}, v, raw, {})['data']
    assert any(r['person_id'] for r in d['intervals'] if r['end'] <= 3)
    assert all(r['person_id'] is None for r in d['intervals'] if r['start'] >= 3)


def test_duplicate_mapping_windows_do_not_manufacture_consensus():
    _, v, _ = fixture(10)
    r = {'start': 0, 'end': 3, 'speaker': 'S', 'person_id': 'PERSON_A', 'confidence': .99}
    d = build_active_speaker({'turns': [{'start': 0, 'end': 10, 'speaker': 'S'}]}, v, [r, r, r], {})['data']
    assert not any(x['person_id'] for x in d['intervals'])


def test_old_yaml_loads_defaults():
    cfg = load_config()
    assert resolve_config(cfg['camera_director'])['min_hold_seconds'] == 3.
    cfg['camera_director']['profile'] = 'podcast'
    assert resolve_config(cfg['camera_director'])['min_hold_seconds'] == 4.


def test_lookahead_prepares_open_for_future_voice_without_early_focus():
    d = run(fixture(20, pair=True), [turn(0, 10), turn(10, 20, 'PERSON_B')])
    events = [e for e in d['debug']['events'] if e['time'] < 10 and e['future_speaker'] == 'SPEAKER_B']
    assert events
    assert all(r['focus_person'] != 'PERSON_B' for r in d['timeline'] if r['start'] < 10)


def test_disappearance_overrides_hold_safely():
    m, v, shots = fixture(12)
    v['observations'] = [o for o in v['observations'] if o['time'] < 5]
    for f in v['frames']:
        if f['time'] >= 5:
            f['visible_people'] = []
    d = run((m,v,shots))
    assert all(r['focus_person'] is None for r in d['timeline'] if r['start'] >= 5.5)


def test_sparse_samples_do_not_claim_full_visual_coverage():
    m,v,shots = fixture(20)
    v['frames'] = v['frames'][:1]
    v['observations'] = v['observations'][:1]
    d = run((m,v,shots))
    assert d['metrics']['camera_director_coverage'] < .1
    assert d['metrics']['camera_director_timeline_coverage'] == 1


def test_config_exit_confidence_opens_safely():
    d = run(fixture(20), [turn(0,8), turn(8,20,confidence=.2)])
    assert all(r['focus_person'] is None for r in d['timeline'] if r['start'] >= 8)


def test_tie_cannot_select_larger_or_central_face():
    _,v,_ = fixture(12,pair=True)
    raw=[{'start': i*3,'end':(i+1)*3,'speaker':'S','person_id':p,'confidence':.9}
         for i,p in enumerate(['PERSON_A','PERSON_B','PERSON_A','PERSON_B'])]
    d=build_active_speaker({'turns':[{'start':0,'end':12,'speaker':'S'}]},v,raw,{})['data']
    assert not any(r['person_id'] for r in d['intervals'])


def test_manual_mapping_respects_exact_source_cut_visibility():
    _,v,_=fixture(10,pair=True,cuts=(5,))
    v['scene_intervals']=[{'start':0,'end':5,'scene_id':'SCENE_0'},{'start':5,'end':10,'scene_id':'SCENE_1'}]
    v['observations']=[o for o in v['observations'] if not(o['time']>=5 and o['person_id']=='PERSON_A')]
    for f in v['frames']:
        if f['time']>=5:
            f['visible_people']=['PERSON_B']
    raw=[{'start':0,'end':10,'speaker':'S','person_id':'PERSON_A','method':'user_verified'}]
    d=build_active_speaker({'turns':[{'start':0,'end':10,'speaker':'S'}]},v,raw,{})['data']
    assert all(r['person_id'] is None for r in d['intervals'] if r['start']>=5)


def test_cooldown_defers_otherwise_stable_challenger():
    d = run(fixture(30,pair=True), [turn(0,10),turn(10,30,'PERSON_B')],
            {'switch_cooldown_seconds':12.})
    rows=[r for r in d['timeline'] if r['focus_person']=='PERSON_B']
    assert rows and rows[0]['start']>=15.
    assert any(e['switch_suppressed_reason']=='switch_cooldown' for e in d['debug']['events'])


def test_min_hold_defers_challenger():
    d = run(fixture(30,pair=True), [turn(0,12),turn(12,30,'PERSON_B')],
            {'min_hold_seconds':8.,'preferred_hold_seconds':8.})
    rows=[r for r in d['timeline'] if r['focus_person']=='PERSON_B']
    assert rows and rows[0]['start']>=16.


def test_motion_jerk_is_bounded():
    a=Axis(.2)
    previous_a=0.
    for i in range(100):
        a.advance(.8,.025,.12,.18,.6)
        assert abs(a.acceleration-previous_a)<=.6*.025+1e-10
        previous_a=a.acceleration
