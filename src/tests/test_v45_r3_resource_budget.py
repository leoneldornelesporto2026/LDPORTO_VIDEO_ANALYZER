"""A performance recommendation must never spawn unsafe parallel work."""
import importlib.util
from pathlib import Path

FILE=Path(__file__).resolve().parents[2] / 'scripts/dev/performance_diagnostics_r3.py'
spec=importlib.util.spec_from_file_location('ldporto_resource_advice', FILE)
resource=importlib.util.module_from_spec(spec)
spec.loader.exec_module(resource)


def test_unknown_memory_never_assumes_it_is_safe():
    assert resource.budget(24, None)['workers']==1


def test_conservative_budget_reserves_ram_and_cpu():
    assert resource.budget(24, 4.2)['workers']==1
    assert resource.budget(24, 12)['workers']==4
    assert resource.budget(4, 20)['workers']==2
    assert resource.budget(1, 20)['workers']==1
    assert not resource.budget(24, 12)['auto_parallel_enabled']


def test_measured_stage_breakdown_is_explicitly_not_speedup_claim():
    report=resource.analyze({'semantic': 5500, 'tracking': 2400, 'vision_cache_hit': 0},
                            {'camera_director_coverage':.11, 'zoom_event_count':0},
                            cpu_logical=12, available_ram_gb=12)
    assert report['stage_bottlenecks'][0]['stage']=='semantic'
    assert sum(row['share_of_measured_runtime'] for row in report['stage_bottlenecks']) == 1
    assert 'automatic_parallelization' in report['not_implemented']
    assert report['camera_readiness']['zoom_delivered']==0
