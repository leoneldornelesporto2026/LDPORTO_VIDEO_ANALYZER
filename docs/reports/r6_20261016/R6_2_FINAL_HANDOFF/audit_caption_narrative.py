"""Read-only, per-ID audit of the exact original and derivative handoffs."""
import sys
sys.dont_write_bytecode = True

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def union_seconds(intervals):
    result = []
    for a, b in sorted((float(r['start']), float(r['end'])) for r in intervals if r['end'] > r['start']):
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([a, b])
    return sum(b-a for a, b in result)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def audit(package, label):
    raw = package.read_bytes()
    with zipfile.ZipFile(package) as archive:
        def doc(name):
            return json.loads(archive.read(name))
        def jsonl(name):
            return [json.loads(row) for row in archive.read(name).decode('utf-8-sig').splitlines() if row]
        metadata = doc('source/metadata.json')
        catalog = doc('editorial/candidate_catalog.json')['candidates']
        preflight = doc('subtitles/caption_preflight_r6.json')
        words = jsonl('transcript/relevant_words.jsonl')
        segments = jsonl('transcript/relevant_segments.jsonl')
        units = doc('editorial/story_units.json')['units']
        sequences = doc('editorial/story_sequence_candidates.json')['sequences']
        stories = doc('social/stories_manifest.json')
        quality = doc('editorial/narrative_quality_report.json')
        titles = doc('social/narrative_title_suggestions.json')['titles']
        refs = {name: digest(archive.read(name)) for name in [
            'source/metadata.json', 'editorial/candidate_catalog.json',
            'subtitles/caption_preflight_r6.json', 'transcript/relevant_words.jsonl',
            'transcript/relevant_segments.jsonl', 'editorial/story_units.json',
            'editorial/story_sequence_candidates.json', 'social/stories_manifest.json',
            'editorial/narrative_quality_report.json', 'social/narrative_title_suggestions.json']}
    word_ids = {w['word_id'] for w in words}
    segment_ids = {s['segment_id'] for s in segments}
    candidate_ids = {c['candidate_id'] for c in catalog}
    assert len(catalog) == len(candidate_ids) == 70
    assert candidate_ids == set(preflight['candidates'])
    by_id = {c['candidate_id']: c for c in catalog}
    caption_rows = []
    for cid, row in sorted(preflight['candidates'].items()):
        c = by_id[cid]
        missing_words = sorted(set(row['canonical_word_ids'])-word_ids)
        missing_segments = sorted(set(row['canonical_segment_ids'])-segment_ids)
        assert not missing_words and not missing_segments
        assert row['start'] == c['start'] and row['end'] == c['end']
        assert c['caption_preflight']['status'] == row['status']
        assert 0 <= row['start'] < row['end'] <= metadata['duration']
        caption_rows.append({**row, 'candidate_id': cid,
            'literal_text': c.get('transcript_literal'),
            'literal_text_method': c.get('transcript_literal_method'),
            'audio_type': 'unknown' if not row['audio_categories_observed'] else row['audio_categories_observed'],
            'word_time_coverage_fraction': row['word_evidence_seconds']/(row['end']-row['start']),
            'segment_time_coverage_fraction': row['segment_evidence_seconds']/(row['end']-row['start']),
            'missing_word_refs': missing_words, 'missing_segment_refs': missing_segments,
            'spatial_caption_safety': 'UNVERIFIED: review after final camera crop',
            'required_human_action': 'Listen to original audio, verify literal text and boundaries, then align words before karaoke.'
                if row['status'] == 'ALIGNMENT_REVIEW_REQUIRED' else
                'Listen to original audio and determine audio category/text before permitting captions.',
            'independent_candidates_must_not_inherit_this_block': True})
    caption_result = {'schema_version': 'r6.2-audit-1', 'package': str(package.resolve()),
        'package_sha256': digest(raw), 'source_sha256': metadata['sha256'], 'artifact_sha256': refs,
        'candidate_count': len(caption_rows),
        'candidate_status_counts': dict(Counter(r['status'] for r in caption_rows)),
        'legacy_story_status_counts': dict(Counter(r['status'] for r in preflight['stories'].values())),
        'preflight_combined_status_counts': preflight['status_counts'],
        'exported_segment_count': len(segments), 'exported_word_count': len(words),
        'source_duration_s': metadata['duration'], 'segment_union_seconds': union_seconds(segments),
        'segment_union_source_fraction': union_seconds(segments)/metadata['duration'],
        'word_union_seconds': union_seconds(words), 'word_union_source_fraction': union_seconds(words)/metadata['duration'],
        'alignment_verified_word_count_across_candidates': sum(r['alignment_verified_word_count'] for r in caption_rows),
        'audio_verified_word_count_across_candidates': sum(r['audio_verified_word_count'] for r in caption_rows),
        'candidate_allowed_caption_modes': dict(Counter(r['allowed_caption_mode'] for r in caption_rows)),
        'draft_phrase_subtitle_candidate_count': sum(r['draft_phrase_subtitles_available'] for r in caption_rows),
        'long_unaligned_segment_candidate_count': sum(bool(r['unaligned_long_segment_ids']) for r in caption_rows),
        'new_asr_calls': 0, 'audio_listening_performed': False,
        'approval_created': False, 'publication_ready': False, 'candidates': caption_rows}
    unit_ids = {u['unit_id'] for u in units}
    assert len(unit_ids) == len(units)
    seq_rows = []
    for seq in sequences:
        missing = sorted(set(seq['unit_ids'])-unit_ids)
        assert not missing
        assert all(0 <= r['start'] < r['end'] <= metadata['duration'] for r in seq['source_intervals'])
        seq_rows.append({**seq, 'audit_missing_unit_ids': missing,
            'audited_status': 'NARRATIVE_COMPLETE' if seq['complete_supported'] else
                'PARTIAL' if seq['completeness'] == 'partial_supported' else 'REVIEW_REQUIRED'})
    proposed_titles = defaultdict(list)
    for row in titles:
        for suggestion in row.get('suggested_titles', []):
            proposed_titles[' '.join(suggestion['title'].casefold().split())].append(row['unit_id'])
    duplicates = [{'title': title, 'unit_ids': ids} for title, ids in proposed_titles.items() if len(ids) > 1]
    narrative_result = {'schema_version': 'r6.2-audit-1', 'package': str(package.resolve()),
        'package_sha256': digest(raw), 'source_sha256': metadata['sha256'], 'artifact_sha256': refs,
        'sequence_count': len(sequences), 'provisional_unit_count': len(units),
        'complete_supported_count': sum(bool(s['complete_supported']) for s in sequences),
        'sequence_completeness_counts': dict(Counter(s['completeness'] for s in sequences)),
        'unit_role_counts': dict(Counter(u['narrative_role'] for u in units)),
        'unit_duration_max_s': max(u['end']-u['start'] for u in units),
        'unit_duration_over_60_count': sum(u['end']-u['start'] > 60 for u in units),
        'legacy_independent_story_count': len(stories['stories']),
        'legacy_independent_story_ids': [s['story_id'] for s in stories['stories']],
        'legacy_story_readiness': stories['story_readiness'],
        'source_narrative_status_counts': quality['source_narrative_status_counts'],
        'title_unit_count': len(titles), 'title_suggestion_count': sum(len(t.get('suggested_titles', [])) for t in titles),
        'duplicate_title_suggestions': duplicates,
        'title_claim_scope': 'literal ASR excerpt, uncertain; not a verified title or virality claim',
        'units_are_published_story_parts': False, 'new_narrative_promotions': 0,
        'new_instrument_observations': 0, 'new_identity_associations': 0,
        'new_asr_calls': 0, 'approval_created': False, 'publication_ready': False,
        'sequences': seq_rows, 'units': units}
    assert digest(package.read_bytes()) == digest(raw)
    write(HERE / f'CAPTION_CANDIDATE_AUDIT_{label}.json', caption_result)
    write(HERE / f'STORIES_NARRATIVE_AUDIT_{label}.json', narrative_result)
    print(json.dumps({'label': label, 'candidates': len(caption_rows),
        'caption_states': caption_result['candidate_status_counts'],
        'segment_coverage': caption_result['segment_union_source_fraction'],
        'sequences': len(sequences), 'units': len(units),
        'complete_supported': narrative_result['complete_supported_count'],
        'duplicate_titles': len(duplicates), 'package_preserved': True}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--label', choices=['baseline', 'editorial'], required=True)
    args = parser.parse_args()
    audit(args.package, args.label)
