"""R5.1 additive provenance canaries: synthetic receipts, no model or media."""
from copy import deepcopy

import pytest

from ldporto.build_provenance import (classify_provenance_mismatch, semantic_text_provenance,
                                      validate_semantic_text_provenance)
from ldporto.core import digest


SOURCE = 'a'*64
CHECKPOINT = 'b'*64


def drift():
    identity = {'analyzer_build': 'ORIGINAL', 'code_fingerprint': 'c'*64,
                'exporter': {'code_fingerprint': 'd'*64}, 'build_mismatch': True,
                'mismatch_reasons': ['analysis_code_differs_from_exporter',
                                     'stage_code_differs_from_exporter:20_handoff'],
                'execution_complete': False, 'unverified_stages': ['04_transcription'],
                'stages': {'20_handoff': {'status': 'ok', 'origin': 'executed',
                                         'checkpoint_sha256': CHECKPOINT, 'code_fingerprint': 'c'*64}}}
    replay = {'schema_version': '1.0', 'scope': 'editorial_replay_only', 'source_sha256': SOURCE,
              'new_model_calls': 0, 'new_audiovisual_inference': False,
              'full_pipeline_execution_attested': False, 'publication_ready': False,
              'executed_components': ['second_curation_export'], 'replay_exporter': deepcopy(identity['exporter']),
              'perception_run_identity': deepcopy(identity),
              'replay_code': {'build_provenance.py': {'sha256': 'e'*64, 'bytes': 123}},
              'reused_checkpoints': {'cache/source/20_handoff.json': {'sha256': CHECKPOINT, 'bytes': 123}},
              'reused_artifacts': {'questions_answers.json': {'sha256': 'f'*64, 'bytes': 456}}}
    return identity, replay


def test_expected_drift_becomes_explained_only_with_verified_original_checkpoint():
    identity, replay = drift(); before = deepcopy((identity, replay))
    expected = classify_provenance_mismatch(identity, replay, source_sha256=SOURCE)
    assert expected['classification'] == 'expected' and expected['pending_verification']
    explained = classify_provenance_mismatch(identity, replay, source_sha256=SOURCE,
                                              verified_checkpoint_sha256={'20_handoff': CHECKPOINT})
    assert explained['classification'] == 'explained' and not explained['pending_verification']
    assert explained['original_build_mismatch'] is True
    assert explained['original_mismatch_reasons'] == identity['mismatch_reasons']
    assert explained['stage20']['original'] == identity['stages']['20_handoff']
    assert explained['original_unverified_stages'] == ['04_transcription']
    assert not explained['changes_original_flags'] and not explained['full_pipeline_execution_attested']
    assert explained['original_execution_complete'] is False and (identity, replay) == before


@pytest.mark.parametrize('problem', ['source', 'checkpoint', 'receipt', 'schema', 'replay_calls'])
def test_expected_exporter_drift_cannot_hide_real_incompatibility(problem):
    identity, replay = drift(); verified = {'20_handoff': CHECKPOINT}; source = SOURCE; schema = True
    if problem == 'source': source = '0'*64
    elif problem == 'checkpoint': verified['20_handoff'] = '0'*64
    elif problem == 'receipt': identity['mismatch_reasons'].append('checkpoint_receipt_mismatch:04_transcription')
    elif problem == 'schema': schema = False
    elif problem == 'replay_calls': replay['new_model_calls'] = 1
    result = classify_provenance_mismatch(identity, replay, source_sha256=source,
               verified_checkpoint_sha256=verified, compatible_schema=schema)
    assert result['classification'] == 'incompatible'
    assert result['original_build_mismatch'] is True and not result['full_pipeline_execution_attested']


@pytest.mark.parametrize('problem', ['unknown_reason', 'missing_replay', 'missing_stage20', 'schema_unknown'])
def test_missing_or_unknown_explanation_stays_unresolved(problem):
    identity, replay = drift(); schema = True
    if problem == 'unknown_reason': identity['mismatch_reasons'].append('unrecognized_reason')
    elif problem == 'missing_replay': replay = None
    elif problem == 'missing_stage20': replay['reused_checkpoints'] = {'cache/source/15_semantic.json': {'sha256': CHECKPOINT, 'bytes': 1}}
    elif problem == 'schema_unknown': schema = None
    result = classify_provenance_mismatch(identity, replay, source_sha256=SOURCE, compatible_schema=schema)
    assert result['classification'] == 'unresolved'
    assert result['original_build_mismatch'] is True


def request(call_id='C1', **extra):
    return {'call_id': call_id, 'request_id': 'REQUEST_'+call_id, 'model': 'synthetic-text-model',
            'status': 'ok', 'origin': 'new_textual_inference', 'execution_mode': 'executed',
            'request_sent': True, 'response_sha256': 'f'*64, **extra}


def run(calls):
    return semantic_text_provenance(SOURCE, calls, run_id='SYNTHETIC_RUN', purpose='story_context_review',
             input_sha256={'transcript.json': '1'*64}, code_sha256={'text_runner.py': '2'*64}, prompt_sha256='3'*64)


def test_textual_requests_are_separate_from_zero_call_editorial_replay_and_history():
    identity, replay = drift(); before = deepcopy(replay)
    calls = [request('NEW', eval_count=20, generation_seconds=2.),
             request('HIST', origin='historical_source_inference', eval_count=9999),
             request('CACHE', origin='cache_reused', execution_mode='cache_reused', request_sent=False, eval_count=9999),
             request('FAIL', status='timeout')]
    result = run(calls)
    assert result['scope'] == 'semantic_text_analysis_only'
    assert result['new_textual_model_calls'] == result['observed_new_textual_model_calls'] == 2
    assert result['historical_record_count'] == result['cache_reuse_count'] == 1
    assert result['failed_new_textual_model_calls'] == 1
    assert result['new_textual_measurements']['eval_count'] == 20
    assert result['new_textual_measurements']['generation_seconds'] == 2.
    assert result['measurement_coverage']['eval_count'] == 1
    assert result['new_asr_calls'] == result['new_asd_calls'] == 0
    assert not result['new_audiovisual_inference'] and not result['overwrites_editorial_replay']
    assert replay == before and replay['new_model_calls'] == 0
    assert validate_semantic_text_provenance(result, SOURCE) == []


def test_unknown_request_origin_and_missing_measurements_never_become_fake_zero_cost():
    result = run([request('KNOWN'), {'call_id': 'UNKNOWN', 'model': 'synthetic-text-model', 'status': 'ok'}])
    assert result['observed_new_textual_model_calls'] == 1 and result['new_textual_model_calls'] is None
    assert result['unverified_records'] and result['new_textual_measurements']['duration_seconds'] is None
    assert result['new_textual_measurements']['eval_count'] is None
    assert validate_semantic_text_provenance(result, SOURCE) == []


def test_duplicate_request_ids_do_not_inflate_exact_call_count():
    result = run([request(), request()])
    assert result['new_textual_model_calls'] is None and result['observed_new_textual_model_calls'] == 1
    assert result['unverified_records']


@pytest.mark.parametrize('problem', ['cached_sent', 'non_text', 'wrong_source', 'counter_tampering'])
def test_textual_provenance_rejects_scope_and_counter_contradictions(problem):
    if problem == 'cached_sent':
        with pytest.raises(ValueError, match='cache_reuse_cannot_claim_request_sent'):
            run([request(execution_mode='cache_reused')])
    elif problem == 'non_text':
        with pytest.raises(ValueError, match='non_textual_inference_record'):
            run([request(modality='audio')])
    else:
        document = run([request()])
        if problem == 'wrong_source':
            assert validate_semantic_text_provenance(document, '0'*64)
        else:
            document['new_textual_model_calls'] = 0
            document['provenance_sha256'] = digest({k:v for k,v in document.items() if k!='provenance_sha256'})
            assert validate_semantic_text_provenance(document, SOURCE) == ['semantic_text_counters_or_scope_disagree']
