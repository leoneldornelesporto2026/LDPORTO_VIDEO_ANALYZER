"""Read-only A/B envelope. Missing fingerprints/prompts stay null, never inferred."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.homologation_audit import compare_outputs


def envelope(path, prompts=None):
    path = Path(path)
    if path.is_dir():
        path = path / 'analysis.json'
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    config = data.get('config')
    config_hash = data.get('configuration_sha256')
    if not config_hash and isinstance(config, dict) and config:
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    prompt_receipt = None
    if prompts:
        p = Path(prompts)
        prompt_receipt = {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                          'recorded_requests': json.loads(p.read_text(encoding='utf-8-sig')),
                          'scope': 'user_supplied_request_capture_requires_review'}
    return {'analysis_path': str(path), 'analysis_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_sha256': (data.get('metadata') or {}).get('sha256'),
            'config_hash': config_hash, 'model_fingerprints': (data.get('provenance') or {}).get('model_fingerprints'),
            'effective_prompts': prompt_receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--baseline-prompts')
    parser.add_argument('--current-prompts')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = envelope(args.baseline, args.baseline_prompts)
    after = envelope(args.current, args.current_prompts)
    comparison = compare_outputs(args.baseline, args.current)
    complete = all(row['source_sha256'] and row['config_hash'] and row['model_fingerprints']
                   and row['effective_prompts'] for row in (before, after))
    result = {'schema_version': '62.ab.1', 'baseline': before, 'current': after,
              'comparison': comparison, 'provenance_complete': bool(complete),
              'scope': 'descriptive_requires_human_review', 'publication_approved': False,
              'opusclip_superiority': None,
              'changed_configuration_policy': 'Different config hashes suppress legacy deltas; use annotated body_ab_stage58.py for the controlled HOG/YOLO experiment.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'provenance_complete': bool(complete), 'comparison_status': comparison['status']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
