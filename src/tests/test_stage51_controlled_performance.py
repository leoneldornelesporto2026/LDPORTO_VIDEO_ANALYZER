"""Deterministic fixtures only; no local service, models or media."""
from copy import deepcopy
import importlib.util
import json
import logging
from pathlib import Path
import sys

import pytest

from ldporto.config import DEFAULTS
from ldporto.core import Context, digest, ok
from ldporto.performance import vision_resource_plan, cpu_overlap_budget
from ldporto.semantic import semantic_cache_key
from ldporto.semantic_benchmark import output_contract


def benchmark():
    path = Path(__file__).resolve().parents[2] / 'scripts/dev/benchmark_semantic_r3b.py'
    spec = importlib.util.spec_from_file_location('stage51_benchmark', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def group():
    return [{'segment_id': 'S1', 'start': 0., 'end': 2., 'speaker': None,
             'text': 'Texto sintetico para teste.'}]


def response():
    return {'locale': 'pt-BR', 'topics': [{'topic': 'Teste sintetico',
            'summary': 'Texto sintetico para teste', 'context_required': 'none',
            'start_segment_id': 'S1', 'end_segment_id': 'S1'}], 'moments': []}


def test_fixture_ab_is_deterministic_and_never_measures_runtime(monkeypatch):
    module = benchmark()
    def forbidden(*args, **kwargs):
        pytest.fail('fixture cannot contact Ollama')
    monkeypatch.setattr(module, 'service_info', forbidden)
    monkeypatch.setattr(module, 'call_ollama', forbidden)
    cfg = deepcopy(DEFAULTS['semantic_analysis'])
    fixtures = {'0': {'legacy': response(), 'compact': response()}}
    args = {'sample_indices': [0], 'repeats': 2, 'fixture_outputs': fixtures}
    a = module.make_report({'segments': group()}, cfg, **args)
    b = module.make_report({'segments': group()}, cfg, **args)
    assert a == b and digest(a) == digest(b)
    assert cfg == DEFAULTS['semantic_analysis']
    assert a['scope'] == 'offline_fixture_contract_AB'
    assert a['acceptance']['median_speedup_x'] is None
    assert not a['acceptance']['local_opt_in_recommended']
    for sample in a['samples']:
        assert sample['comparison']['same_grounded_output'] is True
        assert sample['comparison']['quality'] is None
        modes = sample['modes']
        assert modes['legacy']['prompt_schema_sha256'] == modes['compact']['prompt_schema_sha256']
        assert modes['legacy']['prompt_sha256'] != modes['compact']['prompt_sha256']
        for row in modes.values():
            assert row['elapsed_seconds'] is None and row['eval_count'] is None
            assert row['attempts'] == 0 and row['cache_hit'] is False
            assert row['quality'] is None and row['monetary_cost'] is None


@pytest.mark.parametrize('problem', ['missing', 'reference', 'extra', 'coverage'])
def test_fixture_contract_failures_are_not_quality(problem):
    data = response()
    if problem == 'missing': del data['locale']
    if problem == 'reference': data['topics'][0]['end_segment_id'] = 'UNKNOWN'
    if problem == 'extra': data['invented'] = True
    if problem == 'coverage': data['topics'] = []
    result = output_contract(data, group(), DEFAULTS['semantic_analysis'], 0)
    assert result['grounded_output'] is None and result['quality'] is None
    assert result['references_valid'] is not True


def test_real_cli_requires_explicit_confirmation_before_reading_source(monkeypatch):
    module = benchmark()
    monkeypatch.setattr(sys, 'argv', ['benchmark', '--transcription', 'absent.json', '--run-model'])
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


@pytest.mark.parametrize('field,value', [('temperature', .3), ('num_ctx', 4096),
                                        ('seed', 77), ('model', 'fixture-model'),
                                        ('compact_prompt', True), ('structured_ranges', False)])
def test_semantic_hash_invalidators(field, value):
    cfg = deepcopy(DEFAULTS['semantic_analysis'])
    initial = semantic_cache_key(cfg, group(), 'fixture-digest')
    cfg[field] = value
    assert semantic_cache_key(cfg, group(), 'fixture-digest') != initial
    assert semantic_cache_key(DEFAULTS['semantic_analysis'], group(), 'different') != initial


def context(path):
    return Context(path / 'absent.fixture', path, {'strict': False}, 'fixture51', logging.getLogger('stage51'))


def test_cache_telemetry_and_invalidation_without_rewriting_hits(tmp_path):
    first = context(tmp_path)
    first.step('fixture51', {'mode': 1}, lambda: ok({'publish_ready': False}), code_files=['semantic.py'])
    assert first.stage_metrics['fixture51']['cache_lookup_reason'] == 'absent'
    path = first.cache / 'fixture51.json'
    before = path.read_bytes(), path.stat().st_mtime_ns
    second = context(tmp_path)
    second.step('fixture51', {'mode': 1}, lambda: pytest.fail('hit recomputed'), code_files=['semantic.py'])
    row = second.stage_metrics['fixture51']
    assert row['cache_hits'] == 1 and row['cache_misses'] == 0
    assert row['gpu_vram_used_bytes'] is None and row['working_set_bytes'] is None
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    third = context(tmp_path)
    third.step('fixture51', {'mode': 2}, lambda: ok({'publish_ready': False}), code_files=['semantic.py'])
    row = third.stage_metrics['fixture51']
    assert row['invalidators'] == ['params'] and row['cache_lookup_reason'] == 'key_changed'
    assert row['process_cpu_seconds_delta'] >= 0 and row['gpu_vram_used_bytes'] is None
    assert row['dependency_keys'] == {}
    path.write_text('{corrupt', encoding='utf-8')
    fourth = context(tmp_path)
    fourth.step('fixture51', {'mode': 2}, lambda: ok({}), code_files=['semantic.py'])
    assert fourth.stage_metrics['fixture51']['cache_lookup_reason'] == 'corrupt_record'


@pytest.mark.parametrize('kwargs,reason', [
    ({}, 'vram_budget_unknown'),
    ({'free_vram_mib': 500, 'required_vram_mib': 400}, 'vram_budget_insufficient'),
    ({'free_vram_mib': 8192, 'required_vram_mib': 400}, 'gpu_overlap_requires_backend_homologation'),
    ({'pytorch_active': True, 'mediapipe_active': True}, 'pytorch_mediapipe_gpu_conflict'),
    ({'free_vram_mib': float('nan'), 'required_vram_mib': 1}, 'vram_budget_unknown')])
def test_vram_conflicts_fail_closed(kwargs, reason):
    plan = vision_resource_plan(requested=True, gpu_requested=True, cpu_count=8,
                                free_ram_bytes=8 * 1024**3, **kwargs)
    assert plan['enabled'] and plan['gpu_workers'] == 0
    assert plan['gpu_reason'] == reason and not plan['gpu_overlap_enabled']


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), -1, 'unknown'])
def test_invalid_cpu_measurements_do_not_enable_overlap(value):
    assert not cpu_overlap_budget(requested=True, cpu_count=8, free_ram_bytes=8 * 1024**3,
                                  cpu_load_percent=value)['enabled']
