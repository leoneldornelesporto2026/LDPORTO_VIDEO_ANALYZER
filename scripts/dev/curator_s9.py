"""S9 local Curator renderer: READY package -> canary -> manual approval -> MP4 batch -> final review.

Examples in docs/S9_S11_REAL_TEST.md. This never uploads anything.
"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.curator_delivery import (prepare_plan, load_json, save_json, render_clip,
                                      approve_canary, render_batch, finalize_batch)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest='action', required=True)
    pre = commands.add_parser('plan')
    pre.add_argument('--package', required=True)
    pre.add_argument('--source', required=True)
    pre.add_argument('--output', required=True)
    pre.add_argument('--decisions')
    pre.add_argument('--music')
    pre.add_argument('--shortlist', action='store_true')
    for action in ('canary', 'approve', 'batch', 'finalize'):
        cmd = commands.add_parser(action)
        cmd.add_argument('--plan', required=True)
        cmd.add_argument('--output', required=True)
        if action in ('approve', 'batch'):
            cmd.add_argument('--canary-report', required=True)
        if action == 'approve':
            cmd.add_argument('--checklist', required=True)
            cmd.add_argument('--reviewer', required=True)
        if action == 'batch':
            cmd.add_argument('--approval', required=True)
        if action == 'finalize':
            cmd.add_argument('--batch-manifest', required=True)
            cmd.add_argument('--reviews', required=True)
        if action in ('canary', 'batch'):
            cmd.add_argument('--draft-captions', action='store_true')
    args = p.parse_args()
    if args.action == 'plan':
        report = prepare_plan(args.package, args.source, decisions_path=args.decisions,
                              music_path=args.music, output_dir=Path(args.output).parent, prefer_stories=not args.shortlist)
    else:
        plan = load_json(args.plan)
        if args.action == 'canary':
            report = render_clip(plan, 0, Path(args.output).parent, draft_captions=args.draft_captions)
        elif args.action == 'approve':
            report = approve_canary(plan, load_json(args.canary_report), load_json(args.checklist), reviewer=args.reviewer)
        elif args.action == 'batch':
            report = render_batch(plan, load_json(args.approval), load_json(args.canary_report),
                                  args.output, draft_captions=args.draft_captions)
        else:
            report = finalize_batch(plan, load_json(args.batch_manifest), load_json(args.reviews))
    save_json(args.output, report) if args.action != 'batch' else None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
