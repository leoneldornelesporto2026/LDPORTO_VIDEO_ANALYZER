"""Session 7: evidence-only, per-clip subtitle review and word-alignment gates.

ASR probability is NOT an accuracy metric. Nothing here edits recognized words or
converts alternate ASR hypotheses into 'verified' captions.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
import math
from pathlib import Path
import re

from .timeline import captions
from .subtitle_style import wrap_text, checked_text


CRITICAL_ISSUES = {'cut_splits_word', 'interrupted_or_incomplete_word',
                   'overlapping_speech', 'multiple_voices_overlap', 'caption_overlap',
                   'caption_duration_too_short', 'caption_duration_too_long',
                   'caption_temporal_drift', 'word_timestamp_unreliable',
                   'suspected_hallucination', 'alternate_asr_requires_listening',
                   'phrase_boundary_requires_listening'}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe_id(ident):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', ident).strip('.')[:90] or 'candidate'


def _diagnose_caption(start, end, previous_end=None, *, reference=None,
                      min_seconds=.4, max_seconds=2.8, drift_seconds=.25):
    issues = []
    if end - start < min_seconds:
        issues.append('caption_duration_too_short')
    if end - start > max_seconds:
        issues.append('caption_duration_too_long')
    if previous_end is not None and start < previous_end - 1e-6:
        issues.append('caption_overlap')
    if reference and max(abs(start-reference[0]), abs(end-reference[1])) > drift_seconds:
        issues.append('caption_temporal_drift')
    return issues


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
    return wrap_text(text, max_chars)


def clip_karaoke_gate(review, candidate):
    """Require current cut bounds and actual reviewed word evidence, not a boolean."""
    if not isinstance(review, dict) or review.get('karaoke_allowed') is not True:
        return False
    ident = _candidate_id(candidate)
    start, end = candidate.get('ideal_start', candidate.get('start')), candidate.get('ideal_end', candidate.get('end'))
    if review.get('candidate_id') != ident or (review.get('start'), review.get('end')) != (start, end):
        return False
    if not _interval({'start': start, 'end': end}) or not review.get('captions'):
        return False
    last_end = start
    count = 0
    for caption in review['captions']:
        if not isinstance(caption, dict) or set(caption.get('issue_codes') or []) & CRITICAL_ISSUES:
            return False
        words = caption.get('words') or []
        if not words or caption.get('word_karaoke_eligible') is not True or caption.get('human_audio_verified') is not True:
            return False
        for word in words:
            if (not isinstance(word, dict) or not _interval(word) or not str(word.get('word') or '').strip()
                    or word['start'] < last_end or word['end'] > end
                    or word.get('alignment_verified') is not True or word.get('audio_verified') is not True
                    or _word_issues(word)):
                return False
            last_end = word['end']
            count += 1
        if ((caption.get('start'), caption.get('end')) != (words[0]['start'], words[-1]['end'])
                or ' '.join(str(w['word']).strip() for w in words) != ' '.join(str(caption.get('asr_text') or '').split())
                or caption.get('final_text') not in (None, caption.get('asr_text'))):
            return False
    return count == review.get('word_count')


def _event_is_laughter(event):
    return str(event.get('type') or event.get('category') or '').lower() in ('laughter', 'laugh', 'risada')


def review_selected_clips(words, candidates, selected_ids=None, *, alternatives=(),
                          events=(), caption_config=None, threshold=.60, targeted_report=None):
    """Review selected editorial ranges. Not a publication/accuracy approval.

    selected_ids=None means all explicitly eligible candidates. Passing an empty
    list means no selection (NOT every candidate).
    """
    cfg = caption_config or {'max_words': 5, 'max_chars': 38, 'max_seconds': 2.8,
                             'max_gap_seconds': .45, 'uppercase_display': False}
    requested = set(selected_ids) if selected_ids is not None else None
    chosen = [row for row in candidates if _candidate_id(row) and
              ((requested is not None and _candidate_id(row) in requested) or
               (requested is None and row.get('default_shortlist_eligible') is True))]
    by_id, global_reasons, unresolved = {}, Counter(), {}
    if requested is not None:
        unresolved = {ident: 'selected_candidate_missing' for ident in sorted(requested)
                      if not any(_candidate_id(c) == ident for c in chosen)}
    for candidate in chosen:
        ident = _candidate_id(candidate)
        start, end = candidate.get('ideal_start', candidate.get('start')), candidate.get('ideal_end', candidate.get('end'))
        if not _interval({'start': start, 'end': end}):
            unresolved[ident] = 'invalid_candidate_range'
            continue
        inside = sorted([w for w in words if _interval(w) and
                         _hit(start, end, w['start'], w['end']) > 0], key=lambda w: w['start'])
        segments = captions(inside, cfg) if inside else []
        clip_alternatives = []
        for row in alternatives:
            if _interval(row) and _hit(start, end, row['start'], row['end']) > 0:
                # Preserve original and alternate hypotheses as evidence, not verdicts.
                clip_alternatives.append({'start': row['start'], 'end': row['end'],
                                          'priority_reason': row.get('priority_reason'),
                                          'evidence_refs': deepcopy(row.get('evidence_refs', [])),
                                          'word_ids': deepcopy(row.get('word_ids', [])),
                                          'audio_source': row.get('audio_source'),
                                          'selected_source': row.get('selected_source'),
                                          'provenance': deepcopy(row.get('provenance')),
                                          'selected_text': row.get('selected_text'),
                                          'alternatives': deepcopy(row.get('alternatives', [])),
                                          'replacement_applied': False,
                                          'needs_human_review': True})
        laugh_rows = [e for e in events if isinstance(e, dict) and _interval(e) and
                      _event_is_laughter(e) and _hit(start, end, e['start'], e['end']) > 0]
        reviewed_captions = []
        reasons = Counter()
        last_end = None
        # Only flag a possible broken phrase when source context exists across
        # the cut. Missing punctuation alone is not proof of an incomplete phrase.
        context_gap = cfg.get('max_gap_seconds', .45)
        preceding = [w for w in words if _interval(w) and w['end'] <= start
                     and inside and 0 <= inside[0]['start']-w['end'] <= context_gap]
        following = [w for w in words if _interval(w) and w['start'] >= end
                     and inside and 0 <= w['start']-max(x['end'] for x in inside) <= context_gap]
        for caption in segments:
            member = [next(w for w in inside if all(w.get(k) == item.get(k)
                      for k in ('word', 'start', 'end', 'speaker'))) for item in caption['words']]
            word_issues = [_word_issues(w, threshold) for w in member]
            issues = sorted({reason for flags in word_issues for reason in flags})
            issues.extend(_diagnose_caption(caption['start'], caption['end'], last_end,
                                            min_seconds=cfg.get('min_seconds', .4),
                                            max_seconds=cfg.get('max_seconds', 2.8)))
            last_end = max(last_end or 0, caption['end'])
            if any(a.get('speaker') is not None and b.get('speaker') is not None and
                   a['speaker'] != b['speaker'] and _hit(a['start'], a['end'], b['start'], b['end']) > 0
                   for a in member for b in inside):
                issues.append('multiple_voices_overlap')
            if len(_wrap_caption(caption['text'], cfg.get('max_chars', 38)).splitlines()) > 2:
                issues.append('caption_exceeds_two_lines')
            if any(_hit(caption['start'], caption['end'], e['start'], e['end']) > 0 for e in laugh_rows):
                issues.append('laughter_near_speech_review_audio')
            if any(_hit(caption['start'], caption['end'], alt['start'], alt['end']) > 0
                   for alt in clip_alternatives):
                issues.append('alternate_asr_requires_listening')
            boundary = any(w['start'] < start or w['end'] > end for w in member)
            if boundary:
                issues.append('cut_splits_word')
            if ((caption is segments[0] and preceding and
                 not str(max(preceding, key=lambda w: w['end']).get('word', '')).endswith(('.', '?', '!')))
                    or (caption is segments[-1] and following and
                        not caption['text'].rstrip().endswith(('.', '?', '!')))):
                issues.append('phrase_boundary_requires_listening')
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
        karaoke = (bool(reviewed_captions) and all(row['word_karaoke_eligible'] and
                   not (set(row['issue_codes']) & CRITICAL_ISSUES) for row in reviewed_captions)
                   and all(a['end'] <= b['start'] for a, b in zip(inside, inside[1:])))
        by_id[ident] = {
            'candidate_id': ident, 'start': start, 'end': end,
            'srt_time_origin': 'clip_relative', 'csv_time_origin': 'source_absolute',
            'timing_policy': {'min_seconds': cfg.get('min_seconds', .4),
                              'max_seconds': cfg.get('max_seconds', 2.8), 'drift_seconds': .25},
            'word_count': len(inside), 'captions': reviewed_captions,
            'low_confidence_word_count': sum(bool(_word_issues(w, threshold)) for w in inside),
            'word_review_fraction': (sum(bool(_word_issues(w, threshold)) for w in inside) / len(inside)) if inside else None,
            'issue_counts': dict(reasons), 'laughter_windows': laugh_rows,
            'asr_alternatives': clip_alternatives,
            'targeted_asr_status': (targeted_report or {}).get('status'),
            'targeted_unprocessed_regions': deepcopy([r for r in (targeted_report or {}).get('unprocessed_regions', [])
                if r.get('candidate_id') == ident or ident in r.get('evidence_refs', [])
                or (_interval(r) and _hit(start, end, r['start'], r['end']) > 0)]),
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
            'selected_candidate_count': len(requested) if requested is not None else len({_candidate_id(c) for c in chosen}),
            'selected_candidate_ids': sorted(requested) if requested is not None else sorted({_candidate_id(c) for c in chosen}),
            'dossier_candidate_count': len(by_id), 'unresolved_selected_candidates': unresolved,
            'status': 'pending_human_audio_review',
            'targeted_asr': deepcopy({k: v for k, v in (targeted_report or {}).items() if k != 'alternatives'}),
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
    report_hash = _sha256(root / 'subtitle_review_s7.json')
    names = [_safe_id(cid) for cid in report.get('candidates', {})]
    if len(names) != len(set(names)):
        raise ValueError('Candidate filename collision')
    rows = []
    for candidate_id, candidate in report.get('candidates', {}).items():
        # Stable filesystem name: no user-controlled path traversal.
        safe_id = _safe_id(candidate_id)
        blocks = []
        for index, cap in enumerate(candidate['captions'], 1):
            blocks.append(f'{index}\n{_srt_stamp(max(cap["start"], candidate["start"])-candidate["start"])} --> '
                          f'{_srt_stamp(min(cap["end"], candidate["end"])-candidate["start"])}\n'
                          + _wrap_caption(cap['asr_text']) + '\n')
            # Neutralize spreadsheet formula injection in untrusted transcript text.
            shown = str(cap['asr_text'])
            if shown.lstrip().startswith(('=', '+', '-', '@')):
                shown = "'" + shown
            rows.append({'candidate_id': candidate_id, 'caption_id': cap['caption_id'],
                         'start_asr': cap['start'], 'end_asr': cap['end'], 'asr_text': shown,
                         'issue_codes': '|'.join(cap['issue_codes']),
                         'verified_text': '', 'verified_start': '', 'verified_end': '',
                         'reviewer': '', 'audio_listened': 'NO', 'decision': 'PENDING',
                         'source_report_sha256': report_hash, 'resolved_issue_codes': ''})
        (root / f'{safe_id}.draft.srt').write_text('\n'.join(blocks), encoding='utf-8')
    columns = ('candidate_id', 'caption_id', 'start_asr', 'end_asr', 'asr_text', 'issue_codes',
               'verified_text', 'verified_start', 'verified_end', 'reviewer', 'audio_listened', 'decision',
               'source_report_sha256', 'resolved_issue_codes')
    with (root / 'subtitle_human_review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    (root / 'LEIA_ANTES_DE_REVISAR.txt').write_text(
        'S7: .draft.srt NAO e legenda aprovada. Confira audio ORIGINAL de cada corte.\n'
        'Preencha CSV com texto ouvido, timestamps reais, audio_listened=YES, decision=APPROVED.\n'
        'Nao deduza palavras, girias ou punchlines por contexto. Karaoke exige verificacao de alinhamento palavra por palavra.\n'
        'CSV de revisao NAO altera automaticamente a transcricao original.\n', encoding='utf-8')
    with (root / 'LEIA_ANTES_DE_REVISAR.txt').open('a', encoding='utf-8') as guide:
        guide.write('SRT usa tempo RELATIVO ao corte; CSV usa segundos ABSOLUTOS do video fonte.\n'
            'resolved_issue_codes: codigos separados por |, apenas depois de conferir/corrigir ouvindo.\n'
            'Divergencia temporal compara estimativas ASR, nao prova sincronismo com o audio.\n'
            'apply-reviewed-csv exporta arquivo corrigido, ainda sem aprovacao da versao final.\n'
            'No CLI scripts/dev/audit_subtitles_s7.py, use --output PASTA_CORRIGIDA --approve-srt ID '
            '--srt-sha256 HASH --reviewer NOME --audio-listened depois de revisar esse arquivo.\n'
            'Use --output PASTA_CORRIGIDA --check-srt-approval ID para revalidar (exit 2 se bloqueado).\n'
            'Alterar SRT, CSV ou dossie invalida a aprovacao. Reexporte via CSV e aprove o novo hash.\n'
            'Sintaxe SRT valida nao comprova fidelidade ao audio. Nenhuma operacao libera publicacao.\n')
    return {'path': str(root), 'candidate_count': len(report.get('candidates', {})), 'caption_count': len(rows)}


def apply_human_subtitle_review(report_dir, review_csv, output_dir):
    """Export human-reviewed SRT only after every caption has signed audio review.

    This checks fields and geometry, not whether somebody truly heard the words.
    It NEVER overwrites the canonical transcript or auto-approves any row.
    """
    folder = Path(report_dir)
    report = json.loads((folder / 'subtitle_review_s7.json').read_text(encoding='utf-8'))
    report_hash = _sha256(folder / 'subtitle_review_s7.json')
    with Path(review_csv).open('r', encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    entries = {}
    for row in rows:
        key = (row.get('candidate_id'), row.get('caption_id'))
        if key in entries:
            raise ValueError('Duplicate reviewed caption: ' + str(key))
        entries[key] = row
    expected = {(cid, cap['caption_id']) for cid, c in report['candidates'].items() for cap in c['captions']}
    names = [_safe_id(cid) for cid in report['candidates']]
    if len(names) != len(set(names)):
        raise ValueError('Candidate filename collision')
    if set(entries) != expected:
        raise ValueError('Review CSV missing captions or containing unknown IDs.')
    output = Path(output_dir)
    if output.resolve() == folder.resolve():
        raise ValueError('Reviewed output must be separate from the original review kit')
    if not expected or report.get('unresolved_selected_candidates') or any(
            not c['captions'] for c in report['candidates'].values()):
        raise ValueError('Missing subtitle evidence for selected cuts')
    approved = []
    generated = {}
    decisions = {}
    for cid, candidate in report['candidates'].items():
        rows_srt, last_end = [], float('-inf')
        for i, cap in enumerate(candidate['captions'], 1):
            checked = entries[(cid, cap['caption_id'])]
            if checked.get('source_report_sha256') != report_hash:
                raise ValueError('Stale review source hash: ' + cap['caption_id'])
            if (checked.get('decision', '').strip().upper() != 'APPROVED' or
                checked.get('audio_listened', '').strip().upper() != 'YES' or
                not checked.get('reviewer', '').strip()):
                raise ValueError(f'Unapproved or unlistened caption: {cid} / {cap["caption_id"]}')
            text = checked.get('verified_text', '').strip()
            if (not text or len(text) > 400 or '\n\n' in text or '-->' in text or
                    any(ord(c) < 32 and c not in '\n\t' for c in text)):
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
            # Re-evaluate reviewer edits; the ASR timing reference is an estimate,
            # so a large correction requires explicit listening acknowledgement.
            issues = set(cap['issue_codes']) | set(_diagnose_caption(start, end,
                reference=(cap['start'], cap['end']), **candidate.get('timing_policy', {})))
            if re.search(r'[-—–…]$', text):
                issues.add('interrupted_or_incomplete_word')
            resolved = {code.strip() for code in checked.get('resolved_issue_codes', '').split('|') if code.strip()}
            pending = (issues & CRITICAL_ISSUES) - resolved
            if pending:
                raise ValueError('Unreviewed critical divergence: ' + '|'.join(sorted(pending)))
            decisions[cap['caption_id']] = {'reviewer': checked['reviewer'].strip(),
                'resolved_issue_codes': sorted(resolved), 'issue_codes': sorted(issues)}
            local_start, local_end = start-candidate['start'], end-candidate['start']
            if _srt_stamp(local_start) == _srt_stamp(local_end):
                raise ValueError('Caption collapses at SRT millisecond precision')
            rows_srt.append(f'{i}\n{_srt_stamp(local_start)} --> {_srt_stamp(local_end)}\n{checked_text(text)}\n')
        generated[cid] = '\n'.join(rows_srt)
        approved.append(cid)
    # Write only if EVERY caption in the submitted batch passes the validation.
    output.mkdir(parents=True, exist_ok=True)
    for cid, content in generated.items():
        safe = _safe_id(cid)
        (output / f'{safe}.human_reviewed.srt').write_text(content, encoding='utf-8')
    (output / 'REVIEW_PROVENANCE.json').write_text(json.dumps({
        'schema_version': 's7.1', 'status': 'HUMAN_REVIEW_FIELDS_COMPLETE',
        'content_source': 'reviewer_supplied_csv_not_autonomous_ASR',
        'audio_listening': 'reviewer_self_attested_NOT_independently_verified',
        'word_karaoke_approved': False, 'video_render_checked': False,
        'source_report_sha256': report_hash, 'review_csv_sha256': _sha256(review_csv),
        'source_report_path': str((folder / 'subtitle_review_s7.json').resolve()),
        'review_csv_path': str(Path(review_csv).resolve()), 'caption_decisions': decisions,
        'srt_time_origin': 'clip_relative', 'human_file_approval': None,
        'files': {cid: {'filename': f'{_safe_id(cid)}.human_reviewed.srt',
                        'sha256': _sha256(output / f'{_safe_id(cid)}.human_reviewed.srt')}
                  for cid in approved},
        'candidate_ids': approved}, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'candidate_count': len(approved), 'output': str(output),
            'status': 'HUMAN_REVIEW_FIELDS_COMPLETE', 'publication_ready': False}


def _review_version(directory, candidate_id):
    root = Path(directory)
    provenance_path = root / 'REVIEW_PROVENANCE.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
    file = provenance['files'][candidate_id]
    if file['filename'] != f'{_safe_id(candidate_id)}.human_reviewed.srt':
        raise ValueError('Invalid reviewed filename')
    digest = _sha256(root / file['filename'])
    if digest != file['sha256']:
        raise ValueError('Corrected SRT changed; repeat CSV review and approval')
    for kind in ('source_report', 'review_csv'):
        if _sha256(provenance[kind + '_path']) != provenance[kind + '_sha256']:
            raise ValueError('Review source changed: ' + kind)
    return digest, _sha256(provenance_path)


def approve_reviewed_subtitles(directory, candidate_id, *, expected_sha256, reviewer, audio_listened):
    """Explicit human approval of exact exported bytes, independently per cut.

    The reviewer must supply the hash they reviewed. Listening is self-attested;
    neither this API nor valid SRT syntax verifies fidelity to the original audio.
    """
    if not str(reviewer or '').strip() or audio_listened is not True:
        raise ValueError('Reviewer and original audio listening required')
    digest, provenance_hash = _review_version(directory, candidate_id)
    if expected_sha256 != digest:
        raise ValueError('Approval hash does not match corrected SRT')
    approval = {'candidate_id': candidate_id, 'srt_sha256': digest,
                'provenance_sha256': provenance_hash, 'reviewer': reviewer.strip(),
                'audio_listened': True, 'status': 'HUMAN_SUBTITLE_APPROVED',
                'independent_audio_verification': False, 'publication_ready': False}
    path = Path(directory) / f'{_safe_id(candidate_id)}.approval.json'
    path.write_text(json.dumps(approval, ensure_ascii=False, indent=2), encoding='utf-8')
    return approval


def subtitle_finalization_gate(directory, candidate_id):
    """Recheck approval against current files before using final subtitles.

    This gate grants no preview or publication approval.
    """
    try:
        digest, provenance_hash = _review_version(directory, candidate_id)
        approval = json.loads((Path(directory) / f'{_safe_id(candidate_id)}.approval.json').read_text('utf-8'))
        valid = (approval.get('candidate_id') == candidate_id and
                 approval.get('srt_sha256') == digest and
                 approval.get('provenance_sha256') == provenance_hash and
                 approval.get('status') == 'HUMAN_SUBTITLE_APPROVED' and
                 approval.get('audio_listened') is True and bool(approval.get('reviewer')))
        reason = None if valid else 'approval_version_mismatch'
    except (OSError, ValueError, KeyError, TypeError) as exc:
        valid, reason = False, str(exc)
    return {'candidate_id': candidate_id, 'subtitles_final_allowed': valid,
            'status': 'HUMAN_SUBTITLE_APPROVED' if valid else 'HUMAN_AUDIO_REVIEW_REQUIRED',
            'reason': reason, 'publication_ready': False}
