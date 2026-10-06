from collections import defaultdict
from copy import deepcopy
import bisect
from .core import overlap
from .transcription import word_text


def captions(words, cfg):
    groups, current = [], []
    for w in words:
        if w["end"] <= w["start"]:
            continue
        if current:
            proposed = word_text(current+[w])
            if (len(current) >= cfg["max_words"] or len(proposed) > cfg["max_chars"]
                    or w["end"]-current[0]["start"] > cfg["max_seconds"]
                    or w["start"]-current[-1]["end"] > cfg["max_gap_seconds"]
                    or w.get("speaker") != current[-1].get("speaker")
                    or (current[-1]["word"].endswith((".", "?", "!")))):
                groups.append(current)
                current = []
        current.append(w)
    if current:
        groups.append(current)
    result = []
    for i, group in enumerate(groups):
        text = word_text(group)
        result.append({"caption_id": f"CAP_{i:06}", "start": group[0]["start"],
                       "end": group[-1]["end"], "text": text,
                       "display_text": text.upper() if cfg["uppercase_display"] else text,
                       "speaker": group[0].get("speaker"), "speech_overlap": any(w.get("speech_overlap") for w in group),
                       "needs_review": any(w.get("needs_review") for w in group),
                       "words": [{key: w.get(key) for key in
                           ("word", "raw", "start", "end", "confidence", "word_id", "speaker", "needs_review")}
                                 for w in group]})
    return result


def build_timeline(metadata, transcript, scenes, topics, vision, mappings, diarization):
    duration = metadata["duration"]
    segments = transcript["segments"]
    boundaries = {0.0, duration}
    for collection in (segments, scenes, topics, mappings, diarization.get("turns", [])):
        for row in collection:
            boundaries.update((max(0, min(duration, row["start"])), max(0, min(duration, row["end"]))))
    boundaries = sorted(boundaries)
    frames = vision.get("frames", [])
    frame_times = [f["time"] for f in frames]
    observations = defaultdict(dict)
    for obs in vision.get("observations", []):
        observations[obs["time"]][obs["person_id"]] = obs
    words = transcript["words"]
    timeline = []
    # Monotonic cursors: each data source is consumed in chronological order.
    def active(rows, start, end):
        return [r for r in rows if overlap(start, end, r["start"], r["end"]) > 1e-8]
    cursors = {name: 0 for name in ("segments", "scenes", "topics", "mappings", "turns", "words")}
    ordered = {"segments": sorted(segments, key=lambda x: x["start"]),
               "scenes": sorted(scenes, key=lambda x: x["start"]),
               "topics": sorted(topics, key=lambda x: x["start"]),
               "mappings": sorted(mappings, key=lambda x: x["start"]),
               "turns": sorted(diarization.get("turns", []), key=lambda x: x["start"]),
               "words": words}
    def rows_for(name, start, end):
        rows = ordered[name]
        i = cursors[name]
        while i < len(rows) and rows[i]["end"] <= start:
            i += 1
        cursors[name] = i
        found = []
        while i < len(rows) and rows[i]["start"] < end:
            if rows[i]["end"] > start:
                found.append(rows[i])
            i += 1
        return found
    for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
        if end-start < 1e-7:
            continue
        segs = rows_for("segments", start, end)
        visual = rows_for("scenes", start, end)
        semantic = rows_for("topics", start, end)
        links = rows_for("mappings", start, end)
        turns = rows_for("turns", start, end)
        chosen_words = [w for w in rows_for("words", start, end)
                        if start <= (w["start"]+w["end"])/2 < end]
        speaker_ids = sorted({r["speaker"] for r in turns if r.get("speaker")})
        speaker = speaker_ids[0] if len(speaker_ids) == 1 else None
        active_links = [l for l in links if l.get("visible_person") and l["speaker"] in speaker_ids]
        sample_index = bisect.bisect_left(frame_times, (start+end)/2)
        options = [j for j in (sample_index-1, sample_index) if 0 <= j < len(frames)]
        nearest = min(options, key=lambda j: abs(frame_times[j]-(start+end)/2)) if options else None
        frame = frames[nearest] if nearest is not None else None
        frame_valid = frame and abs(frame["time"]-(start+end)/2) <= max(
            0.75, 1/max(vision.get("sample_fps", 2), 0.01)) and (
            not visual or frame["scene_id"] == visual[0]["scene_id"])
        visible = frame["visible_people"] if frame_valid else []
        persons = sorted({m["visible_person"] for m in active_links if m["visible_person"] in visible})
        primary = persons[0] if len(persons) == 1 and len(speaker_ids) == 1 else None
        layout, reason = "unknown", "Sem vínculo suficiente entre voz e imagem."
        secondary = None
        if len(speaker_ids) > 1 and len(persons) >= 2:
            layout, reason = "split_screen_candidate", "Duas vozes sobrepostas com vínculos visuais registrados; revisar."
            primary, secondary = persons[:2]
        elif primary:
            layout = "single_focus" if len(visible) == 1 else "speaker_follow"
            reason = "Priorizar a pessoa vinculada ao locutor; vínculo pode ser inferência."
        elif len(visible) == 2:
            layout, reason = "two_person_scene", "Duas pessoas visíveis; participação de ambas ainda não comprovada."
        elif len(visible) > 2:
            layout, reason = "group_scene", "Grupo visível sem locutor visual resolvido."
        word_ids = [w.get("word_id") for w in chosen_words]
        timeline.append({"timeline_id": f"TL_{i:07}", "start": start, "end": end,
                         "scene_id": visual[0]["scene_id"] if visual else None,
                         "topic_id": semantic[0]["topic_id"] if semantic else None,
                         "speaker": speaker, "speakers": speaker_ids,
                         "active_person": primary, "primary_person": primary, "secondary_person": secondary,
                         "visible_people": visible, "visual_observed_at": frame["time"] if frame_valid else None,
                         "visual_is_sample": True, "speech_overlap": len(speaker_ids) > 1,
                         "text": word_text(chosen_words),
                         "word_ids": word_ids, "segment_ids": [s["segment_id"] for s in segs],
                         "recommended_layout": layout, "layout_reason": reason,
                         "people_positions": [{k: o.get(k) for k in (
                             "person_id", "bbox", "bbox_kind", "face_bbox", "center",
                             "estimated_vertical_crop", "safe_crop_possible", "crop_target")}
                             for o in observations.get(frame["time"], {}).values()] if frame_valid else []})
    return timeline


def enrich_editorial(semantics, timeline, mappings, transcript):
    data = deepcopy(semantics)
    for topic in data.get("topics", []):
        topic["people"] = sorted({p for row in timeline
                                 if overlap(topic["start"], topic["end"], row["start"], row["end"]) > 0
                                 for p in row["visible_people"]})
    for moment in data.get("moments", []):
        start, end = moment["start"], moment["end"]
        rows = [r for r in timeline if overlap(start, end, r["start"], r["end"]) > 0]
        persons = sorted({r["active_person"] for r in rows if r["active_person"]})
        speakers = sorted({s for r in rows for s in r["speakers"]})
        layout = "speaker_follow" if persons else "unknown"
        primary, secondary = None, None
        # Distinct voices and linked people must actually take part, not merely appear.
        if len(speakers) == 2 and len(persons) == 2:
            layout = "split_screen_candidate"
            primary, secondary = persons
        moment.update(speakers=speakers, people=persons, recommended_layout=layout,
                      primary_person=primary, secondary_person=secondary,
                      layout_needs_review=True, layout_intervals=[{
                          key: r[key] for key in ("start", "end", "scene_id", "speaker",
                          "active_person", "visible_people", "recommended_layout",
                          "people_positions")} for r in rows])
        if not moment.get("complete_sentence"):
            moment["needs_review"] = True
            moment["end_boundary_warning"] = "Fala não termina com pontuação completa; não aprovar corte automático."
    return data
