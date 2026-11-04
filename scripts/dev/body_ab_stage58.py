"""Local bounded body audit; no automatic video A/B, downloads or publication."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.body_ab import create_manifest, derive_frames, run_backend, compare_ab


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('manifest')
    create.add_argument('--source-metadata', type=Path, required=True)
    create.add_argument('--windows', type=Path)
    create.add_argument('--count', type=int, default=14)
    derive = commands.add_parser('derive')
    derive.add_argument('--video', type=Path, required=True)
    derive.add_argument('--images-dir', type=Path, required=True)
    derive.add_argument('--consent-local', action='store_true')
    run = commands.add_parser('run')
    run.add_argument('--vision-config', type=Path, required=True)
    run.add_argument('--mode', choices=('baseline', 'candidate'), required=True)
    run.add_argument('--consent-local', action='store_true')
    compare = commands.add_parser('compare')
    compare.add_argument('--baseline', type=Path, required=True)
    compare.add_argument('--candidate', type=Path, required=True)
    for command in (derive, run, compare):
        command.add_argument('--manifest', type=Path, required=True)
    for command in (create, derive, run, compare):
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path):
        return json.loads(path.read_text(encoding='utf-8-sig'))
    # Check before decoding/inference; exclusive final creation is a second guard.
    if args.output.exists():
        parser.error('Output already exists; prior artifacts are preserved')
    if args.command == 'manifest':
        result = create_manifest(read(args.source_metadata), count=args.count,
                                 windows=read(args.windows) if args.windows else None)
    elif args.command == 'derive':
        result = derive_frames(read(args.manifest), args.video, args.images_dir,
                               consent_local=args.consent_local)
    elif args.command == 'run':
        result = run_backend(read(args.manifest), read(args.vision_config), mode=args.mode,
                             consent_local=args.consent_local)
    else:
        result = compare_ab(read(args.manifest), read(args.baseline), read(args.candidate))
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        stream.write(encoded + '\n')
    print(json.dumps({'output': str(args.output), 'status': result.get('status'),
                      'mode': result.get('mode'), 'improvement_accepted': result.get('improvement_accepted')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
