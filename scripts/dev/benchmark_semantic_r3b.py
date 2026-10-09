"""Non-destructive R3B A/B benchmark of Ollama schema prompt modes.

Dry run is OFFLINE. --run-model explicitly spends local Ollama inference time;
never writes to Analyzer's cache and never changes current analysis outputs.
"""
import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
import platform
import hashlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.config import load_config
from ldporto.core import digest
from ldporto.ollama_local import service_info, resolve_model, profile_options, validate_url
from ldporto.semantic_benchmark import parse_metrics, benchmark_hash, write_csv
from ldporto.performance_acceptance import evaluate_semantic_ab
from ldporto.semantic import (PROMPT, call_ollama, chunks, ground_model_output,
                             ollama_schema, range_schema)


def build_prompt(cfg, group):
    schema = range_schema(group) if cfg.get('structured_ranges', True) else ollama_schema()
    note = (' Use start_segment_id/end_segment_id para cada intervalo; a expansao para IDs intermediarios e feita pelo programa. '
            'O primeiro topic comeca no primeiro segmento e o ultimo termina no ultimo; intervalos sao adjacentes, nao sobrepostos.') if cfg.get('structured_ranges', True) else ''
    if cfg.get('compact_prompt', False):
        return PROMPT + note + '\nResponda conforme o JSON Schema enviado no parametro format da API.', schema
    return PROMPT + note + '\nSchema obrigatório: ' + json.dumps(schema, ensure_ascii=False, separators=(',', ':')), schema


def make_report(transcription, cfg, *, sample_indices, run_model=False, repeats=1):
    if repeats < 1 or not sample_indices or len(set(sample_indices)) != len(sample_indices):
        raise ValueError('Use repeats >= 1 e indices unicos nao vazios')
    cfg = dict(cfg)
    validate_url(cfg['ollama_url'])
    info = service_info(cfg['ollama_url']) if run_model else {'reachable': None, 'version': None, 'models': []}
    model = cfg.get('_resolved_model') or cfg['model']
    if run_model and info['reachable']:
        model = resolve_model(model, info['models'])
    cfg['_resolved_model'] = model
    segments = transcription.get('data', transcription).get('segments', [])
    all_groups = chunks(segments, cfg['chunk_seconds'], cfg['max_chars'])
    results = []
    for position in range(len(sample_indices) * repeats):
        i = sample_indices[position % len(sample_indices)]
        repeat = position // len(sample_indices)
        if i < 0 or i >= len(all_groups):
            raise ValueError(f'Bloco {i} fora do intervalo 0..{len(all_groups)-1}')
        group = all_groups[i]
        order = ('legacy', 'compact') if (position % len(sample_indices) + repeat) % 2 == 0 else ('compact', 'legacy')
        row = {'index': i, 'repeat': repeat, 'segments': len(group), 'subset_sha256': digest(group),
               'call_order': list(order), 'modes': {}}
        for mode in order:
            conf = dict(cfg, compact_prompt=(mode=='compact'))
            prompt, schema = build_prompt(conf, group)
            metrics = {'system_prompt_chars': len(prompt),
                       'schema_format_chars': len(json.dumps(schema, ensure_ascii=False, separators=(',', ':'))),
                       'status': 'offline_size_only', 'attempts': 0, 'retries': 0,
                       'elapsed_seconds': None, 'grounded_output': None, 'output_sha256': None,
                       'ollama_eval_count': None, 'output_token_count': None,
                       **parse_metrics({})}
            if run_model:
                started = perf_counter()
                meta = {}
                try:
                    if not info['reachable']:
                        raise ConnectionError('Ollama indisponivel; use dry-run offline')
                    metrics['attempts'] = 1
                    data, meta = call_ollama(conf, group)
                    grounded = ground_model_output(data, group, i)
                    metrics.update(status='valid_first_pass', topic_count=len(grounded['topics']),
                                   moment_count=len(grounded['moments']),
                                   grounded_output=grounded, output_sha256=digest(grounded),
                                   response_model=meta.get('model'),
                                   output_token_count=meta.get('eval_count'),
                                   repair_attempted=False, # this isolated test performs no automatic repair
                                   elapsed_seconds=round(perf_counter()-started, 3))
                except Exception as exc:
                    metrics.update(status='invalid_or_unavailable', error_type=type(exc).__name__,
                                   elapsed_seconds=round(perf_counter()-started, 3))
                    meta = getattr(exc, 'metadata', meta)
                metrics.update(parse_metrics(meta))
                metrics['ollama_eval_count'] = metrics['eval_count']
                metrics['output_token_count'] = metrics['eval_count']
            row['modes'][mode] = metrics
        row['prompt_char_reduction_pct'] = round(100*(1-row['modes']['compact']['system_prompt_chars'] /
                                                           row['modes']['legacy']['system_prompt_chars']), 2)
        results.append(row)
    report = {'schema_version': '40.1',
            'scope': 'non_destructive_model_AB_test' if run_model else 'offline_prompt_size_only',
            'provenance': {'model': model, 'ollama_version': info['version'],
                           'model_digest': next((m.get('digest') for m in info['models'] if m.get('name') == model), None),
                           'options': profile_options(cfg), 'python': platform.python_version(),
                           'configuration_sha256': digest(cfg), 'transcription_sha256': digest(transcription),
                           'benchmark_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'semantic_code_sha256': hashlib.sha256((ROOT/'src/ldporto/semantic.py').read_bytes()).hexdigest()},
            'configuration': cfg, 'repeats': repeats,
            'retry_policy': 'single_attempt_no_repair_no_fallback',
            'analyzer_cache_modified': False, 'total_chunks': len(all_groups),
            'sample_indices': sample_indices, 'samples': results,
            'caution': 'Prompt length is NOT a measured runtime improvement. Benchmark both validity and latency on the same local Ollama model.'}
    report['benchmark_sha256'] = benchmark_hash(report)
    report['acceptance'] = evaluate_semantic_ab(report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcription', type=Path, required=True, help='04_transcription.json, does not upload any data')
    parser.add_argument('--sample-indices', nargs='+', type=int, default=[0, 8, 30])
    parser.add_argument('--run-model', action='store_true', help='Explicitly invoke local Ollama (2 calls per sampled chunk)')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--csv-dir', type=Path, help='Default: <output-stem>_csv, legacy.csv and compact.csv')
    parser.add_argument('--output', type=Path, default=Path('r3b_semantic_ab.json'))
    args=parser.parse_args()
    transcript=json.loads(args.transcription.read_text(encoding='utf-8-sig'))
    cfg=load_config(ROOT/'config'/'config.yaml')['semantic_analysis']
    report=make_report(transcript,cfg,sample_indices=args.sample_indices,run_model=args.run_model,repeats=args.repeats)
    write_csv(report, args.csv_dir or args.output.with_name(args.output.stem + '_csv'))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
