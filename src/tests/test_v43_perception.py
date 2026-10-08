from copy import deepcopy

import numpy as np
import pytest

from ldporto.config import DEFAULTS
from ldporto.vision import Tracker


def detection(x=.35, embedding=None, body=False):
    face = {"x": x, "y": .15, "width": .1, "height": .15}
    box = {"x": x - .1, "y": .05, "width": .3, "height": .85} if body else face
    return {"bbox": box, "face_bbox": face, "bbox_kind": "body" if body else "face",
            "face_visible": True, "body_visible": body, "detection_confidence": .95,
            "embedding": np.asarray(embedding, dtype=float) if embedding is not None else None}


def tracker():
    return Tracker(deepcopy(DEFAULTS["vision"]))


def test_micro_track_consolidation_uses_same_face_when_body_detection_flickers():
    online = tracker()
    rows = [online.update([detection(body=index % 2 == 0)], index / 6, "SHOT_1")[0]
            for index in range(13)]
    assert len({row["track_id"] for row in rows}) == 1
    assert rows[-1]["track_state"] == "confirmed_track"


def test_track_gap_recovery_retains_confirmed_track_in_same_shot():
    online = tracker()
    first = online.update([detection()], 0, "SHOT_1")[0]
    online.update([detection()], .5, "SHOT_1")
    online.update([detection()], 1, "SHOT_1")
    online.update([], 1.5, "SHOT_1")
    assert online.tracks[first["person_id"]]["state"] == "temporarily_lost"
    recovered = online.update([detection()], 2.5, "SHOT_1")[0]
    assert recovered["track_id"] == first["track_id"]
    assert recovered["occlusion_recovered"]


def test_shot_cut_never_connects_geometry_without_face_identity():
    online = tracker()
    first = online.update([detection()], 0, "SHOT_1")[0]
    second = online.update([detection()], .2, "SHOT_2")[0]
    assert first["track_id"] != second["track_id"]
    assert first["person_id"] != second["person_id"]


def test_missing_embedding_does_not_erase_track_identity_evidence():
    online = tracker()
    first = online.update([detection(embedding=[1, 0])], 0, "SHOT_1")[0]
    online.update([detection()], .2, "SHOT_1")
    assert online.tracks[first["person_id"]]["embedding"] is not None
    changed = online.update([detection(embedding=[0, 1])], .4, "SHOT_1")[0]
    assert changed["person_id"] != first["person_id"]


def test_simultaneous_identity_collision_is_not_merged():
    online = tracker()
    rows = online.update([detection(.1, [1, 0]), detection(.6, [1, 0])], 0, "SHOT_1")
    assert len({row["person_id"] for row in rows}) == 2
    assert len({row["track_id"] for row in rows}) == 2


def test_motion_and_embedding_can_recover_low_iou_within_shot():
    online = tracker()
    first = online.update([detection(.1, [1, 0])], 0, "SHOT_1")[0]
    online.update([detection(.14, [1, 0])], .5, "SHOT_1")
    last = online.update([detection(.25, [1, 0])], 1.5, "SHOT_1")[0]
    assert first["track_id"] == last["track_id"]


def test_physical_jump_without_embedding_is_not_track_continuity():
    online = tracker()
    first = online.update([detection(.05)], 0, "SHOT_1")[0]
    last = online.update([detection(.85)], .1, "SHOT_1")[0]
    assert first["track_id"] != last["track_id"]


def test_tentative_detection_is_not_a_confirmed_editorial_track():
    online = tracker()
    row = online.update([detection()], 0, "SHOT_1")[0]
    assert row["track_state"] == "tentative_track"
    online.update([], 4, "SHOT_1")
    assert any(track["track_id"] == row["track_id"] and track["state"] == "terminated_track"
               for track in online.completed_tracks)


def test_checkpoint_restores_lifecycle_embedding_memory_and_counters():
    from ldporto.vision_checkpoint import VisionCheckpointStore
    online = tracker()
    first = online.update([detection(embedding=[1, 0])], 0, "SHOT_1")[0]
    online.update([detection()], .5, "SHOT_1")
    online.update([], 1, "SHOT_1")
    payload = VisionCheckpointStore.serialize_tracker(online)
    resumed = tracker()
    VisionCheckpointStore.restore_tracker(resumed, payload)
    assert resumed.tracks[first["person_id"]]["state"] == "temporarily_lost"
    assert resumed.association_count == online.association_count
    assert resumed.update([detection()], 1.5, "SHOT_1")[0]["track_id"] == first["track_id"]


def test_face_embedding_aggregation_rejects_first_sample_outlier():
    from ldporto.person_reid import _embedding
    rows = [{"face_embedding": vector} for vector in ([0, 1], [1, 0], [1, 0], [1, 0])]
    assert np.allclose(_embedding(rows), [1, 0])
    assert _embedding([{"face_embedding": [float("nan"), 1]}]) is None


def test_reid_templates_accumulate_without_simultaneous_person_merge():
    from ldporto.person_reid import build_person_identities
    from test_v42_perception import track_fixture
    vision = track_fixture([("T1", "P1", 0, 2, [1, 0]), ("T2", "P2", 5, 7, [1, 0]),
                            ("T3", "P3", 5, 7, [1, 0])])
    result = build_person_identities(vision)["data"]
    assert len(result["identities"]) == 2
    assert max(person["embedding_sample_count"] for person in result["identities"]) == 6
    assert result["metrics"]["simultaneous_identity_conflict_count"] > 0
    assert result["metrics"]["id_switch_count"] is None


def test_detector_cascade_reduces_redundant_work_and_refreshes_on_shot_cut():
    import cv2
    from collections import defaultdict
    from ldporto.vision import PersonDetectionEngine

    class Face:
        def setInputSize(self, size):
            pass

        def detect(self, frame):
            return None, np.array([[20, 20, 40, 40, 25, 25, 40, 25, 30, 35, 25, 45, 40, 45, .99]])

    class Embedding:
        def alignCrop(self, frame, row):
            return frame

        def feature(self, frame):
            return np.array([1., 0.])

    class Body:
        def detectMultiScale(self, frame, **kwargs):
            return [], []

    detector = object.__new__(PersonDetectionEngine)
    detector.cv2, detector.cfg = cv2, deepcopy(DEFAULTS["vision"])
    detector.cfg["face_quality_gate"] = False  # mocked flat-black frame
    detector.cfg["face_rescue_upsample"] = False  # mock detector does not scale rows
    detector.face, detector.sface, detector.hog, detector.yolo = Face(), Embedding(), Body(), None
    detector.phase_seconds = defaultdict(float)
    frame = np.zeros((180, 240, 3), dtype=np.uint8)
    for index in range(12):
        assert detector.detect(frame, time=index / 6, shot_id="S1")
    assert detector.calls["face_detection_calls"] == 12
    assert detector.calls["body_detection_calls"] < 12
    assert detector.calls["embedding_calls"] == 2
    detector.detect(frame, time=2, shot_id="S2")
    assert detector.calls["embedding_calls"] == 3


def test_detector_cascade_can_be_disabled_for_accuracy_comparison():
    cfg = deepcopy(DEFAULTS)
    cfg["vision"]["detector_cascade"] = False
    from ldporto.config import validate
    validate(cfg)


def test_recurrent_visual_identity_is_not_automatically_editorial_participant():
    from ldporto.understanding import build_participants
    vision = {"people": [{"person_id": "P1", "total_visual_seconds": 90,
                           "observation_count": 200, "scene_ids": ["S1", "S2", "S3"]}]}
    assert build_participants({"segments": []}, {"speakers": []}, vision, [], []) == []
    catalog = build_participants({"segments": []}, {"speakers": []}, vision, [], [], include_background=True)
    assert catalog[0]["participant_category"] == "visual_participant"
    assert not catalog[0]["editorial_significant"]
    assert catalog[0]["participant_significance_score"] is not None


def test_speaker_person_evidence_promotes_editorial_participant_without_face_naming():
    from ldporto.understanding import build_participants
    vision = {"people": [{"person_id": "P1", "total_visual_seconds": 30,
                           "observation_count": 80, "scene_ids": ["S1", "S2"]}]}
    mapping = [{"speaker_id": "S1", "person_id": "P1", "confidence": .85}]
    participants = build_participants({"segments": []}, {"speakers": [{"speaker_id": "S1", "speech_seconds": 30}]}, vision, mapping, [])
    assert participants[0]["participant_category"] == "editorial_participant"
    assert participants[0]["person_id"] == "P1"
    assert participants[0]["possible_name"] is None
    assert not participants[0]["civil_identity_inferred"]


def affinity_fixture(scores=(.85, -.3), overlap=False):
    turns = [{"start": 0, "end": 6, "speaker": "S1"}]
    raw = [{"start": start, "end": start + 3, "speaker_id": "S1", "person_id": None,
            "overlap": overlap, "evidence_window_id": f"WIN_{index}",
            "candidates": [{"person_id": f"P{person + 1}", "correlation": score}
                           for person, score in enumerate(scores)]}
           for index, start in enumerate((0, 3))]
    vision = {"people": [{"person_id": "P1"}, {"person_id": "P2"}],
              "frames": [{"time": time, "scene_id": "SHOT1", "visible_people": ["P1", "P2"]} for time in np.arange(0, 6, .5)],
              "observations": [{"time": time, "scene_id": "SHOT1", "person_id": person,
                                 "face_visible": True, "mouth_activity": .1}
                                for time in np.arange(0, 6, .5) for person in ("P1", "P2")]}
    return {"turns": turns}, vision, raw


def test_global_affinity_retains_candidates_from_locally_unresolved_windows():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture()
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] == "P1"
    # S5 separates global identity coverage from locally verified active speech.
    assert result["metrics"]["speaker_person_mapping_coverage"] > 0
    assert result["metrics"]["active_speaker_coverage"] == 0
    assert len(result["affinity"]) == 2
    assert next(pair for pair in result["affinity"] if pair["person_id"] == "P2")["negative_windows"] == 2


def test_ambiguous_global_affinity_remains_null_with_multiple_visible_people():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture((.85, .84))
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] is None
    assert all(row["person_id"] is None for row in result["intervals"])


def test_consecutive_frames_are_not_independent_affinity_evidence():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture()
    raw = [{**raw[0], "start": index / 30, "end": (index + 1) / 30, "evidence_window_id": str(index)} for index in range(30)]
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] is None


def test_overlapping_speech_does_not_create_unfounded_affinity():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture(overlap=True)
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] is None


def test_globally_mapped_but_offscreen_person_does_not_target_another_face():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture()
    vision["observations"] = [row for row in vision["observations"] if row["person_id"] != "P1"]
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] == "P1"
    assert not any(row["person_id"] for row in result["intervals"])
    assert result["metrics"]["offscreen_speaker_fraction"] > 0


def test_simultaneous_speakers_cannot_share_one_global_person():
    from ldporto.active_speaker import build_active_speaker
    diarization, vision, raw = affinity_fixture()
    diarization["turns"].append({"start": 0, "end": 6, "speaker": "S2"})
    raw += [{**row, "speaker_id": "S2", "evidence_window_id": row["evidence_window_id"] + "B"} for row in list(raw)]
    result = build_active_speaker(diarization, vision, raw, DEFAULTS["active_speaker"])["data"]
    assert all(row["person_id"] is None for row in result["mapping_summary"])


def test_audio_mouth_windows_split_at_real_shot_boundaries(tmp_path):
    import logging
    import soundfile as sf
    from ldporto.core import Context
    from ldporto.vision import ActiveSpeakerEngine
    from ldporto.active_speaker import build_active_speaker
    rate = 16000
    time = np.arange(rate * 6) / rate
    envelope = .2 + .1 * np.sin(2 * np.pi * time)
    mono = tmp_path / "mono.wav"
    sf.write(mono, envelope * np.sin(2 * np.pi * 440 * time), rate)
    cfg = deepcopy(DEFAULTS)
    ctx = Context(tmp_path / "video.mp4", tmp_path, cfg, "fixture", logging.getLogger("asd_fixture"))
    diarization = {"turns": [{"start": 1, "end": 6, "speaker": "S1"}], "speakers": [{"speaker_id": "S1"}]}
    observations = [{"time": stamp, "person_id": "P1", "track_id": "T1" if stamp < 3 else "T2",
                     "scene_id": "SHOT1" if stamp < 3 else "SHOT2", "face_visible": True,
                     "lip_opening": .2 + .1 * np.sin(2 * np.pi * stamp), "mouth_activity": .1}
                    for stamp in np.arange(0, 6, .25)]
    vision = {"people": [{"person_id": "P1"}], "observations": observations,
              "frames": [{"time": row["time"], "scene_id": row["scene_id"], "visible_people": ["P1"]} for row in observations],
              "scene_intervals": [{"start": 0, "end": 3, "scene_id": "SHOT1"}, {"start": 3, "end": 6, "scene_id": "SHOT2"}]}
    raw = ActiveSpeakerEngine().run(ctx, {"mono": str(mono)}, diarization, vision, {"duration": 6})["data"]["mappings"]
    assert len(raw) == 2
    assert all(row["candidates"] for row in raw)
    result = build_active_speaker(diarization, vision, raw, cfg["active_speaker"])["data"]
    assert result["mapping_summary"][0]["person_id"] == "P1"

def test_face_supported_micro_tracklet_can_reenter_established_identity_without_position():
    from ldporto.person_reid import build_person_identities
    from test_v42_perception import track_fixture
    vision = track_fixture([('T1', 'P1', 0, 2, [1, 0]), ('T2', 'P2', 5, 5.2, [1, 0])])
    data = build_person_identities(vision)['data']
    assert data['metrics']['micro_track_count'] == 1
    assert data['metrics']['micro_reid_attachment_count'] == 1
    assert data['tracklet_to_person']['T2'] == data['tracklet_to_person']['T1']
    decision = [d for d in data['merge_decisions'] if d.get('tracklet_id') == 'T2' and d.get('accepted')]
    assert decision and decision[0]['reason'] == 'strict_face_supported_micro_reentry'
    assert decision[0]['screen_position_used'] is False


def test_micro_tracklet_never_reenters_identity_during_temporal_conflict():
    from ldporto.person_reid import build_person_identities
    from test_v42_perception import track_fixture
    vision = track_fixture([('T1', 'P1', 0, 2, [1, 0]), ('T2', 'P2', 1, 1.2, [1, 0])])
    data = build_person_identities(vision)['data']
    assert data['metrics']['micro_track_count'] == 1
    assert data['tracklet_to_person']['T2'] is None
    assert any(d.get('tracklet_id') == 'T2' and d.get('temporal_conflict') for d in data['merge_decisions'])
