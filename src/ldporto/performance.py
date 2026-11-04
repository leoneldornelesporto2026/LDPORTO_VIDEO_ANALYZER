"""Bounded CPU-only inference concurrency guard (Windows/Python 3.11 safe)."""
from __future__ import annotations

import os
import math
from collections import deque
from datetime import datetime, timezone
from time import perf_counter


def measured_vram(cuda):
    """Instantaneous device-0 measurement, never an allocation/reservation."""
    started = perf_counter()
    free, total = cuda.mem_get_info(0)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) and v >= 0 for v in (free, total)) or free > total or total == 0:
        raise ValueError('Invalid device memory measurement')
    return {'free_vram_mb': free / 1048576, 'total_vram_mb': total / 1048576,
            'measured_at_utc': datetime.now(timezone.utc).isoformat(),
            'query_seconds': perf_counter() - started,
            'measurement_scope': 'device_0_snapshot_not_reserved',
            'concurrent_consumers': 'Ollama/Whisper/pyannote/other_processes_not_attributed',
            'variability': 'may_change_after_query'}


class FrameTelemetry:
    """Bounded latency samples; counts cover only this execution, not resumed data."""
    def __init__(self, stage='07_people_tracking', clock=perf_counter):
        self.stage, self.clock = stage, clock
        self.started = clock()
        self.attempted = self.succeeded = 0
        self.latencies = deque(maxlen=512)

    def attempt(self):
        self.attempted += 1
        return self.clock()

    def success(self, started):
        self.succeeded += 1
        self.latencies.append(max(0., self.clock() - started))

    def report(self):
        elapsed = max(0., self.clock() - self.started)
        values = sorted(self.latencies)
        def percentile(q):
            if not values:
                return None
            index = (len(values) - 1) * q
            lo, hi = math.floor(index), math.ceil(index)
            return values[lo] + (values[hi] - values[lo]) * (index - lo)
        return {'stage': self.stage, 'scope': 'current_execution_only',
                'elapsed_seconds': elapsed, 'frames_attempted': self.attempted,
                'frames_succeeded': self.succeeded,
                'fps': self.succeeded / elapsed if elapsed else None,
                'latency_p50_seconds': percentile(.5), 'latency_p95_seconds': percentile(.95),
                'latency_scope': 'last_512_successful_frames_decode_through_checkpoint',
                'latency_samples': len(values), 'peak_vram_mb': None,
                'peak_vram_reason': 'not_instrumented_system_wide',
                'speedup_x': None, 'eta_seconds': None, 'eta_status': 'calculando',
                'max_frames_in_flight': 1, 'gpu_parallelism': False}


def vision_resource_plan(*, requested=False, gpu_requested=False, free_vram_mib=None,
                         required_vram_mib=None, reserve_vram_mib=1024,
                         pytorch_active=False, mediapipe_active=False, **cpu):
    """Read-only profile guard. Unknown VRAM/conflicts block GPU overlap.

    The implemented parallel detector remains HOG on CPU; this plan does not
    initialize backends or authorize concurrent GPU inference.
    """
    plan = cpu_overlap_budget(requested=requested, **cpu)
    plan.update(gpu_workers=0, gpu_overlap_enabled=False, free_vram_mib=free_vram_mib,
                required_vram_mib=required_vram_mib, reserve_vram_mib=reserve_vram_mib)
    valid = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
    if not gpu_requested:
        reason = 'gpu_overlap_not_requested'
    elif pytorch_active and mediapipe_active:
        reason = 'pytorch_mediapipe_gpu_conflict'
    elif not all(valid(value) for value in (free_vram_mib, required_vram_mib, reserve_vram_mib)):
        reason = 'vram_budget_unknown'
    elif free_vram_mib < required_vram_mib + reserve_vram_mib:
        reason = 'vram_budget_insufficient'
    else:
        reason = 'gpu_overlap_requires_backend_homologation'
    plan['gpu_reason'] = reason
    return plan


def cpu_overlap_budget(*, cpu_count=None, free_ram_bytes=None, cpu_load_percent=None, requested=False):
    """One extra CPU worker ONLY when both CPU and memory are safely known.

    No GPU tasks, no speculative extra frames, no hidden CPU fallback.
    """
    if not requested:
        return {"enabled": False, "workers": 0, "reason": "disabled_by_config"}
    cpu = cpu_count if cpu_count is not None else os.cpu_count()
    if free_ram_bytes is None:
        try:
            import psutil
            free_ram_bytes = psutil.virtual_memory().available
            if cpu_load_percent is None:
                cpu_load_percent = psutil.cpu_percent(interval=0.1)
        except (ImportError, OSError, AttributeError):
            return {"enabled": False, "workers": 0, "reason": "ram_unknown_fail_closed"}
    if isinstance(cpu, bool) or not isinstance(cpu, int) or cpu < 4:
        return {"enabled": False, "workers": 0, "reason": "cpu_insufficient"}
    if cpu_load_percent is not None and (isinstance(cpu_load_percent, bool) or not isinstance(cpu_load_percent, (int, float)) or not math.isfinite(cpu_load_percent) or cpu_load_percent < 0 or cpu_load_percent > 100):
        return {"enabled": False, "workers": 0, "reason": "cpu_load_invalid"}
    if cpu_load_percent is not None and cpu_load_percent >= 80:
        return {"enabled": False, "workers": 0, "reason": "cpu_current_load_high"}
    if isinstance(free_ram_bytes, bool) or not isinstance(free_ram_bytes, (int, float)) or not math.isfinite(free_ram_bytes) or free_ram_bytes < 4 * 1024 ** 3:
        return {"enabled": False, "workers": 0, "reason": "ram_below_4gib"}
    return {"enabled": True, "workers": 1, "reason": "cpu_ram_headroom", "gpu_workers": 0,
            "memory_floor_gib": 4, "logical_cpu": cpu}
