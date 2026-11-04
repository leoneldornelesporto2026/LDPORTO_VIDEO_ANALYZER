"""Commercial/ranking snapshot replay; no external inference."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.commercial_gate import refine_candidates
from ldporto.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    read = lambda n: json.loads((args.folder / n).read_text(encoding='utf-8-sig'))
    original = read('main_moments.json')
    rows = refine_candidates(original, read('transcript_segments.json'), cfg=load_config()['understanding'])
    before = {r['moment_id']: r for r in original}
    changed = [{'moment_id': r['moment_id'], 'before': before[r['moment_id']].get('content_type'),
                'after': r['content_type'], 'commercial_score': r['commercial_score'],
                'signals': r['commercial_classification']['signals']} for r in rows
               if before[r['moment_id']].get('content_type') != r['content_type']]
    report = {'execution_scope': 'commercial_snapshot_replay', 'candidate_count': len(rows),
              'excluded_commercial_before': sum(r.get('commercial_score', 0) >= .6 for r in original),
              'excluded_commercial_after': sum(r['commercial_classification']['eligibility'] == 'excluded' for r in rows),
              'changed': changed, 'ocr_rerun': False, 'asr_rerun': False, 'llm_rerun': False}
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('commercial_replay_metrics.json', report), ('main_moments.json', rows)]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
