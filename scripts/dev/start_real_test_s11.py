"""One-command, non-publishing S9–S11 REAL smoke on Windows.

Only renders ONE 1080x1920 canary. Requires the real READY ZIP and its exact
original video; never authorizes stories batch nor asserts human approval.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curator_delivery import prepare_plan, save_json, render_clip
from ldporto.performance_acceptance import resource_diagnostic
from ldporto.homologation_s11 import homologate, markdown_report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', required=True)
    p.add_argument('--source', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--music')
    p.add_argument('--decisions')
    p.add_argument('--draft-captions', action='store_true', help='Burn unapproved ASR subtitles for comparison ONLY')
    args = p.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    resources = resource_diagnostic()
    save_json(output/'S10_RESOURCES.json', resources)
    plan = prepare_plan(args.package, args.source, music_path=args.music, decisions_path=args.decisions, output_dir=output)
    save_json(output/'CURATOR_S9_PLAN.json', plan)
    preview = render_clip(plan, 0, output, draft_captions=args.draft_captions)
    save_json(output/'S9_CANARY_REPORT.json', preview)
    report = homologate(package=args.package, source=args.source, preview=preview['file'])
    save_json(output/'S11_HOMOLOGATION_PENDING.json', report)
    (output/'S11_HOMOLOGATION_PENDING.md').write_text(markdown_report(report), encoding='utf-8')
    print(json.dumps({'status': 'CANARY_RENDERED_REQUIRES_HUMAN_REVIEW',
                      'plan': str(output/'CURATOR_S9_PLAN.json'),
                      'preview_mp4': preview['file'],
                      'preview_sha256': preview['sha256'],
                      'clips_planned': len(plan['clips']),
                      'no_batch_without_human_approval': True,
                      'no_publishing_actions': True}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
