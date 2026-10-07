"""Finalize the V4.4 benchmark only after the resumed full run is complete.

This helper never resumes inference and never mutates the preserved V4.3 baseline.
It validates completion, delegates artifact/package/compare checks to report_full_v44,
and prints a compact status for the operator.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from ldporto.core import read_json
from scripts.dev import report_full_v44

RUN = ROOT / 'analysis/video_31329be78ca4_v44_full_20261006'
VALIDATION = ROOT / '.cache/v44_validation/full_run'


def latest_resume_result():
    results = sorted(VALIDATION.glob('RESUME_*_RESULT.json'))
    return results[-1] if results else None


def completion_state():
    result_path = latest_resume_result()
    if result_path is None:
        return {'ready': False, 'reason': 'resume_result_missing'}
    result = read_json(result_path)
    if result.get('return_code') != 0:
        return {'ready': False, 'reason': 'resume_not_successful', 'return_code': result.get('return_code')}
    if (RUN / 'RUNNING.lock').exists():
        return {'ready': False, 'reason': 'run_still_locked'}
    required = ('analysis_summary.json', 'analysis_quality.json', 'run_manifest.json', 'second_curation_export.json')
    missing = [name for name in required if not (RUN / name).is_file()]
    if missing:
        return {'ready': False, 'reason': 'final_artifacts_missing', 'missing': missing}
    return {'ready': True, 'result': str(result_path)}


def main():
    state = completion_state()
    if not state['ready']:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 2
    report_full_v44.main()
    comparison = ROOT / 'docs/benchmarks/V43_V44_COMPARE.json'
    payload = read_json(comparison) if comparison.is_file() else {}
    changes = payload.get('changes', {})
    summary = {
        'status': 'FINALIZED',
        'comparison': str(comparison),
        'speaker_person': changes.get('speaker_person_mapping_coverage'),
        'active_speaker': changes.get('active_speaker_coverage'),
        'semantic_fallback': changes.get('semantic_fallback_ratio'),
        'camera_focus': changes.get('resolved_focus_coverage'),
        'zoom_proposed': changes.get('proposed_zoom_event_count'),
        'zoom_delivered': changes.get('zoom_event_count'),
        'story_payoff': changes.get('story_payoff_coverage'),
        'shortlist': changes.get('actual_package_shortlist_count') or changes.get('final_shortlist_count'),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
