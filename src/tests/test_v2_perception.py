from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import logging

from ldporto.core import Context, ok, read_json, write_json
from ldporto.config import load_config
from ldporto.person_reid import build_person_identities
from ldporto.person_motion import build_person_motion
from ldporto.active_speaker import build_active_speaker
from ldporto.shots import build_shots
from ldporto.camera_timeline import build_camera_timeline
from ldporto.understanding import (extract_entities, build_participants, build_story_arcs,
                                  build_main_moments, build_thumbnail_candidates)
from ldporto.master_timeline import build_master_timeline
from ldporto.reports import ReportEngine


def visual_fixture():
    obs, frames = [], []
    for i, t in enumerate([x/2 for x in range(20)]):
        pid = "PERSON_001"
        track = "TRACK_00001" if t < 2.5 else "TRACK_00002"
        x = .3 + .001*t  # deliberately below motion deadzone after smoothing
        obs.append({"time": t, "person_id": pid, "track_id": track, "scene_id": "SCENE_00000",
                    "center": {"x": x, "y": .45}, "head_center": {"x": x, "y": .35},
                    "bbox": {"x": x-.1, "y": .2, "width": .2, "height": .5},
                    "face_bbox": {"x": x-.05, "y": .2, "width": .1, "height": .22},
                    "face_height": .22, "face_area": .022, "face_visible": True,
                    "safe_crop_possible": True, "percent_frame": .1,
                    "same_person_confidence": .82 if track == "TRACK_00002" else None,
                    "tracking_method": "anonymous_face_embedding" if track == "TRACK_00002" else "temporal_iou"})
        frames.append({"time": t, "scene_id": "SCENE_00000", "visible_people": [pid],
                       "blur_laplacian_variance": 150+i, "possible_black_frame": False,
                       "boundary_difference": None})
    return {"people": [{"person_id": "PERSON_001", "first_seen": 0, "last_seen": 9.5,
                         "observation_count": len(obs)}],
            "observations": obs, "frames": frames,
            "thumbnails": [{"time": 0, "path": "thumbnails/a.jpg", "reason": "scene_start"}],
            "sample_fps": 2}


def test_persistent_person_identity_has_multiple_tracks():
    identity = build_person_identities(visual_fixture())["data"]["identities"][0]
    assert identity["person_id"] == "PERSON_001"
    assert identity["track_ids"] == ["TRACK_00001", "TRACK_00002"]
    assert identity["persistent_across_tracks"] is True
    assert identity["civil_identity_inferred"] is False


def test_motion_deadzone_suppresses_detector_jitter():
    motion = build_person_motion(visual_fixture(), {"smoothing_alpha": .35,
                                                     "deadzone_per_second": .012,
                                                     "max_gap_seconds": 1.5})["data"]["people"][0]
    values = [x["velocity_x"] for x in motion["samples"] if x["velocity_x"] is not None]
    assert values and all(v == 0 for v in values)


def test_active_speaker_null_fallback_without_evidence():
    diar = {"turns": [{"start": 0, "end": 3, "speaker": "SPEAKER_00", "overlap": False}]}
    data = build_active_speaker(diar, visual_fixture(), [], {"min_consensus_windows": 2,
                                                             "min_consensus_share": .67})["data"]
    assert data["intervals"][0]["person_id"] is None
    assert data["intervals"][0]["evidence"] == ["diarization"]


def test_active_speaker_consensus_maps_person():
    diar = {"turns": [{"start": 0, "end": 2, "speaker": "SPEAKER_00", "overlap": False},
                      {"start": 2, "end": 4, "speaker": "SPEAKER_00", "overlap": False}]}
    raw = [{"start": 0, "end": 2, "speaker": "SPEAKER_00", "visible_person": "PERSON_001",
            "association_confidence": .8, "method": "lip_audio_correlation"},
           {"start": 2, "end": 4, "speaker": "SPEAKER_00", "visible_person": "PERSON_001",
            "association_confidence": .85, "method": "lip_audio_correlation"}]
    data = build_active_speaker(diar, visual_fixture(), raw, {"min_consensus_windows": 2,
                                                              "min_consensus_share": .67})["data"]
    assert data["mapping_summary"][0]["person_id"] == "PERSON_001"
    assert all(x["person_id"] == "PERSON_001" for x in data["intervals"])


def test_shot_classification_and_camera_timeline():
    vision = visual_fixture()
    metadata = {"duration": 10.0}
    scenes = [{"scene_id": "SCENE_00000", "start": 0, "end": 10}]
    shots = build_shots(scenes, vision, metadata, {"hard_cut_difference": .18})["data"]["shots"]
    assert shots[0]["shot_type"] == "medium"
    motion = build_person_motion(vision, {"smoothing_alpha": .35, "deadzone_per_second": .012,
                                          "max_gap_seconds": 1.5})["data"]["people"]
    active = [{"start": 0, "end": 10, "speaker_id": "SPEAKER_00", "person_id": "PERSON_001",
               "confidence": .8, "overlap": False}]
    camera = build_camera_timeline(metadata, vision, shots, active, motion,
                                   {"min_window_seconds": .25, "max_window_seconds": 1.0})["data"]["timeline"]
    assert camera and camera[0]["active_person"] == "PERSON_001"
    assert camera[0]["vertical_crop"]["recommended_layout"] == "single_person"


def transcript_fixture():
    segments = [
        {"segment_id": "SEG_00000", "start": 0, "end": 3, "speaker": "SPEAKER_00",
         "text": "Eu sou Rick. Quando comecei na banda Alpha, tudo parecia simples."},
        {"segment_id": "SEG_00001", "start": 3, "end": 7, "speaker": "SPEAKER_00",
         "text": "Mas a gravadora Beta disse que havia um problema."},
        {"segment_id": "SEG_00002", "start": 7, "end": 10, "speaker": "SPEAKER_00",
         "text": "No final deu certo e o disco Horizonte virou sucesso."},
    ]
    words = [{"word_id": f"WORD_{i:07}", "word": s["text"].split()[0],
              "raw": " "+s["text"].split()[0], "start": s["start"], "end": s["start"]+.2,
              "confidence": .9, "speaker": s["speaker"], "segment_id": s["segment_id"]}
             for i, s in enumerate(segments)]
    return {"segments": segments, "words": words}


def test_entities_are_text_grounded_and_self_intro_is_not_overcaptured():
    entities = extract_entities(transcript_fixture())
    names = {e["name"] for e in entities}
    assert {"Rick", "Alpha", "Beta", "Horizonte"} <= names
    assert "Rick. Quando" not in names


def test_story_arc_and_context_expansion():
    transcript = transcript_fixture()
    topics = [{"topic_id": "TOPIC_0", "start": 0, "end": 10, "topic": "história",
               "summary": "história", "evidence_segment_ids": [s["segment_id"] for s in transcript["segments"]]}]
    arcs = build_story_arcs(transcript, topics)
    assert len(arcs) == 1
    moments = [{"moment_id": "M1", "start": 3, "end": 10, "text": "núcleo", "categories": ["storytelling"],
                "editorial": {"hook_strength": .7, "clarity": .8}, "standalone_class": "good",
                "context_required": "", "complete_sentence": True,
                "evidence_segment_ids": ["SEG_00001", "SEG_00002"]}]
    main = build_main_moments(transcript, topics, moments, [], arcs, [], None)
    assert main[0]["ideal_start"] == 0
    assert main[0]["recommended_context_seconds"] >= 10


def test_master_timeline_fuses_camera_and_story():
    transcript = transcript_fixture()
    scenes = [{"scene_id": "SCENE_0", "start": 0, "end": 10}]
    topics = [{"topic_id": "TOPIC_0", "start": 0, "end": 10}]
    camera = [{"start": 0, "end": 10, "scene_id": "SCENE_0", "shot_id": "SHOT_0",
               "shot_type": "medium", "active_person": "PERSON_001", "active_person_confidence": .8,
               "visible_people": ["PERSON_001"], "vertical_crop": {"safe": True, "center_x": .4,
               "center_y": .4, "recommended_zoom": 1.1, "recommended_layout": "single_person"},
               "camera_score": .8, "movement": None, "visual_observed_at": 1, "evidence": ["sampled_frame"]}]
    active = [{"start": 0, "end": 10, "speaker_id": "SPEAKER_00", "person_id": "PERSON_001", "overlap": False}]
    data = build_master_timeline({"duration": 10}, transcript, scenes, topics, [], [], camera, active)["data"]["timeline"]
    assert data[0]["shot_id"] == "SHOT_0"
    assert data[0]["active_person"] == "PERSON_001"
    assert data[0]["speaker_id"] == "SPEAKER_00"


def test_scoped_cache_resume():
    with TemporaryDirectory() as d:
        out = Path(d)
        logger = logging.getLogger("cache-test")
        logger.handlers = [logging.NullHandler()]
        ctx = Context(Path("fake.mp4"), out, {"strict": False}, "signature", logger)
        calls = {"n": 0}
        def first():
            calls["n"] += 1
            return ok({"value": 1})
        assert ctx.step("stage", {"x": 1}, first, code_files=["core.py"])["value"] == 1
        ctx2 = Context(Path("fake.mp4"), out, {"strict": False}, "signature", logger)
        def must_not_run():
            raise AssertionError("cache was not resumed")
        assert ctx2.step("stage", {"x": 1}, must_not_run, code_files=["core.py"])["value"] == 1
        assert calls["n"] == 1


def test_report_exports_v2_handoff():
    with TemporaryDirectory() as d:
        out = Path(d)
        ctx = SimpleNamespace(output=out, signature="abc")
        analysis = {
            "metadata": {"filename":"x.mp4","duration":10,"width":1920,"height":1080,"fps":30,"analyzer_version":"2.0.0"},
            "analysis_status":"complete", "topics":[], "editorial_moments":[], "speakers":[], "people":[],
            "person_identities":[], "questions_answers":[], "candidate_hooks":[], "candidate_endings":[],
            "ollama_editorial_review":None, "issues":[], "stage_status":{}, "timeline":[], "transcript_segments":[],
            "speaker_person_mapping":[], "silences":[], "audio_events":[], "ocr_text":[], "low_confidence_words":[],
            "transcription_alternatives":[], "words":[], "people_observations":[], "scenes":[], "audio_analysis":{},
            "video_analysis":{}, "person_motion":[], "active_speaker":[], "speaker_person_summary":[], "shots":[],
            "participants":[], "entities":[], "story_arcs":[], "main_moments":[], "camera_timeline":[],
            "master_timeline":[], "video_understanding":{"about":None,"main_topics":[]}, "thumbnail_candidates":[],
            "analysis_quality":{}, "unaligned_segments":[]
        }
        ReportEngine().run(ctx, analysis, [])
        for filename in ("analysis.json", "manifest.json", "CHATGPT_ANALYSIS_HANDOFF.json",
                         "CHATGPT_ANALYSIS_HANDOFF.md", "active_speaker.json", "shots.json", "master_timeline.json"):
            assert (out/filename).is_file()


def test_tracker_equal_iou_mixed_nullable_similarity_does_not_crash():
    from ldporto.vision import Tracker
    import numpy as np
    cfg = {"track_max_gap_seconds": 2.0, "reid_threshold": .55, "reid_margin": .08}
    tracker = Tracker(cfg)
    box = {"x": .1, "y": .1, "width": .2, "height": .2}
    # Seed one track with an embedding and one without. Both have equal IoU on next frame.
    tracker.tracks = {
        "PERSON_001": {"bbox": box, "time": 0.0, "scene": "S", "embedding": np.array([1.,0.]), "track_id":"TRACK_00001"},
        "PERSON_002": {"bbox": box, "time": 0.0, "scene": "S", "embedding": None, "track_id":"TRACK_00002"},
    }
    tracker.next_id = 3
    tracker.next_track_id = 3
    detections = [
        {"bbox": dict(box), "embedding": np.array([1.,0.]), "face_bbox": dict(box)},
        {"bbox": dict(box), "embedding": None, "face_bbox": dict(box)},
    ]
    rows = tracker.update(detections, 0.1, "S")
    assert len(rows) == 2
    assert any(r["tracking_similarity"] is None for r in rows)


def test_write_json_sanitizes_nan_inf_as_null(tmp_path):
    from ldporto.core import write_json, read_json
    path = tmp_path/'finite.json'
    write_json(path, {"nan": float('nan'), "pos": float('inf'), "neg": float('-inf'), "zero": 0.0})
    data = read_json(path)
    assert data == {"nan": None, "pos": None, "neg": None, "zero": 0.0}


def test_vision_checkpoint_roundtrip_and_integrity(tmp_path):
    from ldporto.vision_checkpoint import VisionCheckpointStore
    from ldporto.vision import Tracker
    from ldporto.core import Context
    import logging
    import numpy as np
    cfg = load_config()
    ctx = Context(tmp_path/'v.mp4', tmp_path/'out', cfg, 'abc123', logging.getLogger('checkpoint'))
    store = VisionCheckpointStore(ctx, cfg['vision'])
    tracker = Tracker(cfg['vision'])
    tracker.tracks['PERSON_001'] = {'bbox':{'x':.1,'y':.1,'width':.2,'height':.2},'time':1.0,'scene':'S',
                                    'embedding':np.array([1.,0.]),'track_id':'TRACK_00001'}
    tracker.gallery['PERSON_001'] = np.array([1.,0.])
    store.save(0,0.0,1.0,[{'person_id':'PERSON_001','time':.5}],[{'time':.5}],[],
               {'PERSON_001':{'person_id':'PERSON_001','observation_count':1}},tracker,
               np.zeros((2,2),dtype=np.uint8),'S',1.1,10,{'face':'test'})
    loaded = store.load()
    assert loaded['end'] == 1.0
    assert loaded['observations'][0]['person_id'] == 'PERSON_001'
    restored = Tracker(cfg['vision'])
    store.restore_tracker(restored, loaded['tracker'])
    assert restored.tracks['PERSON_001']['track_id'] == 'TRACK_00001'
    # Broken/partial checkpoint is never reused.
    chunk = next(store.root.glob('chunk_*.json'))
    data = read_json(chunk); data['end'] = 999; write_json(chunk, data)
    assert store.load() is None
