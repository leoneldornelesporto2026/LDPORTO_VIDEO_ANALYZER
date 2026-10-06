# V4.3 Architecture

The V4.3 pipeline keeps the existing staged architecture and adds stronger contracts between perception, editorial understanding and camera decisions:

`source -> metadata/audio -> ASR -> diarization -> visual perception/tracking -> Re-ID -> speaker-person affinity -> active speaker -> semantic understanding -> editorial structure -> candidate/commercial gate/ranking -> global camera planner -> Camera Director + Smart Zoom -> preview verifier -> second-curation handoff`

Key invariants:

- Missing evidence stays null/unresolved rather than being fabricated.
- Raw detections/tracklets are not editorial participants.
- Speaker-person mapping is global evidence aggregation, not a face-only guess.
- Camera/zoom is downstream-only and falls back to source framing when safety or identity evidence is insufficient.
- LLM outputs select grounded refs where possible; invalid items are repaired locally rather than discarding valid work.
- Expensive upstream stages are fingerprinted and replayable; camera/GUI changes do not invalidate ASR/vision/semantic artifacts.
- `SECOND_CURATION_READY/PARTIAL` is a versioned downstream API artifact, not a dump of the entire analysis folder.
