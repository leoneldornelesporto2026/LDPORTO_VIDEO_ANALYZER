"""Offline review diagnostics. Flags are not transcription errors or corrections."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from collections import Counter


CATEGORIES = ('asr_confidence', 'overlapping_speech', 'truncation', 'non_word',
              'punctuation', 'timestamps', 'hallucination_proxy', 'unexplained_flag')
MARKERS = {'[inaudível]', '[inaudivel]', '[risos]', '[risada]', '[laughter]',
           '[crosstalk]', '[ininteligível]', '[ininteligivel]'}
SLANG = {'mano', 'pô', 'porra', 'cara', 'moleque', 'tá', 'né'}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _interval(row):
    return (_number(row.get('start')) and _number(row.get('end'))
            and 0 <= row['start'] < row['end'])


def audit_uncertain_words(data, threshold=.6, overlaps=None, sample_limit=10):
    """Return derived evidence without mutating words, segments, or audio.

    Denominator includes every supplied aligned word/token record, punctuation
    included. Unaligned hypotheses and text-only segments are separate inventories.
    Category memberships may overlap; signatures partition the original flags.
    """
    if not _number(threshold) or not 0 <= threshold <= 1:
        raise ValueError('threshold must be finite and between 0 and 1')
    if not isinstance(sample_limit, int) or sample_limit < 0:
        raise ValueError('sample_limit must be a nonnegative integer')
    words = data.get('words', [])
    segments = data.get('segments', data.get('transcript_segments', []))
    overlap_rows = overlaps if overlaps is not None else data.get('speech_overlaps', [])
    counts, flagged_counts, signatures = Counter(), Counter(), Counter()
    rows, buckets = [], {key: [] for key in ('slang_candidate', 'laughter_marker', 'crosstalk', 'name_candidate')}
    for index, word in enumerate(words):
        text = str(word.get('word', ''))
        token = text.strip().casefold()
        lexical = token.strip('.,!?;:…')
        confidence = word.get('confidence')
        reasons, details = [], []
        if not _number(confidence) or not 0 <= confidence <= 1 or confidence < threshold:
            reasons.append('asr_confidence')
            details.append('missing_or_invalid_probability' if not _number(confidence) or not 0 <= confidence <= 1 else 'below_threshold')
        hits = [r for r in overlap_rows if _interval(word) and _interval(r)
                and min(word['end'], r['end']) > max(word['start'], r['start'])]
        if word.get('speech_overlap') or hits:
            reasons.append('overlapping_speech')
        if word.get('truncated') is True or word.get('truncation') is True or lexical.endswith('-'):
            reasons.append('truncation')
            details.append('explicit_marker_or_trailing_hyphen_not_verified_cut')
        if not token or token in MARKERS or word.get('non_word') is True:
            reasons.append('non_word')
        if token and all(not c.isalnum() and not c.isspace() for c in token):
            reasons.append('punctuation')
        if not _interval(word) or word.get('timestamp_repaired'):
            reasons.append('timestamps')
        if word.get('suspected_hallucination'):
            reasons.append('hallucination_proxy')
        flagged = bool(word.get('needs_review'))
        if flagged and not reasons:
            reasons.append('unexplained_flag')
        counts.update(reasons)
        if flagged:
            flagged_counts.update(reasons)
            signatures['+'.join(reasons)] += 1
        row = {'word_index': index, 'word_id': word.get('word_id'),
               'segment_id': word.get('segment_id'), 'word': word.get('word'),
               'original_segment_id': word.get('original_segment_id'),
               'start': word.get('start'), 'end': word.get('end'),
               'raw_start': word.get('raw_start'), 'raw_end': word.get('raw_end'),
               'confidence': confidence, 'original_needs_review': flagged,
               'categories': reasons, 'details': details,
               'overlap_intersections': [{'start': max(word['start'], r['start']),
                                         'end': min(word['end'], r['end'])} for r in hits],
               'context_before': ' '.join(str(w.get('word', '')) for w in words[max(0, index-5):index]),
               'context_after': ' '.join(str(w.get('word', '')) for w in words[index+1:index+6]),
               'corrected_word': None, 'listening_status': 'pending_original_audio',
               'confirmed_error': None}
        rows.append(row)
        if lexical in SLANG:
            buckets['slang_candidate'].append(index)
        if token in {'[risos]', '[risada]', '[laughter]'}:
            buckets['laughter_marker'].append(index)
        if 'overlapping_speech' in reasons or token == '[crosstalk]':
            buckets['crosstalk'].append(index)
        if word.get('entity_type') in {'PERSON', 'person', 'name'} or (text.strip()[:1].isupper() and any(c.isalpha() for c in text)):
            buckets['name_candidate'].append(index)
    n, flagged = len(words), sum(r['original_needs_review'] for r in rows)
    by_segment = {}
    for row in rows:
        by_segment.setdefault(row['segment_id'], []).append(row)
    segment_rows = []
    for index, segment in enumerate(segments):
        members = by_segment.get(segment.get('segment_id'), [])
        segment_rows.append({'segment_index': index, 'segment_id': segment.get('segment_id'),
                             'start': segment.get('start'), 'end': segment.get('end'),
                             'text': segment.get('text'), 'word_count': len(members),
                             'flagged_word_count': sum(r['original_needs_review'] for r in members),
                             'categories': sorted({c for r in members for c in r['categories']}),
                             'corrected_text': None, 'listening_status': 'pending_original_audio'})
    return {'schema_version': '19.1', 'denominator': 'supplied_aligned_word_token_records',
            'word_count': n, 'original_flagged_count': flagged,
            'original_flagged_fraction': flagged / n if n else None,
            'asr_threshold': threshold, 'categories_are_nonexclusive': True,
            'confidence_is_calibrated_correctness': False,
            'categories': {c: {'observed_count': counts[c], 'flagged_count': flagged_counts[c],
                               'fraction_all_words': counts[c] / n if n else None,
                               'fraction_flagged_words': flagged_counts[c] / flagged if flagged else None}
                           for c in CATEGORIES},
            'flagged_signature_partition': dict(sorted(signatures.items())),
            'unaligned_word_count': len(data.get('unaligned_words', [])),
            'unaligned_segment_count': len(data.get('unaligned_segments', [])),
            'text_only_segment_count': sum(not by_segment.get(s.get('segment_id')) for s in segments),
            'samples': {k: {'eligible_count': len(v), 'word_indices': v[:sample_limit],
                            'method': 'first_in_source_order_marker_or_lexical_candidate_not_semantic_confirmation'}
                        for k, v in buckets.items()},
            'words': rows, 'segments': segment_rows, 'transcription_error_rate': None,
            'confirmed_corrections': None, 'publication_ready': False,
            'limitations': ['No listening or independent audio verification performed.',
                            'Capitalization/slang lists are sampling hints, not identity or error evidence.',
                            'Punctuation inside lexical tokens is retained and not an error flag.',
                            'Absent truncation/non-word markers do not prove absence of these phenomena.']}


def write_listening_audit(report, output):
    """Create a new report directory only; never overwrite analysis evidence."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for key in ('words', 'segments'):
        rows = report[key]
        with (output / f'listening_{key}.csv').open('w', encoding='utf-8-sig', newline='') as stream:
            if not rows:
                continue
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                                 for k, v in row.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Existing transcript/analysis JSON (read only)')
    parser.add_argument('output', type=Path, help='New directory for audit and listening CSVs')
    parser.add_argument('--threshold', type=float, default=.6)
    args = parser.parse_args()
    source = args.input.read_bytes()
    report = audit_uncertain_words(json.loads(source), args.threshold)
    report['source'] = {'path': str(args.input), 'sha256': hashlib.sha256(source).hexdigest()}
    write_listening_audit(report, args.output)


if __name__ == '__main__':
    main()
