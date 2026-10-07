"""Bounded CPU-only inference concurrency guard (Windows/Python 3.11 safe)."""
from __future__ import annotations

import os


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
    if not isinstance(cpu, int) or cpu < 4:
        return {"enabled": False, "workers": 0, "reason": "cpu_insufficient"}
    if cpu_load_percent is not None and cpu_load_percent >= 80:
        return {"enabled": False, "workers": 0, "reason": "cpu_current_load_high"}
    if not isinstance(free_ram_bytes, (int, float)) or free_ram_bytes < 4 * 1024 ** 3:
        return {"enabled": False, "workers": 0, "reason": "ram_below_4gib"}
    return {"enabled": True, "workers": 1, "reason": "cpu_ram_headroom", "gpu_workers": 0,
            "memory_floor_gib": 4, "logical_cpu": cpu}
