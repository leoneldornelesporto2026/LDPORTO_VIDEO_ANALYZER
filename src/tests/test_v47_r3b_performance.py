"""R3B: tests for guarded overlap, schema-prompt opt-in and exact cache semantics."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Event
import os
import time

import numpy as np
import pytest

from ldporto.config import DEFAULTS, validate
from ldporto.performance import cpu_overlap_budget
from ldporto.semantic import call_ollama, semantic_cache_key, range_schema, PROMPT, PROMPT_VERSION, SCHEMA_VERSION
from ldporto.core import digest
from ldporto.ollama_local import profile_options
from ldporto.vision import PersonDetectionEngine


def group():
    return [{"segment_id": "S1", "start": 0., "end": 2., "text": "O que aprendemos?", "speaker": "SPEAKER_00"},
            {"segment_id": "S2", "start": 2., "end": 5., "text": "Aprendemos a pensar.", "speaker": "SPEAKER_00"}]


def config(compact=False):
    return {**DEFAULTS['semantic_analysis'], 'compact_prompt': compact}


def test_semantic_legacy_cache_key_identical_and_compact_uses_separate_cache():
    cfg, rows = config(), group()
    original = digest({'cache_contract': '4.3', 'input':
        [{key: item.get(key) for key in ('segment_id', 'start', 'end', 'speaker', 'text')} for item in rows],
        'prompt_version': PROMPT_VERSION, 'prompt_digest': digest(PROMPT),
        'schema_version': SCHEMA_VERSION, 'schema': range_schema(rows),
        'model': cfg['model'], 'model_fingerprint': 'abc',
        'options': profile_options(cfg), 'think': cfg.get('think'), 'structured_ranges': True})
    assert semantic_cache_key(cfg, rows, 'abc') == original
    assert semantic_cache_key(config(True), rows, 'abc') != original


def test_schema_still_sent_to_ollama_when_prompt_is_compact(monkeypatch):
    calls = []
    def fake(url, model, messages, schema, cfg):
        calls.append((messages[0]['content'], schema))
        return {'locale': 'pt-BR', 'topics': [], 'moments': []}, {}
    monkeypatch.setattr('ldporto.semantic.ollama_chat', fake)
    call_ollama(config(False), group())
    call_ollama(config(True), group())
    old_prompt, old_schema = calls[0]
    new_prompt, new_schema = calls[1]
    assert old_schema == new_schema
    assert 'Schema obrigatório:' in old_prompt
    assert 'Schema obrigatório:' not in new_prompt
    assert 'format' in new_prompt and 'segment_id' in str(new_schema)
    assert len(new_prompt) < len(old_prompt) - 400


@pytest.mark.parametrize('mode', ('parallel_hog_with_face', 'compact_prompt'))
def test_config_boolean_guard(mode):
    cfg = deepcopy(DEFAULTS)
    area = 'vision' if mode.startswith('parallel') else 'semantic_analysis'
    cfg[area][mode] = 1
    with pytest.raises(ValueError, match=mode):
        validate(cfg)


def test_budget_guards_unknown_ram_small_ram_small_cpu_and_opt_out():
    assert not cpu_overlap_budget(cpu_count=16, free_ram_bytes=10**10)['enabled']
    assert not cpu_overlap_budget(cpu_count=2, free_ram_bytes=10**10, requested=True)['enabled']
    assert not cpu_overlap_budget(cpu_count=16, free_ram_bytes=3*1024**3, requested=True)['enabled']
    assert cpu_overlap_budget(cpu_count=16, free_ram_bytes=5*1024**3, requested=True)['workers'] == 1
    assert cpu_overlap_budget(cpu_count=16, free_ram_bytes=5*1024**3, requested=True)['gpu_workers'] == 0
    assert not cpu_overlap_budget(cpu_count=0, free_ram_bytes=5*1024**3, requested=True)['enabled']
    assert cpu_overlap_budget(cpu_count=16, free_ram_bytes=5*1024**3, cpu_load_percent=87, requested=True)['reason'] == 'cpu_current_load_high'


class FakeFace:
    def __init__(self, *, hog_started=None):
        self.hog_started = hog_started
    def setInputSize(self, dims):
        pass
    def detect(self, frame):
        if self.hog_started is not None:
            assert self.hog_started.wait(timeout=1), 'HOG not running during face detection'
        result = np.zeros((1, 15), dtype=np.float32)
        result[0, :4] = [10, 10, 24, 30]
        result[0, 14] = 0.98
        return None, result


class FakeHog:
    def __init__(self, started=None):
        self.started = started
        self.calls = 0
    def detectMultiScale(self, frame, **kwargs):
        self.calls += 1
        if self.started is not None:
            self.started.set()
        return np.array([[4, 4, 65, 145]]), np.array([.91])


def detection_engine(*, parallel=False, started=None):
    import cv2
    from collections import defaultdict
    d = object.__new__(PersonDetectionEngine)
    d.cv2, d.cfg, d.notes = cv2, dict(DEFAULTS['vision']), []
    d.cfg.update({'detector_cascade': True, 'body_refresh_seconds': .5})
    d.phase_seconds, d.calls = defaultdict(float), defaultdict(int)
    d.face_history, d.last_body_time, d.last_shot = [], -float('inf'), None
    d.face, d.sface, d.hog, d.yolo = FakeFace(hog_started=started if parallel else None), None, FakeHog(started), None
    d._hog_pool = ThreadPoolExecutor(max_workers=1) if parallel else None
    d.overlap_budget = {'enabled': parallel, 'workers': 1 if parallel else 0}
    return d


def test_hog_overlap_returns_identical_detections_on_refresh_frame():
    event = Event()
    serial = detection_engine()
    concurrent = detection_engine(parallel=True, started=event)
    frame = np.zeros((180, 180, 3), dtype=np.uint8)
    try:
        a = serial.detect(frame, time=0., shot_id='SC1')
        b = concurrent.detect(frame, time=0., shot_id='SC1')
        assert a == b
        assert serial.hog.calls == concurrent.hog.calls == 1
        assert serial.calls['body_detection_calls'] == concurrent.calls['body_detection_calls'] == 1
        # Face-only short interval should NOT schedule an extra HOG detection.
        serial.detect(frame, time=.1, shot_id='SC1')
        concurrent.detect(frame, time=.1, shot_id='SC1')
        assert serial.hog.calls == concurrent.hog.calls == 1
    finally:
        concurrent.close()
        serial.close()
    assert concurrent._hog_pool is None


def test_hog_parallel_fallback_when_no_pool():
    d = detection_engine()
    frame = np.zeros((180, 180, 3), dtype=np.uint8)
    try:
        assert d.detect(frame, time=0., shot_id='S1')
        assert d.hog.calls == 1
    finally:
        d.close()


def test_semantic_chunk_cache_hit_never_rewrites_a_valid_record(tmp_path, monkeypatch):
    import logging
    import ldporto.semantic as semantic
    cfg = {**config(), 'backend': 'ollama', 'global_review': False}
    calls = []
    monkeypatch.setattr(semantic, 'ollama_service_info', lambda *a, **kw: {
        'reachable': True, 'models': [{'name': cfg['model'], 'digest': 'fp123'}]})
    def fake_inference(*args, **kw):
        calls.append(1)
        return {'locale': 'pt-BR', 'topics': [{
            'topic': 'Reflexão', 'summary': 'Conversa sobre aprendizado',
            'start_segment_id': 'S1', 'end_segment_id': 'S2', 'context_required': 'none'}],
            'moments': []}, {'eval_count': 10}
    monkeypatch.setattr(semantic, 'call_ollama', fake_inference)

    class Ctx:
        config = {'semantic_analysis': cfg, 'understanding': {}}
        force = False
        signature = 'test123'
        cache = tmp_path
        logger = logging.getLogger('semantic-cache-test')
        def progress(self, *args, **kwargs): pass
        def check_cancel(self, *args): pass
    ctx = Ctx()
    transcript = {'segments': group()}
    first = semantic.SemanticEngine().run(ctx, transcript)
    chunk_files = list((tmp_path/'semantic_chunks').glob('*.json'))
    assert len(chunk_files) == 1
    before = chunk_files[0].read_bytes()
    assert len(calls) == 1
    # Cached inference must survive a fresh SemanticEngine invocation unchanged.
    def no_writes(*args):
        raise AssertionError('valid cached chunk must not be rewritten')
    monkeypatch.setattr(semantic, 'write_json', no_writes)
    second = semantic.SemanticEngine().run(ctx, transcript)
    assert len(calls) == 1
    assert chunk_files[0].read_bytes() == before
    assert second['data']['semantic_metrics']['chunk_cache_rewrites_avoided'] == 1
    assert first['data']['semantic_metrics']['chunk_cache_rewrites_avoided'] == 0
