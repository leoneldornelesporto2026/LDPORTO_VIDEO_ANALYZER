"""Non-destructive R3B A/B benchmark of Ollama schema prompt modes.

Dry run is OFFLINE. --run-model explicitly spends local Ollama inference time;
never writes to Analyzer's cache and never changes current analysis outputs.
"""
import argparse
from copy import deepcopy
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.config import load_config
from ldporto.semantic import (PROMPT, call_ollama, chunks, ground_model_output,
                             ollama_schema, range_schema)


def build_prompt(cfg, group):
    schema = range_schema(group) if cfg.get('structured_ranges', True) else ollama_schema()
    note = (' Use start_segment_id/end_segment_id para cada intervalo; a expansao para IDs intermediarios e feita pelo programa. '
            'O primeiro topic comeca no primeiro segmento e o ultimo termina no ultimo; intervalos sao adjacentes, nao sobrepostos.') if cfg.get('structured_ranges', True) else ''
    if cfg.get('compact_prompt', False):
        return PROMPT + note + '\nResponda conforme o JSON Schema enviado no parametro format da API.', schema
    return PROMPT + note + '\nSchema obrigatório: ' + json.dumps(schema, ensure_ascii=False, separators=(',', ':')), schema


def make_report(transcription, cfg, *, sample_indices, run_model=False):
    segments = transcription.get('data', transcription).get('segments', [])
    all_groups = chunks(segments, cfg['chunk_seconds'], cfg['max_chars'])
    results = []
    for i in sample_indices:
        if i < 0 or i >= len(all_groups):
            raise ValueError(f'Bloco {i} fora do intervalo 0..{len(all_groups)-1}')
        group = all_groups[i]
        row = {'index': i, 'segments': len(group), 'modes': {}}
        for mode in ('legacy', 'compact'):
            conf = dict(cfg, compact_prompt=(mode=='compact'))
            prompt, schema = build_prompt(conf, group)
            metrics = {'system_prompt_chars': len(prompt),
                       'schema_format_chars': len(json.dumps(schema, ensure_ascii=False, separators=(',', ':'))),
                       'status': 'offline_size_only'}
            if run_model:
                started = perf_counter()
                try:
                    data, meta = call_ollama(conf, group)
                    grounded = ground_model_output(data, group, i)
                    metrics.update(status='valid_first_pass', topic_count=len(grounded['topics']),
                                   moment_count=len(grounded['moments']),
                                   ollama_eval_count=meta.get('eval_count'),
                                   prompt_eval_count=meta.get('prompt_eval_count'),
                                   total_duration_ns=meta.get('total_duration_ns'),
                                   eval_duration_ns=meta.get('eval_duration_ns'),
                                   tokens_per_second=(round(meta['eval_count'] * 1e9 / meta['eval_duration_ns'], 2)
                                       if isinstance(meta.get('eval_count'), (int, float)) and
                                       isinstance(meta.get('eval_duration_ns'), (int, float)) and meta['eval_duration_ns'] > 0 else None),
                                   output_token_count=meta.get('eval_count'),
                                   repair_attempted=False, # this isolated test performs no automatic repair
                                   elapsed_seconds=round(perf_counter()-started, 3))
                except Exception as exc:
                    metrics.update(status='invalid_or_unavailable', error_type=type(exc).__name__,
                                   elapsed_seconds=round(perf_counter()-started, 3))
            row['modes'][mode] = metrics
        row['prompt_char_reduction_pct'] = round(100*(1-row['modes']['compact']['system_prompt_chars'] /
                                                           row['modes']['legacy']['system_prompt_chars']), 2)
        results.append(row)
    return {'scope': 'non_destructive_model_AB_test' if run_model else 'offline_prompt_size_only',
            'analyzer_cache_modified': False, 'total_chunks': len(all_groups),
            'sample_indices': sample_indices, 'samples': results,
            'caution': 'Prompt length is NOT a measured runtime improvement. Benchmark both validity and latency on the same local Ollama model.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transcription', type=Path, required=True, help='04_transcription.json, does not upload any data')
    parser.add_argument('--sample-indices', nargs='+', type=int, default=[0, 8, 30])
    parser.add_argument('--run-model', action='store_true', help='Explicitly invoke local Ollama (2 calls per sampled chunk)')
    parser.add_argument('--output', type=Path, default=Path('r3b_semantic_ab.json'))
    args=parser.parse_args()
    transcript=json.loads(args.transcription.read_text(encoding='utf-8-sig'))
    cfg=load_config(ROOT/'config'/'config.yaml')['semantic_analysis']
    report=make_report(transcript,cfg,sample_indices=args.sample_indices,run_model=args.run_model)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
