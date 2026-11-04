"""Deterministic editorial-only replay. Historical analyses are read-only."""
from copy import deepcopy
import json
from pathlib import Path
import time

from .core import digest, file_hash, read_json, write_json


def narrative_replay_plan(mode='editorial'):
    if mode not in {'editorial', 'targeted_repair', 'full'}:
        raise ValueError('unsupported_narrative_replay_mode')
    return {'mode': mode, 'automatic_full_processing': False, 'model_calls': 0,
        'action': 'reuse_canonical_artifacts_and_export' if mode == 'editorial' else
                  'prepare_bounded_repair_plan_no_inference' if mode == 'targeted_repair' else
                  'use_existing_full_pipeline_only_with_explicit_user_instruction',
        'publication_ready': False}


def replay_narrative_analysis(folder, output, cfg=None, reference_package=None, test_evidence=None):
    from .replay import ReplayArtifacts, safe_replay_path, checkpoint_hashes
    from .understanding import build_story_arcs, _validate_story_arcs_contract
    from .narrative_handoff import build_narrative_handoff, validate_narrative_handoff, ARTIFACTS
    from .build_provenance import editorial_replay_provenance, exporter_identity
    from .second_curation_export import build_core_package, validate_core_package
    from .second_curation import validate_references
    started = time.perf_counter()
    source = ReplayArtifacts(folder)
    output = safe_replay_path(output)
    if output == source.folder or output.is_relative_to(source.folder):
        raise ValueError('narrative_replay_must_preserve_original_analysis')
    output.mkdir(parents=True, exist_ok=True)
    if not (output/'replay_state.json').exists() and any(output.iterdir()):
        raise ValueError('nonempty_nonreplay_output_directory')
    analysis = deepcopy(source.document)
    source.read('analysis.json', required=True)
    trusted_social = None
    reference_candidates = None
    if reference_package:
        reference_package = safe_replay_path(reference_package)
        if validate_core_package(reference_package)['status'] != 'valid':
            raise ValueError('invalid_reference_package')
        import zipfile
        with zipfile.ZipFile(reference_package) as archive:
            metadata = json.loads(archive.read('source/metadata.json'))
            if metadata.get('sha256') != source.source_hash:
                raise ValueError('reference_package_source_mismatch')
            trusted_social = json.loads(archive.read('social/stories_manifest.json'))
            reference_candidates = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
    keys = ('words transcript_segments speakers speaker_turns speech_overlaps speaker_person_summary '
        'shots scenes topics program_sections participants entities story_arcs main_moments questions_answers '
        'question_candidates question_answer_pairs camera_plan camera_director_timeline transcription_alternatives '
        'low_confidence_words source_audio_review transcription_hypothesis_comparison commercial_visual_s8 '
        'person_identities social_output second_curation_package').split()
    for key in keys:
        if key == 'social_output' and trusted_social is not None:
            analysis[key] = trusted_social
            continue
        name = 'stories_manifest.json' if key == 'social_output' else key + '.json'
        value = source.read(name, required=key in {'words', 'transcript_segments', 'topics', 'main_moments', 'story_arcs'})
        if value is not None:
            analysis[key] = value
    source.validate_transcript(analysis['words'], analysis['transcript_segments'])
    checkpoints = checkpoint_hashes(source.folder)
    modules = ('narrative_replay.py', 'narrative_handoff.py', 'narrative_relations.py',
               'understanding.py', 'story_recovery.py', 'commercial_context.py', 'editorial.py',
               'second_curation_export.py', 'second_curation.py', 'build_provenance.py')
    code = {name: file_hash(Path(__file__).parent/name) for name in modules}
    cache_key = digest({'schema': '1.0', 'source_sha256': source.source_hash,
                        'inputs': source.verified, 'checkpoints': checkpoints, 'code': code,
                        'exporter': exporter_identity(), 'config': cfg or {},
                        'reference_package_sha256': file_hash(reference_package) if reference_package else None,
                        'schema_sha256': file_hash(Path(__file__).parents[2]/'schemas/narrative_handoff.schema.json'),
                        'test_evidence': test_evidence})
    state_path, cache_path = output/'replay_state.json', output/'NARRATIVE_REPLAY_BUNDLE.json'
    state = read_json(state_path) if state_path.is_file() else {}
    if state and state.get('cache_key') != cache_key:
        raise ValueError('changed_replay_inputs_require_new_output_directory')
    if state.get('status') == 'complete':
        result_path = output/'replay_result.json'
        if not result_path.is_file() or file_hash(result_path) != state.get('result_sha256'):
            raise ValueError('replay_result_checksum_mismatch')
        result = read_json(result_path)
        package = safe_replay_path(result['result']['path'])
        if file_hash(package) != result['package_sha256'] or validate_core_package(package)['status'] != 'valid':
            raise ValueError('cached_narrative_package_invalid')
        return {**result, 'cache_hit': True, 'new_model_calls': 0}
    original_package = analysis.get('second_curation_package')
    if not isinstance(original_package, dict) or not isinstance(original_package.get('candidates'), list):
        raise ValueError('canonical_candidate_package_required_no_silent_reranking')
    candidates = original_package['candidates']
    original_refs = validate_references(analysis, original_package)
    if original_refs['status'] != 'resolved':
        raise ValueError({'replay_source_references_unresolved': original_refs['unresolved'][:3],
                          'unresolved_count': len(original_refs['unresolved'])})
    before_arcs = deepcopy(analysis['story_arcs'])
    before = {'source_arcs': len(before_arcs), 'narrative_supported': sum(a.get('narrative_supported') is True for a in before_arcs),
        'questions': len(analysis.get('questions_answers') or []),
        'canonical_qa_status_counts': dict(__import__('collections').Counter(q.get('answer_status') for q in analysis.get('questions_answers') or [])),
        'candidate_count': len(candidates), 'official_shortlist_count': len(analysis.get('editorial_shortlist') or []),
        'legacy_story_count': len((analysis.get('social_output') or {}).get('stories') or []),
        'arc_interval_conflicts': sum(bool((a.get('support_diagnostics') or {}).get('canonical_interval_conflicts')) for a in before_arcs)}
    write_json(state_path, {'cache_key': cache_key, 'status': 'building', 'source_sha256': source.source_hash,
                            'new_model_calls': 0})
    cache_hit = False
    if state.get('bundle_sha256') and cache_path.is_file() and file_hash(cache_path) == state['bundle_sha256']:
        cached = read_json(cache_path)
        analysis['story_arcs'] = cached['story_arcs']
        bundle = cached['bundle']
        cache_hit = True
    else:
        arcs = build_story_arcs({'segments': analysis['transcript_segments']}, analysis['topics'], analysis.get('questions_answers') or [])
        arcs, normalization = _validate_story_arcs_contract(arcs, analysis['transcript_segments'])
        if {a['story_arc_id'] for a in arcs} != {a['story_arc_id'] for a in before_arcs}:
            raise ValueError('new_arc_ids_require_explicit_candidate_link_migration')
        analysis['story_arcs'] = arcs
        bundle = build_narrative_handoff(analysis, candidates)
        write_json(cache_path, {'cache_key': cache_key, 'story_arcs': arcs, 'bundle': bundle,
                                'contract_normalization': normalization})
    validation = validate_narrative_handoff(bundle, analysis['transcript_segments'], candidates, analysis['metadata'])
    if validation['status'] != 'valid':
        raise ValueError({'narrative_contract_failed': validation['errors']})
    write_json(state_path, {'cache_key': cache_key, 'status': 'bundle_validated',
                            'bundle_sha256': file_hash(cache_path), 'new_model_calls': 0})
    analysis.update(narrative_handoff_bundle=bundle, narrative_handoff_enabled=True,
                    narrative_baseline_metrics=before, narrative_test_evidence=test_evidence)
    inputs = {name: source.folder/name for name in source.verified}
    if reference_package:
        inputs['reference_package.zip'] = reference_package
    analysis['editorial_replay_provenance'] = editorial_replay_provenance(analysis,
        {name: source.folder/name for name in checkpoints}, inputs,
        ['story_arcs', *ARTIFACTS.values()], ['narrative_analysis', 'question_answer_proposals',
        'narrative_handoff', 'commercial_context_review', 'targeted_repair_plan', 'second_curation_export'])
    historical_digest = digest(candidates)
    result = build_core_package(analysis, source=None, output_dir=output/'package',
        cfg={**(cfg or {}), 'narrative_handoff_enabled': True,
             'second_curation_visual_candidate_limit': 0, 'include_candidate_previews': False}, package=original_package)
    if historical_digest != digest(candidates):
        raise ValueError('source_candidate_mutation')
    import zipfile
    with zipfile.ZipFile(result['path']) as archive:
        exported = json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        exported_shortlist = json.loads(archive.read('editorial/default_shortlist.json'))['candidate_ids']
    by_candidate = {c['candidate_id']: c for c in exported}
    historical_fields = ('start', 'end', 'rank', 'editorial_score_raw', 'editorial_score_final',
        'score_components', 'score_weights', 'penalties', 'ranking_uncertainty', 'editorial_blockers',
        'default_shortlist_eligible', 'commercial_review_state', 'eligible_for_human_review')
    drift = [{'candidate_id': c['candidate_id'], 'field': key} for c in reference_candidates or candidates
             for key in historical_fields if c.get(key) != by_candidate.get(c['candidate_id'], {}).get(key)]
    if drift or set(by_candidate) != {c['candidate_id'] for c in candidates} or exported_shortlist != (analysis.get('editorial_shortlist') or []):
        raise ValueError({'historical_candidate_field_drift': drift,
                          'official_shortlist_changed': exported_shortlist != (analysis.get('editorial_shortlist') or [])})
    if checkpoint_hashes(source.folder) != checkpoints:
        raise ValueError('historical_checkpoint_mutation')
    record = {'status': bundle['handoff']['status'], 'result': result, 'cache_key': cache_key,
        'cache_hit': cache_hit, 'package_sha256': file_hash(result['path']),
        'wall_seconds': time.perf_counter()-started, 'before': before,
        'after': bundle['artifacts'][ARTIFACTS['quality']], 'validation': validation,
        'source_sha256': source.source_hash, 'verified_input_sha256': source.verified,
        'checkpoint_sha256': checkpoints, 'replay_code_sha256': code,
        'historical_candidate_digest': historical_digest, 'original_candidates_modified': False,
        'historical_field_drift': drift,
        'canonical_qa_modified': False, 'new_model_calls': 0, 'source_media_decoded': False,
        'publication_ready': False}
    write_json(output/'replay_result.json', record)
    write_json(state_path, {'status': 'complete', 'cache_key': cache_key,
        'bundle_sha256': file_hash(cache_path), 'result_sha256': file_hash(output/'replay_result.json'),
        'new_model_calls': 0})
    return record


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis')
    parser.add_argument('--output', required=True)
    parser.add_argument('--reference-package')
    parser.add_argument('--test-evidence')
    args = parser.parse_args()
    evidence = read_json(Path(args.test_evidence)) if args.test_evidence else None
    result = replay_narrative_analysis(args.analysis, args.output,
        reference_package=args.reference_package, test_evidence=evidence)
    print(json.dumps({k: result[k] for k in ('status', 'cache_hit', 'wall_seconds', 'package_sha256', 'new_model_calls')}))
    print(result['result']['path'])


if __name__ == '__main__':
    main()
