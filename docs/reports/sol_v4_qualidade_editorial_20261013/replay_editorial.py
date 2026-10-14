"""Read preserved checkpoints; export a NEW editorial handoff, no model calls."""
from collections import Counter
import json
from pathlib import Path
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
PREVIOUS = REPORT.parent/'sol_v4_pos_foquinha_20261013'
sys.path.insert(0, str(ROOT/'src'))


def main():
    from ldporto.core import file_hash, digest
    from ldporto.second_curation_export import build_core_package, validate_core_package
    from ldporto.build_provenance import editorial_replay_provenance
    from ldporto.review_media import resolve_review_media, review_player_html
    folder = ROOT/'analysis/video_1da839aad175'
    preserved = json.loads((PREVIOUS/'preservation_before.json').read_text(encoding='utf8'))
    inputs = {}
    def read(name):
        path = folder/name
        if file_hash(path) != preserved['analysis_files'][name]['sha256']:
            raise ValueError('original_input_changed:' + name)
        inputs['analysis/' + name] = path
        return json.loads(path.read_text(encoding='utf-8-sig'))
    analysis = read('analysis.json')
    keys = ['words', 'transcript_segments', 'speakers', 'speaker_turns', 'speech_overlaps',
        'speaker_person_summary', 'shots', 'scenes', 'topics', 'program_sections', 'participants',
        'entities', 'story_arcs', 'main_moments', 'questions_answers', 'question_candidates',
        'question_answer_pairs', 'camera_director_timeline', 'transcription_alternatives',
        'low_confidence_words', 'source_audio_review', 'transcription_hypothesis_comparison',
        'commercial_visual_s8']
    for key in keys:
        reference = analysis.get('collection_refs', {}).get(key)
        if reference:
            analysis[key] = read(reference['path'])
    old_zip = next((PREVIOUS/'derived_export').glob('*.zip'))
    if file_hash(old_zip) != 'd703664b432b1dda128f81276418fb85ff50c145107b1a977a768873da9c509c':
        raise ValueError('previous_derived_package_changed')
    with zipfile.ZipFile(old_zip) as archive:
        old_candidates = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        old_queue = json.loads(archive.read('editorial/human_review_queue.json'))
        old_shortlist = json.loads(archive.read('editorial/default_shortlist.json'))
        analysis['person_identities'] = json.loads(archive.read('people/person_identities.json'))
        # Reuse the completed V4 refinement, do not rerun Q&A/story construction.
        analysis['story_arcs'] = json.loads(archive.read('editorial/story_arcs.json'))
    inputs['prior_derived_package.zip'] = old_zip
    preview_path = PREVIOUS/'source_previews_manifest.json'
    inputs['source_previews_manifest.json'] = preview_path
    analysis['review_media_manifest'] = json.loads(preview_path.read_text(encoding='utf8'))
    initial = json.loads((PREVIOUS/'initial_state.json').read_text(encoding='utf8'))
    checkpoints = {name: folder/'cache'/'0231c20cfd8147d9'/name for name in initial['completed_checkpoints']}
    for name, path in checkpoints.items():
        if file_hash(path) != initial['completed_checkpoints'][name]['sha256']:
            raise ValueError('checkpoint_changed:' + name)
    analysis['editorial_replay_provenance'] = editorial_replay_provenance(analysis,
        checkpoints, inputs, ['editorial_potential', 'review_milestones',
            'boundary_review_proposals', 'source_media_references', 'human_review_queue'],
        ['editorial_potential', 'boundary_review_proposals', 'review_media_binding', 'second_curation_export'])
    destination = REPORT/('derived_export_final' if '--final' in sys.argv else 'derived_export')
    if destination.exists():
        raise FileExistsError('New destination required; never overwrite a prior handoff')
    before_moments = digest(analysis['main_moments'])
    started = time.perf_counter()
    result = build_core_package(analysis, source=None, output_dir=destination,
        cfg={'second_curation_visual_candidate_limit': 0, 'include_candidate_previews': False})
    validation = validate_core_package(Path(result['path']))
    if validation['status'] != 'valid':
        raise ValueError(validation)
    with zipfile.ZipFile(result['path']) as archive:
        candidates = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        queue = json.loads(archive.read('editorial/human_review_queue.json'))
        shortlist = json.loads(archive.read('editorial/default_shortlist.json'))
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
    by_id = {c['candidate_id']: c for c in candidates}
    historical = ['start', 'end', 'segment_ids', 'rank', 'original_rank', 'editorial_score_raw',
        'editorial_score_final', 'score_components', 'score_weights', 'penalties', 'ranking_uncertainty',
        'default_shortlist_eligible', 'eligible_for_human_review', 'editorial_blockers',
        'publication_ready', 'human_approved']
    drift = [{'candidate_id': c['candidate_id'], 'field': key} for c in old_candidates for key in historical
             if c.get(key) != by_id.get(c['candidate_id'], {}).get(key)]
    if drift or set(by_id) != {c['candidate_id'] for c in old_candidates} or shortlist != old_shortlist:
        raise ValueError({'historical_drift': drift, 'shortlist_equal': shortlist == old_shortlist})
    if len(queue['entries']) != 77 or shortlist['candidate_ids']:
        raise ValueError('official_queue_or_shortlist_changed')
    source = ROOT/'input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4'
    media_checks = []
    player_dir = REPORT/'review_players'
    player_dir.mkdir(exist_ok=True)
    selected = ['MOMENT_00002_0000', 'MOMENT_00006_0002', 'MOMENT_00008_0002',
                'MOMENT_00018_0002', 'MOMENT_00020_0000']
    for cid in selected:
        refs = by_id[cid]['source_media_references']
        for kind in ('video', 'audio'):
            resolved = resolve_review_media(refs, source, kind)
            (player_dir/(cid + '_' + kind + '.html')).write_text(review_player_html(resolved), encoding='utf8')
            media_checks.append({k: v for k, v in resolved.items() if k != 'path'})
    for c in candidates:
        refs = c['source_media_references']
        if refs and refs['existing_previews']:
            resolved = resolve_review_media(refs, kind='preview', preview_root=PREVIOUS)
            (player_dir/(c['candidate_id'] + '_preview.html')).write_text(review_player_html(resolved), encoding='utf8')
            media_checks.append({k: v for k, v in resolved.items() if k != 'path'})
    def positions(q):
        return {cid: i for i, cid in enumerate(q['candidate_ids'], 1)}
    old_pos, new_pos = positions(old_queue), positions(queue)
    comparison = [{ 'candidate_id': c['candidate_id'], 'old_priority_rank': old_pos.get(c['candidate_id']),
        'new_priority_rank': new_pos.get(c['candidate_id']), 'historical_score': c['editorial_score_final'],
        'potential': c['editorial_potential'], 'gate_reasons': c['review_plan']['local_gate_reasons'],
        'alternates': c.get('alternates'), 'boundary_review_proposals': c.get('boundary_review_proposals')}
        for c in candidates]
    record = {'state': 'VERIFIED', 'validation': validation, 'result': result,
        'package_sha256': file_hash(result['path']), 'package_bytes': Path(result['path']).stat().st_size,
        'manifest_files': len(manifest['files']), 'export_seconds': time.perf_counter() - started,
        'scope': 'CPU_editorial_triage_export_and_media_hash_checks_only', 'new_model_calls': 0,
        'candidate_count': len(candidates), 'human_review_queue_count': len(queue['entries']),
        'official_shortlist_count': len(shortlist['candidate_ids']), 'historical_field_drift': drift,
        'source_main_moments_unchanged': before_moments == digest(analysis['main_moments']),
        'potential_counts': dict(Counter(c['editorial_potential']['classification'] for c in candidates)),
        'priority_comparison': comparison, 'media_resolution_checks': media_checks,
        'original_zip_validation': validate_core_package(ROOT/preserved['package']),
        'previous_zip_validation': validate_core_package(old_zip),
        'publication_ready': False}
    record_name = 'editorial_replay_final.json' if '--final' in sys.argv else 'editorial_replay.json'
    (REPORT/record_name).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps({k: v for k, v in record.items() if k not in
        ('priority_comparison', 'media_resolution_checks', 'validation', 'result',
         'original_zip_validation', 'previous_zip_validation')}, ensure_ascii=True))
    print(json.dumps({'original_zip_validation': record['original_zip_validation']['status'],
                      'previous_zip_validation': record['previous_zip_validation']['status']}))


if __name__ == '__main__':
    main()
