"""R3 conservative, non-executing worker budget and measured stage bottlenecks.

No auto-tuning is applied to GPU/CUDA/FFmpeg/OpenCV threads. Verify on Windows
with measurements before enabling concurrency (avoids oversubscription/OOM).
"""
import argparse
import json
import os
from pathlib import Path


def budget(cpu_logical, available_ram_gb, *, reserve_gb=3.0, worker_ram_gb=1.5):
    if cpu_logical is None or available_ram_gb is None:
        return {'workers': 1, 'evidence': 'unknown_resources', 'auto_parallel_enabled': False}
    cpu = max(1, int(cpu_logical))
    free = max(0., float(available_ram_gb))
    # Cap to 4, retain >= half logical cores, and reserve RAM for Windows/GPU.
    workers = max(1, min(4, cpu // 2, int(max(0., free-reserve_gb) / worker_ram_gb)))
    return {'workers': workers, 'evidence': 'conservative_cpu_and_ram_budget',
            'cpu_logical': cpu, 'available_ram_gb': round(free, 2),
            'reserve_gb': reserve_gb, 'assumed_ram_per_worker_gb': worker_ram_gb,
            'auto_parallel_enabled': False, 'gpu_concurrency': 1,
            'advisory_only': True}


def analyze(stage_seconds, zoom_summary=None, *, cpu_logical=None, available_ram_gb=None):
    entries = [{'stage': name, 'measured_seconds': round(float(value), 2)}
               for name, value in stage_seconds.items()
               if isinstance(value, (float, int)) and not isinstance(value, bool) and value > 0]
    entries.sort(key=lambda row: -row['measured_seconds'])
    total = sum(row['measured_seconds'] for row in entries)
    for row in entries:
        row['share_of_measured_runtime'] = round(row['measured_seconds']/total, 4) if total else None
    zoom_summary=zoom_summary or {}
    focus=zoom_summary.get('resolved_focus_coverage', zoom_summary.get('camera_director_coverage'))
    return {'schema_version': '1.0', 'scope': 'performance_and_camera_advisory_not_execution',
            'total_measured_stage_seconds': round(total, 2), 'stage_bottlenecks': entries,
            'worker_budget': budget(cpu_logical, available_ram_gb),
            'camera_readiness': {'resolved_focus_coverage': focus,
                'zoom_proposed': zoom_summary.get('proposed_zoom_event_count'),
                'zoom_delivered': zoom_summary.get('zoom_delivered_event_count', zoom_summary.get('zoom_event_count')),
                'zoom_opportunities': zoom_summary.get('zoom_opportunity_window_count'),
                'zoom_block_reasons': zoom_summary.get('zoom_block_reason_counts'),
                'interpretation': 'diagnostic_only_not_visual_quality_score'},
            'priorities': [
                'Measure semantic first-pass/repair and per-block latency before parallel LLM calls.',
                'Profile body detector (HOG) and visual inference before changing its accuracy/sampling.',
                'Parallelize CPU-only independent chunks only after a RAM and reproducibility benchmark.',
                'Never overlap Whisper, diarization or LLM GPU tasks without dedicated VRAM headroom.',
                'Keep one decoder per stream and compare sequential vs concurrent wall-clock time.',
                'Check camera zoom blockers and editorial upstream readiness before loosening safety rules.'
            ],
            'not_implemented': ['adaptive_worker_scheduler', 'gpu_vram_guard', 'automatic_parallelization']}


def _load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-runtime', type=Path, required=True,
                        help='JSON with stage seconds or stage_runtime rows of elapsed_seconds')
    parser.add_argument('--camera-summary', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data=_load(args.stage_runtime)
    stages=data.get('stage_runtime', data.get('stage_metrics', data))
    durations={name:(r.get('original_elapsed_seconds') if r.get('cache_hit') else r.get('elapsed_seconds'))
               if isinstance(r, dict) else r for name,r in stages.items()}
    free_gb=None
    try:
        import psutil
        free_gb=psutil.virtual_memory().available/(1024**3)
    except ImportError:
        pass
    report=analyze(durations, _load(args.camera_summary) if args.camera_summary else {},
                   cpu_logical=os.cpu_count(), available_ram_gb=free_gb)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
