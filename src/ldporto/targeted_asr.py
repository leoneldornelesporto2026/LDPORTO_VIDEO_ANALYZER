"""Budgeted ASR alternatives prioritized by editorial evidence, with immutable raw words."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from importlib.metadata import version, PackageNotFoundError
import math
from .core import digest, file_hash, read_json, write_json
from .audio import ffmpeg_audio
from .transcription import TranscriptionEngine, alternative_evidence, word_text


def _candidate_range(candidate):
    start = candidate.get('ideal_start', candidate.get('start'))
    end = candidate.get('ideal_end', candidate.get('end'))
    if all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)
           for t in (start, end)) and 0 <= start < end:
        return start, end
    return float('inf'), float('-inf')


def select_repair_windows(words, candidates, arcs, questions, duration, max_regions=4, max_audio_seconds=60,
                          shortlist_ids=None, speech_overlaps=(), events=(), diagnostics=None,
                          bounded_to_candidates=False):
    options = []
    selected_ids = set(shortlist_ids) if shortlist_ids is not None else None
    if selected_ids == set():
        return []  # No editorial selection: avoid budget burn on unrelated words.
    for word in words:
        a, b = word.get('start'), word.get('end')
        if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t)
                   for t in (a, b)) or not 0 <= a < b <= duration:
            if diagnostics is not None and word.get('needs_review'):
                diagnostics.append({'word_id': word.get('word_id'), 'reason': 'invalid_word_range', 'status': 'pending'})
            continue
        if selected_ids is not None and not any(
            (c.get('moment_id') or c.get('candidate_id')) in selected_ids and
            _candidate_range(c)[0] <= word.get('start', -1) < _candidate_range(c)[1]
            for c in candidates):
            continue
        if not (word.get('needs_review') or word.get('timestamp_repaired') or
                word.get('speech_overlap') or word.get('timestamp_suspect') or
                word.get('asr_discrepancy') or word.get('noise')):
            continue
        time = float(word['start'])
        priority, reason, refs = 1., 'LOW_CONFIDENCE_OR_TIMESTAMP', []
        for arc in arcs:
            payoff = arc.get('payoff') or {}
            if arc.get('kind', 'complete_story') == 'complete_story' and payoff.get('start') is not None and payoff['start'] - 2 <= time <= payoff['end'] + 2:
                priority, reason, refs = 5., 'STORY_PAYOFF', payoff.get('segment_ids', [])
        for row in candidates:
            start, end = _candidate_range(row)
            ident = row.get('moment_id') or row.get('candidate_id')
            if (selected_ids is not None and ident not in selected_ids) or (selected_ids is None and row.get('default_shortlist_eligible') is False) or not start <= time < end:
                continue
            score = float(row.get('editorial_score_final') or row.get('editorial_score') or 0)
            value = (4. if time < start + 8 else 2.) + score * .5
            if value > priority:
                priority, reason, refs = value, 'CANDIDATE_HOOK' if time < start + 8 else 'HIGH_VALUE_CANDIDATE', [ident]
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
            if ident not in selected_ids:
                continue
            start = candidate.get('ideal_start', candidate.get('start'))
            end = candidate.get('ideal_end', candidate.get('end'))
            if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (start, end)) or not 0 <= start < end <= duration:
                if diagnostics is not None:
                    diagnostics.append({'candidate_id': ident, 'reason': 'invalid_candidate_range', 'status': 'pending'})
                continue
            for location, why, priority in ((start, 'SHORTLIST_HOOK', 6.8), (end, 'SHORTLIST_PAYOFF', 7.0)):
                a, b = max(0., location-2), min(duration, location+2)
                if a < b:
                    options.append({'start': a, 'end': b, 'priority': priority,
                                    'priority_reason': why, 'evidence_refs': [ident], 'word_ids': []})
            for question in questions:
                a, b = question.get('question_start', question.get('start')), question.get('question_end', question.get('end'))
                if not all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in (a, b)) or not a < b:
                    continue
                if start < b and a < end:
                    options.append({'start': max(start, a - 1), 'end': min(end, b + 1),
                                    'priority': 6.9, 'priority_reason': 'SHORTLIST_QUESTION',
                                    'evidence_refs': [ident, question.get('question_id')], 'word_ids': []})
        # Diarization overlap is worth reviewing where the selected cut lives;
        # absence of a usable overlap model does not mean no cross-talk.
        for region in speech_overlaps:
            a, b = region.get('start'), region.get('end')
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or a >= b:
                continue
            refs = [c.get('moment_id') or c.get('candidate_id') for c in candidates
                    if (c.get('moment_id') or c.get('candidate_id')) in selected_ids
                    and _candidate_range(c)[0] < b and a < _candidate_range(c)[1]]
            if refs:
                options.append({'start': max(0., a-1), 'end': min(duration, b+1),
                                'priority': 6.0, 'priority_reason': 'OVERLAPPING_SPEECH',
                                'evidence_refs': refs, 'word_ids': []})
    if bounded_to_candidates:
        for event in events:
            a, b = event.get('start'), event.get('end')
            if (event.get('kind') not in {'noise', 'asr_discrepancy'} or not all(isinstance(t, (int, float)) and
                    not isinstance(t, bool) and math.isfinite(t) for t in (a, b)) or not 0 <= a < b <= duration):
                continue
            options.append({'start': a, 'end': b, 'priority': 6.,
                            'priority_reason': 'NOISE_REVIEW' if event['kind'] == 'noise' else 'ASR_DISCREPANCY',
                            'evidence_refs': [], 'word_ids': []})
        bounded = []
        for row in options:
            for candidate in candidates:
                ident = candidate.get('moment_id') or candidate.get('candidate_id')
                a, b = _candidate_range(candidate)
                if ident not in (selected_ids or set()) or not 0 <= a < b <= duration:
                    continue
                start, end = max(a, row['start']), min(b, row['end'])
                if start < end:
                    bounded.append({**row, 'start': start, 'end': end,
                                    'candidate_id': ident,
                                    'evidence_refs': list(dict.fromkeys([ident] + row['evidence_refs']))})
        options = bounded
    selected, audio_seconds = [], 0.
    for row in sorted(options, key=lambda r: (-r['priority'], r['start'])):
        if row['end'] <= row['start']:
            continue
        # Editorial regions retain their own evidence even when they overlap.
        if not row['priority_reason'].startswith('SHORTLIST_') and any(r['end'] > row['start'] and r['start'] < row['end'] for r in selected):
            if diagnostics is not None:
                diagnostics.append({**row, 'reason': 'overlap_with_planned_region', 'status': 'pending'})
            continue
        cost = row['end'] - row['start']
        if len(selected) >= max_regions or audio_seconds + cost > max_audio_seconds:
            if diagnostics is not None:
                diagnostics.append({**row, 'reason': 'region_budget' if len(selected) >= max_regions else 'audio_seconds_budget', 'status': 'pending'})
            continue
        selected.append(row)
        audio_seconds += cost
    return selected


def run_targeted_repair(ctx, audio, transcript, candidates, arcs, questions, duration, recognize=None,
                        shortlist_ids=None, speech_overlaps=(), events=(), bounded_to_candidates=False,
                        expected_source_sha256=None):
    cfg = ctx.config['transcription']
    selected_ids = list(dict.fromkeys(shortlist_ids or []))
    deferred = []
    windows = select_repair_windows(transcript.get('words', []), candidates, arcs, questions, duration,
                                   cfg.get('targeted_max_regions', 4), cfg.get('targeted_max_audio_seconds', 60),
                                   shortlist_ids=shortlist_ids, speech_overlaps=speech_overlaps, events=events,
                                   diagnostics=deferred, bounded_to_candidates=bounded_to_candidates)
    known = {c.get('moment_id') or c.get('candidate_id') for c in candidates}
    deferred.extend({'candidate_id': ident, 'reason': 'selected_candidate_missing', 'status': 'pending'}
                    for ident in selected_ids if ident not in known)
    base = {'selected_candidate_count': len(selected_ids), 'selected_candidate_ids': selected_ids,
            'selection_source': 'final_editorial_shortlist' if shortlist_ids is not None else 'legacy_uncertain_words',
            'windows': windows, 'unprocessed_regions': deferred,
            'original_audio_verified': False, 'raw_replacement_count': 0,
            'publication_ready': False, 'scope': 'candidate_windows'}
    def pending(reason):
        return {**base, 'status': 'pending', 'pending_reason': reason, 'alternatives': [], 'cache_hits': 0,
                'audio_seconds': 0, 'candidate_coverage': dict.fromkeys(selected_ids, 0),
                'unreviewed_selected_candidates': selected_ids,
                'unprocessed_regions': deferred + [{**w, 'reason': reason, 'status': 'pending'} for w in windows]}
    if not cfg.get('targeted_repair_enabled', True) or cfg.get('import_file'):
        return pending('targeted_repair_disabled_or_imported') if selected_ids else {**base, 'status': 'skipped', 'alternatives': [], 'cache_hits': 0}
    if not windows:
        if selected_ids or deferred:
            return pending('no_regions_processed')
        return {**base, 'status': 'no_repair_needed', 'alternatives': [], 'cache_hits': 0,
                'candidate_coverage': {}}
    engine = None
    results, hits, new_seconds = [], 0, 0.
    try:
        source = (audio or {}).get('mono')
        if not source or not Path(source).is_file():
            return pending('original_audio_unavailable')
        audio_hash = file_hash(source)
        if expected_source_sha256 is not None and audio_hash != expected_source_sha256:
            return pending('source_sha256_mismatch')
    except OSError:
        return pending('original_audio_unreadable')
    try:
        try:
            backend_version = version('faster-whisper')
        except PackageNotFoundError:
            backend_version = None
        for row in windows:
            key = digest({'contract': 'targeted_asr_v1', 'audio': audio_hash, 'window': row,
                          'language': ctx.config['language'], 'settings': cfg,
                          'runtime': {k: ctx.config.get(k) for k in ('device', 'compute_type')},
                          'backend_version': backend_version, 'canonical': digest(transcript),
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
            try:
                ffmpeg_audio(audio['mono'], wav, start=row['start'], duration=row['end'] - row['start'])
            except (OSError, RuntimeError) as exc:
                wav.unlink(missing_ok=True)
                deferred.append({**row, 'reason': 'audio_extraction_unavailable',
                                 'error_type': type(exc).__name__, 'status': 'pending'})
                continue
            try:
                new_seconds += row['end'] - row['start']
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
            result = {**row, 'provenance': {'audio_sha256': audio_hash, 'cache_key': key,
                      'selection_source': base['selection_source'], 'independent_audio_verification': False},
                      'audio_source': 'original_mono', 'selected_source': 'canonical_raw_preserved',
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
        r['start'] < _candidate_range(c)[1] and
        r['end'] > _candidate_range(c)[0]
        for c in candidates if (c.get('moment_id') or c.get('candidate_id')) == ident))
        for ident in (shortlist_ids or [])}
    return {**base, 'status': ('partial_pending' if results else 'pending') if deferred else 'alternatives_for_review', 'alternatives': results, 'cache_hits': hits, 'windows': windows,
            'new_asr_audio_seconds': new_seconds,
            'audio_seconds': sum(r['end'] - r['start'] for r in results), 'scope': 'candidate_windows',
            'candidate_coverage': coverage, 'unreviewed_selected_candidates': [k for k, v in coverage.items() if not v],
            'original_audio_verified': False, 'raw_replacement_count': 0}


def on_demand_source_fingerprint(config, audio):
    """Outer step cache must also invalidate when the queued source bytes change."""
    if config['transcription'].get('targeted_review_opt_in') is not True:
        return None
    source = (audio or {}).get('mono')
    try:
        return file_hash(source) if source and Path(source).is_file() else None
    except OSError:
        return None


def run_on_demand_review(ctx, audio, transcript, candidates, arcs, questions, duration,
                         recognize=None, speech_overlaps=(), events=()):
    """Production entry: explicit human queue, opt-in and expected source SHA256.

    The legacy repair API remains available for existing offline integrations.
    Source integrity is distinct from listening; no hypothesis grants approval.
    """
    cfg = ctx.config['transcription']
    ids = list(dict.fromkeys(cfg.get('targeted_review_candidate_ids', [])))
    prior = transcript.get('transcription_alternatives', [])
    review_events = list(events)
    for row in prior:
        if any(alt.get('text') is not None and row.get('selected_text') is not None and
               alt['text'] != row['selected_text'] for alt in row.get('alternatives', [])):
            review_events.append({'kind': 'asr_discrepancy', 'start': row.get('start'), 'end': row.get('end')})
    deferred = []
    windows = select_repair_windows(transcript.get('words', []), candidates, arcs, questions, duration,
        cfg.get('targeted_max_regions', 4), cfg.get('targeted_max_audio_seconds', 60),
        shortlist_ids=ids, speech_overlaps=speech_overlaps, events=review_events,
        diagnostics=deferred, bounded_to_candidates=True)
    expected = cfg.get('targeted_source_sha256')
    source = (audio or {}).get('mono')
    actual, reason = None, None
    if not ids:
        reason = 'human_review_queue_empty'
    elif cfg.get('targeted_review_opt_in') is not True:
        reason = 'targeted_review_not_requested'
    elif not cfg.get('targeted_repair_enabled', True) or cfg.get('import_file'):
        reason = 'targeted_repair_disabled_or_imported'
    elif not isinstance(expected, str) or len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
        reason = 'expected_source_sha256_required'
    else:
        try:
            actual = file_hash(source) if source and Path(source).is_file() else None
            reason = 'source_sha256_mismatch' if actual and actual != expected else (
                'original_audio_unavailable' if actual is None else None)
        except OSError:
            reason = 'original_audio_unreadable'
    if reason:
        report = {'status': 'pending', 'pending_reason': reason, 'windows': windows,
                  'alternatives': [], 'cache_hits': 0, 'audio_seconds': 0,
                  'unprocessed_regions': deferred + [{**w, 'reason': reason, 'status': 'pending'} for w in windows],
                  'candidate_coverage': dict.fromkeys(ids, 0), 'unreviewed_selected_candidates': ids}
    else:
        report = run_targeted_repair(ctx, audio, transcript, candidates, arcs, questions, duration,
            recognize=recognize, shortlist_ids=ids, speech_overlaps=speech_overlaps,
            events=review_events, bounded_to_candidates=True, expected_source_sha256=expected)
    report.update({'selection_source': 'explicit_human_review_queue', 'selected_candidate_ids': ids,
                   'selected_candidate_count': len(ids), 'source_sha256_validated': actual is not None and actual == expected
                   and report.get('pending_reason') != 'source_sha256_mismatch',
                   'original_audio_verified': False, 'raw_replacement_count': 0,
                   'publication_ready': False, 'subtitle_publish_ready': False})
    rows = []
    for window in report['windows']:
        original = deepcopy([w for w in transcript.get('words', [])
                             if isinstance(w.get('start'), (int, float)) and
                             isinstance(w.get('end'), (int, float)) and
                             w['start'] < window['end'] and w['end'] > window['start']])
        alternatives = deepcopy([r for r in report['alternatives']
                                 if r['start'] == window['start'] and r['end'] == window['end']])
        preserved = deepcopy([r for r in prior if all(isinstance(r.get(k), (int, float))
            and not isinstance(r.get(k), bool) and math.isfinite(r[k]) for k in ('start', 'end'))
            and r['start'] < window['end'] and r['end'] > window['start']])
        evidence = {'interval': {'start': window['start'], 'end': window['end']},
                    'candidate_id': window['candidate_id'], 'audio_path': str(source) if source else None,
                    'audio_sha256': actual, 'expected_audio_sha256': expected,
                    'ORIGINAL': original, 'alternatives': alternatives, 'prior_alternatives': preserved}
        reasons = sorted(set([window['priority_reason']] + [flag for w in original for flag in
            ('needs_review', 'speech_overlap', 'timestamp_suspect', 'timestamp_repaired', 'asr_discrepancy', 'noise') if w.get(flag)]))
        rows.append({**evidence, 'review_sha256': digest(evidence), 'reasons': reasons,
                     'needs_review': True, 'verified_by_audio': None, 'correction_approved': False,
                     'subtitle_publish_ready': False, 'reviewer': None, 'corrected_text': None})
    lengths = sorted(w['end'] - w['start'] for w in report['windows'])
    metrics = {}
    for ident in ids:
        candidate = next((c for c in candidates if (c.get('moment_id') or c.get('candidate_id')) == ident), {})
        a, b = _candidate_range(candidate)
        words = [w for w in transcript.get('words', []) if a <= w.get('start', -1) < b]
        flagged = sum(bool(w.get('needs_review')) for w in words)
        metrics[ident] = {'word_count': len(words), 'flagged_word_count': flagged,
                          'flagged_fraction': flagged / len(words) if words else None,
                          'incorrect_word_fraction': None,
                          'planned_window_count': sum(r['candidate_id'] == ident for r in rows),
                          'reason_counts': dict(Counter(reason for r in rows if r['candidate_id'] == ident for reason in r['reasons']))}
    report['manual_review'] = {'schema_version': '49.1', 'selection_source': 'explicit_human_review_queue',
        'windows': rows, 'candidate_metrics': metrics, 'flag_rate_is_error_rate': False,
        'budget': {'max_regions': cfg.get('targeted_max_regions', 4),
                   'max_audio_seconds': cfg.get('targeted_max_audio_seconds', 60),
                   'planned_audio_seconds': sum(lengths),
                   'window_seconds_p95': lengths[math.ceil(.95 * len(lengths)) - 1] if lengths else None,
                   'asr_calls': len(report['alternatives']) - report['cache_hits'],
                   'new_asr_audio_seconds': report.get('new_asr_audio_seconds', 0)},
        'publication_ready': False}
    reason_durations = {}
    for row in rows:
        for reason in row['reasons']:
            reason_durations.setdefault(reason, []).append(row['interval']['end'] - row['interval']['start'])
    report['manual_review']['reason_window_seconds_p95'] = {
        reason: sorted(values)[math.ceil(.95 * len(values)) - 1] for reason, values in reason_durations.items()}
    return report
