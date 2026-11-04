"""R5.1 textual replay, separate from the zero-model R5 editorial operation."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import time
import uuid

from .core import digest, file_hash
from .export_privacy import sanitize_export
from .semantic_package import (read_package, decoded_documents, validate_embedded_schemas,
                               validate_semantic_artifacts, export_semantic_package)
from .semantic_runtime import atomic_json, CachedSemanticInference, inference_history


def _save_artifacts(output, artifacts):
    from pathlib import PurePosixPath
    for name, document in artifacts.items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
            raise ValueError('unsafe_semantic_artifact_path')
        atomic_json(output/'artifacts'/name, document)


def _load_artifacts(output, state):
    from pathlib import PurePosixPath
    artifacts = {}
    for name, expected in state.get('artifact_hashes', {}).items():
        logical = PurePosixPath(name)
        if logical.is_absolute() or '..' in logical.parts or ':' in name or '\\' in name:
            raise ValueError('unsafe_persisted_semantic_artifact_path')
        path = output/'artifacts'/name
        if not path.is_file() or file_hash(path) != expected:
            raise ValueError('persisted_semantic_artifact_checksum_mismatch:'+name)
        artifacts[name] = json.loads(path.read_text(encoding='utf-8'))
    return artifacts


def _checkpoint(output, state, artifacts, phase):
    if state.get('artifact_hashes'):
        # Derived revisions remain inspectable, including rejected/abstained passes.
        previous = _load_artifacts(output, state)
        if digest(previous) != digest(artifacts):
            import shutil
            revision = output/'revisions'/(datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'_'+uuid.uuid4().hex[:6])
            for name in previous:
                target = revision/'artifacts'/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(output/'artifacts'/name, target)
            atomic_json(revision/'semantic_state.json', state)
    _save_artifacts(output, artifacts)
    state.update(phase=phase, artifact_hashes={n: file_hash(output/'artifacts'/n) for n in artifacts},
                 updated_at=datetime.now(timezone.utc).isoformat())
    atomic_json(output/'semantic_state.json', state)


def evidence_summary_schema(task_id, context, schema):
    """Optional extractive repair: constrain abstractions, preserve model choices.

    IDs, semantic status, relationships and evidence remain model proposals. Only
    summary/rationale text is limited to an actual source utterance after an
    abstractive attempt adds unsupported facts. An unresolved answer stays legal.
    """
    from copy import deepcopy
    schema = deepcopy(schema)
    texts = list(dict.fromkeys(s['text'] for s in context.get('data', {}).get('segments', [])
                               if s.get('text') and not s['text'].strip().endswith('?')))
    if not texts:
        return schema
    extract = {'type': 'string', 'enum': texts}
    if str(task_id).startswith('semantic.qa.'):
        proposal = schema['properties']['proposals']['items']['properties']
        proposal['reasoning_summary'] = extract
        proposal['answers']['items']['properties']['summary'] = extract
    elif str(task_id).startswith('semantic.relations.'):
        schema['properties']['relations']['maxItems'] = 2
        schema['properties']['relations']['items']['properties']['reasoning_summary'] = extract
    elif str(task_id).startswith('semantic.completion.'):
        schema['properties']['proposals']['items']['properties']['summary'] = extract
    return schema


def source_excerpt_repair(task_id, context, payload, proof):
    """Keep source associations; quarantine abstractions instead of publishing them.

    This deterministic evidence-verification pass never adds a source ID, quote,
    relationship, or answer. Raw model output remains in the inference archive.
    Replaced summaries are labelled by provenance and supported QA is downgraded.
    """
    from copy import deepcopy
    import re
    rows = {s['segment_id']: s for s in context.get('data', {}).get('segments', [])}
    output, rules = deepcopy(payload), []
    def literal_quotes(items):
        if not items or any(q.get('segment_id') not in rows or not isinstance(q.get('quote'), str)
                            or q['quote'] not in rows[q['segment_id']]['text'] for q in items):
            return None
        return ' […] '.join(q['quote'] for q in items)
    if str(task_id).startswith('semantic.qa.'):
        for index, proposal in enumerate(output.get('proposals', [])):
            excerpts = []
            valid = True
            for answer in proposal.get('answers', []):
                ids = answer.get('answer_segment_ids') or []
                if not ids or any(sid not in rows for sid in ids) or literal_quotes(answer.get('supporting_quotes')) is None:
                    valid = False
                    break
                excerpt = ' […] '.join(rows[sid]['text'] for sid in ids)
                answer['summary'] = excerpt
                excerpts.append(excerpt)
            if excerpts and valid:
                proposal['reasoning_summary'] = ' […] '.join(excerpts)
                if proposal.get('status') == 'ANSWER_SUPPORTED':
                    proposal['status'] = 'ANSWER_PROPOSED'
                proposal['uncertainty_reasons'] = list(proposal.get('uncertainty_reasons') or []) + [
                    'abstractive_summary_not_accepted; source_excerpts_only; semantic_association_requires_review']
                rules.append({'proposal_index': index, 'rule': 'canonical_answer_excerpt_replaces_model_abstraction',
                              'association_promoted': False})
    elif str(task_id).startswith('semantic.relations.'):
        kept = []
        for index, relation in enumerate(output.get('relations', [])):
            excerpt = literal_quotes(relation.get('supporting_quotes'))
            if excerpt and relation.get('semantic_basis') == 'EXPLICIT_CAUSAL_STATEMENT' and not re.search(
                    r'(?i)\b(porque|por isso|devido|causou|provocou|consequentemente|por causa|fez com que)\b', excerpt):
                rules.append({'proposal_index': index, 'rule': 'causal_basis_without_literal_cause_rejected'})
                continue
            if excerpt:
                relation['reasoning_summary'] = excerpt
                rules.append({'proposal_index': index, 'rule': 'literal_evidence_replaces_model_abstraction',
                              'relation_type_unchanged': True})
            kept.append(relation)
        output['relations'] = kept
    if rules:
        proof = {**proof, 'source_verification_transform': {'rules': rules,
            'raw_payload_sha256': digest(payload), 'verified_payload_sha256': digest(output),
            'verification_code_sha256': file_hash(Path(__file__)),
            'summary_scope': 'literal_source_excerpts_not_abstractive_explanation',
            'raw_model_output_preserved': True, 'human_semantic_verification': False}}
    return output, proof


def reuse_grounded_series(artifacts, legacy, output, state):
    """An abstention does not erase a prior, still valid proposal for this source."""
    name = 'editorial/story_series_proposals.json'
    if artifacts[name].get('series'):
        return artifacts
    revisions = sorted((output/'revisions').glob('*/semantic_state.json'), reverse=True)
    for receipt in revisions:
        previous = json.loads(receipt.read_text(encoding='utf-8'))
        if previous.get('reference_package_sha256') != state['reference_package_sha256']:
            continue
        candidate = receipt.parent/'artifacts'/name
        expected = (previous.get('artifact_hashes') or {}).get(name)
        if not candidate.is_file() or not expected or file_hash(candidate) != expected:
            continue
        proposal = json.loads(candidate.read_text(encoding='utf-8'))
        if not proposal.get('series'):
            continue
        validation = validate_semantic_artifacts({name: proposal}, legacy)
        if validation['status'] == 'valid':
            artifacts[name] = proposal
            artifacts['provenance/semantic_series_reuse.json'] = {
                'schema_version': '1.0', 'reason': 'current_model_abstained; prior_source_grounded_proposal_preserved',
                'prior_artifact_path': candidate.relative_to(output).as_posix(), 'prior_artifact_sha256': expected,
                'reference_package_sha256': state['reference_package_sha256'], 'validation': validation,
                'new_model_calls': 0, 'human_review_completed': False, 'publication_ready': False}
            break
    return artifacts


def semantic_replay(reference, output, *, phase='semantic', cfg=None, test_evidence=None):
    """Execute B, then C, then package D; all intermediate tasks survive a restart."""
    from .build_provenance import exporter_identity, classify_provenance_mismatch
    from .replay import safe_replay_path
    started = time.perf_counter()
    reference, output = safe_replay_path(reference), safe_replay_path(output)
    cfg = cfg or {}
    if phase not in {'semantic', 'curation', 'package'}:
        raise ValueError('unsupported_semantic_phase')
    root = Path(__file__).parents[2]
    forbidden = [root/'analysis', root/'input', root/'models', root/'src']
    if output == root or any(output == p or output.is_relative_to(p) for p in forbidden):
        raise ValueError('semantic_output_must_be_a_separate_derived_directory')
    output.mkdir(parents=True, exist_ok=True)
    state_path = output/'semantic_state.json'
    if not state_path.exists() and any(output.iterdir()):
        raise ValueError('nonempty_nonsemantic_output_directory')
    members = read_package(reference)
    legacy = decoded_documents(members)
    source = legacy['source/metadata.json']
    input_hash = file_hash(reference)
    schemas = {n: json.loads((root/n).read_text(encoding='utf-8')) for n in members
               if n.startswith('schemas/') and (root/n).is_file()}
    if validate_embedded_schemas(schemas)['status'] != 'valid':
        raise ValueError('P0_schema_gate_failed')
    identity = legacy['SECOND_CURATION_MANIFEST.json']['build_provenance']
    editorial = legacy.get('provenance/editorial_replay.json') or {}
    verification = cfg.get('verified_checkpoint_sha256')
    provenance = classify_provenance_mismatch(identity, editorial,
        source_sha256=source['sha256'], verified_checkpoint_sha256=verification, compatible_schema=True)
    if provenance['classification'] in {'incompatible', 'unresolved'}:
        raise ValueError({'P0_provenance_gate_failed': provenance})
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'schema_version': '1.0', 'operation': 'semantic-replay', 'run_id': 'R51_'+uuid.uuid4().hex[:16],
        'reference_package_sha256': input_hash, 'source_sha256': source['sha256'],
        'input_transcript_sha256': digest(legacy['transcript/relevant_segments.jsonl']),
        'input_story_units_sha256': digest(legacy['editorial/story_units.json']),
        'input_arcs_sha256': digest(legacy['editorial/story_arcs.json']),
        'input_graph_sha256': digest(legacy['editorial/narrative_graph.json']),
        'phase': 'P0_VALIDATED', 'artifact_hashes': {}, 'publication_ready': False}
    if state['reference_package_sha256'] != input_hash:
        raise ValueError('changed_reference_package_requires_new_semantic_run')
    artifacts = _load_artifacts(output, state)
    # Persist ownership/identity before the first slow request, so a killed
    # process can resume its already saved task cache in this same directory.
    atomic_json(state_path, state)
    atomic_json(output/'P0_VALIDATION.json', {'embedded_schemas': validate_embedded_schemas(schemas),
        'provenance': provenance, 'legacy_schema_issue': validate_embedded_schemas(legacy),
        'original_reference_unchanged': True})
    runtime = None
    context_topics = {t['topic_id']: t for t in (artifacts.get('editorial/global_topic_map.json') or {}).get('topics', [])}
    def audited_infer(task_id, context, schema):
        from copy import deepcopy
        context = deepcopy(context)
        if cfg.get('focus_topic_context') and str(task_id).startswith(('semantic.relations.', 'semantic.completion.', 'semantic.series.')):
            data = context.get('data') or {}
            topic_id = (data.get('topic') or {}).get('topic_id')
            topic = context_topics.get(topic_id)
            if topic:
                selected_arcs = set(topic['source_arc_ids'])
                selected_questions = set((cfg.get('resolver') or {}).get('qa_question_ids') or [])
                question_ids = {sid for q in legacy['editorial/qa_pairs.json'] if q['question_id'] in selected_questions
                                for sid in q.get('question_segment_ids') or []}
                unit_rows = [u for u in data.get('units') or [] if selected_arcs.intersection(u.get('source_arc_ids') or [])
                             or question_ids.intersection(u.get('source_segment_ids') or [])]
                selected_segments = {s for u in unit_rows for s in u.get('source_segment_ids') or []} | question_ids
                data['units'] = unit_rows
                data['arcs'] = [a for a in data.get('arcs') or [] if a['story_arc_id'] in selected_arcs]
                data['segments'] = [s for s in data.get('segments') or [] if s['segment_id'] in selected_segments]
                for key in ('validated_relation_proposals', 'relation_proposals'):
                    if key in data:
                        data[key] = [r for r in data[key] if r.get('source_arc_id', r.get('source_node_id')) in selected_arcs
                                     and r.get('target_arc_id', r.get('target_node_id')) in selected_arcs]
        if str(task_id).startswith('semantic.qa.') and cfg.get('compact_canonical_question'):
            question = context.get('data', {}).get('question') or {}
            context['data']['question'] = {k: question.get(k) for k in (
                'question_id', 'question_segment_ids', 'question', 'question_speaker', 'question_start', 'question_end')}
        override = (cfg.get('task_prompt_overrides') or {}).get(task_id)
        if override:
            context['instruction'] += '\n'+override
        if cfg.get('title_attempt_required') and str(task_id).startswith('titles:'):
            # Generate a reviewable attempt; the independent source validator can
            # still reject every title. This never requires accepting the result.
            schema = deepcopy(schema)
            schema['properties']['primary_title'] = schema['properties']['primary_title']['anyOf'][0]
            schema['properties']['alternative_titles']['minItems'] = 2
            context['instruction'] += ('\nProduza uma tentativa com três títulos PROPOSED, sustentados nas falas. '
                'A validação independente rejeitará claims sem suporte. Isto não é aprovação editorial, '
                'de direitos, preview ou publicação. Não acrescente fatos para satisfazer o formato.')
        if cfg.get('extractive_evidence_summaries') and str(task_id).startswith(('semantic.qa.', 'semantic.relations.', 'semantic.completion.')):
            schema = evidence_summary_schema(task_id, context, schema)
            context['instruction'] += ('\nNesta reparação, os campos de resumo/rationale limitados por enum '
                'devem copiar uma fala da fonte que esteja ENTRE OS SEGMENTOS CITADOS nessa proposta. '
                'Não altere a fala. A classificação e as associações continuam sendo propostas; '
                'arrays vazios e abstenção continuam válidos. Evite IDs no texto de resumo.')
        atomic_json(output/'inference_requests'/(digest([task_id, context, schema])+'.json'),
                    {'task_id': task_id, 'context': context, 'schema': schema,
                     'context_sha256': digest(context), 'schema_sha256': digest(schema)})
        result = runtime(task_id, context, schema)
        if task_id == 'semantic.global_topic_map':
            for topic in result[0].get('topics', []):
                context_topics['SEM_TOPIC_'+digest(topic)[:16]] = topic
        if cfg.get('source_excerpt_repair'):
            result = source_excerpt_repair(task_id, context, result[0], result[1])
        return result
    if phase == 'semantic':
        from .semantic_narrative import build_semantic_analysis
        runtime = CachedSemanticInference(output, cfg=cfg.get('inference'))
        artifacts = build_semantic_analysis(legacy, audited_infer, cfg=cfg.get('resolver'))
        artifacts = reuse_grounded_series(artifacts, legacy, output, state)
        validation = validate_semantic_artifacts(artifacts, legacy)
        actual_evidence = bool(artifacts['editorial/cross_arc_relations.json']['relations'] or any(
            q.get('answer_segment_ids') for q in artifacts['editorial/semantic_qa_proposals.json']['proposals']))
        _checkpoint(output, state, artifacts, 'B_PARTIAL' if validation['status'] != 'valid' or not actual_evidence else 'B_VALIDATED')
        atomic_json(output/'CHECKPOINT_B.json', {'status': state['phase'], 'validation': validation,
            'actual_semantic_evidence_available': actual_evidence,
            'new_model_calls': len(runtime.calls), 'cache_hits': runtime.cache_hits,
            'wall_seconds': time.perf_counter()-started,
            'diagnostics_ref': 'artifacts/editorial/semantic_resolver_diagnostics.json'})
        return {'phase': state['phase'], 'validation': validation, 'new_model_calls': len(runtime.calls),
                'cache_hits': runtime.cache_hits, 'wall_seconds': time.perf_counter()-started}
    if state['phase'] not in {'B_VALIDATED', 'C_VALIDATED', 'D_VALIDATED'}:
        raise ValueError('semantic_checkpoint_B_required_before_curation_or_export')
    if phase == 'curation':
        from .story_visual_handoff import build_story_visual_handoff
        runtime = CachedSemanticInference(output, cfg=cfg.get('inference'))
        artifacts.update(build_story_visual_handoff(legacy, artifacts, audited_infer))
        validation = validate_semantic_artifacts(artifacts, legacy)
        if validation['status'] != 'valid':
            _save_artifacts(output/'failed_curation', artifacts)
            atomic_json(output/'CHECKPOINT_C_FAILED.json', validation)
            raise ValueError({'checkpoint_C_invalid': validation})
        _checkpoint(output, state, artifacts, 'C_VALIDATED')
        atomic_json(output/'CHECKPOINT_C.json', {'status': state['phase'], 'validation': validation,
            'new_model_calls': len(runtime.calls), 'cache_hits': runtime.cache_hits,
            'wall_seconds': time.perf_counter()-started})
        return {'phase': state['phase'], 'validation': validation, 'new_model_calls': len(runtime.calls),
                'cache_hits': runtime.cache_hits, 'wall_seconds': time.perf_counter()-started}
    if state['phase'] not in {'C_VALIDATED', 'D_VALIDATED'}:
        raise ValueError('semantic_checkpoint_C_required_before_package')
    code = {p.name: file_hash(p) for p in (Path(__file__).parent).glob('*.py')}
    export_key = digest({'artifacts': state['artifact_hashes'], 'code': code, 'tests': test_evidence})
    if state.get('export_key') == export_key and state.get('package'):
        from .semantic_package import validate_semantic_package
        previous = state['package']
        if file_hash(Path(previous['path'])) != previous['sha256'] or validate_semantic_package(previous['path'], reference=reference)['status'] != 'valid':
            raise ValueError('cached_semantic_package_invalid')
        result = {'phase': 'D_VALIDATED', 'package': previous, 'cache_hit': True, 'new_model_calls': 0,
                  'wall_seconds': time.perf_counter()-started}
        atomic_json(output/'cached_repeat_validation.json', result)
        return result
    additions = delivery_documents(legacy, artifacts, state, output, provenance, test_evidence)
    package = export_semantic_package(reference, output/'package', additions)
    state.update(phase='D_VALIDATED', export_key=export_key, package=package)
    atomic_json(state_path, state)
    result = {'phase': 'D_VALIDATED', 'package': package, 'cache_hit': False, 'new_model_calls': 0,
              'wall_seconds': time.perf_counter()-started}
    atomic_json(output/'CHECKPOINT_D.json', result)
    return result


def delivery_documents(legacy, artifacts, state, output, provenance, test_evidence):
    from .build_provenance import exporter_identity, semantic_text_provenance
    artifacts = dict(artifacts)
    history = inference_history(output)
    model = semantic_text_provenance(state['source_sha256'], history['calls'], run_id=state['run_id'],
        purpose='incremental_semantic_narrative_and_story_metadata',
        input_sha256=state['input_transcript_sha256'], code_sha256=digest(exporter_identity()),
        prompt_sha256=digest([r.get('request_sha256') for r in history['calls']]))
    series = artifacts['editorial/story_series_proposals.json']['series']
    stories = [s for seq in series for s in seq['stories']]
    qa = artifacts['editorial/semantic_qa_proposals.json']['proposals']
    relations = artifacts['editorial/cross_arc_relations.json']['relations']
    completion = artifacts['editorial/narrative_completion_proposals.json']['proposals']
    visual = artifacts['social/story_visual_handoff.json']
    visual_stories = [s for seq in visual['series'] for s in seq['stories']]
    visual_report = artifacts['editorial/story_visual_completeness_report.json']
    visual_counts = {
        'stories_with_main_and_two_alternatives': sum(s.get('primary_title') is not None and len(s.get('alternative_titles', [])) == 2 for s in visual_stories),
        'subtitle_granularity_counts': visual_report.get('alignment_granularity_counts'),
        'visual_metadata_status_counts': visual_report.get('metadata_status_counts'),
        'grounded_highlight_candidates': sum(len(s.get('highlight_candidates', [])) for s in visual_stories),
        'editorial_title_proposals': sum(int(s.get('primary_title') is not None)+len(s.get('alternative_titles', [])) for s in visual_stories),
        'title_proposals_abstained': sum(s.get('primary_title') is None for s in visual_stories),
        'broken_references': 0, 'final_gate': 'SEMANTIC_HANDOFF_PARTIAL'}
    comparison = {'arcs_R5': len(legacy['editorial/story_arcs.json']), 'arcs_R51_preserved': len(legacy['editorial/story_arcs.json']),
        'cross_arc_relations': len(relations), 'relations_with_source_quotes': len(relations),
        'rejected_relations': len(artifacts['editorial/cross_arc_relations.json'].get('rejected_proposals') or []),
        'semantic_answers_proposed': sum(bool(q.get('answer_segment_ids')) for q in qa),
        'semantic_questions_not_evaluated': sum(q.get('evaluation_status') == 'NOT_EVALUATED' for q in qa),
        'canonical_qa_preserved': True, 'complete_explanations_proposed': sum(p['completeness_type']=='COMPLETE_EXPLANATION' for p in completion),
        'complete_narratives_proposed': sum(p['completeness_type']=='COMPLETE_NARRATIVE' for p in completion),
        'story_series': len(series), 'real_stories': len(stories), 'stories_per_series': [len(s['stories']) for s in series],
        'new_textual_model_calls': history['new_model_calls'], 'task_cache_hits': history['cache_hits'],
        'new_audiovisual_inference': False, 'source_scores_and_shortlist_preserved': True,
        'human_review_completed': False, 'preview_approved': False, 'publication_ready': False}
    comparison.update(visual_counts)
    # Coverage and human/audio uncertainty remain explicit; structural validity is separate.
    status = 'SEMANTIC_HANDOFF_PARTIAL'
    refs = {n.replace('/', '_').replace('.json', '')+'_ref': n for n in artifacts}
    handoff = {'schema_version': '1.0', 'contract': 'ldporto.semantic_narrative_handoff',
        'project_id': legacy['source/metadata.json'].get('source', {}).get('id'), 'run_id': state['run_id'],
        'schema_ref': 'schemas/semantic_handoff.schema.json',
        'source_sha256': state['source_sha256'], 'source_package_revision': 'R5.1',
        'analyzer_version': exporter_identity()['analyzer_version'], 'semantic_schema_version': '1.0',
        'original_build_fingerprint': legacy['SECOND_CURATION_MANIFEST.json'].get('code_fingerprint'),
        'replay_build_fingerprint': exporter_identity()['code_fingerprint'],
        'original_build_provenance_ref': 'SECOND_CURATION_MANIFEST.json#/build_provenance',
        'legacy_editorial_replay_ref': 'provenance/editorial_replay.json',
        'provenance_classification_ref': 'provenance/semantic_compatibility.json',
        'model_provenance_ref': 'provenance/semantic_text_inference.json', 'model_provenance': model,
        'model_runtime_identities': [{'model': m, 'model_digest': d, 'service_version': v}
            for m,d,v in sorted({(r.get('model'),r.get('model_digest'),r.get('service_version')) for r in history['runs']}, key=str)],
        'artifact_refs': refs, 'story_visual_handoff_ref': 'social/story_visual_handoff.json',
        'story_visual_schema_ref': 'schemas/story_visual_handoff.schema.json',
        'status': status, 'human_editorial_approval': False, 'publication_ready': False,
        'requires_curator_review': True, 'no_final_render': True,
        'readiness': {'narrative': 'PROPOSALS_REQUIRE_REVIEW', 'transcription': 'HUMAN_AUDIO_REVIEW_PENDING',
            'commercial': 'ORIGINAL_GATES_PRESERVED', 'rights': 'HUMAN_REVIEW_PENDING',
            'visual': 'METADATA_ONLY_NOT_RENDER_VALIDATED', 'camera': 'SOURCE_PRESERVE_NOT_REINFERRED'},
        'limitations': ['targeted_textual_replay_not_full_semantic_coverage',
            'source_quotes_verified_semantic_entailment_not_human_verified',
            'source_ASR_and_numbers_require_listening', 'no_new_frames_audio_or_render_validation']}
    artifacts.update({'SECOND_CURATION_SEMANTIC_HANDOFF.json': handoff,
        'schemas/semantic_handoff.schema.json': json.loads((Path(__file__).parents[2]/'schemas/semantic_handoff.schema.json').read_text(encoding='utf-8')),
        'provenance/semantic_text_inference.json': model, 'provenance/semantic_compatibility.json': provenance,
        'provenance/semantic_inference_ledger.json': history,
        'editorial/semantic_readiness_report.json': {'status': status, 'comparison': comparison,
            'publication_ready': False, 'limitations': handoff['limitations']},
        'R5_VS_R51.json': comparison, 'tests/semantic_test_evidence.json': test_evidence or {'status': 'not_supplied'},
        'provenance/semantic_replay_evidence.json': {**state, 'new_audiovisual_inference': False,
            'replay_input_reference_sha256': state['reference_package_sha256']}})
    for p in ('CHECKPOINT_B.json', 'CHECKPOINT_C.json'):
        if (output/p).is_file():
            artifacts['provenance/'+p] = json.loads((output/p).read_text(encoding='utf-8'))
    for request in (output/'inference_requests').glob('*.json'):
        artifacts['provenance/requests/'+request.name] = json.loads(request.read_text(encoding='utf-8'))
    for response in (output/'inference_cache').glob('*.json'):
        cached = json.loads(response.read_text(encoding='utf-8'))
        artifacts['provenance/model_responses/'+response.name] = {
            'task_id': cached['task_id'], 'payload': cached['payload'],
            'response_sha256': cached['response_sha256'], 'model_provenance': cached['provenance'],
            'scope': 'raw_model_output_not_accepted_evidence; consult_validated_editorial_artifacts'}
    table = ['# Resumo executivo de consumo\n',
        '| Série / parte | Título principal | Alternativas | Função | Fonte (s absolutos) | Legenda | Destaques | Revisão | Artefato |',
        '|---|---|---|---|---|---|---|---|---|']
    for seq in visual['series']:
        for s in seq['stories']:
            main = (s.get('primary_title') or {}).get('text') or 'Indisponível; consultar blocking_issues'
            alternatives = ' / '.join(t['text'] for t in s['alternative_titles']) or 'Abstenção registrada'
            spans = ', '.join(f"{v['start']:.2f}–{v['end']:.2f}" for v in s['source_intervals'])
            values = [seq['series_id']+' '+str(s['sequence_position'])+'/'+str(s['sequence_total']), main,
                alternatives, s['narrative_role'], spans, s['speech_subtitles']['alignment_granularity'],
                str(len(s['highlight_candidates'])), s['editorial_status']+'; revisão humana pendente',
                'social/story_visual_handoff.json#'+s['story_id']]
            table.append('| '+' | '.join(v.replace('|','/').replace('\n',' ') for v in values)+' |')
    artifacts['RESUMO_EXECUTIVO_CONSUMO.md'] = '\n'.join(table)+'\n'
    artifacts['README_R51_CURATOR.md'] = (
        '# Consumo R5.1 no VIDEO CURATOR\n\n'
        '1. Verifique SHA-256 do ZIP e todos os hashes de SECOND_CURATION_MANIFEST.json.\n'
        '2. Leia SECOND_CURATION_SEMANTIC_HANDOFF.json e valide social/story_visual_handoff.json pelo schema enviado.\n'
        '3. Resolva IDs em editorial/story_series_proposals.json, editorial/story_units.json e transcript/relevant_segments.jsonl.\n'
        '4. Vincule o original pelo source_sha256; os intervalos são segundos absolutos da fonte. '
        'edit_mapping é proposta e exige confirmar a montagem. Não substitua os sete Reels existentes.\n'
        '5. Consuma títulos, alternativas, captions, tokens de fala, destaques e capa como propostas. '
        'O Curator aplica seus presets de câmera, safe areas, watermark, instrumental, PNG final e render.\n'
        '6. Nenhuma etapa de importação destes metadados exige Whisper, Qwen, visão ou Director. '
        'Não use um comando que dispare novamente o Analyzer. Importação automática na versão instalada do Curator '
        'não foi modificada nem comprovada: valide sua compatibilidade antes de aplicar a uma revisão nova.\n'
        '7. Escuta, conferência de fatos, direitos, câmera, layout, preview e autorização de publicação continuam gates independentes.\n')
    artifacts['SEMANTIC_REVIEW.html'] = review_html(legacy, artifacts)
    return {n: sanitize_export(v) if isinstance(v, (dict, list)) else v for n, v in artifacts.items()}


def review_html(legacy, artifacts):
    esc = lambda value: html.escape(str(value), quote=True)
    visual = artifacts['social/story_visual_handoff.json']
    visual_by_id = {s['story_id']: s for series in visual.get('series', []) for s in series.get('stories', [])}
    header = ('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>R5.1 · Revisão semântica</title>'
        '<style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px;background:#111827;color:#edf2f7}'
        'a{color:#7dd3fc}article,details{background:#1f2937;padding:20px;margin:16px 0;border-radius:12px}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere}button,select{font:inherit;padding:8px;margin:6px}'
        'video{width:100%;max-height:440px}small{color:#cbd5e1}</style>'
        '<h1>VARIG · propostas R5.1</h1><p>Revisão textual. Sem aprovação humana, render ou autorização de publicação.</p>'
        '<p>Abra uma cópia local do original para conferir timestamps. O arquivo fica no navegador.</p>'
        '<input id="source" type="file" accept="video/*,audio/*"><video id="player" controls></video>')
    blocks = ['<p><small>SHA-256 exigido do original: '+esc(legacy['source/metadata.json']['sha256'])+
        '. Confirmar fonte e montagem no Curator. As escolhas abaixo alteram somente a visualização.</small></p>']
    for sequence in artifacts['editorial/story_series_proposals.json']['series']:
        blocks.append('<h2>'+esc(sequence.get('title', sequence['series_id']))+'</h2>')
        for story in sequence['stories']:
            sid = story['story_id']
            blocks.append('<article id="'+esc(sid)+'"><h3>'+esc(f"{story['sequence_position']}/{story['sequence_total']} · {story['narrative_role']}")+'</h3>')
            v = visual_by_id.get(sid, {})
            titles = ([v['primary_title']] if v.get('primary_title') else []) + v.get('alternative_titles', [])
            title_id = 'title_'+sid
            blocks.append('<h4 id="'+esc(title_id)+'">'+esc(titles[0]['text'] if titles else 'Título pendente de revisão')+'</h4>')
            if titles:
                blocks.append('<label>Título proposto <select data-output="'+esc(title_id)+'" onchange="document.getElementById(this.dataset.output).textContent=this.value">'+''.join(
                    '<option value="'+esc(t['text'])+'">'+esc(t['text'])+'</option>' for t in titles)+'</select></label>')
            blocks.append('<p>'+esc(story['summary'])+'</p>')
            blocks.append('<p>Granularidade: '+esc(v.get('speech_subtitles', {}).get('alignment_granularity', 'unavailable'))+
                ' · Destaques: '+str(len(v.get('highlight_candidates', [])))+
                ' · Regiões visuais: '+esc(v.get('layout_constraints', {}).get('subject_regions_status', 'UNKNOWN'))+'</p>')
            if v:
                blocks.append('<p><b>Gancho:</b> '+esc(v.get('opening_hook_text'))+' <small>(3–5 s sugeridos; sem render)</small></p>')
                blocks.append('<p><b>Descrição da postagem:</b> '+esc(v.get('social_caption', {}).get('text'))+
                    '<br><b>CTA:</b> '+esc(v.get('suggested_cta'))+'</p>')
                blocks.append('<details><summary>Fala, palavras e tempos absolutos</summary><pre>'+esc(json.dumps(v.get('speech_subtitles'),ensure_ascii=False,indent=2))+'</pre></details>')
                blocks.append('<details><summary>Destaques, capa, layout e pendências</summary><pre>'+esc(json.dumps(
                    {k:v.get(k) for k in ('highlight_candidates','cover_concept','layout_constraints','blocking_issues','audiovisual_policy')},ensure_ascii=False,indent=2))+'</pre></details>')
            for span in story['source_intervals']:
                blocks.append('<button onclick="document.getElementById(\'player\').currentTime='+str(span['start'])+'">'
                    +esc(f"{span['segment_id']} · {span['start']:.2f}–{span['end']:.2f}s")+'</button>')
            blocks.append('<details open><summary>Storyboard e evidências da fonte</summary><pre>'+esc(json.dumps(story,ensure_ascii=False,indent=2))+'</pre></details></article>')
    for name in ['social/narrative_editorial_title_proposals.json', 'social/story_visual_handoff.json',
                 'editorial/semantic_qa_proposals.json', 'editorial/cross_arc_relations.json',
                 'editorial/narrative_completion_proposals.json', 'editorial/global_topic_map.json',
                 'R5_VS_R51.json', 'provenance/semantic_compatibility.json']:
        blocks.append('<details><summary>'+esc(name)+'</summary><pre>'+esc(json.dumps(artifacts.get(name),ensure_ascii=False,indent=2))+'</pre></details>')
    return header+''.join(blocks)+('<script>document.getElementById("source").onchange=e=>{const f=e.target.files[0];'
        'if(f)document.getElementById("player").src=URL.createObjectURL(f)};</script></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description='R5.1 semantic-replay textual; no audiovisual pipeline')
    parser.add_argument('--semantic-replay', required=True, metavar='REFERENCE_ZIP')
    parser.add_argument('--semantic-output', required=True)
    parser.add_argument('--semantic-phase', choices=['semantic','curation','package'], default='semantic')
    parser.add_argument('--semantic-test-evidence')
    parser.add_argument('--semantic-config', help='Task budgets/retrieval config JSON; no provider replacement')
    args = parser.parse_args(argv)
    cfg = json.loads(Path(args.semantic_config).read_text(encoding='utf-8')) if args.semantic_config else {}
    tests = json.loads(Path(args.semantic_test_evidence).read_text(encoding='utf-8')) if args.semantic_test_evidence else None
    result = semantic_replay(args.semantic_replay, args.semantic_output, phase=args.semantic_phase,
                             cfg=cfg, test_evidence=tests)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
