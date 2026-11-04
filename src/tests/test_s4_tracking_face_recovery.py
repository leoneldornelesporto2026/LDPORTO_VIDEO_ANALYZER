"""S4: recovery is measurable; only face evidence supports cross-shot ID."""
from collections import defaultdict
import csv
import json
import numpy as np
import pytest
from ldporto.face_quality import assess_face
from ldporto.visual_sampling import ShotBoundarySamplingPlan
from ldporto.visual_identity_audit import audit_embedding_gaps
from ldporto.identity_goldset import (sample_tracklets, write_annotation_csv, read_annotation_csv,
                                      evaluate_annotations, write_contact_sheet)
from ldporto.person_reid import build_person_identities
from ldporto.vision import PersonDetectionEngine
from ldporto.config import DEFAULTS


def image():
    rng = np.random.default_rng(148)
    return rng.integers(55, 190, (120, 160, 3), dtype=np.uint8)


def test_quality_accepts_usable_face_and_rejects_small_blurred_clipped():
    a = image()
    clear = assess_face(a, {'x': .25, 'y': .2, 'width':.35,'height':.5}, confidence=.96)
    assert clear['embedding_eligible']
    small = assess_face(a, {'x':.2,'y':.2,'width':.10,'height':.10}, confidence=.98)
    assert 'face_too_small' in small['rejection_reasons']
    blank = np.zeros_like(a)
    bad = assess_face(blank, {'x':0,'y':0,'width':.4,'height':.4}, confidence=.25)
    assert {'face_clipped_at_frame_edge','low_detection_confidence','face_blurred','face_bad_exposure'} <= set(bad['rejection_reasons'])


class FakeYuNet:
    def __init__(self, *, rescue=False):
        self.calls=[];self.dims=None;self.rescue=rescue

    def setInputSize(self, size):
        self.dims=size

    def detect(self, frame):
        self.calls.append(tuple(self.dims))
        if self.rescue and self.dims[0] < 200:
            return None, None
        k = 1.5 if self.dims[0] >= 200 else 1.
        a=np.zeros((1,15),dtype=np.float32)
        a[0, :4] = np.array([45.,27.,54.,60.])*k
        a[0, 4:14] = np.array([60,45,85,45,72,61,62,75,84,75])*k
        a[0,14] = .96
        return None, a


class FakeSFace:
    def __init__(self): self.calls=0
    def alignCrop(self, frame, row): self.calls+=1;return frame
    def feature(self, frame): return np.array([[1.,0.,.2]],dtype=np.float32)


def detector(face):
    import cv2
    model=object.__new__(PersonDetectionEngine)
    model.cv2=cv2;model.cfg={**DEFAULTS['vision'],'detector_cascade':True}
    model.calls=defaultdict(int);model.phase_seconds=defaultdict(float)
    model.face_history=[];model.last_rescue_time=-float('inf')
    model.last_body_time=-float('inf');model.last_shot=None
    model.face=face;model.sface=FakeSFace();model.hog=None;model.yolo=None
    model._hog_pool=None
    return model


def test_yunet_rescue_uses_inverse_scale_and_reports_fresh_embedding():
    model=detector(FakeYuNet(rescue=True))
    model.set_frame_context(2.,'CAM1',5)
    observations=model.detect(image())
    assert len(observations)==1
    assert observations[0]['face_embedding'] if 'face_embedding' in observations[0] else observations[0]['embedding'] is not None
    assert abs(observations[0]['face_bbox']['x'] - 45/160) < 1e-5
    assert model.calls['face_rescue_calls']==1
    assert model.calls['face_rescue_detected_faces']==1
    assert model.face.dims==(160,120)
    assert observations[0]['face_quality']['embedding_eligible']


def test_quality_gate_rejects_embedding_but_keeps_visual_face():
    model=detector(FakeYuNet())
    model.set_frame_context(1.,'CAM1',5)
    observations=model.detect(np.zeros((120,160,3),dtype=np.uint8))
    assert len(observations)==1
    assert observations[0]['face_visible']
    assert observations[0]['embedding'] is None
    assert observations[0]['embedding_missing_reason']=='quality_rejected'
    assert model.sface.calls==0
    assert model.calls['embedding_quality_rejections']==1


def test_boundary_plan_is_bounded_and_never_crosses_short_shot_plan():
    shots=[{'start':0.,'end':10.},{'start':10.,'end':10.7},{'start':10.7,'end':20.}]
    plan=ShotBoundarySamplingPlan(shots, short_max_seconds=1.5)
    assert len(plan.times)==4
    assert 10.12 not in plan.times
    assert not plan.due(.05)
    assert plan.due(.15)
    assert not plan.due(.2)
    assert plan.due(10.0)
    resumed=ShotBoundarySamplingPlan(shots, start_time=10.)
    assert all(t>10 for t in resumed.times)


def test_diagnostic_evidence_by_cause_without_assuming_742():
    rows=[{'track_id':'A','time':1.,'face_visible':False},
          {'track_id':'B','time':2.,'face_visible':True,'embedding_missing_reason':'quality_rejected'},
          {'track_id':'C','time':3.,'face_visible':True,'embedding_missing_reason':'sface_unavailable'},
          {'track_id':'D','time':4.,'face_visible':True,'face_embedding':[1.,0.]}]
    reid={'tracklets':[{'track_id':tid,'tracklet_state':'micro_tracklet'} for tid in 'ABCD']}
    report=audit_embedding_gaps({'observations':rows},reid)
    assert report['tracklets_without_embedding']==3
    assert report['micro_without_embedding_by_cause']=={'body_only_no_face_detected':1,
             'quality_rejected':1,'sface_unavailable':1}


def test_micro_reid_rejects_overlap_and_supports_safe_return():
    def row(track,person,time,embed,scene):
        return {'track_id':track,'person_id':person,'time':time,'scene_id':scene,
                'face_visible':True,'face_embedding':embed}
    a=np.ones(128).tolist()
    base=[row('a','P1',t,a,'S1') for t in [0,1,2]]
    base += [row('micro','P2',t,a,'S2') for t in [10,10.2]]
    data=build_person_identities({'observations':base})['data']
    assert data['tracklet_to_person']['micro']==data['tracklet_to_person']['a']
    simultaneous=[row('micro','P2',t,a,'S1') for t in [1.5,1.6]]
    data=build_person_identities({'observations':base[:3]+simultaneous})['data']
    assert data['tracklet_to_person']['micro'] is None


def test_annotation_metrics_only_after_human_verified_labels(tmp_path):
    annotated=[{'track_id':'t1','annotation_label':'A','annotation_status':'verified','predicted_person_id':'X'},
               {'track_id':'t2','annotation_label':'A','annotation_status':'verified','predicted_person_id':'Y'},
               {'track_id':'t3','annotation_label':'B','annotation_status':'verified','predicted_person_id':'X'},
               {'track_id':'t4','annotation_label':'B','annotation_status':'unreviewed','predicted_person_id':'X'}]
    metrics=evaluate_annotations(annotated)
    assert metrics['false_merge_pairs']==1
    assert metrics['false_split_pairs']==1
    assert metrics['fragmented_identity_count']==1
    assert metrics['verified_samples']==3
    assert evaluate_annotations(annotated[:1])['pairwise_precision'] is None
    dest=tmp_path/'sample.csv';write_annotation_csv(annotated,dest)
    assert len(read_annotation_csv(dest))==4


def test_annotation_sample_preserves_face_bbox_and_labels_blank():
    rows=[{'track_id':'m','person_id':'P1','time':1.,'face_bbox':{'x':.2,'y':.2,'width':.2,'height':.3},
           'face_visible':True,'face_embedding':None, 'scene_id':'S1'},
          {'track_id':'x','person_id':'P2','time':4.,'face_visible':True,'face_embedding':[1.,0.], 'scene_id':'S2'}]
    reid={'tracklets':[{'track_id':'m','tracklet_state':'micro_tracklet','embedding_sample_count':0},
                       {'track_id':'x','tracklet_state':'stable_tracklet','embedding_sample_count':1}],
          'tracklet_to_person':{'m':None,'x':'PX'}}
    chosen=sample_tracklets({'observations':rows},reid,limit=2)
    assert len(chosen)==2
    assert chosen[0]['review_bbox']==rows[0]['face_bbox']
    assert all(row['annotation_status']=='unreviewed' and not row['annotation_label'] for row in chosen)


def test_contact_sheet_is_available_with_local_video(tmp_path):
    cv2=pytest.importorskip('cv2')
    source=tmp_path/'test.avi'
    fourcc=cv2.VideoWriter_fourcc(*'MJPG')
    writer=cv2.VideoWriter(str(source),fourcc,5.,(100,80))
    if not writer.isOpened(): pytest.skip('MJPG writer nao instalado')
    for i in range(10):writer.write(np.full((80,100,3),i*8,dtype=np.uint8))
    writer.release()
    path=tmp_path/'contact.jpg'
    write_contact_sheet([{'track_id':'t1','time':.4,'review_bbox':{'x':.2,'y':.2,'width':.3,'height':.3}}],source,path)
    assert path.is_file() and path.stat().st_size>500


def test_offline_diagnostics_work_on_zip_and_directory(tmp_path):
    import zipfile
    from scripts.dev.audit_tracking_s4 import analyze
    observations=[{'track_id':'R1','person_id':'P1','scene_id':'S1','time':0.,'face_visible':False},
                  {'track_id':'R2','person_id':'P2','scene_id':'S2','time':5.,'face_visible':True,
                   'face_embedding':[1.,0.,.3]},
                  {'track_id':'R2','person_id':'P2','scene_id':'S2','time':6.,'face_visible':True,
                   'face_embedding':[1.,0.,.3]},
                  {'track_id':'R2','person_id':'P2','scene_id':'S2','time':7.,'face_visible':True,
                   'face_embedding':[1.,0.,.3]}]
    raw={'status':'ok','data':{'observations':observations,'people':[]}}
    (tmp_path/'07_people_tracking.json').write_text(json.dumps(raw),encoding='utf-8')
    report, samples=analyze(tmp_path)
    assert report['embedding_absence_by_cause']['body_only_no_face_detected']==1
    assert {sample['track_id'] for sample in samples}=={'R1','R2'}
    zipped=tmp_path/'fixture.zip'
    with zipfile.ZipFile(zipped,'w') as z:
        z.writestr('analysis/07_people_tracking.json', json.dumps(raw))
    report2, samples2=analyze(zipped)
    assert report2==report
    assert samples2==samples


def test_unresolved_predicted_persons_count_as_fragmentation():
    rows=[{'track_id':'a','annotation_label':'X','annotation_status':'verified', 'predicted_person_id':None},
          {'track_id':'b','annotation_label':'X','annotation_status':'verified', 'predicted_person_id':None}]
    report=evaluate_annotations(rows)
    assert report['false_split_pairs']==1
    assert report['fragmented_identity_count']==1
    assert report['pairwise_recall']==0
