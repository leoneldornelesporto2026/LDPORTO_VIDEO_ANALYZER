from collections import Counter, defaultdict
from pathlib import Path
import math
import re
from .core import ok, overlap, run_command, write_json
from .editorial import (GENERIC_TERMS, fold_text, normalize_moment, optimize_boundaries,
                        rank_candidate, deduplicate_candidates, classify_content,
                        _complete_story, _story_component_ids)
from .editorial_intelligence import narrative_integrity, humor_integrity, select_editorial_shortlist

_CAP = r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][A-Za-zÀ-ÖØ-öø-ÿ0-9'’_-]*"
_NAME = rf"{_CAP}(?:\s+(?:(?:de|da|do|dos|das|e)\s+)?{_CAP}){{0,4}}"
_CUES = {
    "artist_or_band": r"(?:banda|grupo|cantor(?:a)?|artista)",
    "song": r"(?:música|musica|canção|cancao|faixa)",
    "album": r"(?:álbum|album|disco)",
    "organization": r"(?:empresa|companhia|gravadora|organizacao|organização)",
    "brand": r"(?:marca)",
    "program": r"(?:programa|podcast|rádio|radio|canal)",
    "location": r"(?:cidade|estado|país|pais|bairro|em)",
    "event": r"(?:evento|festival|congresso|show)",
    "product": r"(?:produto|suplemento|modelo)",
    "person": r"(?:senhor|senhora|doutor|doutora|professor|professora|apresentador|apresentadora)",
}


def _dict_rows(value):
    """Return only mapping rows from a list-like stage contract.

    Downstream editorial stages must not crash because one optional model/provider
    returned a nested list or other non-object item.  Invalid rows are ignored here
    and surfaced by ``run_understanding`` as a contract-normalization note instead
    of being silently treated as evidence.
    """
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _contract_issue(path, expected, value, action):
    return {
        "path": path,
        "expected": expected,
        "received": type(value).__name__,
        "action": action,
    }


def _sanitize_list_field(row, key, path, diagnostics):
    value = row.get(key, [])
    if isinstance(value, list):
        return value
    diagnostics.append(_contract_issue(f"{path}.{key}", "list", value, "replaced_with_empty_list"))
    return []


def _sanitize_mapping_field(row, key, path, diagnostics):
    value = row.get(key)
    if value is None or isinstance(value, dict):
        return value
    diagnostics.append(_contract_issue(f"{path}.{key}", "object|null", value, "replaced_with_empty_object"))
    return {}


def _normalize_semantic_contract(semantic):
    """Normalize the semantic->understanding boundary without inventing evidence.

    V4.4 real runs showed that provider/model output can preserve the top-level list
    shape while one nested control field arrives as a list instead of an object.
    The old normalizer only filtered top-level rows, so downstream code could still
    crash on ``.get``.  This function now validates the known control-plane fields
    and returns path-level diagnostics suitable for replay/debugging.
    """
    notes, diagnostics = [], []
    if not isinstance(semantic, dict):
        diagnostics.append(_contract_issue("semantic", "object", semantic, "replaced_with_empty_contract"))
        notes.append(f"semantic_contract_normalized: root={type(semantic).__name__}; expected object")
        return {"topics": [], "moments": [], "questions_answers": [], "program_sections": [],
                "editorial_review": None}, notes, diagnostics
    data = dict(semantic)
    for key in ("topics", "moments", "questions_answers", "program_sections"):
        raw = data.get(key, [])
        rows = _dict_rows(raw)
        if not isinstance(raw, list) or len(rows) != len(raw):
            raw_count = len(raw) if isinstance(raw, list) else 0
            diagnostics.append(_contract_issue(f"semantic.{key}", "list[object]", raw,
                                               f"kept_{len(rows)}_valid_objects"))
            notes.append(f"semantic_contract_normalized: {key} valid_objects={len(rows)}/{raw_count}; expected list[object]")
        clean = []
        for index, original in enumerate(rows):
            row = dict(original)
            path = f"semantic.{key}[{index}]"
            if key == "topics":
                row["evidence_segment_ids"] = _sanitize_list_field(row, "evidence_segment_ids", path, diagnostics)
                row["speakers"] = _sanitize_list_field(row, "speakers", path, diagnostics)
            elif key == "moments":
                row["evidence_segment_ids"] = _sanitize_list_field(row, "evidence_segment_ids", path, diagnostics)
                row["categories"] = _sanitize_list_field(row, "categories", path, diagnostics)
                row["editorial"] = _sanitize_mapping_field(row, "editorial", path, diagnostics) or {}
            elif key == "questions_answers":
                for field in ("answer_segment_ids", "question_segment_ids", "evidence_segment_ids"):
                    if field in row:
                        row[field] = _sanitize_list_field(row, field, path, diagnostics)
            elif key == "program_sections":
                row["topic_ids"] = _sanitize_list_field(row, "topic_ids", path, diagnostics)
                if "evidence_segment_ids" in row:
                    row["evidence_segment_ids"] = _sanitize_list_field(row, "evidence_segment_ids", path, diagnostics)
            clean.append(row)
        data[key] = clean
    review = data.get("editorial_review")
    if isinstance(review, list):
        valid = _dict_rows(review)
        data["editorial_review"] = {"top_moments": valid, "content_angles": [],
                                    "status": "partial", "needs_review": True,
                                    "method": "normalized_legacy_top_moments_list"}
        diagnostics.append(_contract_issue("semantic.editorial_review", "object|null", review,
                                           f"normalized_legacy_list_{len(valid)}_rows"))
        notes.append(f"semantic_contract_normalized: editorial_review list -> object ({len(valid)} valid rows)")
    elif isinstance(review, dict):
        normalized_review = dict(review)
        top = normalized_review.get("top_moments", [])
        valid = _dict_rows(top)
        if not isinstance(top, list) or len(valid) != len(top):
            diagnostics.append(_contract_issue("semantic.editorial_review.top_moments", "list[object]", top,
                                               f"kept_{len(valid)}_valid_objects"))
            notes.append("semantic_contract_normalized: editorial_review.top_moments contained invalid rows")
        normalized_review["top_moments"] = valid
        content_angles = normalized_review.get("content_angles", [])
        if not isinstance(content_angles, list):
            diagnostics.append(_contract_issue("semantic.editorial_review.content_angles", "list", content_angles,
                                               "replaced_with_empty_list"))
            normalized_review["content_angles"] = []
        data["editorial_review"] = normalized_review
    elif review is not None:
        diagnostics.append(_contract_issue("semantic.editorial_review", "object|null", review, "omitted"))
        notes.append(f"semantic_contract_normalized: editorial_review={type(review).__name__}; omitted")
        data["editorial_review"] = None
    if diagnostics:
        notes.append(f"semantic_contract_diagnostics: {len(diagnostics)} normalization event(s); see understanding_contract_diagnostics.json")
    return data, notes, diagnostics


def _validate_story_arcs_contract(arcs, transcript_segments):
    """Normalize only observed IDs and invalidate unsupported story claims.

    Story recovery and the duration exception use different component shapes.
    This boundary guarantees that ranking sees a mapping with grounded
    ``segment_ids`` or None, never a provider list masquerading as a mapping.
    """
    diagnostics = []
    known = {segment.get('segment_id') for segment in transcript_segments}
    normalized = []
    for index, original in enumerate(arcs):
        if not isinstance(original, dict):
            diagnostics.append(_contract_issue(f'story_arcs[{index}]', 'object', original, 'omitted'))
            continue
        arc = dict(original)
        for key in ('setup', 'development', 'payoff'):
            part = arc.get(key)
            if part is None:
                continue
            ids = _story_component_ids(arc, key)
            valid = bool(ids) and all(item in known for item in ids)
            if valid and isinstance(part, list):
                arc[key] = {'segment_ids': ids}
                diagnostics.append(_contract_issue(f'story_arcs[{index}].{key}', 'object', part,
                                                   'normalized_existing_segment_ids'))
            elif not valid:
                arc[key] = None
                diagnostics.append(_contract_issue(f'story_arcs[{index}].{key}',
                                                   'object_with_known_segment_ids|null', part,
                                                   'invalid_evidence_removed'))
        if arc.get('kind') == 'complete_story' and not _complete_story(
                arc, arc.get('evidence_segment_ids') or []):
            arc.update(kind='partial_story', completeness='unresolved_payoff',
                       standalone_score=None, needs_review=True,
                       narrative_supported=False)
            diagnostics.append(_contract_issue(f'story_arcs[{index}].kind',
                                               'complete_story_with_ordered_grounded_components',
                                               original.get('kind'), 'downgraded_to_partial_story'))
        normalized.append(arc)
    return normalized, diagnostics


def extract_entities(transcript):
    """Conservative textual entities. No external recognition or face naming."""
    found = {}
    for segment in transcript.get("segments", []):
        text = segment.get("text") or ""
        for entity_type, cue in _CUES.items():
            pattern = re.compile(rf"(?i:\b{cue})\s+(?:(?i:do|da|de|o|a)\s+)?({_NAME})")
            for match in pattern.finditer(text):
                name = _trim_entity_name(match.group(1))
                # Generated by GitHub Copilot - Oct-05-2026
                location_prefix = entity_type == "location" and re.match(r"^(?:sao|santo|santa)\s+\w+", fold_text(name))
                if not entity_name_valid(name) and not location_prefix:
                    continue
                key = (name.casefold(), entity_type)
                row = found.setdefault(key, {"name": name, "type": entity_type,
                                             "mentions": 0, "first_time": segment["start"],
                                             "evidence_segment_ids": [], "confidence": None,
                                             "source": "transcript_textual_cue", "inference": True})
                row["method"] = "strong_textual_cue"
                row.setdefault("mentions_evidence", []).append({"segment_id": segment["segment_id"],
                    "start_char": match.start(1), "end_char": match.start(1) + len(name),
                    "literal": text[match.start(1):match.start(1) + len(name)],
                    "start": segment["start"], "end": segment.get("end"), "timestamp_method": "segment_interval"})
                row["confidence_is_calibrated"] = False
                row["mentions"] += 1
                row["first_time"] = min(row["first_time"], segment["start"])
                if segment["segment_id"] not in row["evidence_segment_ids"]:
                    row["evidence_segment_ids"].append(segment["segment_id"])
        # Explicit self-introduction is strong textual evidence for a name mention.
        intro = re.search(rf"(?i:\b(?:eu sou|me chamo|meu nome é|meu nome e))\s+({_NAME})", text)
        if intro:
            name = _trim_entity_name(intro.group(1))
            if not entity_name_valid(name):
                continue
            key = (name.casefold(), "person")
            row = found.setdefault(key, {"name": name, "type": "person", "mentions": 0,
                                         "first_time": segment["start"], "evidence_segment_ids": [],
                                         "confidence": None, "source": "explicit_self_introduction",
                                         "inference": False})
            row["method"] = "explicit_self_introduction"
            row.setdefault("mentions_evidence", []).append({"segment_id": segment["segment_id"],
                "start_char": intro.start(1), "end_char": intro.start(1) + len(name),
                "literal": text[intro.start(1):intro.start(1) + len(name)],
                "start": segment["start"], "end": segment.get("end"), "timestamp_method": "segment_interval"})
            row["confidence_is_calibrated"] = False
            row["mentions"] += 1
            if segment["segment_id"] not in row["evidence_segment_ids"]:
                row["evidence_segment_ids"].append(segment["segment_id"])
    rows = sorted(found.values(), key=lambda r: (-r["mentions"], r["first_time"], r["name"].casefold()))
    from .core import digest
    for row in rows:
        row["entity_id"] = "ENTITY_" + digest([fold_text(row["name"]), row["type"]])[:12]
        row["canonical_name"] = row["name"]
        row["canonical_entity_id"] = row["entity_id"]
        row["possible_aliases"] = []
        row["needs_review"] = row.get("source") != "explicit_self_introduction"
    for row in rows:
        parts = fold_text(row["name"]).split()
        longer = [candidate for candidate in rows if candidate["type"] == row["type"] and
                  len(candidate["name"].split()) > len(parts) and fold_text(candidate["name"]).split()[:len(parts)] == parts]
        if len(longer) == 1:
            row.update(canonical_name=longer[0]["name"], canonical_entity_id=longer[0]["entity_id"],
                       alias_method="unique_grounded_name_prefix_requires_review", needs_review=True)
        elif len(longer) > 1:
            row.update(canonical_entity_id=None, possible_aliases=[candidate["entity_id"] for candidate in longer],
                       alias_method="ambiguous_grounded_prefix", needs_review=True)
    return rows


def _trim_entity_name(value):
    for token in re.finditer(r"\S+", value):
        normalized = fold_text(token.group().strip(".,;:!?"))
        if token.start() and normalized in GENERIC_TERMS | {"pelas", "pelos"} and normalized not in {"de", "da", "do", "dos", "das", "e"}:
            value = value[:token.start()].rstrip()
            break
    return value.strip(" .,;:!?\"'()[]")


# Generated by GitHub Copilot - Oct-05-2026
def entity_name_valid(name):
    """Reject PT-BR pronouns, common verbs and sentence-initial false positives."""
    words = re.findall(r"\w+", fold_text(name))
    return bool(words and len(name) >= 2 and words[0] not in GENERIC_TERMS and
                not all(word in GENERIC_TERMS for word in words))


def _speaker_name_evidence(transcript, questions_answers=None):
    out = {}
    for s in transcript.get("segments", []):
        if not s.get("speaker"):
            continue
        match = re.search(rf"(?i:\b(?:eu sou|me chamo|meu nome é|meu nome e))\s+({_NAME})", s.get("text", ""))
        if match and entity_name_valid(match.group(1)):
            out.setdefault(s["speaker"], {"possible_name": _trim_entity_name(match.group(1)),
                                          "name_source": "explicit_self_introduction",
                                          "name_evidence_segment_id": s["segment_id"],
                                          "name_confidence": None})
    for pair in questions_answers or []:
        if not pair.get("answer_speaker") or not pair.get("question_answer_complete"):
            continue
        match = re.match(rf"(?:(?i:professor|doutor|senhor)\s+)?({_NAME})\s*,", pair.get("question", ""))
        if match and entity_name_valid(match.group(1)):
            out.setdefault(pair["answer_speaker"], {"possible_name": _trim_entity_name(match.group(1)),
                "name_source": "direct_address_with_grounded_answer_turn", "name_evidence_segment_id": pair.get("question_segment_id"),
                "name_confidence": None})
    return out


# Generated by GitHub Copilot - Oct-05-2026
def build_participants(transcript, diarization, vision, mapping_summary, questions_answers, cfg=None, shots=None, include_background=False):
    """Separate editorial participants from raw tracks and anonymous visual candidates."""
    cfg = cfg or {}
    shots = shots or []
    min_visual = cfg.get("participant_min_visual_seconds", 8.0)
    min_observations = cfg.get("participant_min_observations", 12)
    min_speech = cfg.get("participant_min_speech_seconds", 3.0)
    min_shots = cfg.get("participant_min_distinct_shots", 2)
    speaker_to_person = {r["speaker_id"]: r.get("person_id") for r in mapping_summary if r.get("person_id")}
    person_to_speakers = defaultdict(list)
    for speaker, person in speaker_to_person.items():
        person_to_speakers[person].append(speaker)
    speech = {s["speaker_id"]: s.get("speech_seconds") for s in diarization.get("speakers", [])}
    q_count = Counter(q.get("question_speaker") for q in questions_answers if q.get("question_speaker"))
    a_count = Counter(q.get("answer_speaker") for q in questions_answers if q.get("answer_speaker"))
    names = _speaker_name_evidence(transcript, questions_answers)
    participants = []
    known_people = {p["person_id"]: p for p in vision.get("people", [])}

    for person_id, person in sorted(known_people.items()):
        speakers = sorted(person_to_speakers.get(person_id, []))
        visual_seconds = person.get("total_visual_seconds", 0.0) or 0.0
        observations = person.get("observation_count", 0) or 0
        distinct_shots = len(person.get("scene_ids", []))
        speech_seconds = sum(speech.get(speaker) or 0 for speaker in speakers)
        confirmed = speech_seconds >= min_speech
        likely = visual_seconds >= min_visual and observations >= min_observations and (
                 distinct_shots >= min_shots or visual_seconds >= 4 * min_visual)
        status = ("confirmed_editorial_participant" if confirmed else "likely_visual_participant" if likely else
                  "background_person" if visual_seconds >= 1 else "insufficient_evidence")
        if not confirmed and not include_background:
            continue
        questions = sum(q_count[s] for s in speakers)
        answers = sum(a_count[s] for s in speakers)
        role = "unknown"
        role_confidence = None
        role_evidence = []
        if questions >= 3 and questions >= max(2, answers*2):
            role, role_confidence = "likely_host", min(0.85, 0.55+0.05*questions)
            role_evidence = ["repeated_questions"]
        elif answers >= 3 and answers >= max(2, questions*2):
            role, role_confidence = "likely_guest", min(0.80, 0.50+0.05*answers)
            role_evidence = ["repeated_answers"]
        name_rows = [names[s] for s in speakers if s in names]
        name = name_rows[0] if name_rows else {}
        participants.append({
            "participant_id": f"PARTICIPANT_{len(participants):04}", "status": status,
            "person_id": person_id, "speaker_ids": speakers,
            "total_visual_seconds": visual_seconds, "distinct_shots": distinct_shots,
            "first_seen": person.get("first_seen"), "last_seen": person.get("last_seen"),
            "observation_count": person.get("observation_count"),
            "speech_seconds": sum(speech.get(s) or 0 for s in speakers) if speakers else None,
            "question_count": questions, "answer_count": answers,
            "role": role, "role_confidence": role_confidence, "role_evidence": role_evidence,
            "possible_name": name.get("possible_name"), "name_source": name.get("name_source"),
            "name_evidence_segment_id": name.get("name_evidence_segment_id"),
            "name_confidence": name.get("name_confidence"),
            "civil_identity_inferred": False,
        })
    mapped_speakers = {s for p in participants for s in p["speaker_ids"]}
    for speaker_id in sorted(speech):
        if speaker_id in mapped_speakers:
            continue
        if (speech[speaker_id] or 0) < min_speech and not include_background:
            continue
        name = names.get(speaker_id, {})
        participants.append({
            "participant_id": f"PARTICIPANT_{len(participants):04}",
            "status": "confirmed_editorial_participant" if (speech[speaker_id] or 0) >= min_speech else "insufficient_evidence",
            "person_id": None, "speaker_ids": [speaker_id], "first_seen": None, "last_seen": None,
            "observation_count": None, "speech_seconds": speech.get(speaker_id),
            "question_count": q_count[speaker_id], "answer_count": a_count[speaker_id],
            "role": "unknown", "role_confidence": None, "role_evidence": [],
            "possible_name": name.get("possible_name"), "name_source": name.get("name_source"),
            "name_evidence_segment_id": name.get("name_evidence_segment_id"),
            "name_confidence": name.get("name_confidence"), "civil_identity_inferred": False,
        })
    for participant in participants:
        speech_seconds = participant.get("speech_seconds")
        visual_seconds = participant.get("total_visual_seconds")
        questions, answers = participant.get("question_count", 0), participant.get("answer_count", 0)
        components = {
            "speech_duration": .35 * min(1.0, speech_seconds / 60) if speech_seconds is not None else None,
            "visual_duration": .25 * min(1.0, visual_seconds / 60) if visual_seconds is not None else None,
            "shot_recurrence": .15 * min(1.0, participant.get("distinct_shots", 0) / 3),
            "qa_participation": .15 * min(1.0, (questions + answers) / 3),
            "textual_introduction": .1 if participant.get("possible_name") else 0.0,
        }
        significance = sum(value for value in components.values() if value is not None)
        editorial = (speech_seconds or 0) >= min_speech
        category = ("main_participant" if editorial and significance >= .65 else
                    "editorial_participant" if editorial else
                    "visual_participant" if participant["status"] == "likely_visual_participant" else
                    "incidental_person" if (visual_seconds or 0) >= 1 else "background_person")
        participant.update(participant_category=category, editorial_significant=editorial,
                           participant_significance_score=round(significance, 3),
                           significance_components=components,
                           significance_method="weighted_observed_relevance_not_probability",
                           confidence_is_calibrated=False, needs_review=True)
        if participant["role"] == "unknown" and questions >= 3 and questions >= max(2, answers * 2):
            participant.update(role="likely_host", role_evidence=["repeated_questions"], role_confidence=None)
        elif participant["role"] == "unknown" and answers >= 3 and answers >= max(2, questions * 2):
            participant.update(role="likely_guest", role_evidence=["repeated_answers"], role_confidence=None)
    return participants


# Generated by GitHub Copilot - Oct-05-2026
def build_story_arcs(transcript, topics, questions_answers=None):
    """Keep marker-supported narratives and explicit unresolved discussion-arc candidates."""
    from .story_recovery import recover_story_arcs, literal_outcome, TOPIC_SHIFT, ACTION
    by_id = {s["segment_id"]: s for s in transcript.get("segments", [])}
    arcs = []
    conflict_re = re.compile(r"\b(mas|só que|so que|porém|porem|problema|dificuldade|errado|não deu|nao deu)\b", re.I)
    setup_re = re.compile(r"\b(quando|na época|na epoca|um dia|começou|comecou|aconteceu)\b", re.I)
    for topic in topics:
        segments = sorted([by_id[sid] for sid in topic.get("evidence_segment_ids", []) if sid in by_id],
                          key=lambda s: s['start'])
        if len(segments) < 3:
            continue
        setup = next((s for s in segments if setup_re.search(s["text"])), None)
        conflict = next((s for s in segments if setup and s['start'] > setup['start']
                         and conflict_re.search(s["text"])), None)
        payoff = next((s for s in segments if conflict and s["start"] > conflict["start"]
                       and literal_outcome(s["text"])), None)
        complete_qa = next((pair for pair in questions_answers or [] if pair.get("question_answer_complete") and
                            topic["start"] <= pair["question_start"] and pair["answer_end"] <= topic["end"]), None)
        marker_supported = (setup is not None and conflict is not None and payoff is not None and
                            setup["start"] < conflict["start"] < payoff["start"])
        if marker_supported:
            span = [s for s in segments if setup['start'] <= s['start'] <= payoff['start']]
            marker_supported = bool(ACTION.search(fold_text(setup['text'])) and setup.get('speaker')
                                    and conflict.get('speaker') == setup['speaker']
                                    and payoff.get('speaker') == setup['speaker']
                                    and payoff['end'] - setup['start'] <= 360
                                    and not any(TOPIC_SHIFT.search(fold_text(s['text'])) for s in span)
                                    and all(s.get('speaker') and (s['speaker'] == setup['speaker']
                                            or s['end'] - s['start'] <= 12) for s in span)
                                    and all(b['start'] - a['end'] <= 15 for a, b in zip(span, span[1:])))
        kind = "complete_story" if marker_supported else "qa_arc" if complete_qa else "partial_story" if setup and conflict else "anecdote" if setup else "discussion_segment"
        if not marker_supported:
            payoff = None
            if kind in ("discussion_segment", "qa_arc"):
                setup, conflict = None, None
            if complete_qa:
                payoff = by_id.get(complete_qa["answer_segment_ids"][-1])
        if classify_content(" ".join(segment["text"] for segment in segments))["eligibility"] == "excluded":
            continue
        middle = ([segment for segment in segments if setup and payoff and
                   setup["start"] < segment["start"] < payoff["start"]
                   and segment.get('speaker') == setup.get('speaker')] if marker_supported else
                  [segment for segment in segments[1:-1] if not payoff or segment["start"] < payoff["start"]])
        # A story's development must be independently grounded and temporally
        # ordered between setup and outcome. The conflict can be the climax.
        if marker_supported and not middle:
            marker_supported = False
            kind = 'partial_story'
        ending = segments[-1]
        start = setup["start"] if setup else segments[0]["start"]
        duration = ending["end"]-start
        if duration < 8:
            continue
        complete = ending["text"].rstrip().endswith((".", "?", "!"))
        score = min(1.0, 0.55 + 0.10*bool(setup) + 0.15*bool(middle) + 0.15*complete)
        arcs.append({
            "story_arc_id": f"STORY_{len(arcs):04}", "topic_id": topic.get("topic_id"),
            "kind": kind, "narrative_supported": kind == "complete_story",
            "topic_ids": [topic.get("topic_id")], "section_id": None,
            "title": topic.get("topic"), "summary": topic.get("summary"),
            "evidence_segment_ids": [segment["segment_id"] for segment in segments],
            "start": start, "end": ending["end"],
            "setup": {"text": setup["text"], "segment_ids": [setup["segment_id"]],
                      "start": setup['start'], "end": setup['end']} if setup else None,
            "conflict": {"text": conflict["text"], "segment_ids": [conflict["segment_id"]],
                         "start": conflict['start'], "end": conflict['end']} if conflict else None,
            "development": {"text": " ".join(s["text"] for s in middle) or None,
                            "segment_ids": [s["segment_id"] for s in middle],
                            "start": middle[0]['start'] if middle else None,
                            "end": middle[-1]['end'] if middle else None} if kind != "discussion_segment" else None,
            "climax": {"text": conflict["text"], "segment_ids": [conflict["segment_id"]],
                       "start": conflict['start'], "end": conflict['end']} if marker_supported else None,
            "payoff": {"text": payoff["text"], "segment_ids": [payoff["segment_id"]], "start": payoff['start'], "end": payoff['end']} if payoff else None,
            "ending": {"text": ending["text"], "segment_ids": [ending["segment_id"]],
                       "start": ending['start'], "end": ending['end']},
            "narrative_structure": {"introduction": [setup['segment_id']] if setup else [],
                                     "development": [s['segment_id'] for s in middle],
                                     "climax": [conflict['segment_id']] if marker_supported else [],
                                     "resolution": [payoff['segment_id']] if payoff else [],
                                     "ending": [ending['segment_id']]},
            "standalone_score": score if marker_supported or complete_qa else None,
            "completeness": "supported_setup_development_payoff" if marker_supported else "supported_question_answer" if complete_qa else "unresolved_payoff",
            "method": "narrative_marker_heuristic" if marker_supported else "grounded_qa_arc" if complete_qa else "discussion_section_candidate",
            "inference": True,
            "confidence": None, "needs_review": True,
            "missing_component_reasons": {key: "not_narrative_or_unresolved" for key, value in (("setup", setup), ("conflict", conflict), ("payoff", payoff)) if value is None},
        })
    existing = [(a['start'], a['end']) for a in arcs if a['kind'] == 'complete_story']
    arcs.extend(a for a in recover_story_arcs(transcript.get('segments', []), topics)
                if not any(start <= a['start'] and end >= a['end'] for start, end in existing))
    from .semantic import propagate_semantic_degradation
    propagate_semantic_degradation(arcs, topics)
    return arcs


def _score_class(value):
    return {"excellent": 0.95, "good": 0.78, "needs_context": 0.45, "poor": 0.20}.get(value)


# Generated by GitHub Copilot - Oct-05-2026
def build_main_moments(transcript, topics, moments, questions_answers, story_arcs, shots, editorial_review=None, cfg=None):
    """Optimize grounded boundaries then rank and deduplicate editorial candidates."""
    cfg = cfg or {}
    segments = transcript.get("segments", [])
    review_scores = {r["moment_id"]: r.get("editorial_score")
                     for r in (editorial_review or {}).get("top_moments", [])}
    result = []
    for original in moments:
        moment = normalize_moment(original)
        start, end = moment["start"], moment["end"]
        topic = next((t for t in topics if overlap(start, end, t["start"], t["end"]) > 0), None)
        lo = max(0.0, start-30.0, topic["start"] if topic else 0.0)
        hi = min((segments[-1]["end"] if segments else end), end+30.0,
                 topic["end"] if topic else (segments[-1]["end"] if segments else end+30.0))
        matching_stories = [arc for arc in story_arcs if overlap(start, end, arc['start'], arc['end']) > 0]
        story = max(matching_stories, key=lambda arc: (
                    overlap(start, end, arc['start'], arc['end']) / max(end-start, 1e-9),
                    arc.get('kind') == 'complete_story'), default=None)
        boundaries = optimize_boundaries(moment, segments, cfg, story, questions_answers, topic, shots)
        ideal_start, ideal_end = boundaries["ideal_start"], boundaries["ideal_end"]
        segment_ids = boundaries.get('boundary_segment_ids') or moment.get('evidence_segment_ids', [])
        narrative = narrative_integrity(story, segment_ids)
        humor = humor_integrity(segments, ideal_start, ideal_end,
                                hinted=bool(set(moment.get('categories') or []) & {'humor', 'punchline'}))
        if (boundaries.get('humor_boundary_proposal') or {}).get('expansion_unresolved'):
            humor['blockers'].append('humor_context_exceeds_topic_shot_or_duration')
            humor['status'] = 'incomplete'
        qa_overlap = [q for q in questions_answers if q.get('answer_expected') and
                      overlap(start, end, q['question_start'], q.get('answer_end') or q['question_end']) > 0]
        qa_blockers = ['question_without_complete_answer'] if any(
            q['question_start'] >= ideal_start and q['question_start'] < ideal_end and
            (not q.get('question_answer_complete') or not q.get('answer_end') or
             q['answer_end'] > ideal_end) for q in qa_overlap) else []
        editorial_blockers = sorted(set(narrative['blockers'] + humor['blockers'] + qa_blockers + boundaries.get('boundary_blockers', [])))
        if editorial_blockers:
            boundaries['standalone_assessment'] = 'context_required'
            boundaries['boundary_decision'] = 'pending'
            boundaries['boundary_decision_reasons'] = sorted(set(
                boundaries.get('boundary_decision_reasons', []) + editorial_blockers))
        q_complete = any(q.get("question_answer_complete") is True and q.get("answer_end") is not None and
                         q["question_start"] >= ideal_start and q["answer_end"] <= ideal_end
                         for q in questions_answers)
        visual = [s.get("camera_score") for s in shots if overlap(start, end, s["start"], s["end"]) > 0 and
                  isinstance(s.get("camera_score"), (int, float))]
        editorial_payload = moment.get("editorial")
        ed = editorial_payload if isinstance(editorial_payload, dict) else {}
        from .semantic import classify_hook
        hook = classify_hook(' '.join(segment.get('text', '') for segment in segments if ideal_start <= segment['start'] < ideal_start + 15))
        cats = set(moment.get("categories") or [])
        available = [v for v in ed.values() if isinstance(v, (int, float))]
        editorial_score = review_scores.get(moment["moment_id"])
        if editorial_score is None:
            editorial_score = sum(available)/len(available) if available else None
        result.append({
            "moment_id": moment["moment_id"],
            "degraded_reason": list(moment.get('degraded_reason') or []),
            "text": " ".join(segment.get("text", "") for segment in segments if ideal_start <= segment["start"] and segment["end"] <= ideal_end),
            "topic_id": topic.get("topic_id") if topic else None,
            "story_arc_id": story.get("story_arc_id") if story else None,
            "story_type": story.get("kind") if story else None,
            "speaker_ids": sorted({s['speaker'] for s in segments
                                   if s.get('speaker') and s['end'] > ideal_start and s['start'] < ideal_end}),
            "core_moment": {"start": start, "end": end, "text": moment.get("text")},
            "possible_start": max(lo, start-10.0), "ideal_start": ideal_start,
            "possible_end": min(hi, end+10.0), "ideal_end": ideal_end,
            "context_required": moment.get("context_required"),
            "context_requirement": moment["context_requirement"], "context_reason": moment["context_reason"],
            "context_seconds_before": boundaries["context_added_before"], "context_seconds_after": boundaries["context_added_after"],
            "content_type": moment["content_type"], "commercial_score": moment["commercial_score"],
            "commercial_classification": moment["commercial_classification"],
            "metadata_locale": "pt-BR", **boundaries,
            "recommended_context_seconds": max(0.0, ideal_end-ideal_start),
            "standalone_score": None if editorial_blockers else _score_class(moment.get("standalone_class")),
            "original_standalone_class": moment.get('standalone_class'),
            "hook_strength": hook['hook_strength'], "hook_type": hook['hook_type'],
            "ending_strength": 1.0 if moment.get("complete_sentence") else 0.35,
            "story_completeness": story.get("standalone_score") if story and narrative["status"] == "complete_candidate" else None,
            "question_answer_complete": q_complete,
            "qa_integrity_status": 'complete_candidate' if q_complete else 'unresolved' if qa_overlap else 'not_applicable',
            "editorial_blockers": editorial_blockers, "narrative_integrity": narrative,
            "humor_integrity": humor,
            "editorial_score": editorial_score,
            "story_score": story.get("standalone_score") if story else None,
            "hook_score": min(hook['hook_strength'], ed.get('hook_strength')) if hook['hook_strength'] is not None and isinstance(ed.get('hook_strength'), (int, float)) else hook['hook_strength'],
            "information_score": ed.get("clarity"),
            "nostalgia_score": None,
            "surprise_score": ed.get("curiosity") if "surprise" in cats else None,
            "conflict_score": ed.get("controversy") if "conflict" in cats else None,
            "visual_score": sum(visual)/len(visual) if visual else None,
            "evidence_segment_ids": boundaries.get("boundary_segment_ids") or moment.get("evidence_segment_ids", []),
            "core_evidence_segment_ids": moment.get("evidence_segment_ids", []),
            "categories": sorted(cats), "method": "grounded_sentence_story_boundaries_and_weighted_utility",
            "inference": True, "needs_review": True,
        })
    from .story_recovery import candidate_recovery
    from .semantic import propagate_semantic_degradation
    propagate_semantic_degradation(result, topics)
    ranked = []
    for candidate in result:
        evaluated = rank_candidate(candidate, cfg)
        evaluated['recovery'] = candidate_recovery(evaluated, candidate.get('editorial_score'))
        ranked.append(evaluated)
    return deduplicate_candidates(ranked)[0]


# Generated by GitHub Copilot - Oct-05-2026
def build_thumbnail_candidates(vision, shots, max_candidates=80, main_moments=None):
    """Prioritize editorial timing and meaningful anonymous presence, not new raw IDs."""
    shot_by_scene = {s.get("scene_id"): s for s in shots}
    obs_by_time = defaultdict(list)
    for obs in vision.get("observations", []):
        obs_by_time[obs["time"]].append(obs)
    rows = []
    seen = set()
    meaningful={person['person_id'] for person in vision.get('people',[]) if person.get('meaningful')}
    for thumb in vision.get("thumbnails", []):
        # Generated by GitHub Copilot - Oct-05-2026
        if thumb.get("reason") == "new_person":
            continue
        time = float(thumb["time"])
        if time in seen:
            continue
        seen.add(time)
        obs = obs_by_time.get(time, [])
        scene = obs[0].get("scene_id") if obs else None
        shot = shot_by_scene.get(scene)
        face_sizes = [o.get("face_height") for o in obs if o.get("face_height") is not None]
        left_space = min((o["face_bbox"]["x"] for o in obs if o.get("face_bbox")), default=None)
        right_space = min((1-o["face_bbox"]["x"]-o["face_bbox"]["width"] for o in obs if o.get("face_bbox")), default=None)
        rows.append({
            "time": time, "path": thumb.get("path"), "reason": thumb.get("reason"),
            "shot_id": shot.get("shot_id") if shot else None,
            "person_ids": sorted({o.get("person_id") for o in obs if o.get("person_id")}),
            "sharpness": shot.get("sharpness_score") if shot else None,
            "motion_blur": shot.get("motion_blur_score") if shot else None,
            "face_size": max(face_sizes) if face_sizes else None,
            "eyes_open": None,
            "composition": shot.get("composition_score") if shot else None,
            "negative_space_left": left_space,
            "negative_space_right": right_space,
            "thumbnail_score": shot.get("thumbnail_score") if shot else None,
            "evidence": ["saved_visual_sample"],
            "editorial_moment_ids":[moment['moment_id'] for moment in main_moments or [] if
                                     moment['ideal_start']<=time<=moment['ideal_end']],
            "meaningful_person_present":any(observation.get('person_id') in meaningful for observation in obs),
        })
    rows.sort(key=lambda row:(bool(row['editorial_moment_ids']),row['meaningful_person_present'],
                              row.get('thumbnail_score') is not None,row.get('thumbnail_score') or -1,-row['time']),reverse=True)
    return rows[:int(max_candidates)]


def extract_moment_frames(ctx, main_moments, thumbnail_candidates, cfg):
    if not cfg.get("extract_frames", True):
        return []
    limit = int(cfg.get("max_moments", 12))
    out = []
    root = ctx.output / "moment_frames"
    root.mkdir(parents=True, exist_ok=True)
    for moment in main_moments[:limit]:
        mid = moment["moment_id"]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',mid) or '..' in mid:
            raise ValueError('ID de momento inseguro para extracao de frames.')
        if not moment.get('default_shortlist_eligible',True):
            continue
        folder = root / mid
        folder.mkdir(exist_ok=True)
        start = float(moment["ideal_start"])
        core = moment["core_moment"]
        candidates = [t for t in thumbnail_candidates if core["start"]-5 <= t["time"] <= core["end"]+5]
        best = max(candidates, key=lambda r: r.get("thumbnail_score") or -1, default=None)
        best_t = best["time"] if best else (core["start"]+core["end"])/2
        clean_t = core["end"] if core["end"] > core["start"] else best_t
        files = {}
        for name, timestamp in (("opening_frame.jpg", start), ("best_frame.jpg", best_t), ("clean_frame.jpg", clean_t)):
            path = folder / name
            run_command(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}",
                         "-i", str(ctx.video), "-frames:v", "1", "-q:v", "2", str(path)])
            files[name] = str(path.relative_to(ctx.output)).replace("\\", "/")
        out.append({"moment_id": mid, "frames": files})
    return out


def build_video_understanding(metadata, transcript, topics, participants, entities, story_arcs,
                              main_moments, questions_answers, shots):
    top_topics = sorted(topics, key=lambda t: t.get("end", 0)-t.get("start", 0), reverse=True)
    top_entities = sorted(entities, key=lambda e: (-e.get("mentions", 0), e.get("first_time", 0)))
    speech_participants = sorted(participants, key=lambda p: p.get("speech_seconds") or 0, reverse=True)
    qualified = [topic for topic in top_topics if topic.get('method') == 'ollama' and
                 classify_content(' '.join(segment.get('text', '') for segment in transcript.get('segments', [])
                                          if segment.get('segment_id') in topic.get('evidence_segment_ids', [])))['eligibility'] != 'excluded']
    episode_sections = [{key: topic.get(key) for key in ('topic_id', 'topic', 'summary', 'start', 'end', 'evidence_segment_ids')}
                        for topic in qualified[:12]]
    about = 'Programa com blocos sobre: ' + '; '.join(dict.fromkeys(topic['topic'] for topic in episode_sections)) + '.' if episode_sections else None
    duration = metadata.get('duration') or 0
    primary = {**episode_sections[0], 'coverage_fraction': (episode_sections[0]['end'] - episode_sections[0]['start']) / duration if duration else None,
               'method': 'duration_coverage_of_grounded_topic_not_best_clip_score', 'needs_review': True} if episode_sections else None
    best_clip = max(main_moments, key=lambda moment: moment.get('editorial_score_final') or 0, default=None)
    dense = sorted(main_moments, key=lambda m: m.get("information_score") or -1, reverse=True)[:10]
    best_image = sorted(shots, key=lambda s: s.get("camera_score") or -1, reverse=True)[:10]
    return {
        "about": about,
        "episode_summary": {'text': about, 'primary_sections': episode_sections,
                            'main_guest_or_theme': {'participant_id': speech_participants[0]['participant_id'],
                                'possible_name': speech_participants[0].get('possible_name'), 'method': 'observed_speech_duration'} if speech_participants else None,
                            'secondary_topics': [topic['topic'] for topic in episode_sections[1:]],
                            'method': 'grounded_multisection_aggregation_requires_review'},
        "episode_primary_theme": primary,
        "best_clip_theme": next((topic.get('topic') for topic in topics if best_clip and topic['topic_id'] == best_clip.get('topic_id')), None),
        "duration": metadata.get("duration"),
        "main_topics": top_topics[:12],
        "main_participants": speech_participants[:10],
        "top_entities": top_entities[:30],
        "story_arcs": story_arcs,
        "main_moments": main_moments[:30],
        "questions_answers": questions_answers,
        "high_information_sections": [m["moment_id"] for m in dense if m.get("information_score") is not None],
        "best_visual_shots": [s["shot_id"] for s in best_image if s.get("camera_score") is not None],
        "method": "derived_from_grounded_analyzer_artifacts",
        "inference": True,
    }


def run_understanding(ctx, metadata, transcript, diarization, vision, active_data, semantic, shots, cfg):
    semantic, contract_notes, contract_diagnostics = _normalize_semantic_contract(semantic)
    active_data = active_data if isinstance(active_data, dict) else {}
    transcript = dict(transcript) if isinstance(transcript, dict) else {}
    transcript["segments"] = _dict_rows(transcript.get("segments", []))
    transcript["words"] = _dict_rows(transcript.get("words", []))
    diarization = dict(diarization) if isinstance(diarization, dict) else {}
    diarization["speakers"] = _dict_rows(diarization.get("speakers", []))
    vision = dict(vision) if isinstance(vision, dict) else {}
    vision["people"] = _dict_rows(vision.get("people", []))
    vision["observations"] = _dict_rows(vision.get("observations", []))
    vision["thumbnails"] = _dict_rows(vision.get("thumbnails", []))
    shots = _dict_rows(shots)
    diagnostics_path = ctx.output / "understanding_contract_diagnostics.json"
    write_json(diagnostics_path, {
        "schema_version": "1.0",
        "normalization_event_count": len(contract_diagnostics),
        "events": contract_diagnostics,
        "semantic_counts": {key: len(semantic.get(key, [])) for key in ("topics", "moments", "questions_answers", "program_sections")},
        "input_types": {
            "transcript_segments": type(transcript.get("segments")).__name__,
            "diarization_speakers": type(diarization.get("speakers")).__name__,
            "vision_people": type(vision.get("people")).__name__,
            "shots": type(shots).__name__,
        },
    })
    entities = extract_entities(transcript)
    qas = semantic["questions_answers"]
    participants = build_participants(transcript, diarization, vision,
                                      _dict_rows(active_data.get("mapping_summary", [])), qas, cfg, shots)
    participant_catalog = build_participants(transcript, diarization, vision,
                                      _dict_rows(active_data.get("mapping_summary", [])), qas, cfg, shots, include_background=True)
    story_arcs = build_story_arcs(transcript, semantic["topics"], qas)
    story_arcs, arc_diagnostics = _validate_story_arcs_contract(story_arcs, transcript['segments'])
    if arc_diagnostics:
        contract_diagnostics.extend(arc_diagnostics)
        contract_notes.append(f'story_arc_contract_normalized: {len(arc_diagnostics)} events')
    section_by_topic = {topic_id: section["section_id"] for section in semantic["program_sections"]
                        if isinstance(section.get("topic_ids"), list) and section.get("section_id")
                        for topic_id in section["topic_ids"]}
    for arc in story_arcs:
        arc["section_id"] = section_by_topic.get(arc.get("topic_id"))
    main_moments = build_main_moments(transcript, semantic["topics"], semantic["moments"],
                                      qas, story_arcs, shots, semantic.get("editorial_review"), cfg)
    for index, candidate in enumerate(main_moments):
        if candidate.get('duration_exception_proof_rejected'):
            contract_diagnostics.append(_contract_issue(
                f'main_moments[{index}].duration_exception_evidence',
                'ordered_source_segment_ids', candidate.get('duration_exception_evidence'),
                'duration_exception_revoked'))
    # Save contract facts only: never dump transcription/prompt bodies into logs.
    write_json(diagnostics_path, {
        'schema_version': '1.0',
        'normalization_event_count': len(contract_diagnostics),
        'events': contract_diagnostics,
        'semantic_counts': {key: len(semantic.get(key, [])) for key in
                            ('topics', 'moments', 'questions_answers', 'program_sections')},
        'input_types': {
            'transcript_segments': type(transcript.get('segments')).__name__,
            'diarization_speakers': type(diarization.get('speakers')).__name__,
            'vision_people': type(vision.get('people')).__name__,
            'shots': type(shots).__name__,
        },
        'story_arc_count': len(story_arcs),
        'candidate_count': len(main_moments),
    })
    for candidate in main_moments:
        candidate["program_section_id"] = section_by_topic.get(candidate.get("topic_id"))
    shortlist_rows, selection_report = select_editorial_shortlist(
        main_moments, cfg.get('max_moments', 12), cfg.get('min_editorial_score', .50),
        cfg.get('max_candidates_per_topic', 2))
    shortlist_ids = [row['moment_id'] for row in shortlist_rows]
    # Keep excluded primaries and dedup alternates addressable without adding
    # any of them to the shortlist. Priority uses the post-context evaluation.
    from .story_recovery import candidate_recovery_queue
    recovery_queue = candidate_recovery_queue(main_moments)
    candidate_metrics = {"candidates_before_dedup": len(semantic.get("moments", [])),
                         "candidates_after_dedup": len(main_moments),
                         "alternate_count": sum(len(candidate.get("alternates", [])) for candidate in main_moments),
                         "excluded_commercial_count": sum((candidate.get('commercial_classification') or {}).get('eligibility') == 'excluded' for candidate in main_moments),
                         "excluded_eligibility_count": sum(not candidate.get('default_shortlist_eligible', True) for candidate in main_moments),
                         "editorial_participant_count": len(participants),
                         "final_shortlist_count": len(shortlist_ids),
                         "selection_report": selection_report}
    candidate_metrics.update(complete_story_arc_count=sum(arc.get('kind') == 'complete_story' for arc in story_arcs),
                             partial_story_arc_count=sum(arc.get('kind') == 'partial_story' for arc in story_arcs),
                             discussion_block_count=sum(arc.get('kind') == 'discussion_segment' for arc in story_arcs),
                             qa_arc_count=sum(arc.get('kind') == 'qa_arc' for arc in story_arcs),
                                      story_payoff_coverage=sum(arc.get('payoff') is not None for arc in story_arcs if arc.get('kind') in {'complete_story', 'partial_story', 'anecdote'}) /
                                          max(1, sum(arc.get('kind') in {'complete_story', 'partial_story', 'anecdote'} for arc in story_arcs)),
                             duration_violation_count=sum(not candidate.get('duration_in_target_range', False) and not candidate.get('duration_exception') for candidate in main_moments))
    thumbnails = build_thumbnail_candidates(vision, shots, cfg.get("max_thumbnail_candidates", 80),
                    shortlist_rows)
    moment_frames = []
    try:
        moment_frames = extract_moment_frames(ctx, main_moments, thumbnails, cfg)
    except Exception as exc:
        ctx.logger.warning("Frames dos momentos: %s: %s", type(exc).__name__, exc)
    video_understanding = build_video_understanding(metadata, transcript, semantic["topics"],
                                                   participants, entities, story_arcs, main_moments, qas, shots)
    notes = ["Entidades são extraídas apenas de evidência textual; nomes não são inferidos por rosto.",
             "Story arcs e papéis host/guest são heurísticas conservadoras e permanecem needs_review.",
             *contract_notes]
    artifacts = []
    for row in moment_frames:
        for relative in (row.get("frames") or {}).values():
            artifacts.append(ctx.output / relative)
    return ok({"entities": entities, "participants": participants, "story_arcs": story_arcs,
               "participant_catalog": participant_catalog,
               "participant_metrics": dict(Counter(row["participant_category"] for row in participant_catalog)),
               "candidate_metrics": candidate_metrics,
               "editorial_shortlist": shortlist_ids, "candidate_recovery_queue": recovery_queue,
               "main_moments": main_moments, "thumbnail_candidates": thumbnails,
               "moment_frames": moment_frames, "video_understanding": video_understanding},
              "ok" if transcript.get("segments") else "partial", notes, [*artifacts, diagnostics_path])
