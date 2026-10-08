"""Budgeted ASR alternatives prioritized by editorial evidence, with immutable raw words."""
from .core import digest, file_hash, read_json, write_json, ok
from .audio import ffmpeg_audio
from .transcription import TranscriptionEngine, alternative_evidence, word_text


def select_repair_windows(words, candidates, arcs, questions, duration, max_regions=4, max_audio_seconds=60,
                          shortlist_ids=None, speech_overlaps=(), events=()):
    options = []
    selected_ids = set(shortlist_ids) if shortlist_ids is not None else None
    if selected_ids == set():
        return []  # No editorial selection: avoid budget burn on unrelated words.
    for word in words:
        if selected_ids is not None and not any(
            (c.get('moment_id') or c.get('candidate_id')) in selected_ids and
            c.get('start', float('inf')) <= word.get('start', -1) < c.get('end', float('-inf'))
            for c in candidates):
            continue
        if not (word.get('needs_review') or word.get('timestamp_repaired') or
                word.get('speech_overlap') or word.get('timestamp_suspect')):
            continue
        time = float(word['start'])
        priority, reason, refs = 1., 'LOW_CONFIDENCE_OR_TIMESTAMP', []
        for arc in arcs:
            payoff = arc.get('payoff') or {}
            if arc.get('kind', 'complete_story') == 'complete_story' and payoff.get('start') is not None and payoff['start'] - 2 <= time <= payoff['end'] + 2:
                priority, reason, refs = 5., 'STORY_PAYOFF', payoff.get('segment_ids', [])
        for row in candidates:
            start = row.get('ideal_start', row.get('start', 0))
            end = row.get('ideal_end', row.get('end', 0))
            if row.get('default_shortlist_eligible') is False or not start <= time < end:
                continue
            score = float(row.get('editorial_score_final') or row.get('editorial_score') or 0)
            value = (4. if time < start + 8 else 2.) + score * .5
            if value > priority:
                priority, reason, refs = value, 'CANDIDATE_HOOK' if time < start + 8 else 'HIGH_VALUE_CANDIDATE', [row['moment_id']]
        for row in questions:
            if row.get('answer_start') is not None and row['answer_start'] <= time <= (row.get('answer_end') or row['answer_start']) and priority < 3:
                priority, reason, refs = 3., 'QUESTION_ANSWER', [row.get('question_id')]
        options.append({'start': max(0., time - 2), 'end': min(duration, word['end'] + 2),
                        'priority': priority, 'priority_reason': reason, 'evidence_refs': refs, 'word_ids': [word.get('word_id')]})
    if selected_ids is not None:
        # Independently revisit actual SHORTLIST hooks and endings, even when
        # no model probability flagged the crucial punchline. These are still
        # hypotheses, NOT word corrections. Budget constrains GPU usage.
        for candidate in candidates:
            ident = candidate.get('moment_id') or candidate.get('candidate_id')
            if ident not in selected_ids or candidate.get('default_shortlist_eligible') is False:
                continue
            start = candidate.get('ideal_start', candidate.get('start'))
            end = candidate.get('ideal_end', candidate.get('end'))
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not 0 <= start < end <= duration + 1:
                continue
            for location, why, priority in ((start, 'SHORTLIST_HOOK', 6.8), (end, 'SHORTLIST_PAYOFF', 7.0)):
                a, b = max(0., location-2), min(duration, location+2)
                if a < b:
                    options.append({'start': a, 'end': b, 'priority': priority,
                                    'priority_reason': why, 'evidence_refs': [ident], 'word_ids': []})
        # Diarization overlap is worth reviewing where the selected cut lives;
        # absence of a usable overlap model does not mean no cross-talk.
        for region in speech_overlaps:
            a, b = region.get('start'), region.get('end')
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a >= b:
                continue
            refs = [c.get('moment_id') or c.get('candidate_id') for c in candidates
                    if (c.get('moment_id') or c.get('candidate_id')) in selected_ids
                    and c.get('start', float('inf')) < b and a < c.get('end', float('-inf'))]
            if refs:
                options.append({'start': max(0., a-1), 'end': min(duration, b+1),
                                'priority': 6.0, 'priority_reason': 'OVERLAPPING_SPEECH',
                                'evidence_refs': refs, 'word_ids': []})
    selected, audio_seconds = [], 0.
    for row in sorted(options, key=lambda r: (-r['priority'], r['start'])):
        if row['end'] <= row['start'] or any(r['end'] > row['start'] and r['start'] < row['end'] for r in selected):
            continue
        cost = row['end'] - row['start']
        if len(selected) >= max_regions or audio_seconds + cost > max_audio_seconds:
            continue
        selected.append(row)
        audio_seconds += cost
    return selected


def run_targeted_repair(ctx, audio, transcript, candidates, arcs, questions, duration, recognize=None,
                        shortlist_ids=None, speech_overlaps=(), events=()):
    cfg = ctx.config['transcription']
    if not cfg.get('targeted_repair_enabled', True) or cfg.get('import_file'):
        return {'status': 'skipped', 'alternatives': [], 'cache_hits': 0, 'scope': 'candidate_windows'}
    windows = select_repair_windows(transcript.get('words', []), candidates, arcs, questions, duration,
                                   cfg.get('targeted_max_regions', 4), cfg.get('targeted_max_audio_seconds', 60),
                                   shortlist_ids=shortlist_ids, speech_overlaps=speech_overlaps, events=events)
    if not windows:
        return {'status': 'no_repair_needed', 'alternatives': [], 'cache_hits': 0, 'scope': 'candidate_windows',
                'candidate_coverage': {ident: 0 for ident in (shortlist_ids or [])}}
    engine = None
    results, hits = [], 0
    audio_hash = file_hash(audio['mono'])
    try:
        for row in windows:
            key = digest({'contract': 'targeted_asr_v1', 'audio': audio_hash, 'window': row,
                          'language': ctx.config['language'], 'settings': {k: cfg.get(k) for k in ('model', 'beam_size', 'vad_filter', 'glossary')},
                          'code': file_hash(__file__)})
            record = ctx.cache / 'targeted_asr' / (key + '.json')
            if record.is_file() and not ctx.force:
                try:
                    cached = read_json(record)
                    if cached.get('key') == key and cached.get('checksum') == digest(cached['data']):
                        results.append(cached['data'])
                        hits += 1
                        continue
                except (OSError, ValueError, TypeError, KeyError):
                    pass  # Invalid cache must not silently become a verified hypothesis.

            wav = record.with_suffix('.wav')
            ffmpeg_audio(audio['mono'], wav, start=row['start'], duration=row['end'] - row['start'])
            try:
                if recognize is None:
                    if engine is None:
                        semantic = ctx.config.get('semantic_analysis', {})
                        if semantic.get('backend') == 'ollama' and ctx.config.get('device') != 'cpu':
                            from urllib.parse import urlparse
                            from .ollama_local import _request_json
                            url = semantic.get('ollama_url', 'http://localhost:11434')
                            if urlparse(url).hostname in {'localhost', '127.0.0.1', '::1'}:
                                _request_json(url, '/api/generate', payload={'model': semantic['model'],
                                              'prompt': '', 'stream': False, 'keep_alive': 0}, timeout=30)
                        engine = TranscriptionEngine(ctx)
                        engine._load()
                    hypothesis = engine.recognize(wav, row['start'])
                else:
                    hypothesis = recognize(wav, row['start'])
            finally:
                wav.unlink(missing_ok=True)
            result = {**row, 'audio_source': 'original_mono', 'selected_source': 'canonical_raw_preserved',
                      'selected_text': word_text([w for w in transcript.get('words', []) if row['start'] <= w['start'] < row['end']]),
                      'alternatives': [{'source': 'original_targeted', 'words': hypothesis['words'],
                                        'text': word_text(hypothesis['words']), 'comparison': alternative_evidence(hypothesis, row['start'], row['end'])}],
                      'replacement_applied': False, 'replacement_decision': 'human_audio_verification_required', 'needs_human_review': True}
            write_json(record, {'key': key, 'checksum': digest(result), 'data': result})
            results.append(result)
    finally:
        if engine:
            engine.model = None
    coverage = {ident: sum(1 for r in results if any(
        r['start'] < c.get('ideal_end', c.get('end', 0)) and
        r['end'] > c.get('ideal_start', c.get('start', 0))
        for c in candidates if (c.get('moment_id') or c.get('candidate_id')) == ident))
        for ident in (shortlist_ids or [])}
    return {'status': 'alternatives_for_review', 'alternatives': results, 'cache_hits': hits, 'windows': windows,
            'audio_seconds': sum(r['end'] - r['start'] for r in windows), 'scope': 'candidate_windows',
            'candidate_coverage': coverage, 'unreviewed_selected_candidates': [k for k, v in coverage.items() if not v],
            'original_audio_verified': False, 'raw_replacement_count': 0}

