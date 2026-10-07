"""Budgeted ASR alternatives prioritized by editorial evidence, with immutable raw words."""
from .core import digest, file_hash, read_json, write_json, ok
from .audio import ffmpeg_audio
from .transcription import TranscriptionEngine, alternative_evidence, word_text


def select_repair_windows(words, candidates, arcs, questions, duration, max_regions=4, max_audio_seconds=60):
    options = []
    for word in words:
        if not word.get('needs_review') and not word.get('timestamp_repaired'):
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


def run_targeted_repair(ctx, audio, transcript, candidates, arcs, questions, duration, recognize=None):
    cfg = ctx.config['transcription']
    if not cfg.get('targeted_repair_enabled', True) or cfg.get('import_file'):
        return {'status': 'skipped', 'alternatives': [], 'cache_hits': 0, 'scope': 'candidate_windows'}
    windows = select_repair_windows(transcript.get('words', []), candidates, arcs, questions, duration,
                                   cfg.get('targeted_max_regions', 4), cfg.get('targeted_max_audio_seconds', 60))
    if not windows:
        return {'status': 'no_repair_needed', 'alternatives': [], 'cache_hits': 0, 'scope': 'candidate_windows'}
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
                cached = read_json(record)
                if cached.get('key') == key and cached.get('checksum') == digest(cached['data']):
                    results.append(cached['data'])
                    hits += 1
                    continue
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
            result = {**row, 'selected_source': 'canonical_raw_preserved',
                      'selected_text': word_text([w for w in transcript.get('words', []) if row['start'] <= w['start'] < row['end']]),
                      'alternatives': [{'source': 'original_targeted', 'words': hypothesis['words'],
                                        'text': word_text(hypothesis['words']), 'comparison': alternative_evidence(hypothesis, row['start'], row['end'])}],
                      'replacement_applied': False, 'replacement_decision': 'human_audio_verification_required', 'needs_human_review': True}
            write_json(record, {'key': key, 'checksum': digest(result), 'data': result})
            results.append(result)
    finally:
        if engine:
            engine.model = None
    return {'status': 'alternatives_for_review', 'alternatives': results, 'cache_hits': hits, 'windows': windows,
            'audio_seconds': sum(r['end'] - r['start'] for r in windows), 'scope': 'candidate_windows', 'raw_replacement_count': 0}
