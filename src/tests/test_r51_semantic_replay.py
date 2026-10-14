import json
from pathlib import Path

import pytest

import ldporto.build_provenance as provenance
import ldporto.semantic_replay as replay
from ldporto.semantic_runtime import atomic_json
from test_r51_semantic_narrative import legacy_fixture, callback


def configure(monkeypatch, tmp_path, *, interrupted=False):
    legacy = legacy_fixture()
    legacy['source/metadata.json'].update(sha256='a'*64, source={'id': 'fixture'})
    legacy['SECOND_CURATION_MANIFEST.json'] = {'build_provenance': {}}
    members = {n: ('\n'.join(json.dumps(row) for row in v).encode() if n.endswith('.jsonl') else json.dumps(v).encode())
               for n, v in legacy.items()}
    reference = tmp_path/'reference.zip'
    reference.write_bytes(b'explicitly synthetic reference; reader mocked')
    monkeypatch.setattr(replay, 'read_package', lambda path: members)
    monkeypatch.setattr(provenance, 'classify_provenance_mismatch', lambda *a, **kw: {'classification': 'expected'})
    invoke = callback(legacy)
    class Runtime:
        def __init__(self, output, **kwargs):
            self.output, self.calls, self.cache_hits = output, [], 0
            assert (output/'semantic_state.json').is_file(), 'ownership must precede model work'
        def __call__(self, task, context, schema):
            if interrupted:
                raise KeyboardInterrupt('synthetic killed first request')
            return invoke(task, context, schema)
    monkeypatch.setattr(replay, 'CachedSemanticInference', Runtime)
    return reference


def test_first_request_interruption_leaves_resumable_owned_directory(monkeypatch, tmp_path):
    reference = configure(monkeypatch, tmp_path, interrupted=True)
    output = tmp_path/'semantic'
    with pytest.raises(KeyboardInterrupt):
        replay.semantic_replay(reference, output)
    state = json.loads((output/'semantic_state.json').read_text())
    assert state['phase'] == 'P0_VALIDATED'
    configure(monkeypatch, tmp_path)
    result = replay.semantic_replay(reference, output)
    assert result['phase'] == 'B_VALIDATED' and result['validation']['status'] == 'valid'


def test_package_cannot_precede_semantic_and_visual_checkpoints(monkeypatch, tmp_path):
    reference = configure(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='checkpoint_B_required'):
        replay.semantic_replay(reference, tmp_path/'new', phase='package')
    replay.semantic_replay(reference, tmp_path/'complete_B')
    with pytest.raises(ValueError, match='checkpoint_C_required'):
        replay.semantic_replay(reference, tmp_path/'complete_B', phase='package')


def test_artifact_loading_rejects_traversal_before_access(tmp_path):
    with pytest.raises(ValueError, match='unsafe_persisted'):
        replay._load_artifacts(tmp_path, {'artifact_hashes': {'../../anything.json': 'a'*64}})


def test_changed_derived_revision_preserves_previous_artifact_bytes(tmp_path):
    state = {'artifact_hashes': {}}
    replay._checkpoint(tmp_path, state, {'editorial/example.json': {'value': 'first'}}, 'B_VALIDATED')
    original = (tmp_path/'artifacts/editorial/example.json').read_bytes()
    replay._checkpoint(tmp_path, state, {'editorial/example.json': {'value': 'second'}}, 'B_VALIDATED')
    preserved = list((tmp_path/'revisions').glob('*/artifacts/editorial/example.json'))
    assert len(preserved) == 1 and preserved[0].read_bytes() == original
    assert json.loads((tmp_path/'artifacts/editorial/example.json').read_text())['value'] == 'second'


def test_corrupt_persisted_artifact_is_rejected(tmp_path):
    state = {'artifact_hashes': {}}
    replay._checkpoint(tmp_path, state, {'editorial/example.json': {'value': 'first'}}, 'B_VALIDATED')
    (tmp_path/'artifacts/editorial/example.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        replay._load_artifacts(tmp_path, state)


def test_extractive_qa_repair_constrains_summary_without_forcing_answer():
    from ldporto.semantic_narrative import task_schema
    schema = task_schema('qa', 1)
    import copy
    original = copy.deepcopy(schema)
    result = replay.evidence_summary_schema('semantic.qa.Q', {'data': {'segments': [
        {'text': 'Como funciona?'}, {'text': 'O instrumento aponta a direção.'}]}}, schema)
    fields = result['properties']['proposals']['items']['properties']
    assert fields['answers']['items']['properties']['summary']['enum'] == ['O instrumento aponta a direção.']
    assert 'UNRESOLVED' in fields['status']['enum'] and schema == original


def test_extractive_repair_leaves_title_and_global_schemas_unchanged():
    from ldporto.semantic_narrative import task_schema
    schema = task_schema('global', 2)
    result = replay.evidence_summary_schema('semantic.global_topic_map', {'data': {'segments': [{'text': 'Fala.'}]}}, schema)
    assert result == schema


def test_unsafe_abstraction_can_be_quarantined_without_changing_answer_ids():
    payload = {'proposals': [{'status': 'ANSWER_SUPPORTED', 'reasoning_summary': 'Invented GPS claim',
        'uncertainty_reasons': [], 'answers': [{'answer_segment_ids': ['S'], 'summary': 'Invented expansion',
        'supporting_quotes': [{'segment_id': 'S', 'quote': 'O ADF aponta a direção.'}]}]}]}
    context = {'data': {'segments': [{'segment_id': 'S', 'text': 'O ADF aponta a direção.'}]}}
    fixed, provenance = replay.source_excerpt_repair('semantic.qa.Q', context, payload, {'call_id': 'actual_ref'})
    proposal = fixed['proposals'][0]
    assert proposal['status'] == 'ANSWER_PROPOSED' and proposal['answers'][0]['answer_segment_ids'] == ['S']
    assert proposal['answers'][0]['summary'] == 'O ADF aponta a direção.'
    assert payload['proposals'][0]['answers'][0]['summary'] == 'Invented expansion'
    assert provenance['source_verification_transform']['raw_model_output_preserved'] is True


def test_excerpt_repair_cannot_create_a_quote_or_answer_from_unknown_source():
    payload = {'proposals': [{'status': 'ANSWER_SUPPORTED', 'answers': [
        {'answer_segment_ids': ['MISSING'], 'summary': 'Claim',
         'supporting_quotes': [{'segment_id': 'MISSING', 'quote': 'Claim'}]}]}]}
    assert replay.source_excerpt_repair('semantic.qa.Q', {'data': {'segments': []}}, payload, {})[0] == payload


def test_abstention_preserves_a_hash_verified_prior_series_for_same_source(tmp_path):
    from ldporto.semantic_narrative import build_semantic_analysis
    legacy = legacy_fixture()
    old = build_semantic_analysis(legacy, callback(legacy))
    name = 'editorial/story_series_proposals.json'
    state = {'artifact_hashes': {}, 'reference_package_sha256': 'same-source'}
    replay._checkpoint(tmp_path, state, {name: old[name]}, 'B_VALIDATED')
    replay._checkpoint(tmp_path, state, {name: {'series': []}}, 'B_VALIDATED')
    current = {name: {'series': []}}
    result = replay.reuse_grounded_series(current, legacy, tmp_path, state)
    assert result[name] == old[name]
    assert result['provenance/semantic_series_reuse.json']['publication_ready'] is False


def test_prior_series_for_other_source_is_never_reused(tmp_path):
    from ldporto.semantic_narrative import build_semantic_analysis
    legacy = legacy_fixture()
    old = build_semantic_analysis(legacy, callback(legacy))
    name = 'editorial/story_series_proposals.json'
    state = {'artifact_hashes': {}, 'reference_package_sha256': 'source-one'}
    replay._checkpoint(tmp_path, state, {name: old[name]}, 'B_VALIDATED')
    replay._checkpoint(tmp_path, state, {name: {'series': []}}, 'B_VALIDATED')
    current = {name: {'series': []}}
    assert replay.reuse_grounded_series(current, legacy, tmp_path, {'reference_package_sha256': 'source-two'})[name]['series'] == []
