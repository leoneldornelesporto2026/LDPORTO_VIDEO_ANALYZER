"""Collect this completed benchmark without rewriting either run's evidence."""
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from ldporto.core import file_hash, read_json, write_json
from ldporto.second_curation_export import validate_core_package
from compare_runs import compare_runs, comparison_markdown


def main():
    baseline = ROOT / 'analysis/video_31329be78ca4'
    run = ROOT / 'analysis/video_31329be78ca4_v44_full_20261006'
    folder = ROOT / '.cache/v44_validation/full_run'
    results = sorted(folder.glob('RESUME_*_RESULT.json'))
    if not results or read_json(results[-1])['return_code'] != 0:
        raise SystemExit('The resumed full pipeline has not completed successfully.')
    if (run / 'RUNNING.lock').exists():
        raise SystemExit('Output is still locked; validation must wait.')
    summary = read_json(run / 'analysis_summary.json')
    quality = read_json(run / 'analysis_quality.json')
    manifest = read_json(run / 'run_manifest.json')
    source_hash = summary['metadata']['sha256']
    if source_hash != read_json(baseline / 'analysis_summary.json')['metadata']['sha256']:
        raise SystemExit('Source mismatch; do not compare these runs.')
    required = ['speaker_person_diagnostics.json', 'semantic_chunk_profile.json',
                'broadcast_graphics.json', 'camera_director_timeline.json', 'story_arcs.json',
                'targeted_asr_repair.json', 'second_curation_export.json', 'report.html']
    missing = [name for name in required if not (run / name).is_file()]
    if missing:
        raise SystemExit('Missing final artifacts: ' + ', '.join(missing))
    exported = read_json(run / 'second_curation_export.json')
    package_validation = validate_core_package(exported['path'])
    if package_validation['status'] != 'valid':
        raise SystemExit('Full-run package failed validation: ' + json.dumps(package_validation))
    preserved = {}
    snapshot = ROOT / '.cache/v44_baseline_v43'
    for path in snapshot.rglob('*'):
        if path.is_file():
            relative = path.relative_to(snapshot)
            original = baseline / relative
            preserved[relative.as_posix()] = original.is_file() and file_hash(path) == file_hash(original)
    if not all(preserved.values()):
        raise SystemExit('Baseline preservation check failed.')
    attempts = [read_json(folder / 'FULL_RUN_RESULT.json'), *[read_json(p) for p in results]]
    runtimes = summary.get('stage_runtime', {})
    successful_costs = {name:row.get('original_elapsed_seconds') if row.get('cache_hit') else row.get('elapsed_seconds')
                        for name,row in runtimes.items()}
    totals = [value for value in successful_costs.values() if isinstance(value,(int,float))]
    combined = {
        'execution_scope':'completed_full_pipeline_resumed_own_v44_checkpoints',
        'source_sha256':source_hash, 'output':str(run), 'attempts':attempts,
        'total_attempt_wall_seconds':sum(row['wall_seconds'] for row in attempts),
        'end_to_end_including_repair_wait_seconds':
            (datetime.fromisoformat(attempts[-1]['finished_at']) - datetime.fromisoformat(attempts[0]['started_at'])).total_seconds(),
        'successful_stage_costs_seconds':successful_costs,
        'summed_successful_stage_costs_seconds':sum(totals),
        'stage_sum_is_wall_time':False, 'controlled_performance_gain_claim':False,
        'baseline_artifacts_preserved':preserved, 'package_validation':package_validation,
        'package_sha256':file_hash(exported['path']),
        'package_candidate_count':exported.get('candidate_count'),
        'package_shortlist_count':exported.get('shortlist_count'),
        'analysis_status':manifest.get('analysis_status'), 'root_cause_stage':manifest.get('root_cause_stage'),
        'diarization_stage_status':manifest.get('stage_status',{}).get('05_diarization',{}).get('status'),
        'quality':quality, 'candidate_metrics':summary.get('candidate_metrics'),
        'semantic_metrics':summary.get('semantic_metrics'),
        'limitations':['No annotated identity/camera accuracy measurement.',
                       'Resumed wall time alone is not comparable to a fresh full run.',
                       'Explicit partial/degraded stages remain visible.']}
    write_json(folder / 'FULL_VALIDATION_SUMMARY.json', combined)
    comparison = compare_runs(baseline, run)
    comparison['benchmark_attempt_provenance'] = {key:combined[key] for key in (
        'execution_scope','total_attempt_wall_seconds','end_to_end_including_repair_wait_seconds',
        'successful_stage_costs_seconds','summed_successful_stage_costs_seconds','controlled_performance_gain_claim')}
    destination = ROOT / 'docs/benchmarks'
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / 'V43_V44_COMPARE.json', comparison)
    (destination / 'V43_V44_COMPARE.md').write_text(comparison_markdown(comparison), encoding='utf-8')
    print(json.dumps({key:combined[key] for key in ('analysis_status','root_cause_stage','diarization_stage_status',
                      'package_candidate_count','package_shortlist_count','total_attempt_wall_seconds')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
