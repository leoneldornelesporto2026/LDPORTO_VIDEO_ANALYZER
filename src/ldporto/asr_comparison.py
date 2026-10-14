"""Localize observed ASR differences; this is neither correction nor accuracy."""
from collections import Counter
from copy import deepcopy
import math
import re
import unicodedata


COMPARISON_VERSION = '1.0'


def valid_interval(row):
    if not isinstance(row, dict):
        return False
    a, b = row.get('start'), row.get('end')
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (a, b)) and 0 <= a < b


def lexical_token(value):
    # Keep accented letters, scripts, digits and repetitions. No translation,
    # stemming, synonym expansion or guessed spelling correction.
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFC', str(value)).casefold())


def lexical_text(value):
    return [token for part in str(value or '').split() if (token := lexical_token(part))]


def _overlaps(word, start, end):
    return valid_interval(word) and word['start'] < end and word['end'] > start


def compare_hypotheses(original_words, alternative, start, end, *, original_text=None,
                       timing_tolerance=.75, max_alignment_words=512):
    """Monotonic lexical alignment with timestamps breaking repeated-token ties."""
    result = {'schema_version': COMPARISON_VERSION, 'method': 'monotonic_word_time_alignment',
              'start': start, 'end': end, 'status': 'equivalent', 'lexical_difference_count': 0,
              'cosmetic_difference_count': 0, 'timestamp_difference_count': 0,
              'affected_word_ids': [], 'affected_intervals': [], 'boundary_word_ids': [],
              'boundary_intervals': [], 'unresolved_regions': [], 'events': [],
              'independent_audio_verification': False, 'replacement_permitted': False}
    original = [w for w in original_words if _overlaps(w, start, end) and lexical_token(w.get('word', ''))]
    alternate_words = alternative.get('words')
    if (not isinstance(alternate_words, list) or any(not valid_interval(w) for w in alternate_words)
            or (not alternate_words and lexical_text(alternative.get('text')))):
        text = original_text if original_text is not None else ' '.join(w.get('word', '') for w in original)
        if lexical_text(text) != lexical_text(alternative.get('text')):
            result.update(status='unlocalized_text_difference', lexical_difference_count=None,
                          unresolved_regions=[{'start': start, 'end': end, 'reason': 'word_timestamps_unavailable'}])
        elif str(text).strip() != str(alternative.get('text') or '').strip():
            result['cosmetic_difference_count'] = 1
        return result
    alternate = [w for w in alternate_words if _overlaps(w, start, end) and lexical_token(w.get('word', ''))]
    if max(len(original), len(alternate)) > max_alignment_words:
        result.update(status='alignment_budget_exceeded', lexical_difference_count=None,
                      unresolved_regions=[{'start': start, 'end': end, 'reason': 'alignment_word_budget'}])
        return result
    a, b = [lexical_token(w['word']) for w in original], [lexical_token(w['word']) for w in alternate]
    n, m = len(a), len(b)
    costs = [[0.] * (m + 1) for _ in range(n + 1)]
    choices = [[''] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        costs[i][0], choices[i][0] = float(i), 'delete'
    for j in range(1, m + 1):
        costs[0][j], choices[0][j] = float(j), 'insert'
    center = lambda word: (word['start'] + word['end']) / 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            drift = abs(center(original[i-1]) - center(alternate[j-1]))
            paired_cost = min(.2, drift * .05) if a[i-1] == b[j-1] else 1.2 + min(.8, drift * .3)
            options = [(costs[i-1][j-1] + paired_cost, 'equal' if a[i-1] == b[j-1] else 'replace'),
                       (costs[i-1][j] + 1., 'delete'), (costs[i][j-1] + 1., 'insert')]
            costs[i][j], choices[i][j] = min(options, key=lambda item: item[0])
    alignment, i, j = [], n, m
    while i or j:
        operation = choices[i][j]
        alignment.append((operation, i-1 if operation != 'insert' else None,
                          j-1 if operation != 'delete' else None))
        i -= operation != 'insert'
        j -= operation != 'delete'
    alignment.reverse()
    affected, boundary = set(), set()
    def remember(index, is_boundary=False):
        word = original[index]
        (boundary if is_boundary else affected).add(index)
        return word.get('word_id')
    for position, (operation, index, alt_index) in enumerate(alignment):
        word = original[index] if index is not None else None
        alt = alternate[alt_index] if alt_index is not None else None
        if operation == 'equal':
            if word['word'] != alt['word']:
                result['cosmetic_difference_count'] += 1
            # Small attention-alignment drift is recorded separately from text.
            drift = max(abs(word['start']-alt['start']), abs(word['end']-alt['end']))
            if drift > timing_tolerance and start <= word['start'] and word['end'] <= end:
                result['timestamp_difference_count'] += 1
                result['events'].append({'kind': 'timestamp_difference', 'word_id': word.get('word_id'),
                                         'start': word['start'], 'end': word['end'], 'drift_seconds': drift})
            continue
        event = {'kind': operation, 'original_word': word.get('word') if word else None,
                 'alternative_word': alt.get('word') if alt else None, 'word_ids': []}
        if word:
            clipped = word['start'] < start - 1e-7 or word['end'] > end + 1e-7
            ident = remember(index, clipped)
            event.update(start=max(start, word['start']), end=min(end, word['end']), clip_boundary=clipped)
            if ident:
                event['word_ids'].append(ident)
            if clipped:
                event['kind'] = 'clip_boundary_not_comparable'
            else:
                result['lexical_difference_count'] += 1
        else:
            event.update(start=alt['start'], end=alt['end'], clip_boundary=False)
            result['lexical_difference_count'] += 1
            # Insertions have no canonical word to replace. Use nearby timed
            # anchors only; never implicate the rest of a phrase/chunk.
            neighbors = [entry[1] for entry in alignment[:position] if entry[1] is not None][-1:]
            neighbors += [entry[1] for entry in alignment[position+1:] if entry[1] is not None][:1]
            for neighbor in neighbors:
                candidate = original[neighbor]
                distance = max(0., candidate['start']-alt['end'], alt['start']-candidate['end'])
                if distance <= timing_tolerance:
                    ident = remember(neighbor)
                    if ident:
                        event['word_ids'].append(ident)
        result['events'].append(event)
    for indices, id_key, interval_key in ((affected, 'affected_word_ids', 'affected_intervals'),
                                          (boundary, 'boundary_word_ids', 'boundary_intervals')):
        result[id_key] = [original[index]['word_id'] for index in sorted(indices) if original[index].get('word_id')]
        result[interval_key] = [{'start': original[index]['start'], 'end': original[index]['end']}
                                for index in sorted(indices)]
    # Insertion timings also localize source-to-source differences where the
    # original hypothesis omitted a phrase and has no nearby matching anchor.
    result['affected_intervals'].extend({'start': event['start'], 'end': event['end']}
                                       for event in result['events'] if event['kind'] == 'insert')
    if result['lexical_difference_count']:
        result['status'] = 'localized_lexical_difference'
    elif boundary:
        result['status'] = 'clip_boundary_unresolved'
    elif result['timestamp_difference_count']:
        result['status'] = 'timing_difference_only'
    return result


def review_reason_metrics(words):
    flagged = [w for w in words if w.get('needs_review')]
    signatures = Counter(tuple(sorted(set(w.get('review_reasons', []) or ['external_review_flag']))) for w in flagged)
    reasons = Counter(reason for signature, count in signatures.items() for reason in signature for _ in range(count))
    return {'flagged_word_count': len(flagged), 'word_count': len(words),
            'flagged_fraction': len(flagged) / len(words) if words else None,
            'exclusive_reason_signatures': [{'reasons': list(signature), 'word_count': count}
                                           for signature, count in sorted(signatures.items())],
            'overlapping_reason_counts': dict(sorted(reasons.items())),
            'observed_condition_counts': {'overlapping_speech': sum(bool(w.get('speech_overlap')) for w in words),
                                          'timestamp_suspect_or_repaired': sum(bool(w.get('timestamp_suspect') or w.get('timestamp_repaired')) for w in words)},
            'flag_rate_is_error_rate': False, 'word_error_rate': None,
            'verified_correct_word_count': None, 'human_audio_verification_performed': False}


def source_review_dossier(transcript, duration, *, max_regions=16, max_audio_seconds=180, padding=2.):
    """Plan source listening independently of shortlist, reusing acoustic evidence."""
    options = []
    for word in transcript.get('words', []):
        if (word.get('needs_review') or word.get('speech_overlap') or word.get('timestamp_suspect')) and valid_interval(word):
            reasons = list(word.get('review_reasons', []))
            if word.get('speech_overlap'):
                reasons.append('overlapping_speech')
            options.append({'start': max(0., word['start']-padding), 'end': min(duration, word['end']+padding),
                            'word_ids': [word.get('word_id')], 'reasons': sorted(set(reasons))})
    for region in transcript.get('hypothesis_comparison', {}).get('unresolved_regions', []):
        if valid_interval(region):
            options.append({'start': region['start'], 'end': min(duration, region['end']), 'word_ids': [],
                            'reasons': [region.get('reason', 'unlocalized_asr_comparison')]})
    merged = []
    for row in sorted(options, key=lambda item: (item['start'], item['end'])):
        if row['end'] <= row['start']:
            continue
        if merged and row['start'] <= merged[-1]['end'] and max(row['end'], merged[-1]['end'])-merged[-1]['start'] <= 30:
            prior = merged[-1]
            prior['end'] = max(prior['end'], row['end'])
            prior['word_ids'] = list(dict.fromkeys(prior['word_ids'] + row['word_ids']))
            prior['reasons'] = sorted(set(prior['reasons'] + row['reasons']))
        else:
            merged.append(deepcopy(row))
    windows, deferred, seconds = [], [], 0.
    for row in merged:
        if len(windows) >= max_regions or seconds + row['end']-row['start'] > max_audio_seconds:
            deferred.append({**row, 'pending_reason': 'source_review_region_budget' if len(windows) >= max_regions else 'source_review_audio_budget'})
            continue
        seconds += row['end']-row['start']
        original = [w for w in transcript.get('words', []) if _overlaps(w, row['start'], row['end'])]
        alternatives = [r for r in transcript.get('transcription_alternatives', []) if _overlaps(r, row['start'], row['end'])]
        windows.append({**row, 'window_id': f'SOURCE_REVIEW_{len(windows):05}', 'candidate_id': None,
                        'ORIGINAL': deepcopy(original), 'prior_alternatives': deepcopy(alternatives),
                        'verified_by_audio': None, 'reviewer': None, 'correction_approved': False})
    acoustic = deepcopy(transcript.get('review_budget', {}))
    return {'schema_version': '1.0', 'scope': 'source_uncertainty_independent_of_shortlist',
            'selection_source': 'observed_asr_uncertainty', 'status': 'pending_human_audio_review' if windows or deferred else 'no_source_flags_recorded',
            'windows': windows, 'deferred': deferred, 'requires_editorial_shortlist': False,
            'metrics': review_reason_metrics(transcript.get('words', [])),
            'listening_budget': {'max_regions': max_regions, 'max_audio_seconds': max_audio_seconds, 'planned_audio_seconds': seconds},
            'acoustic_multipass': {'status': 'executed' if acoustic.get('asr_calls', 0) else 'not_executed',
                                  'asr_calls': acoustic.get('asr_calls', 0),
                                  'processed_audio_seconds': acoustic.get('processed_audio_seconds', 0),
                                  'human_audio_review': False},
            'new_asr_calls': 0, 'audio_verification_performed': False,
            'subtitle_publish_ready': False, 'publication_ready': False}
