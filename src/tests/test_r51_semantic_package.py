from copy import deepcopy
import json
from pathlib import Path

import pytest

from ldporto.semantic_narrative import build_semantic_analysis
from ldporto.semantic_package import validate_semantic_artifacts
from test_r51_semantic_narrative import legacy_fixture, callback


def sample():
    legacy = legacy_fixture()
    return legacy, build_semantic_analysis(legacy, callback(legacy))


def test_offline_consumer_accepts_evidence_bound_graph_without_model():
    legacy, artifacts = sample()
    before = deepcopy(legacy)
    result = validate_semantic_artifacts(artifacts, legacy)
    assert result['status'] == 'valid' and result['publication_ready'] is False
    assert legacy == before


@pytest.mark.parametrize('damage', ['node', 'interval', 'quote', 'publication', 'segment', 'unit', 'cycle', 'part'])
def test_consumer_rejects_freshly_serialized_damaged_derived_contract(damage):
    legacy, artifacts = sample()
    story = artifacts['editorial/story_series_proposals.json']['series'][0]['stories'][0]
    graph = artifacts['editorial/semantic_narrative_graph.json']
    if damage == 'node':
        graph['edges'][0]['target_node_id'] = 'DOES_NOT_EXIST'
    elif damage == 'interval':
        story['source_intervals'][0]['end'] = 999
    elif damage == 'quote':
        story['supporting_quotes'][0]['quote'] = 'Invented claim'
    elif damage == 'publication':
        story['publication_ready'] = True
    elif damage == 'segment':
        story['source_segment_ids'] = ['INVENTED']
    elif damage == 'unit':
        story['source_unit_ids'] = ['INVENTED']
    elif damage == 'cycle':
        story['previous_story_dependency'] = story['story_id']
    elif damage == 'part':
        story['sequence_total'] = 999
    assert validate_semantic_artifacts(artifacts, legacy)['status'] == 'invalid'


def test_rejected_inference_remains_diagnostic_without_becoming_valid_evidence():
    legacy, artifacts = sample()
    artifacts['editorial/cross_arc_relations.json']['rejected_proposals'] = [
        {'source_segment_ids': ['MISSING'], 'reason': 'source_unknown'}]
    assert validate_semantic_artifacts(artifacts, legacy)['status'] == 'valid'


@pytest.mark.parametrize('keyword,valid', [('navegação', True), ('fato inexistente', False)])
def test_keyword_is_a_literal_excerpt_instead_of_the_whole_segment(keyword, valid):
    legacy, artifacts = sample()
    artifacts['social/narrative_editorial_title_proposals.json'] = {'pieces': [{
        'validated_payload': {'keywords': [{'segment_id': 'S2', 'text': keyword, 'reason': 'KEY_FACT'}]}}]}
    assert (validate_semantic_artifacts(artifacts, legacy)['status'] == 'valid') is valid


def test_real_zip_consumer_resolves_new_provenance_and_preserves_legacy(tmp_path):
    from pathlib import Path
    from ldporto.core import digest, file_hash
    from ldporto.second_curation_export import build_core_package
    from ldporto.semantic_package import read_package, decoded_documents, export_semantic_package, validate_semantic_package
    from ldporto.semantic_replay import delivery_documents
    from ldporto.story_visual_handoff import build_story_visual_handoff
    from test_stage06_report_coherence import fixture
    analysis = fixture()
    analysis['metadata'].update(sha256='a'*64, source={'id':'synthetic-semantic-consumer'})
    from ldporto.build_provenance import editorial_replay_provenance
    persisted = tmp_path/'persisted_fixture.json'
    persisted.write_text('{"scope":"synthetic persisted evidence"}', encoding='utf-8')
    analysis['editorial_replay_provenance'] = editorial_replay_provenance(analysis,
        {'04_transcription.json': persisted}, {'analysis.json': persisted},
        ['narrative_handoff'], ['narrative_handoff'])
    original = build_core_package(analysis, output_dir=tmp_path/'original',
        cfg={'narrative_handoff_enabled':True, 'second_curation_visual_candidate_limit':0})
    reference = Path(original['path'])
    legacy = decoded_documents(read_package(reference))
    sem = build_semantic_analysis(legacy, lambda *a: ({'topics':[], 'abstentions':['synthetic empty input']}, {'origin':'fixture'}))
    def no_copy(*args):
        return {'primary_title':None, 'alternative_titles':[], 'opening_hook_text':None,
            'hook_supporting_quotes':[], 'social_caption':None, 'caption_supporting_quotes':[],
            'engagement_question':None, 'cta':None, 'keywords':[],
            'abstention_reason':'synthetic contract fixture'}, {'origin':'fixture_no_inference'}
    sem.update(build_story_visual_handoff(legacy, sem, no_copy))
    sem['provenance/assisted_editorial_draft.json'] = {'origin':'synthetic_only', 'publication_ready':False}
    sem['provenance/semantic_series_reuse.json'] = {'origin':'synthetic_only', 'publication_ready':False}
    state = {'run_id':'fixture', 'source_sha256':'a'*64, 'input_transcript_sha256':digest(legacy['transcript/relevant_segments.jsonl']),
             'reference_package_sha256':file_hash(reference)}
    documents = delivery_documents(legacy, sem, state, tmp_path, {'classification':'expected'}, {'scope':'synthetic-contract-test'})
    exported = export_semantic_package(reference, tmp_path/'export', documents)
    result = validate_semantic_package(exported['path'], reference=reference)
    original_members = read_package(reference)
    protected_count = sum(n != 'SECOND_CURATION_MANIFEST.json' and not n.startswith('schemas/') for n in original_members)
    assert result['status'] == 'valid' and result['legacy_documents_preserved'] == protected_count
    assert result['publication_ready'] is False


@pytest.mark.parametrize('damage', ['shortened', 'missing_span', 'wrong_segment'])
def test_consumer_rejects_intervals_inside_segment_that_misrepresent_selected_source(damage):
    legacy, artifacts = sample()
    story = artifacts['editorial/story_series_proposals.json']['series'][0]['stories'][0]
    if damage == 'shortened': story['source_intervals'][0]['end'] -= .1
    elif damage == 'missing_span': story['source_intervals'] = []
    else: story['source_intervals'][0] = {'segment_id': 'S2', 'start': 3.1, 'end': 8.}
    result = validate_semantic_artifacts(artifacts, legacy)
    assert result['status'] == 'invalid'
    assert any('source_interval_segment_correspondence' in error for error in result['errors'])


def test_consumer_independently_preserves_recorded_commercial_exclusion():
    legacy, artifacts = sample()
    legacy['editorial/story_units.json']['units'][0]['sequence_unit_eligibility'] = 'BLOCKED_RECORDED_COMMERCIAL'
    assert 'recorded_commercial_gate_preserved' in validate_semantic_artifacts(artifacts, legacy)['errors']


def visual_sample():
    from ldporto.story_visual_handoff import build_story_visual_handoff
    legacy, artifacts = sample()
    legacy['source/metadata.json'].update(sha256='a'*64, source={'id': 'SYNTHETIC_FIXTURE'})
    def unavailable(*args):
        raise RuntimeError('synthetic local model unavailable')
    artifacts.update(build_story_visual_handoff(legacy, artifacts, unavailable))
    return legacy, artifacts


def test_package_consumer_passes_full_artifacts_to_visual_validator():
    legacy, artifacts = visual_sample()
    result = validate_semantic_artifacts(artifacts, legacy)
    assert result['status'] == 'valid', result


def handoff_sample():
    legacy, artifacts = visual_sample()
    schema = json.loads((Path(__file__).parents[2]/'schemas/semantic_handoff.schema.json').read_text(encoding='utf-8'))
    artifacts['schemas/semantic_handoff.schema.json'] = schema
    artifacts['SECOND_CURATION_SEMANTIC_HANDOFF.json'] = {
        'schema_version': '1.0', 'contract': 'ldporto.semantic_narrative_handoff',
        'project_id': 'SYNTHETIC_FIXTURE', 'run_id': 'FIXTURE_RUN', 'source_sha256': 'a'*64,
        'analyzer_version': 'fixture', 'semantic_schema_version': '1.0',
        'original_build_fingerprint': None, 'replay_build_fingerprint': 'b'*64,
        'model_provenance': {}, 'artifact_refs': {'series': 'editorial/story_series_proposals.json'},
        'story_visual_handoff_ref': 'social/story_visual_handoff.json',
        'story_visual_schema_ref': 'schemas/story_visual_handoff.schema.json',
        'status': 'SEMANTIC_HANDOFF_PARTIAL', 'human_editorial_approval': False,
        'publication_ready': False, 'requires_curator_review': True, 'no_final_render': True,
        'readiness': {}, 'limitations': ['synthetic fixture without inference']}
    return legacy, artifacts


def test_semantic_handoff_schema_and_references_are_checked_offline():
    legacy, artifacts = handoff_sample()
    assert validate_semantic_artifacts(artifacts, legacy)['status'] == 'valid'


@pytest.mark.parametrize('damage', ['schema_missing', 'dialect', 'status', 'source', 'reference', 'approval'])
def test_consumer_rejects_invalid_semantic_handoff_metadata(damage):
    legacy, artifacts = handoff_sample()
    handoff = artifacts['SECOND_CURATION_SEMANTIC_HANDOFF.json']
    if damage == 'schema_missing': artifacts.pop('schemas/semantic_handoff.schema.json')
    elif damage == 'dialect': artifacts['schemas/semantic_handoff.schema.json']['$schema'] = 'http[PRIVATE_PATH]'
    elif damage == 'status': handoff['status'] = 'PUBLISH_READY'
    elif damage == 'source': handoff['source_sha256'] = 'c'*64
    elif damage == 'reference': handoff['artifact_refs']['series'] = 'editorial/NOT_INCLUDED.json'
    elif damage == 'approval': handoff['human_editorial_approval'] = True
    assert validate_semantic_artifacts(artifacts, legacy)['status'] == 'invalid'


@pytest.mark.parametrize('pointer,valid', [('#/duration', True), ('#/missing_build', False)])
def test_handoff_json_pointer_resolves_against_preserved_legacy(pointer, valid):
    legacy, artifacts = handoff_sample()
    artifacts['SECOND_CURATION_SEMANTIC_HANDOFF.json']['original_build_provenance_ref'] = 'source/metadata.json'+pointer
    result = validate_semantic_artifacts(artifacts, legacy)
    assert (result['status'] == 'valid') is valid
    if not valid:
        assert any('dangling_json_pointer' in error for error in result['errors'])


@pytest.mark.parametrize('summary,reason', [
    ('O instrumento ADF (Automatic Direction Finder) aponta a direção.', 'unsupported_parenthetical_expansion_or_name'),
    ('O instrumento ADF (automatic direction finder) aponta a direção.', 'unsupported_acronym_expansion'),
    ('O instrumento ADF orientava antes do GPS.', 'unsupported_acronym_in_claim:GPS'),
    ('O instrumento ADF apontava para Tucuruí.', 'unsupported_named_term_in_claim:Tucuruí'),
    ('O instrumento ADF apontava para uma antena (como a de Tucuruí).', 'unsupported_parenthetical_expansion_or_name:Tucuruí')])
def test_consumer_rejects_acronym_expansion_and_names_absent_from_selected_evidence(summary, reason):
    legacy = legacy_fixture()
    legacy['transcript/relevant_segments.jsonl'][2]['text'] = 'O instrumento ADF aponta a direção.'
    artifacts = build_semantic_analysis(legacy, callback(legacy))
    answer = artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]['answer_candidates'][0]
    answer['summary'] = summary
    result = validate_semantic_artifacts(artifacts, legacy)
    assert result['status'] == 'invalid'
    assert any(reason in error for error in result['errors'])


def test_source_local_parenthetical_acronym_and_name_remain_valid():
    legacy = legacy_fixture()
    legacy['transcript/relevant_segments.jsonl'][2]['text'] = 'O instrumento ADF (Automatic Direction Finder) aponta a direção para Tucuruí.'
    artifacts = build_semantic_analysis(legacy, callback(legacy))
    answer = artifacts['editorial/semantic_qa_proposals.json']['proposals'][0]['answer_candidates'][0]
    answer['summary'] = 'O instrumento ADF (Automatic Direction Finder) aponta para Tucuruí.'
    result = validate_semantic_artifacts(artifacts, legacy)
    assert result['status'] == 'valid', result
