"""Session 7: evidence-only, per-clip subtitle review and word-alignment gates.

ASR probability is NOT an accuracy metric. Nothing here edits recognized words or
converts alternate ASR hypotheses into 'verified' captions.
"""
from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path
import re

from .timeline import captions


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _interval(row):
    a, b = row.get('start'), row.get('end')
    return (_number(a) and _number(b) and 0 <= a < b)


def _hit(a, b, c, d):
    return max(0., min(b, d) - max(a, c))


def _candidate_id(row):
    return row.get('moment_id') or row.get('candidate_id')


def _word_issues(word, threshold=.60):
    problems = []
    prob = word.get('confidence')
    if prob is None or not _number(prob) or prob < threshold or word.get('needs_review'):
        problems.append('asr_text_uncertain')
    if not _interval(word) or word.get('timestamp_repaired') or word.get('timestamp_suspect'):
        problems.append('word_timestamp_unreliable')
    if word.get('speech_overlap'):
        problems.append('overlapping_speech')
    if word.get('suspected_hallucination'):
        problems.append('suspected_hallucination')
    if re.search(r'[-—–…]$', str(word.get('word') or '').strip()):
        problems.append('interrupted_or_incomplete_word')
    return list(dict.fromkeys(problems))


def _strip_timing(word):
    """Expose minimal source evidence without inventing phonemes, text, or timing."""
    return {key: word.get(key) for key in ('word_id', 'word', 'raw', 'start', 'end', 'speaker',
                                         'confidence', 'needs_review', 'speech_overlap',
                                         'timestamp_repaired', 'alignment_verified', 'audio_verified')}


def _srt_stamp(seconds):
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(milliseconds, 3600000)
    minutes, rem = divmod(rem, 60000)
    secs, milli = divmod(rem, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02},{milli:03}'


def _wrap_caption(text, max_chars=38):
    words = str(text).split()
    lines, current = [], ''
    for word in words:
        if current and len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = (current + ' ' + word).strip()
    if current:
        lines.append(current)
    return '\n'.join(lines)


def _event_is_laughter(event):
    return str(event.get('type') or event.get('category') or '').lower() in ('laughter', 'laugh', 'risada')


def review_selected_clips(words, candidates, selected_ids=None, *, alternatives=(),
                          events=(), caption_config=None, threshold=.60):
    """Review selected editorial ranges. Not a publication/accuracy approval.

    selected_ids=None means all explicitly eligible candidates. Passing an empty
    list means no selection (NOT every candidate).
    """
    cfg = caption_config or {'max_words': 5, 'max_chars': 38, 'max_seconds': 2.8,
                             'max_gap_seconds': .45, 'uppercase_display': False}
    requested = set(selected_ids) if selected_ids is not None else None
    chosen = [row for row in candidates if _candidate_id(row) and _interval(row) and
              row.get('default_shortlist_eligible') is not False and
              ((requested is not None and _candidate_id(row) in requested) or
               (requested is None and row.get('default_shortlist_eligible') is True))]
    by_id, global_reasons = {}, Counter()
    for candidate in chosen:
        ident = _candidate_id(candidate)
        start, end = float(candidate.get('ideal_start', candidate['start'])), float(candidate.get('ideal_end', candidate['end']))
        if not (0 <= start < end):
            continue
        inside = [w for w in words if _interval(w) and start <= (w['start'] + w['end']) / 2 < end]
        segments = captions(inside, cfg) if inside else []
        clip_alternatives = []
        for row in alternatives:
            if _interval(row) and _hit(start, end, row['start'], row['end']) > 0:
                # Preserve original and alternate hypotheses as evidence, not verdicts.
                clip_alternatives.append({'start': row['start'], 'end': row['end'],
                                          'priority_reason': row.get('priority_reason'),
                                          'selected_text': row.get('selected_text'),
                                          'alternatives': [{'source': alt.get('source'), 'text': alt.get('text'),
                                                            'comparison': alt.get('comparison')}
                                                           for alt in row.get('alternatives', [])],
                                          'replacement_applied': False,
                                          'needs_human_review': True})
        laugh_rows = [e for e in events if isinstance(e, dict) and _interval(e) and
                      _event_is_laughter(e) and _hit(start, end, e['start'], e['end']) > 0]
        reviewed_captions = []
        reasons = Counter()
        for caption in segments:
            member = [w for w in inside if _interval(w) and
                      caption['start'] <= (w['start'] + w['end']) / 2 <= caption['end']]
            word_issues = [_word_issues(w, threshold) for w in member]
            issues = sorted({reason for flags in word_issues for reason in flags})
            if len(_wrap_caption(caption['text'], cfg.get('max_chars', 38)).splitlines()) > 2:
                issues.append('caption_exceeds_two_lines')
            if any(_hit(caption['start'], caption['end'], e['start'], e['end']) > 0 for e in laugh_rows):
                issues.append('laughter_near_speech_review_audio')
            if any(_hit(caption['start'], caption['end'], alt['start'], alt['end']) > 0
                   for alt in clip_alternatives):
                issues.append('alternate_asr_requires_listening')
            boundary = member and (member[0]['start'] < start or member[-1]['end'] > end)
            if boundary:
                issues.append('cut_splits_word')
            # Word timings from the model are estimates, never automatically verified.
            aligned = bool(member) and all(w.get('alignment_verified') is True and not flags
                                           for w, flags in zip(member, word_issues))
            if not aligned:
                issues.append('word_alignment_not_verified')
            issues = sorted(set(issues))
            reasons.update(issues)
            reviewed_captions.append({
                'caption_id': f'{ident}_{caption["caption_id"]}',
                'start': caption['start'], 'end': caption['end'],
                'asr_text': caption['text'], 'suggested_display_text': caption['text'],
                'words': [_strip_timing(w) for w in member],
                'issue_codes': issues, 'word_karaoke_eligible': bool(aligned),
                'human_audio_verified': bool(member) and all(w.get('audio_verified') is True for w in member), 'final_text': None,
                'status': 'LISTEN_AND_REVIEW', 'audio_source_to_check': 'original_mono',
            })
        if not inside:
            reasons['no_words_in_candidate'] += 1
        if laugh_rows:
            reasons['laughter_window_not_exact_timestamp'] += 1
        if inside and (inside[0]['start'] > start + .8 or inside[-1]['end'] < end - .8):
            reasons['speech_coverage_gap_review_context'] += 1
        # Hard default: model alignment alone does not justify word-by-word animation.
        karaoke = bool(reviewed_captions) and all(row['word_karaoke_eligible'] for row in reviewed_captions)
        by_id[ident] = {
            'candidate_id': ident, 'start': start, 'end': end,
            'word_count': len(inside), 'captions': reviewed_captions,
            'low_confidence_word_count': sum(bool(_word_issues(w, threshold)) for w in inside),
            'word_review_fraction': (sum(bool(_word_issues(w, threshold)) for w in inside) / len(inside)) if inside else None,
            'issue_counts': dict(reasons), 'laughter_windows': laugh_rows,
            'asr_alternatives': clip_alternatives,
            'karaoke_allowed': karaoke and all(w.get('audio_verified') is True for w in inside),
            'word_alignment_verified': karaoke,
            'effective_caption_mode': 'word_karaoke' if karaoke and all(w.get('audio_verified') is True for w in inside) else 'phrase_subtitles',
            'approval_state': 'HUMAN_AUDIO_REVIEW_REQUIRED',
            'audio_verified': False, 'publication_ready': False,
        }
        global_reasons.update(reasons)
    base = list(words)
    suspect = [w for w in base if _word_issues(w, threshold)]
    originally_flagged = [w for w in base if w.get('needs_review')]
    return {'schema_version': 's7.1', 'analysis_scope': 'selected_editorial_ranges',
            'asr_probability_is_accuracy': False, 'audio_verification_performed': False,
            'selected_candidate_count': len(by_id),
            'total_words': len(base), 'originally_flagged_for_review': len(originally_flagged),
            'original_review_fraction': (len(originally_flagged)/len(base)) if base else None,
            'words_flagged_for_review': len(suspect),
            'words_flagged_fraction': len(suspect) / len(base) if base else None,
            'global_word_reasons': dict(Counter(r for w in base for r in _word_issues(w, threshold))),
            'candidate_issue_counts': dict(global_reasons),
            'candidates': by_id, 'all_captions_require_final_audio_review': True,
            'notes': ['Neither original nor alternative ASR text is independently verified by this tool.',
                      'Laughter events may be coarse audio-window classifications, not exact laugh starts.',
                      'Slang, jokes and interrupted words must be checked by listening; do not infer missing words.']}


def write_review_kit(directory, report):
    """Create per-clip draft SRT and human-editable CSV, never approved subtitles."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'subtitle_review_s7.json').write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                   allow_nan=False), encoding='utf-8')
    rows = []
    for candidate_id, candidate in report.get('candidates', {}).items():
        # Stable filesystem name: no user-controlled path traversal.
        safe_id = re.sub(r'[^A-Za-z0-9_.-]', '_', candidate_id).strip('.')[:90] or 'candidate'
        blocks = []
        for index, cap in enumerate(candidate['captions'], 1):
            blocks.append(f'{index}\n{_srt_stamp(cap["start"])} --> {_srt_stamp(cap["end"])}\n'
                          + _wrap_caption(cap['asr_text']) + '\n')
            # Neutralize spreadsheet formula injection in untrusted transcript text.
            shown = str(cap['asr_text'])
            if shown.lstrip().startswith(('=', '+', '-', '@')):
                shown = "'" + shown
            rows.append({'candidate_id': candidate_id, 'caption_id': cap['caption_id'],
                         'start_asr': cap['start'], 'end_asr': cap['end'], 'asr_text': shown,
                         'issue_codes': '|'.join(cap['issue_codes']),
                         'verified_text': '', 'verified_start': '', 'verified_end': '',
                         'reviewer': '', 'audio_listened': 'NO', 'decision': 'PENDING'})
        (root / f'{safe_id}.draft.srt').write_text('\n'.join(blocks), encoding='utf-8')
    columns = ('candidate_id', 'caption_id', 'start_asr', 'end_asr', 'asr_text', 'issue_codes',
               'verified_text', 'verified_start', 'verified_end', 'reviewer', 'audio_listened', 'decision')
    with (root / 'subtitle_human_review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (root / 'LEIA_ANTES_DE_REVISAR.txt').write_text(
        'S7: .draft.srt NAO e legenda aprovada. Confira audio ORIGINAL de cada corte.\n'
        'Preencha CSV com texto ouvido, timestamps reais, audio_listened=YES, decision=APPROVED.\n'
        'Nao deduza palavras, girias ou punchlines por contexto. Karaoke exige verificacao de alinhamento palavra por palavra.\n'
        'CSV de revisao NAO altera automaticamente a transcricao original.\n', encoding='utf-8')
    return {'path': str(root), 'candidate_count': len(report.get('candidates', {})), 'caption_count': len(rows)}


def apply_human_subtitle_review(report_dir, review_csv, output_dir):
    """Export human-reviewed SRT only after every caption has signed audio review.

    This checks fields and geometry, not whether somebody truly heard the words.
    It NEVER overwrites the canonical transcript or auto-approves any row.
    """
    folder = Path(report_dir)
    report = json.loads((folder / 'subtitle_review_s7.json').read_text(encoding='utf-8'))
    with Path(review_csv).open('r', encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    entries = {}
    for row in rows:
        key = (row.get('candidate_id'), row.get('caption_id'))
        if key in entries:
            raise ValueError('Duplicate reviewed caption: ' + str(key))
        entries[key] = row
    expected = {(cid, cap['caption_id']) for cid, c in report['candidates'].items() for cap in c['captions']}
    if set(entries) != expected:
        raise ValueError('Review CSV missing captions or containing unknown IDs.')
    output = Path(output_dir)
    approved = []
    generated = {}
    for cid, candidate in report['candidates'].items():
        rows_srt, last_end = [], float('-inf')
        for i, cap in enumerate(candidate['captions'], 1):
            checked = entries[(cid, cap['caption_id'])]
            if (checked.get('decision', '').strip().upper() != 'APPROVED' or
                checked.get('audio_listened', '').strip().upper() != 'YES' or
                not checked.get('reviewer', '').strip()):
                raise ValueError(f'Unapproved or unlistened caption: {cid} / {cap["caption_id"]}')
            text = checked.get('verified_text', '').strip()
            if not text or len(text) > 400 or any(ord(c) < 32 and c not in '\n\t' for c in text):
                raise ValueError('Invalid verified_text: ' + cap['caption_id'])
            try:
                start, end = float(checked['verified_start']), float(checked['verified_end'])
            except (ValueError, KeyError, TypeError):
                raise ValueError('Verified timestamps required: ' + cap['caption_id']) from None
            if (not math.isfinite(start + end) or
                not candidate['start'] <= start < end <= candidate['end'] or start < last_end - 1e-6):
                raise ValueError('Reviewed timestamp outside clip or out of order: ' + cap['caption_id'])
            last_end = end
            if len(_wrap_caption(text).splitlines()) > 2:
                raise ValueError('Reviewed caption exceeds two readable lines: ' + cap['caption_id'])
            rows_srt.append(f'{i}\n{_srt_stamp(start)} --> {_srt_stamp(end)}\n{_wrap_caption(text)}\n')
        generated[cid] = '\n'.join(rows_srt)
        approved.append(cid)
    # Write only if EVERY caption in the submitted batch passes the validation.
    output.mkdir(parents=True, exist_ok=True)
    for cid, content in generated.items():
        safe = re.sub(r'[^A-Za-z0-9_.-]', '_', cid).strip('.')[:90] or 'candidate'
        (output / f'{safe}.human_reviewed.srt').write_text(content, encoding='utf-8')
    (output / 'REVIEW_PROVENANCE.json').write_text(json.dumps({
        'schema_version': 's7.1', 'status': 'HUMAN_REVIEW_FIELDS_COMPLETE',
        'content_source': 'reviewer_supplied_csv_not_autonomous_ASR',
        'audio_listening': 'reviewer_self_attested_NOT_independently_verified',
        'word_karaoke_approved': False, 'video_render_checked': False,
        'candidate_ids': approved}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'candidate_count': len(approved), 'output': str(output),
            'status': 'HUMAN_REVIEW_FIELDS_COMPLETE', 'publication_ready': False}
