"""S6 synthesized fixtures and offline audits, NOT real-video quality measurements."""
import json
import zipfile
from copy import deepcopy

import numpy as np
import pytest

from director_fixtures import fixture, turn
from ldporto.camera_director import _prepare, _editorial_zoom_beat, build_camera_director
from ldporto.director_config import resolve_config
from ldporto.camera_preflight import preflight_target, preflight_split
from ldporto.preview_verifier import border_geometry_evidence, verify_preview
from scripts.dev.audit_camera_s6 import assess, main


def test_predecision_funnel_explains_unconfirmed_audio_without_fabricating_identity():
    m, vision, shots = fixture(8)
    rows = [dict(turn(0, 8), person_id=None, active_speaker_state='UNCERTAIN', active_person=None)]
    result = build_camera_director(m, vision, shots, rows, [], {'dominant_face_fallback':False})['data']
    funnel = result['metrics']['focus_evidence_funnel']
    assert funnel['duration_seconds']['NO_CONFIRMED_AUDIO_VISUAL_TARGET'] == 8
    assert result['metrics']['camera_director_coverage'] == 0
    assert all(r['focus_person'] is None for r in result['timeline'])


def test_visual_fallback_remains_visual_only_not_confirmed_voice():
    m, vision, shots = fixture(12)
    rows = [dict(turn(0, 12), person_id=None, active_speaker_state='UNCERTAIN', active_person=None)]
    result = build_camera_director(m, vision, shots, rows, [], {'dominant_face_fallback':True})['data']
    focused = [r for r in result['timeline'] if r['focus_person']]
    assert focused
    assert all(r['camera_evidence_role'] == 'DOMINANT_FACE' and not r['speaker_identity_confirmed'] for r in focused)
    assert result['metrics']['visual_only_fallback_windows'] > 0


def test_crop_preflight_refuses_face_lost_within_same_source_shot():
    m, vision, shots = fixture(8)
    vision['observations'] = [r for r in vision['observations'] if r['time'] < 3.0]
    cfg = resolve_config(None)
    records = _prepare(m, vision, shots, [turn(0,8)], cfg)
    at = next(i for i,r in enumerate(records) if 2.4 < r['mid'] < 2.7)
    safety = preflight_target('PERSON_A', at, records, m, cfg, horizon=1)
    assert not safety['safe'] and safety['preflight_reason']=='target_lost_in_lookahead'


def test_split_uses_panel_aspect_ratio_and_both_faces_are_in_own_crops():
    from ldporto.camera_geometry import contains, subject_box
    m,v,shots = fixture(10,pair=True,distant=True)
    cfg = resolve_config({'output_width':540,'output_height':960})
    records = _prepare(m,v,shots,[turn(0,10)],cfg)
    result = preflight_split(('PERSON_A','PERSON_B'),10,records,m,cfg)
    assert result['safe'] and result['panel_aspect_correct']
    for pid, rect in ((result['left_person'],result['left_crop']),(result['right_person'],result['right_crop'])):
        assert contains(rect,subject_box(records[10]['obs'][pid],cfg))
        assert rect['width']/rect['height'] == pytest.approx((540/2/960)/(3840/2160),rel=.01)


def test_grounded_understanding_typed_reveal_triggers_opportunity():
    m,v,shots=fixture(30)
    moment={'moment_id':'M_REVEAL','start':0,'end':10,
        'core_moment':{'start':0,'end':10},'evidence_segment_ids':['SEG_A'],
        'categories':['curiosity'],'hook_type':'reveal','hook_score':.8}
    result=build_camera_director(m,v,shots,[turn(0,30)],[],
        {'output_width':540,'output_height':960},main_moments=[moment])['data']
    assert result['metrics']['editorial_beat_raw_windows'] > 0
    assert result['metrics']['zoom_opportunity_window_count'] > 0
    assert result['metrics']['zoom_accepted_event_count'] > 0
    assert result['metrics']['zoom_delivered_event_count'] > 0


def test_qa_zoom_requires_completed_answer_and_verified_refs():
    qa={'question_id':'QA1','answer_start':5,'answer_end':8,
        'answer_segment_ids':['SEG_REPLY'],'question_answer_complete':True}
    assert _editorial_zoom_beat(6,[],[],[qa])['reason']=='QA_ANSWER_PAYOFF'
    assert _editorial_zoom_beat(6,[],[],[{**qa,'question_answer_complete':False}]) is None
    assert _editorial_zoom_beat(6,[],[],[{**qa,'answer_segment_ids':[]}]) is None


def test_dark_background_is_not_a_black_border_but_added_stripe_is():
    studio=np.full((180,320),5,dtype=np.uint8)
    studio[40:140,30:290]=17
    assert not border_geometry_evidence(studio,np)['possible_padding']
    padded=np.full((180,320),120,dtype=np.uint8)
    padded[:10]=0
    padded[-10:]=0
    evidence=border_geometry_evidence(padded,np)
    assert evidence['possible_padding']
    assert {'top','bottom'} <= {r['side'] for r in evidence['rails']}


def test_rendered_preview_confirms_temporal_borders_without_falsely_flagging_dark_studio(tmp_path):
    cv2=pytest.importorskip('cv2')
    def write(name,rect):
        path=tmp_path/name
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(320,180))
        assert writer.isOpened()
        for i in range(40):
            frame=np.full((180,320,3),5,dtype=np.uint8)
            if rect:
                frame[:]=130
                frame[:12]=0
                frame[-12:]=0
            else:
                frame[40:140,30:290]=12
            writer.write(frame)
        writer.release()
        return path
    row={'start':0,'end':4,'layout':'single_person','focus_person':None,'camera':{'keyframes':[]}}
    dark=verify_preview(write('dark.avi',False),{'duration':4},[row])['data']
    stripe=verify_preview(write('stripe.avi',True),{'duration':4},[row])['data']
    assert not any(x['issue_type']=='UNEXPECTED_BORDER' for x in dark['issues'])
    assert any(x['issue_type']=='UNEXPECTED_BORDER' for x in stripe['issues'])
    assert stripe['border_detector_method']=='contrast_and_temporal_bar_geometry_v2'


def test_auditor_folder_and_zip_preserve_causal_no_zoom_diagnosis(tmp_path):
    m,v,shots=fixture(6)
    director=build_camera_director(m,v,shots,[turn(0,6)],[])['data']
    folder=tmp_path/'analysis'; folder.mkdir()
    (folder/'19_camera_director.json').write_text(json.dumps({'data':director}),encoding='utf-8')
    zip_path=tmp_path/'run.zip'
    with zipfile.ZipFile(zip_path,'w') as z:
        z.write(folder/'19_camera_director.json','analysis/19_camera_director.json')
    from_folder=main([str(folder),'--output',str(tmp_path/'f_out')])
    from_zip=main([str(zip_path),'--output',str(tmp_path/'z_out')])
    assert from_folder['focus']==from_zip['focus']
    assert from_folder['zoom']['zoom_zero_root_cause']=='NO_GROUNDED_EDITORIAL_BEAT'
    assert (tmp_path/'f_out'/'camera_s6_diagnostic.json').is_file()


def test_auditor_replay_uses_only_cached_artifacts(tmp_path):
    m,v,shots=fixture(6)
    folder=tmp_path/'analysis';folder.mkdir()
    sources={'01_metadata.json':m,'08_person_reid.json':v,'11_shots.json':{'shots':shots},
             '10_active_speaker.json':{'intervals':[turn(0,6)]}}
    for name,obj in sources.items():
        (folder/name).write_text(json.dumps({'data':obj}),encoding='utf-8')
    report=main([str(folder),'--output',str(tmp_path/'out'),'--replay'])
    assert report['focus']['resolved_focus_coverage'] > 0
    assert (tmp_path/'out'/'camera_director_s6_timeline.json').is_file()


def test_real_director_split_panels_remain_geometry_safe_during_tv_exchange():
    from ldporto.camera_geometry import contains, subject_box
    m,v,shots=fixture(30,pair=True,distant=True)
    turns=[turn(i,i+1,person='PERSON_A' if i%2==0 else 'PERSON_B',speaker='S'+str(i%2)) for i in range(30)]
    result=build_camera_director(m,v,shots,turns,[],{'output_width':540,'output_height':960})['data']
    splits=[r for r in result['timeline'] if r['layout']=='split_candidate']
    assert splits
    assert all(row['split']['panel_aspect_correct'] for row in splits)
    for row in splits:
        observations={r['person_id']:r for r in v['observations'] if r['time']==row['visual_observed_at_start']}
        for side in ('left','right'):
            person=row['split'][side+'_person']
            if person in observations:
                assert contains(row['split'][side+'_crop'],subject_box(observations[person],resolve_config(None)))


def test_one_frame_does_not_authorize_smart_zoom():
    m,v,shots=fixture(12)
    v['frames']=v['frames'][:1]
    v['observations']=v['observations'][:1]
    moment={'moment_id':'HOOK_ONLY','start':0,'end':10,'evidence_segment_ids':['SEG_1'],
            'categories':['hook'],'hook_score':.9}
    data=build_camera_director(m,v,shots,[turn(0,12)],[],
         {'output_width':540,'output_height':960},main_moments=[moment])['data']
    assert data['metrics']['zoom_event_count']==0
    assert data['metrics']['zoom_temporal_preflight_rejected_windows']>=0
    assert data['metrics']['evaluation_windows_without_visual_sample']>0
