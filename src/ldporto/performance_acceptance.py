"""S10 measured-only A/B acceptance, resumability diagnosis, local resource snapshot."""
from __future__ import annotations

from statistics import median
from pathlib import Path
import json
import math
import os
import platform
import shutil
import subprocess


def _valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def evaluate_vision_ab(report, *, min_samples=8, min_speedup=1.12):
    frames = report.get('sample_count', 0)
    x = report.get('speedup_x')
    problems = []
    if frames < min_samples:
        problems.append('insufficient_sample_frames')
    if report.get('detection_boxes_identical') is not True or report.get('detector_calls_identical') is not True:
        problems.append('detections_not_identical')
    if not report.get('cpu_parallel_available'):
        problems.append('parallel_execution_not_available')
    if not _valid(x) or x < min_speedup:
        problems.append('speedup_not_proven')
    return {'experiment': 'HOG_face_serial_vs_cpu_parallel', 'status': 'measured' if _valid(x) else 'not_measured',
            'speedup_x': x, 'min_required_speedup_x': min_speedup,
            'safe_to_enable_automatically': False,
            'local_opt_in_recommended': not problems, 'blocking_reasons': problems,
            'cache_invalidation_required': False}


def evaluate_semantic_ab(report, *, min_samples=3, min_speedup=1.10):
    """Never promote compact prompt on character reduction alone.

    Paired comparisons require successful grounded outputs in *both* modes.
    Semantic equivalence needs a human-labeled evaluation; these are structural
    and throughput acceptance metrics, not proof of storytelling quality.
    """
    pairs, reasons = [], []
    for sample in report.get('samples', []):
        modes = sample.get('modes') or {}
        baseline, compact = modes.get('legacy') or {}, modes.get('compact') or {}
        if baseline.get('status') != 'valid_first_pass' or compact.get('status') != 'valid_first_pass':
            continue
        a, b = baseline.get('elapsed_seconds'), compact.get('elapsed_seconds')
        if _valid(a) and _valid(b):
            pairs.append({'index': sample.get('index'), 'legacy_seconds': a, 'compact_seconds': b,
                          'speedup': a/b, 'legacy_tokens_per_second': baseline.get('tokens_per_second'),
                          'compact_tokens_per_second': compact.get('tokens_per_second'),
                          'topic_delta': compact.get('topic_count', 0) - baseline.get('topic_count', 0),
                          'moment_delta': compact.get('moment_count', 0) - baseline.get('moment_count', 0)})
    if len(pairs) < min_samples:
        reasons.append('insufficient_paired_valid_model_samples')
    speedup = median([p['speedup'] for p in pairs]) if pairs else None
    if not _valid(speedup) or speedup < min_speedup:
        reasons.append('runtime_speedup_not_proven')
    # A single successful JSON response cannot measure semantic/editorial quality.
    reasons.append('human_semantic_quality_goldset_not_attached')
    return {'experiment': 'ollama_compact_vs_legacy', 'paired_samples': pairs, 'median_speedup_x': speedup,
            'semantic_quality_approved': False, 'safe_to_enable_automatically': False,
            'min_required_speedup_x': min_speedup, 'blockers': reasons,
            'outcome': 'await_windows_ollama_and_human_goldset'}


def physical_memory_available():
    """OS-measured RAM, not inferred from CPU utilization or GPU VRAM."""
    if os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('dwLength', wintypes.DWORD), ('dwMemoryLoad', wintypes.DWORD),
                            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                            ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.WinDLL('kernel32').GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except (OSError, ValueError, AttributeError):
            pass
        return None
    try:
        return int(os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE'))
    except (ValueError, OSError, AttributeError):
        return None


def resource_diagnostic():
    from .ollama_local import nvidia_smi
    from .runtime_metrics import resource_snapshot
    snapshot = resource_snapshot()
    gpu = nvidia_smi()
    result = {'platform': platform.platform(), 'python': platform.python_version(),
              'python311_windows': os.name == 'nt' and platform.python_version().startswith('3.11.'),
              'logical_cpus': os.cpu_count(), 'cpu_process_seconds': snapshot.get('process_cpu_seconds'),
              'ram_available_bytes': physical_memory_available(),
              'working_set_bytes': snapshot.get('working_set_bytes'),
              'gpu': gpu, 'ffmpeg': shutil.which('ffmpeg'), 'ffprobe': shutil.which('ffprobe'),
              'ollama_cli': shutil.which('ollama'),
              'adaptive_parallelism_enabled': False, 'notes': []}
    if not gpu.get('available'):
        result['notes'].append('NVIDIA VRAM not measured: GPU scheduling disabled by default')
    if not result['python311_windows']:
        result['notes'].append('Windows/Python3.11 acceptance pending')
    result['notes'].append('No CPU/GPU dynamic concurrency change without paired A/B and cache isolation')
    return result


def review_checkpoint_state(run_manifest):
    """Diagnose resumability without changing any persisted cache or checkpoints."""
    statuses = run_manifest.get('stage_status') or run_manifest.get('stages') or {}
    records = []
    if isinstance(statuses, dict):
        for name, row in statuses.items():
            if not isinstance(row, dict):
                continue
            state = row.get('status') or row.get('state') or 'unknown'
            records.append({'stage': name, 'status': state, 'cache_hit': row.get('cache_hit'),
                            'replay_required': state in ('failed', 'blocked', 'cancelled'),
                            'reuse_safe': state in ('ok', 'completed', 'cache_hit') and row.get('cache_hit') is True})
    return {'stage_count': len(records), 'replay_needed_stages': [r['stage'] for r in records if r['replay_required']],
            'stages': records, 'cache_mutated': False,
            'rule': 'replay via existing pipeline checkpoint dependency graph; never delete expensive outputs on audit'}
