from collections import defaultdict
from .core import ok, overlap
from .transcription import word_text
from .temporal import IntervalCursor
from bisect import bisect_left


def _overlapping(rows, start, end):
    return [r for r in rows if r.get("start") is not None and r.get("end") is not None and
            overlap(start, end, r["start"], r["end"]) > 1e-9]


def build_master_timeline(metadata, transcript, scenes, topics, questions_answers, story_arcs,
                          camera_timeline, active_speaker):
    """High-resolution fusion timeline driven by camera windows."""
    rows = []
    segments = transcript.get("segments", [])
    words = transcript.get("words", [])
    qas = []
    for i, q in enumerate(questions_answers):
        end = q.get("answer_end") or q.get("question_end")
        qas.append({**q, "question_id": q.get("question_id", f"Q_{i:04}"),
                    "start": q.get("question_start"), "end": end})
    arcs = [{**a, "story_id": a.get("story_arc_id")} for a in story_arcs]
    active = active_speaker or []
    # Sweep by window end; retain rows ending after window start to include partial overlaps.
    collections = {'segments': segments, 'topics': topics, 'scenes': scenes,
                   'active': active, 'qas': qas, 'arcs': arcs}
    cursors = {k: 0 for k in collections}
    collections = {k: sorted((r for r in v if r.get('start') is not None and r.get('end') is not None),
                             key=lambda r: r['start']) for k, v in collections.items()}
    live = {k: [] for k in collections}
    def select(key, a, b):
        live[key] = [r for r in live[key] if r['end'] > a]
        rs = collections[key]
        while cursors[key] < len(rs) and rs[cursors[key]]['start'] < b:
            row = rs[cursors[key]]
            if row['end'] > a:
                live[key].append(row)
            cursors[key] += 1
        return live[key]
    sorted_words = sorted(words, key=lambda w: (w['start']+w['end'])/2)
    word_mids = [(w['start']+w['end'])/2 for w in sorted_words]
    for index, camera in enumerate(camera_timeline):
        start, end = camera["start"], camera["end"]
        segs = select('segments', start, end)
        chosen_words = sorted_words[bisect_left(word_mids, start):bisect_left(word_mids, end)]
        topic_rows = select('topics', start, end)
        scene_rows = select('scenes', start, end)
        active_rows = select('active', start, end)
        q_rows = select('qas', start, end)
        story_rows = select('arcs', start, end)
        speaker_ids = sorted({r.get("speaker_id") for r in active_rows if r.get("speaker_id")})
        speaker = speaker_ids[0] if len(speaker_ids) == 1 else None
        rows.append({
            "timeline_id": f"MTL_{index:07}",
            "start": start, "end": end,
            "text": word_text(chosen_words),
            "word_ids": [w.get("word_id") for w in chosen_words],
            "segment_ids": [s.get("segment_id") for s in segs],
            "speaker_id": speaker, "speaker_ids": speaker_ids,
            "active_person": camera.get("active_person"),
            "active_person_confidence": camera.get("active_person_confidence"),
            "visible_people": camera.get("visible_people", []),
            "shot_id": camera.get("shot_id"), "shot_type": camera.get("shot_type"),
            "scene_id": scene_rows[0].get("scene_id") if scene_rows else camera.get("scene_id"),
            "topic_id": topic_rows[0].get("topic_id") if topic_rows else None,
            "question_id": q_rows[0].get("question_id") if q_rows else None,
            "story_arc_id": story_rows[0].get("story_arc_id") if story_rows else None,
            "speech_overlap": len(speaker_ids) > 1 or any(r.get("overlap") for r in active_rows),
            "camera": {
                "recommended_person": camera.get("active_person"),
                "crop_safe": (camera.get("vertical_crop") or {}).get("safe"),
                "center_x": (camera.get("vertical_crop") or {}).get("center_x"),
                "center_y": (camera.get("vertical_crop") or {}).get("center_y"),
                "recommended_zoom": (camera.get("vertical_crop") or {}).get("recommended_zoom"),
                "recommended_layout": (camera.get("vertical_crop") or {}).get("recommended_layout"),
                "camera_score": camera.get("camera_score"),
            },
            "movement": camera.get("movement"),
            "visual_observed_at": camera.get("visual_observed_at"),
            "evidence": camera.get("evidence", []),
        })
    return ok({"timeline": rows}, "ok" if rows else "partial",
              ["Master timeline preserva o timestamp real da evidência visual em visual_observed_at e não transforma amostragem em observação contínua comprovada."])
