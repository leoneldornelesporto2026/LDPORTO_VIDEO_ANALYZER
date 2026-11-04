"""Text-only semantic boundary tests: no model, media, or human accuracy claims."""
from copy import deepcopy

import jsonschema
import pytest

from ldporto.semantic_narrative import build_semantic_analysis, source_claim_issues, task_schema


def legacy_fixture():
    rows = [
        {'segment_id': 'S1', 'text': 'Como funciona a navegação?', 'start': 0., 'end': 3., 'speaker': 'A'},
        {'segment_id': 'S2', 'text': 'A navegação usa sinais de rádio.', 'start': 3.1, 'end': 8., 'speaker': 'A'},
        {'segment_id': 'S3', 'text': 'Retomando a navegação, o instrumento aponta a direção.', 'start': 100., 'end': 106., 'speaker': 'B'},
        {'segment_id': 'S4', 'text': 'Assim a direção fica compreensível e a explicação termina.', 'start': 300., 'end': 306., 'speaker': 'B'},
    ]
    arcs = [{'story_arc_id': aid, 'title': 'Navegação', 'evidence_segment_ids': ids}
            for aid, ids in [('A1', ['S1', 'S2']), ('A2', ['S3']), ('A3', ['S4'])]]
    units = [{'unit_id': 'U'+str(i), 'story_arc_ids': [aid], 'source_segment_ids': [sid],
              'eligibility': 'PROVISIONAL_REVIEW_READY'}
             for i, (sid, aid) in enumerate([('S1', 'A1'), ('S2', 'A1'), ('S3', 'A2'), ('S4', 'A3')], 1)]
    return {'transcript/relevant_segments.jsonl': rows, 'source/metadata.json': {'duration': 400.},
        'editorial/story_arcs.json': arcs, 'editorial/story_units.json': {'units': units},
        'editorial/qa_pairs.json': [{'question_id': 'Q_0015', 'question_segment_ids': ['S1'],
                                  'question': rows[0]['text']}], 'editorial/narrative_graph.json': {'nodes': [], 'edges': []}}


def quote(legacy, sid):
    return {'segment_id': sid, 'quote': next(r['text'] for r in legacy['transcript/relevant_segments.jsonl'] if r['segment_id'] == sid)}


def callback(legacy, mutate=None):
    def infer(task_id, context, schema):
        q = lambda sid: quote(legacy, sid)
        if task_id == 'semantic.global_topic_map':
            payload = {'topics': [{'label': 'Explicação de navegação', 'kind': 'TOPIC',
                'source_arc_ids': ['A1', 'A2', 'A3'], 'supporting_quotes': [q('S1'), q('S3')],
                'search_terms': ['navegação', 'direção']}], 'abstentions': []}
        elif task_id.startswith('semantic.relations.'):
            payload = {'relations': [{'source_arc_id': 'A1', 'target_arc_id': 'A2',
                'relation_type': 'CONTINUES', 'semantic_basis': 'SEMANTIC_CONTINUITY',
                'supporting_quotes': [q('S2'), q('S3')], 'reasoning_summary': 'Retoma a explicação de navegação.',
                'confidence_basis': ['Retomada textual explícita.'], 'contradictions': []}], 'abstentions': []}
        elif task_id.startswith('semantic.qa.'):
            payload = {'proposals': [{'question_id': 'Q_0015', 'status': 'ANSWER_SUPPORTED',
                'answers': [{'answer_segment_ids': ['S2', 'S3'], 'summary': 'Explica sinais de rádio e direção.',
                    'answer_relation': 'INDIRECT', 'supporting_quotes': [q('S2'), q('S3')]}],
                'reasoning_summary': 'A explicação se desenvolve em outra passagem.',
                'uncertainty_reasons': [], 'contradictions': []}], 'abstentions': []}
        elif task_id.startswith('semantic.completion.'):
            payload = {'proposals': [{'source_arc_ids': ['A1', 'A2', 'A3'], 'content_type': 'EXPLANATION',
                'completeness_type': 'COMPLETE_EXPLANATION', 'components': [
                    {'component': component, 'supporting_quotes': [q(sid)]} for component, sid in
                    [('QUESTION', 'S1'), ('EXPLANATION', 'S2'), ('EXPLANATION', 'S3'), ('RESULT', 'S4')]],
                'missing_components': [], 'summary': 'Explica a navegação e a indicação de direção.',
                'contradictions': [], 'narrative_dependencies': []}], 'abstentions': []}
        else:
            stories = []
            for i, (sid, uid, role) in enumerate([('S1', 'U1', 'HOOK'), ('S3', 'U3', 'EXPLANATION'), ('S4', 'U4', 'CLOSING')], 1):
                stories.append({'source_unit_ids': [uid], 'source_segment_ids': [sid], 'narrative_role': role,
                    'summary': q(sid)['quote'], 'context_required': [], 'previous_story_position': i-1 if i > 1 else None,
                    'next_story_relationship': 'Continua a explicação.' if i < 3 else None,
                    'suggested_opening': 'Apresentar a fala original.', 'suggested_ending': 'Preservar o fim da fala.',
                    'new_information': q(sid)['quote'], 'supporting_quotes': [q(sid)], 'missing_information': []})
            payload = {'series': [{'title': 'Navegação explicada', 'summary': 'Pergunta, explicação e encerramento.',
                'stories': stories, 'continuity_checks': {k: True for k in ['first_story_self_contained',
                    'progression_without_repetition', 'order_understandable', 'hook_closure_honest', 'essential_context_preserved']},
                'contradictions': [], 'missing_information': [], 'ending_status': 'SOURCE_CLOSURE_PROPOSED'}], 'abstentions': []}
        if mutate:
            mutate(task_id, payload)
        return payload, {'model': 'fixture-no-inference', 'execution_kind': 'synthetic_test'}
    return infer


def run(mutate=None, legacy=None, cfg=None):
    legacy = legacy or legacy_fixture()
    return build_semantic_analysis(legacy, callback(legacy, mutate), cfg=cfg)


def test_distant_arcs_qa_completion_and_three_stories_preserve_legacy_and_gates():
    legacy = legacy_fixture(); before = deepcopy(legacy)
    artifacts = run(legacy=legacy)
    relation = artifacts['editorial/cross_arc_relations.json']['relations'][0]
    assert relation['source_intervals'] == [{'segment_id': 'S2', 'start': 3.1, 'end': 8.}, {'segment_id': 'S3', 'start': 100., 'end': 106.}]
    assert relation['requires_review'] and not relation['causality_human_verified']
    qa = artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]
    assert qa['status'] == 'ANSWER_SUPPORTED' and not qa['confirmed'] and not qa['changes_canonical_qa']
    complete = artifacts['editorial/narrative_completion_proposals.json']['proposals'][0]
    assert complete['completeness_type'] == 'COMPLETE_EXPLANATION' and not complete['certified_complete']
    series = artifacts['editorial/story_series_proposals.json']['series'][0]
    assert len(series['stories']) == 3 and series['stories'][2]['previous_story_dependency'] == series['stories'][1]['story_id']
    assert all(not s['publication_ready'] and not s['preview_approved'] for s in series['stories'])
    assert legacy == before
    graph = artifacts['editorial/semantic_narrative_graph.json']
    node_ids = {node['node_id'] for node in graph['nodes']}
    assert any(node['kind'] == 'ANSWER' for node in graph['nodes'])
    assert any(edge['relation_type'] == 'ANSWERS' for edge in graph['edges'])
    assert all(edge['source_node_id'] in node_ids and edge['target_node_id'] in node_ids for edge in graph['edges'])


@pytest.mark.parametrize('kind', ['global', 'relations', 'qa', 'completion', 'series'])
def test_task_schemas_are_real_dialects(kind):
    jsonschema.Draft202012Validator.check_schema(task_schema(kind))


@pytest.mark.parametrize('change,reason', [
    ('unknown_arc', 'relation_unknown'), ('unknown_segment', 'quote_segment_unknown'),
    ('fabricated_quote', 'nonliteral_supporting_quote'), ('causal', 'causal_relation_without'),
    ('same_event_theme', 'theme_similarity'), ('number', 'unsupported_numeric_claim')])
def test_rejects_ungrounded_relations(change, reason):
    def mutate(task, payload):
        if not task.startswith('semantic.relations.'):
            return
        relation = payload['relations'][0]
        if change == 'unknown_arc': relation['target_arc_id'] = 'INVENTED'
        if change == 'unknown_segment': relation['supporting_quotes'][1]['segment_id'] = 'INVENTED'
        if change == 'fabricated_quote': relation['supporting_quotes'][1]['quote'] = 'Uma frase inexistente.'
        if change == 'causal': relation.update(relation_type='CAUSES', semantic_basis='EXPLICIT_CAUSAL_STATEMENT')
        if change == 'same_event_theme': relation.update(relation_type='SAME_EVENT', semantic_basis='THEME_ONLY')
        if change == 'number': relation['reasoning_summary'] = 'A direção mudou em 999 graus.'
    artifacts = run(mutate)
    report = artifacts['editorial/cross_arc_relations.json']
    assert not report['relations'] and reason in report['rejected_proposals'][0]['reason']
    assert artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]['status'] == 'ANSWER_SUPPORTED'


def test_missing_result_downgrades_explanation_without_demanding_climax():
    def mutate(task, payload):
        if task.startswith('semantic.completion.'):
            proposal = payload['proposals'][0]
            proposal['components'] = proposal['components'][:-1]
            proposal['source_arc_ids'] = ['A1', 'A2']
    completion = run(mutate)['editorial/narrative_completion_proposals.json']['proposals'][0]
    assert completion['completeness_type'] == 'PARTIAL_RESOLUTION'
    assert completion['missing_components'] == ['RESULT']


@pytest.mark.parametrize('change', ['incompatible_completion', 'cycle', 'commercial', 'repetition', 'too_long'])
def test_semantic_and_series_guards(change):
    legacy = legacy_fixture()
    if change == 'commercial': legacy['editorial/story_units.json']['units'][2]['eligibility'] = 'BLOCKED_RECORDED_COMMERCIAL'
    if change == 'too_long': legacy['transcript/relevant_segments.jsonl'][2]['end'] = 200.
    def mutate(task, payload):
        if change == 'incompatible_completion' and task.startswith('semantic.completion.'):
            payload['proposals'][0]['completeness_type'] = 'COMPLETE_NARRATIVE'
        if task.startswith('semantic.series.'):
            if change == 'cycle': payload['series'][0]['stories'][0]['previous_story_position'] = 1
            if change == 'repetition': payload['series'][0]['stories'][1] = deepcopy(payload['series'][0]['stories'][0])
    artifacts = run(mutate, legacy)
    if change == 'incompatible_completion':
        assert not artifacts['editorial/narrative_completion_proposals.json']['proposals']
    else:
        assert not artifacts['editorial/story_series_proposals.json']['series']


@pytest.mark.parametrize('error', [TimeoutError('bounded timeout'), RuntimeError('model unavailable'), ValueError('invalid JSON')])
def test_model_failures_abstain_without_fabricating(error):
    legacy = legacy_fixture()
    def fail(*args):
        raise error
    artifacts = build_semantic_analysis(legacy, fail)
    assert not artifacts['editorial/story_series_proposals.json']['series']
    assert artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]['status'] == 'UNRESOLVED'
    assert all(t['status'] == 'ABSTAINED' for t in artifacts['editorial/semantic_resolver_diagnostics.json']['tasks'])


def test_unselected_questions_are_not_claimed_as_evaluated():
    qa = run(cfg={'qa_question_ids': []})['editorial/semantic_qa_proposals.json']['proposals'][0]
    assert qa['status'] == 'UNRESOLVED' and qa['evaluation_status'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('text,source,entities,expected', [
    ('A direção era 999.', 'A direção era 270.', (), 'unsupported_numeric_claim'),
    ('Não houve erro.', 'Houve erro.', (), 'unsupported_negative_assertion'),
    ('A antena evitou o erro.', 'A antena poderia evitar o erro.', (), 'conditional_source_promoted_to_factual_cause'),
    ('João explicou.', 'O narrador explicou.', ('João',), 'unsupported_named_entity:João')])
def test_shared_claim_guard_reports_conservative_blockers(text, source, entities, expected):
    assert expected in source_claim_issues(text, source, entity_names=entities)


def test_invalid_source_duration_is_rejected_before_model():
    legacy = legacy_fixture(); legacy['transcript/relevant_segments.jsonl'][-1]['end'] = 500.
    with pytest.raises(ValueError, match='exceeds_source'):
        build_semantic_analysis(legacy, lambda *args: pytest.fail('model must not run'))


@pytest.mark.parametrize('status', ['RHETORICAL', 'ANSWER_NOT_EXPECTED', 'UNRESOLVED',
                                    'PARTIAL_ANSWER', 'CONTRADICTORY_EVIDENCE'])
def test_qa_states_preserve_abstention_partial_and_contradictory_evidence(status):
    def mutate(task, payload):
        if not task.startswith('semantic.qa.'):
            return
        proposal = payload['proposals'][0]
        proposal['status'] = status
        if status in {'RHETORICAL', 'ANSWER_NOT_EXPECTED', 'UNRESOLVED'}:
            proposal['answers'] = []
        elif status == 'PARTIAL_ANSWER':
            proposal['answers'][0]['answer_relation'] = 'PARTIAL'
        else:
            proposal['contradictions'] = ['Interpretações conflitantes exigem revisão.']
    qa = run(mutate)['editorial/semantic_qa_proposals.json']['proposals'][0]
    assert qa['status'] == status and not qa['confirmed']


def test_multiple_answer_candidates_stay_ambiguous():
    def mutate(task, payload):
        if task.startswith('semantic.qa.'):
            payload['proposals'][0]['answers'].append({'answer_segment_ids': ['S4'],
                'summary': 'A direção fica compreensível.', 'answer_relation': 'INDIRECT',
                'supporting_quotes': [quote(legacy_fixture(), 'S4')]})
    qa = run(mutate)['editorial/semantic_qa_proposals.json']['proposals'][0]
    assert qa['status'] == 'HUMAN_REVIEW_REQUIRED' and len(qa['answer_candidates']) == 2


def test_previous_answer_reference_uses_earlier_source_without_changing_time():
    legacy = legacy_fixture()
    legacy['editorial/qa_pairs.json'][0]['question_segment_ids'] = ['S3']
    def mutate(task, payload):
        if task.startswith('semantic.qa.'):
            answer = payload['proposals'][0]['answers'][0]
            answer.update(answer_segment_ids=['S2'], supporting_quotes=[quote(legacy, 'S2')],
                          answer_relation='PREVIOUS_REFERENCE', summary='A navegação usa sinais de rádio.')
    qa = run(mutate, legacy)['editorial/semantic_qa_proposals.json']['proposals'][0]
    assert qa['answer_candidates'][0]['source_intervals'][0]['end'] < qa['question_intervals'][0]['start']


def test_single_story_preserves_distant_intervals_and_counts_only_source_duration():
    def mutate(task, payload):
        if task.startswith('semantic.series.'):
            story = payload['series'][0]['stories'][0]
            story.update(source_segment_ids=['S1', 'S2', 'S3', 'S4'], source_unit_ids=['U1', 'U2', 'U3', 'U4'])
            payload['series'][0]['stories'] = [story]
    series = run(mutate)['editorial/story_series_proposals.json']['series'][0]
    story = series['stories'][0]
    assert story['sequence_total'] == 1 and len(story['source_intervals']) == 4
    assert story['estimated_source_duration'] == pytest.approx(19.9)
    assert story['assembly_disclosure_required'] and not story['source_is_continuous']
    assert story['next_story_relationship'] is None


def test_open_series_remains_an_explicit_unapproved_proposal():
    def mutate(task, payload):
        if task.startswith('semantic.series.'):
            payload['series'][0].update(ending_status='OPEN_ENDING_DECLARED', missing_information=['Conclusão ausente.'])
    series = run(mutate)['editorial/story_series_proposals.json']['series'][0]
    assert series['ending_status'] == 'OPEN_ENDING_DECLARED' and not series['publication_ready']


def test_causal_counterfactual_is_rejected_even_with_a_causal_marker():
    legacy = legacy_fixture()
    legacy['transcript/relevant_segments.jsonl'][2]['text'] = 'A antena poderia ajudar porque indicava a direção.'
    def mutate(task, payload):
        if task.startswith('semantic.relations.'):
            payload['relations'][0].update(relation_type='CAUSES', semantic_basis='EXPLICIT_CAUSAL_STATEMENT')
    report = run(mutate, legacy)['editorial/cross_arc_relations.json']
    assert not report['relations']
    assert 'counterfactual_or_uncertain_cause' in report['rejected_proposals'][0]['reason']


def test_independent_qa_runs_when_global_model_task_fails():
    legacy = legacy_fixture(); valid = callback(legacy)
    def infer(task, context, schema):
        if task == 'semantic.global_topic_map':
            raise TimeoutError('global timeout')
        return valid(task, context, schema)
    artifacts = build_semantic_analysis(legacy, infer)
    assert artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]['status'] == 'ANSWER_SUPPORTED'
    assert not artifacts['editorial/story_series_proposals.json']['series']


def test_structurally_invalid_model_json_fails_closed():
    def infer(*args):
        return {'topics': 'invalid-array', 'unrequested': 'field'}, {'model': 'fixture'}
    artifacts = build_semantic_analysis(legacy_fixture(), infer)
    assert all(t['status'] == 'ABSTAINED' for t in artifacts['editorial/semantic_resolver_diagnostics.json']['tasks'])


def test_retrieval_provides_canonical_context_in_both_distant_arcs():
    legacy = legacy_fixture(); inspect = callback(legacy); seen = []
    def infer(task, context, schema):
        if task.startswith('semantic.relations.'):
            seen.append({row['segment_id'] for row in context['data']['segments']})
        return inspect(task, context, schema)
    build_semantic_analysis(legacy, infer)
    assert seen and {'S1', 'S3', 'S4'} <= seen[0]
