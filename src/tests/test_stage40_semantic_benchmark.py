"""Synthetic offline A/B evidence only; never an NVIDIA/Ollama performance claim."""
import csv
import importlib.util
import json
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from ldporto.config import DEFAULTS
from ldporto.core import digest
from ldporto.performance_acceptance import evaluate_semantic_ab
from ldporto.semantic_benchmark import parse_metrics, benchmark_hash, write_csv

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/dev/benchmark_semantic_r3b.py'
spec = importlib.util.spec_from_file_location('stage40_benchmark', SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def transcript():
    return {'segments': [{'segment_id': f'S{i}', 'start': i * 100., 'end': i * 100. + 2,
                          'speaker': None, 'text': 'Texto sintético para teste.'} for i in range(3)]}


def config():
    return dict(DEFAULTS['semantic_analysis'], chunk_seconds=10, max_chars=1000)


def test_parser_raw_and_normalized_units():
    raw = {'eval_count': 12, 'eval_duration': 2_000_000_000, 'total_duration': 3_000_000_000,
           'prompt_eval_count': 20, 'prompt_eval_duration': 500_000_000}
    normalized = {k + '_ns' if k.endswith('duration') else k: v for k, v in raw.items()}
    assert parse_metrics(raw) == parse_metrics(normalized)
    assert parse_metrics(raw)['tokens_per_second'] == 6
    assert parse_metrics({})['tokens_per_second'] is None


@pytest.mark.parametrize('value', [True, '12', -1, float('inf'), float('nan'), None])
def test_bad_metrics_remain_null(value):
    assert parse_metrics({'eval_count': value, 'eval_duration': value})['tokens_per_second'] is None


def test_zero_duration_and_fractional_token_count():
    assert parse_metrics({'eval_count': 2, 'eval_duration': 0})['tokens_per_second'] is None
    assert parse_metrics({'eval_count': 2.5, 'eval_duration': 1})['eval_count'] is None


def test_dry_run_never_contacts_service_or_inference_and_csv(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('offline must not call Ollama')
    monkeypatch.setattr(benchmark, 'service_info', forbidden)
    monkeypatch.setattr(benchmark, 'call_ollama', forbidden)
    report = benchmark.make_report(transcript(), config(), sample_indices=[0, 1, 2], repeats=2)
    assert len(report['samples']) == 6
    assert report['provenance']['ollama_version'] is None
    assert report['provenance']['options']['seed'] == 42
    assert not report['acceptance']['local_opt_in_recommended']
    assert report['benchmark_sha256'] == benchmark_hash(report)
    write_csv(report, tmp_path)
    for mode in ('legacy', 'compact'):
        with (tmp_path / (mode + '.csv')).open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 6 and all(r['tokens_per_second'] == '' for r in rows)
    assert report['samples'][0]['call_order'] != report['samples'][1]['call_order']
    even = benchmark.make_report(transcript(), config(), sample_indices=[0, 1], repeats=2)
    assert even['samples'][0]['call_order'] != even['samples'][2]['call_order']


def test_actual_prompts_match_benchmark(monkeypatch):
    import ldporto.semantic as semantic
    sent = []
    monkeypatch.setattr(semantic, 'ollama_chat', lambda url, model, messages, schema, cfg:
                        (sent.append((messages[0]['content'], schema)) or {}, {}))
    for compact in (False, True):
        cfg = dict(config(), compact_prompt=compact)
        semantic.call_ollama(cfg, transcript()['segments'])
        assert sent[-1] == benchmark.build_prompt(cfg, transcript()['segments'])


def test_unavailable_service_records_no_attempts(monkeypatch):
    monkeypatch.setattr(benchmark, 'service_info', lambda *a: {'reachable': False, 'version': None, 'models': []})
    report = benchmark.make_report(transcript(), config(), sample_indices=[0], run_model=True)
    assert all(r['status'] == 'invalid_or_unavailable' and r['attempts'] == 0
               for r in report['samples'][0]['modes'].values())
    assert not report['acceptance']['local_opt_in_recommended']


def test_grounding_failure_retains_measured_metadata(monkeypatch):
    monkeypatch.setattr(benchmark, 'service_info', lambda *a: {'reachable': True, 'version': 'synthetic', 'models': []})
    monkeypatch.setattr(benchmark, 'call_ollama', lambda *a: ({}, {'eval_count': 10, 'eval_duration_ns': 2e9}))
    report = benchmark.make_report(transcript(), config(), sample_indices=[0], run_model=True)
    for row in report['samples'][0]['modes'].values():
        assert row['status'] == 'invalid_or_unavailable'
        assert row['tokens_per_second'] == 5 and row['attempts'] == 1 and row['retries'] == 0
        assert row['grounded_output'] is None


def test_invalid_json_keeps_ollama_metrics_without_network(monkeypatch):
    from ldporto import ollama_local
    monkeypatch.setattr(ollama_local, '_request_json', lambda *a, **kw:
                        {'message': {'content': '{bad json'}, 'eval_count': 10, 'eval_duration': 2e9})
    with pytest.raises(ollama_local.OllamaContentError) as failure:
        ollama_local.chat('http://127.0.0.1:11434', 'synthetic', [], {}, {})
    assert failure.value.metadata['failure_category'] == 'invalid_json'
    assert parse_metrics(failure.value.metadata)['tokens_per_second'] == 5


def test_successful_inference_pairs_same_subset_and_preserves_config(monkeypatch):
    cfg = config()
    original = deepcopy(cfg)
    calls = []
    monkeypatch.setattr(benchmark, 'service_info', lambda *a:
                        {'reachable': True, 'version': 'synthetic',
                         'models': [{'name': cfg['model'], 'digest': 'synthetic'}]})
    def fake(conf, group):
        calls.append((conf['compact_prompt'], deepcopy(group)))
        return {'locale': 'pt-BR', 'topics': [{'topic': 'Teste sintético',
                'summary': 'Texto sintético de teste', 'context_required': 'none',
                'start_segment_id': group[0]['segment_id'], 'end_segment_id': group[-1]['segment_id']}],
                'moments': []}, {'model': cfg['model'], 'eval_count': 12, 'eval_duration_ns': 2e9}
    monkeypatch.setattr(benchmark, 'call_ollama', fake)
    report = benchmark.make_report(transcript(), cfg, sample_indices=[0, 1, 2], run_model=True)
    assert cfg == original and len(calls) == 6
    for n, sample in enumerate(report['samples']):
        assert calls[2*n][1] == calls[2*n+1][1]
        for row in sample['modes'].values():
            assert row['status'] == 'valid_first_pass' and row['topic_count'] == 1
            assert row['output_sha256'] == digest(row['grounded_output'])
            assert row['ollama_eval_count'] == row['eval_count'] == 12
    assert not report['acceptance']['local_opt_in_recommended']  # human quality is still missing


def reviewed_report():
    report = benchmark.make_report(transcript(), config(), sample_indices=[0, 1, 2])
    report['scope'] = 'non_destructive_model_AB_test'
    report['provenance'].update(model_digest='synthetic', ollama_version='synthetic')
    for sample in report['samples']:
        for mode in ('legacy', 'compact'):
            output = {'topics': [], 'moments': [], 'fixture': 'synthetic'}
            sample['modes'][mode].update(status='valid_first_pass', elapsed_seconds=10 if mode == 'legacy' else 5,
                response_model=report['provenance']['model'], grounded_output=output, output_sha256=digest(output))
    report['benchmark_sha256'] = benchmark_hash(report)
    report['quality_review'] = {'reviewer': 'synthetic-test-reviewer', 'rubric': 'Synthetic test, no human approval',
        'benchmark_sha256': report['benchmark_sha256'], 'samples': [
            {'index': s['index'], 'legacy': {'qa': .9, 'stories': .9, 'ranking': .9},
             'compact': {'qa': .9, 'stories': .9, 'ranking': .9}} for s in report['samples']]}
    return report


def test_recommendation_requires_bound_complete_quality_and_runtime():
    report = reviewed_report()
    result = evaluate_semantic_ab(report)
    assert result['local_opt_in_recommended'] and not result['safe_to_enable_automatically']
    report['samples'][0]['modes']['compact']['elapsed_seconds'] = 30
    assert not evaluate_semantic_ab(report)['local_opt_in_recommended']


def test_review_existing_report_cli_without_inference(tmp_path, monkeypatch):
    report = reviewed_report()
    review = report.pop('quality_review')
    source, ratings, output = [tmp_path / name for name in ('ab.json', 'review.json', 'summary.json')]
    source.write_text(json.dumps(report), encoding='utf-8')
    ratings.write_text(json.dumps(review), encoding='utf-8')
    before = source.read_bytes()
    monkeypatch.setattr('ldporto.performance_acceptance.resource_diagnostic', lambda: {'fixture': 'synthetic'})
    monkeypatch.setattr(sys, 'argv', ['performance_s10.py', '--semantic-report', str(source),
        '--quality-review', str(ratings), '--output', str(output)])
    runpy.run_path(str(SCRIPT.with_name('performance_s10.py')), run_name='__main__')
    assert json.loads(output.read_text(encoding='utf-8'))['ollama_ab']['local_opt_in_recommended']
    assert source.read_bytes() == before


@pytest.mark.parametrize('change', ['missing', 'regression', 'null', 'duplicate', 'tampered', 'hash', 'model', 'slow'])
def test_quality_or_performance_fail_closed(change):
    report = deepcopy(reviewed_report())
    if change == 'missing':
        del report['quality_review']
    elif change in ('regression', 'null'):
        report['quality_review']['samples'][0]['compact']['stories'] = .85 if change == 'regression' else None
    elif change == 'duplicate':
        report['quality_review']['samples'][1] = report['quality_review']['samples'][0]
    elif change == 'tampered':
        report['samples'][0]['modes']['compact']['grounded_output']['fixture'] = 'changed'
    elif change == 'hash':
        report['quality_review']['benchmark_sha256'] = 'stale'
    elif change == 'model':
        report['provenance']['model_digest'] = None
    elif change == 'slow':
        for s in report['samples']:
            s['modes']['compact']['elapsed_seconds'] = 12
        report['quality_review']['benchmark_sha256'] = benchmark_hash(report)
    assert not evaluate_semantic_ab(report)['local_opt_in_recommended']
