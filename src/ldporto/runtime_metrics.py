"""Small local-only resource measurements and bounded throughput history."""
import os
import platform
import time
from functools import lru_cache
from pathlib import Path

from .core import digest, read_json, write_json
from .paths import PROJECT_ROOT


def resource_snapshot():
    result = {'process_cpu_seconds': time.process_time(), 'working_set_bytes': None,
              'peak_process_memory_bytes': None, 'system_ram_bytes': None, 'available_ram_bytes': None}
    from .performance_acceptance import physical_memory_available
    result['available_ram_bytes'] = physical_memory_available()
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(key, ctypes.c_size_t) for key in (
                'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            result.update(working_set_bytes=counters.WorkingSetSize, peak_process_memory_bytes=counters.PeakWorkingSetSize,
                          memory_measurement='windows_process_peak_working_set_not_gpu_vram')
    else:
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            result.update(peak_process_memory_bytes=peak * (1 if platform.system() == 'Darwin' else 1024),
                          memory_measurement='process_ru_maxrss_not_gpu_vram')
        except ImportError:
            pass
    return result


@lru_cache(maxsize=1)
def gpu_history_profile():
    from .ollama_local import nvidia_smi
    return [{key: row.get(key) for key in ('name', 'vram_total_mib', 'driver')}
            for row in nvidia_smi().get('gpus', [])]


def history_fingerprint(metadata, cfg):
    return digest({'machine': platform.machine(), 'processor': platform.processor(), 'cpu_count': os.cpu_count(),
                   'device': cfg.get('device'), 'gpus': gpu_history_profile(),
                   'duration_bucket_minutes': round((metadata.get('duration') or 0) / 60),
                   'resolution': [metadata.get('width'), metadata.get('height')], 'fps': metadata.get('fps'),
                   'asr_model': cfg.get('transcription', {}).get('model'),
                   'semantic_model': cfg.get('semantic_analysis', {}).get('model'),
                   'semantic_profile': cfg.get('semantic_analysis', {}).get('profile'),
                   'vision_config': cfg.get('vision', {})})


def record_runtime_history(metadata, cfg, stage_metrics, path=None):
    path = Path(path or PROJECT_ROOT / '.cache' / 'runtime_history.json')
    try:
        previous = read_json(path)
    except (ValueError, OSError):
        previous = {'schema_version': '1.0', 'records': []}
    key = history_fingerprint(metadata, cfg)
    records = previous.get('records', [])
    records.append({'hardware_and_config_fingerprint': key, 'recorded_at': time.time(),
                    'video_duration': metadata.get('duration'), 'resolution': [metadata.get('width'), metadata.get('height')],
                    'fps': metadata.get('fps'), 'stage_runtime': stage_metrics, 'telemetry_external': False})
    write_json(path, {'schema_version': '1.0', 'records': records[-50:]})
    return key


def historical_stage_estimates(metadata, cfg, path=None):
    from collections import defaultdict
    from statistics import median
    try:
        history = read_json(Path(path or PROJECT_ROOT / '.cache/runtime_history.json'))
    except (OSError, ValueError):
        return {}
    matches = [r for r in history.get('records', []) if r.get('hardware_and_config_fingerprint') == history_fingerprint(metadata, cfg)]
    samples = defaultdict(list)
    for record in matches:
        for stage, row in record.get('stage_runtime', {}).items():
            cost = row.get('elapsed_seconds')
            if not row.get('cache_hit') and isinstance(cost, (int,float)) and cost > 0:
                samples[stage].append(cost)
    return {stage:{'median_seconds':median(costs), 'range_seconds':[min(costs), max(costs)], 'sample_count':len(costs)}
            for stage, costs in samples.items() if len(costs) >= 3}
