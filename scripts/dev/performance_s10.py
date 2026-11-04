"""S10: combine measured local benchmark JSONs without mutating Analyzer caches.

Run existing R3B experiments (--run-model for Ollama) before invoking this report.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.performance_acceptance import evaluate_vision_ab, evaluate_semantic_ab, resource_diagnostic, review_checkpoint_state
from ldporto.curator_delivery import save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--semantic-report')
    parser.add_argument('--quality-review', help='Human QA/stories/ranking review bound to semantic benchmark hash; no inference')
    parser.add_argument('--vision-report')
    parser.add_argument('--run-manifest')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.quality_review and not args.semantic_report:
        parser.error('--quality-review requires --semantic-report')
    report = {'schema_version': '10.1', 'resource_diagnostics': resource_diagnostic(),
              'cache_mutated': False, 'performance_gain_proven': False, 'automatic_parallelism_enabled': False}
    if args.semantic_report:
        semantic = json.loads(Path(args.semantic_report).read_text(encoding='utf-8-sig'))
        if args.quality_review:
            semantic['quality_review'] = json.loads(Path(args.quality_review).read_text(encoding='utf-8-sig'))
        report['ollama_ab'] = evaluate_semantic_ab(semantic)
    if args.vision_report:
        report['vision_ab'] = evaluate_vision_ab(json.loads(Path(args.vision_report).read_text(encoding='utf-8')))
    if args.run_manifest:
        report['checkpoints'] = review_checkpoint_state(json.loads(Path(args.run_manifest).read_text(encoding='utf-8')))
    if not args.semantic_report and not args.vision_report:
        report['pending_benchmarks'] = ['real_ollama_compact_legacy', 'windows_face_hog_parallel_serial']
    save_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
