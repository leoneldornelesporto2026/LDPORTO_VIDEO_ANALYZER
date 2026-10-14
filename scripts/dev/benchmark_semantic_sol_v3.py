"""Opt-in, fixed-input local A/B benchmark; does not change analysis or presets."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def save(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def api(base, route, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base.rstrip('/') + route, data=data,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=ROOT / 'config/config.yaml')
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT / 'src'))
    from ldporto.config import load_config
    from ldporto import semantic
    from ldporto.ollama_local import chat, profile_options, nvidia_smi
    from ldporto.core import digest
    import psutil
    cfg = dict(load_config(args.config)['semantic_analysis'])
    cfg.pop('_global_cache_dir', None)
    cfg['_force'] = True
    if cfg['model'] != 'qwen3:14b' or cfg['profile'] != 'max':
        raise ValueError('benchmark requires the existing qwen3:14b/max configuration')
    state = api(cfg['ollama_url'], '/api/tags')
    installed = next((item for item in state['models'] if item['name'] == cfg['model']), None)
    if not installed:
        raise ValueError('required local model missing; no pull is permitted')
    initial_ps = api(cfg['ollama_url'], '/api/ps')
    if any(item.get('name') != cfg['model'] for item in initial_ps.get('models', [])):
        raise ValueError('another model is loaded; do not evict other work')
    read = lambda name: json.loads((args.analysis / name).read_text(encoding='utf-8'))
    segments, topics, moments = read('transcript_segments.json'), read('topics.json'), read('editorial_moments.json')
    if not segments or segments[-1]['end'] > 25:
        raise ValueError('diagnostic limited to one existing short-source chunk')
    snapshots = {}
    class Captured(Exception):
        pass
    def capture(url, model, messages, schema, call_cfg):
        snapshots[capture.key] = {'url': url, 'model': model, 'messages': deepcopy(messages),
                                  'schema': deepcopy(schema), 'cfg': dict(call_cfg)}
        raise Captured()
    previous_chat = semantic.ollama_chat
    semantic.ollama_chat = capture
    try:
        for mode in (False, True):
            config = dict(cfg, compact_prompt=mode)
            for stage in ('chunk', 'global'):
                capture.key = ('compact' if mode else 'legacy') + '_' + stage
                try:
                    if stage == 'chunk':
                        semantic.call_ollama(config, segments)
                    else:
                        semantic.call_global_review(config, topics, moments)
                except Captured:
                    pass
    finally:
        semantic.ollama_chat = previous_chat
    if len(snapshots) != 4:
        raise ValueError('both global and chunk requests must be captured')
    for stage in ('chunk', 'global'):
        legacy, compact = snapshots['legacy_' + stage], snapshots['compact_' + stage]
        if legacy['messages'][1] != compact['messages'][1] or legacy['schema'] != compact['schema']:
            raise ValueError('A/B source/schema drift')
    manifest = {'schema_version': '1.0', 'scope': 'fixed_input_component_benchmark_not_full_pipeline',
        'repetitions_per_mode': 3, 'planned_inference_calls': 12, 'model': installed,
        'config': cfg, 'options': profile_options(cfg), 'think': cfg.get('think'),
        'source_files_sha256': {name: hashlib.sha256((args.analysis/name).read_bytes()).hexdigest()
                               for name in ('transcript_segments.json','topics.json','editorial_moments.json')},
        'code_sha256': {name: hashlib.sha256((ROOT/'src/ldporto'/name).read_bytes()).hexdigest()
                        for name in ('semantic.py', 'ollama_local.py')},
        'requests': snapshots, 'initial_loaded_models': initial_ps,
        'cache_enabled': False, 'cold_definition': 'model unloaded, OS/file cache not reset',
        'command': sys.argv,
        'warm_definition': 'global request after chunk, same loaded model/context',
        'human_semantic_accuracy': None, 'default_compact_prompt_changed': False}
    save(args.output / 'inputs.json', manifest)
    results = []
    benchmark_started = time.monotonic()
    for repetition in range(1, 4):
        for mode in (('legacy','compact') if repetition != 2 else ('compact','legacy')):
            api(cfg['ollama_url'], '/api/generate', {'model': cfg['model'], 'keep_alive': 0})
            unloaded = api(cfg['ollama_url'], '/api/ps')
            if any(item.get('name') == cfg['model'] for item in unloaded.get('models', [])):
                raise RuntimeError('cold condition not established')
            for stage in ('chunk', 'global'):
                if time.monotonic() - benchmark_started > 2400:
                    raise RuntimeError('bounded benchmark wall budget exceeded')
                request = snapshots[mode + '_' + stage]
                item = {'repetition': repetition, 'mode': mode, 'stage': stage,
                        'cache_state': 'cold' if stage == 'chunk' else 'warm',
                        'request_sha256': digest(request), 'quality_is_ground_truth': False,
                        'repair_call_count': 0, 'unloaded_models_before_pair': unloaded}
                samples, stop = [], threading.Event()
                def sampler():
                    while not stop.is_set():
                        try:
                            samples.append({'elapsed': time.monotonic()-benchmark_started,
                                'system_ram_available': psutil.virtual_memory().available,
                                'benchmark_process_rss': psutil.Process().memory_info().rss,
                                'gpu': nvidia_smi()})
                        except Exception:
                            pass
                        stop.wait(2)
                worker = threading.Thread(target=sampler, daemon=True)
                worker.start()
                t0 = time.monotonic()
                try:
                    response, meta = chat(request['url'], request['model'], request['messages'],
                                          request['schema'], request['cfg'])
                    item.update(response=response, metadata=meta, json_valid=True)
                    try:
                        if stage == 'chunk':
                            grounded = semantic.ground_model_output(response, segments, 0)
                            item['grounded'] = grounded
                        else:
                            semantic.validate_global_review(response, moments)
                        item['schema_references_and_coverage_valid'] = True
                    except Exception as exc:
                        item.update(schema_references_and_coverage_valid=False,
                                    validation_error_type=type(exc).__name__, validation_error=str(exc))
                except Exception as exc:
                    item.update(json_valid=False, schema_references_and_coverage_valid=False,
                        error_type=type(exc).__name__, error=str(exc), metadata=getattr(exc,'metadata',{}))
                finally:
                    stop.set()
                    worker.join(timeout=5)
                item.update(wall_seconds=time.monotonic()-t0, resource_samples=samples,
                            model_state_after=api(cfg['ollama_url'], '/api/ps'),
                            resource_scope='system GPU and RAM; no exclusive attribution to model')
                filename = f'{repetition}_{mode}_{stage}.json'
                save(args.output / filename, item)
                results.append(item)
                print(json.dumps({'file':filename,'seconds':item['wall_seconds'],
                    'valid':item['schema_references_and_coverage_valid']}), flush=True)
    summary = {'schema_version':'1.0', 'completed_calls':len(results),
               'wall_seconds':time.monotonic()-benchmark_started, 'groups':{}}
    for mode in ('legacy','compact'):
        for stage in ('chunk','global'):
            rows=[row for row in results if row['mode']==mode and row['stage']==stage]
            values=[row['wall_seconds'] for row in rows]
            summary['groups'][mode+'_'+stage]={'n':len(rows),'median_seconds':statistics.median(values),
                'min_seconds':min(values),'max_seconds':max(values),
                'valid_count':sum(row['schema_references_and_coverage_valid'] for row in rows),
                'prompt_tokens':[row['metadata'].get('prompt_eval_count') for row in rows],
                'output_tokens':[row['metadata'].get('eval_count') for row in rows],
                'load_seconds':[row['metadata'].get('load_seconds') for row in rows],
                'generation_tokens_per_second':[row['metadata'].get('generation_tokens_per_second') for row in rows]}
    summary.update(human_quality_equivalence='PENDING_REVIEW', default_compact_prompt=False,
                   real_model_accuracy=None, full_pipeline_executed=False)
    save(args.output/'summary.json',summary)
    print(json.dumps(summary),flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
