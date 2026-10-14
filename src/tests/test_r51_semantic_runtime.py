import json

import pytest

from ldporto.ollama_local import OllamaContentError
from ldporto.semantic_runtime import CachedSemanticInference, atomic_json, inference_history


SCHEMA = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'],
          'additionalProperties': False}
SERVICE = {'reachable': True, 'version': 'fixture', 'models': [{'name': 'qwen3:14b', 'digest': 'fixture-digest'}]}


def test_actual_task_cache_and_resume_do_not_send_duplicate_request(tmp_path):
    requests = []
    def client(*args):
        requests.append(args)
        return {'ok': True}, {'duration_seconds': 0.001, 'eval_count': 2}
    first = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    value, proof = first('relations:one', {'data': {'segment_id': 'S1'}}, SCHEMA)
    second = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    repeated, cached = second('relations:one', {'data': {'segment_id': 'S1'}}, SCHEMA)
    assert len(requests) == 1 and repeated == value and cached['call_id'] == proof['call_id']
    assert cached['cache_hit'] is True and inference_history(tmp_path)['new_model_calls'] == 1


def test_local_context_or_prompt_changes_only_dependent_task(tmp_path):
    sent = []
    def client(*args):
        sent.append(args)
        return {'ok': True}, {}
    a = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    a('QA:A', {'data': 'old A', 'instruction': 'p1'}, SCHEMA)
    a('QA:B', {'data': 'unchanged B', 'instruction': 'p1'}, SCHEMA)
    a('QA:A', {'data': 'new A', 'instruction': 'p1'}, SCHEMA)
    a('QA:B', {'data': 'unchanged B', 'instruction': 'p1'}, SCHEMA)
    a('QA:A', {'data': 'new A', 'instruction': 'p2'}, SCHEMA)
    assert len(sent) == 4 and a.cache_hits == 1


def test_timeout_is_recorded_and_not_automatically_retried(tmp_path):
    def client(*args):
        raise TimeoutError('timed out')
    engine = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    with pytest.raises(TimeoutError):
        engine('QA:A', {}, SCHEMA)
    assert len(engine.calls) == 1 and engine.calls[0]['status'] == 'timeout'


def test_invalid_json_has_only_one_repair_and_subsequent_resume_works(tmp_path):
    sent = []
    def client(*args):
        sent.append(args)
        if len(sent) == 1:
            raise OllamaContentError('fixture invalid', {'failure_category': 'invalid_json'})
        return {'ok': True}, {}
    engine = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    engine('QA:A', {}, SCHEMA)
    assert [r['status'] for r in engine.calls] == ['failed', 'ok']
    assert engine('QA:A', {}, SCHEMA)[1]['cache_hit'] is True


def test_persistent_invalid_json_abstains_after_bounded_repair(tmp_path):
    def client(*args):
        raise OllamaContentError('invalid', {'failure_category': 'invalid_json'})
    engine = CachedSemanticInference(tmp_path, service=SERVICE, client=client)
    with pytest.raises(OllamaContentError):
        engine('QA:A', {}, SCHEMA)
    assert len(engine.calls) == 2


def test_missing_model_does_not_install_download_or_send_request(tmp_path):
    engine = CachedSemanticInference(tmp_path, service={'reachable': False}, client=lambda *a: pytest.fail('called'))
    with pytest.raises(RuntimeError, match='unavailable'):
        engine('QA:A', {}, SCHEMA)
    assert engine.calls == []


def test_completed_cache_remains_available_when_service_stops(tmp_path):
    CachedSemanticInference(tmp_path, service=SERVICE, client=lambda *a: ({'ok': True}, {}))('QA:A', {}, SCHEMA)
    offline = {**SERVICE, 'reachable': False}
    result = CachedSemanticInference(tmp_path, service=offline, client=lambda *a: pytest.fail('called'))('QA:A', {}, SCHEMA)
    assert result[1]['cache_hit'] is True


def test_corrupt_cache_cannot_be_trusted(tmp_path):
    engine = CachedSemanticInference(tmp_path, service=SERVICE, client=lambda *a: ({'ok': True}, {}))
    engine('QA:A', {}, SCHEMA)
    p = next((tmp_path/'inference_cache').glob('*.json'))
    cached = json.loads(p.read_text())
    cached['payload']['ok'] = False
    atomic_json(p, cached)
    with pytest.raises(ValueError, match='checksum'):
        engine('QA:A', {}, SCHEMA)


def test_budget_enforced_before_next_network_call(tmp_path):
    engine = CachedSemanticInference(tmp_path, service=SERVICE, cfg={'max_new_calls': 1},
                                     client=lambda *a: ({'ok': True}, {}))
    engine('QA:A', {}, SCHEMA)
    with pytest.raises(RuntimeError, match='budget'):
        engine('QA:B', {}, SCHEMA)


def test_manifest_replace_is_atomic_and_finite(tmp_path):
    path = tmp_path/'state.json'
    atomic_json(path, {'state': 'before'})
    with pytest.raises(ValueError):
        atomic_json(path, {'state': float('nan')})
    assert json.loads(path.read_text()) == {'state': 'before'}
