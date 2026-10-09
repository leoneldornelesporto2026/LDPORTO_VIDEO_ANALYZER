"""S11: evidence-based local report (Windows 3.11/NVIDIA/Ollama/FFmpeg/real videos)."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.homologation_s11 import homologate, markdown_report
from ldporto.curator_delivery import save_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('package', 'source', 'preview', 'batch-manifest', 'analysis', 'baseline', 'human-reviews', 'render-plan'):
        p.add_argument('--' + name)
    p.add_argument('--junit')
    p.add_argument('--offline', action='store_true',
                   help='Check CPU tools only; do not contact Ollama or inspect GPU')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    report = homologate(package=args.package, source=args.source, preview=args.preview,
                        batch_manifest=args.batch_manifest, analysis=args.analysis,
                        baseline=args.baseline, human_reviews=args.human_reviews, junit=args.junit,
                        render_plan=args.render_plan, offline=args.offline)
    save_json(args.output, report)
    Path(args.output).with_suffix('.md').write_text(markdown_report(report), encoding='utf-8')
    print(json.dumps({'report': args.output, 'blockers': report['blockers'],
                      'status': report['release_status']}, ensure_ascii=False, indent=2))
    return 0 if not report['blockers'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
