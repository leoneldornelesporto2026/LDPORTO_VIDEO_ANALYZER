"""Offline stage 26: observed causes, bounded rescue, and quality comparisons."""
import copy
import numpy as np
import pytest

from ldporto.face_quality import assess_face
from ldporto.visual_identity_audit import audit_embedding_gaps, compare_embedding_recovery
from ldporto.identity_goldset import sample_tracklets, write_annotation_csv, read_annotation_csv
from test_s4_tracking_face_recovery import detector, image, FakeYuNet
from ldporto.vision import Tracker
from ldporto.config import DEFAULTS


def test_all_observed_causes_are_retained_without_inventing_occlusion():
    rows = [
        {'track_id':'a', 'face_visible':False},
        {'track_id':'b', 'face_visible':False, 'embedding_missing_reason':'face_detector_unavailable'},
        {'track_id':'c', 'face_visible':True, 'embedding_missing_reason':'quality_rejected',
         'face_quality':{'rejection_reasons':['face_too_small', 'eye_landmarks_collapsed']}},
        {'track_id':'c', 'face_visible':True, 'embedding_missing_reason':'embedding_extraction_failed'},
        {'track_id':'d', 'face_visible':True, 'face_occlusion_verified':True},
        {'track_id':'e', 'face_visible':True, 'embedding_missing_reason':'sface_unavailable_haar_fallback'},
    ]
    report = audit_embedding_gaps({'observations':rows})
    assert report['tracklets_without_embedding'] == 5
    assert report['missing_tracklets_by_observed_category'] == {
        'no_face_detected':1, 'face_detector_unavailable':1, 'quality_gate':1,
        'extractor_error':1, 'verified_occlusion':1, 'extractor_unavailable':1}
    c = next(t for t in report['missing_tracklet_evidence'] if t['track_id']=='c')
    assert c['occlusion_verified'] is None
    assert c['quality_rejection_reasons'] == ['eye_landmarks_collapsed','face_too_small']


def test_profile_landmarks_reject_embedding_without_claiming_occlusion():
    box = {'x':.2, 'y':.2, 'width':.4, 'height':.5}
    quality = assess_face(image(), box, confidence=.98,
                          eyes=[{'x':.35,'y':.4}, {'x':.36,'y':.4}])
    assert not quality['embedding_eligible']
    assert 'eye_landmarks_collapsed' in quality['rejection_reasons']


def test_compact_vector_omission_is_not_an_embedding_failure():
    report = audit_embedding_gaps({'observations':[
        {'track_id':'a', 'face_visible':True, 'face_embedding_available':True}]})
    assert report['tracklets_without_embedding']==0
    assert report['tracklets_with_availability_only']==1


@pytest.mark.parametrize('bad', ['blur', 'small', 'profile', 'confidence'])
def test_rescue_refuses_unusable_original_pixels(bad):
    class Rescue(FakeYuNet):
        def detect(self, frame):
            if self.dims[0] < 200:
                return None, None
            _, rows = super().detect(frame)
            if bad == 'small': rows[0, 2:4] = [18.,18.]
            if bad == 'profile': rows[0,6:8] = rows[0,4:6]
            if bad == 'confidence': rows[0,14] = .1
            return None, rows
    model = detector(Rescue())
    model.set_frame_context(0., 'S1', 5.)
    frame = np.full_like(image(), 100) if bad=='blur' else image()
    assert model.detect(frame) == []
    assert model.calls['face_rescue_quality_rejections'] == 1
    assert model.sface.calls == 0


def test_no_face_is_not_identity_and_rescue_has_cooldown():
    class Empty(FakeYuNet):
        def detect(self, frame):
            self.calls.append(self.dims)
            return None, None
    model = detector(Empty())
    for time in (0., .1, .2):
        model.set_frame_context(time, 'S1', 5.)
        assert model.detect(image()) == []
    assert model.calls['face_rescue_calls'] == 1
    assert not Tracker(DEFAULTS['vision']).update([], .2, 'S1')


@pytest.mark.parametrize('failure', ['unavailable', 'error'])
def test_detector_failure_is_separate_from_absent_face(failure):
    class Broken(FakeYuNet):
        def detect(self, frame): raise RuntimeError('fixture')
    model = detector(None if failure=='unavailable' else Broken())
    model.set_frame_context(0., 'S1', 5.)
    assert model.detect(image()) == []
    assert model.last_face_detector_status == failure
    assert model.calls['face_rescue_calls'] == 0


@pytest.mark.parametrize('failure', ['unavailable', 'error'])
def test_body_only_failure_keeps_reason_and_cannot_create_face_identity(failure):
    from ldporto.person_reid import build_person_identities
    class Broken(FakeYuNet):
        def detect(self, frame): raise RuntimeError('fixture')
    model = detector(None if failure=='unavailable' else Broken())
    model.hog = object()
    model._hog_boxes = lambda *args: [{'bbox':{'x':.2,'y':.1,'width':.4,'height':.8},
                                     'source':'hog', 'confidence':None}]
    model.set_frame_context(0., 'S1', 5.)
    detections = model.detect(np.tile(image(), (2,1,1)))
    assert len(detections)==1
    assert detections[0]['embedding_missing_reason']=='face_detector_'+failure
    assert detections[0]['embedding'] is None and not detections[0]['face_visible']
    rows=Tracker(DEFAULTS['vision']).update(detections, 0., 'S1')
    for row in rows: row.update(time=0., scene_id='S1')
    data=build_person_identities({'observations':rows})['data']
    assert all(pid is None for pid in data['tracklet_to_person'].values())


def test_extractor_error_preserves_face_without_embedding():
    model = detector(FakeYuNet())
    def broken(frame): raise RuntimeError('fixture')
    model.sface.feature = broken
    model.set_frame_context(0., 'S1', 5.)
    row = model.detect(image())[0]
    assert row['face_visible'] and row['embedding'] is None
    assert row['embedding_missing_reason'] == 'embedding_extraction_failed'


def test_empty_haar_failure_is_instrumented_with_real_opencv():
    import cv2
    model=detector(cv2.CascadeClassifier())
    model.set_frame_context(0., 'S1', 5.)
    assert model.detect(image())==[]
    assert model.last_face_detector_status=='error'
    assert model.calls['face_detector_failed_frames']==1


def record():
    return {'source_sha256':'a'*64, 'sampling_protocol_sha256':'b'*64,
            'review_set_sha256':'c'*64, 'tracklet_count':100, 'tracklets_without_embedding':80,
            'verified_quality':{'human_verified':True, 'usable_face_fraction':.9,
                                'false_merge_pair_rate':.01}}


def test_comparison_requires_same_source_protocol_review_and_verified_quality():
    before = record(); after = copy.deepcopy(before)
    after['tracklets_without_embedding'] = 70
    assert compare_embedding_recovery(before, after)['reduction_accepted'] is True
    for key in ('source_sha256', 'sampling_protocol_sha256', 'review_set_sha256'):
        altered = copy.deepcopy(after); altered[key] = 'd'*64
        assert compare_embedding_recovery(before, altered)['reduction_accepted'] is None
    after['verified_quality']['human_verified'] = False
    assert compare_embedding_recovery(before, after)['reduction_accepted'] is None


@pytest.mark.parametrize('key,value', [('usable_face_fraction', .8), ('false_merge_pair_rate', .02)])
def test_embedding_reduction_is_rejected_when_quality_worsens(key, value):
    before = record(); after = copy.deepcopy(before)
    after['tracklets_without_embedding'] = 70
    after['verified_quality'][key] = value
    assert compare_embedding_recovery(before, after)['reduction_accepted'] is False


def test_changed_denominator_cannot_claim_gain():
    before=record(); after=record()
    after.update(tracklet_count=70, tracklets_without_embedding=65)
    assert compare_embedding_recovery(before, after)['reduction_accepted'] is False
    assert compare_embedding_recovery({}, {})['reduction_accepted'] is None


def test_annotation_keeps_missing_reason_and_body_without_face_proof(tmp_path):
    rows=[{'track_id':'b', 'time':1., 'face_visible':False,
           'embedding_missing_reason':'face_detector_unavailable'}]
    samples=sample_tracklets({'observations':rows}, {})
    assert samples[0]['predicted_person_id'] is None
    assert samples[0]['review_target']=='body_without_face_proof'
    path=write_annotation_csv(samples, tmp_path/'annotation.csv')
    assert read_annotation_csv(path)[0]['embedding_missing_reason']=='face_detector_unavailable'
