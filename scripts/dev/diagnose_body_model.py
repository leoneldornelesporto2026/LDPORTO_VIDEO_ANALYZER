"""Inspect a local YOLO path without loading models, installing or downloading."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--model', help='Trusted local .pt; preferred location models/body/')
    parser.add_argument('--device', choices=('cpu', 'cuda'))
    args = parser.parse_args(argv)
    from ldporto.config import load_config
    from ldporto.body_model_paths import body_model_diagnostics
    cfg = load_config(args.config)['vision']
    if args.model:
        cfg['yolo_model'] = args.model
    if args.device:
        cfg['yolo_device'] = args.device
    print(json.dumps(body_model_diagnostics(cfg), ensure_ascii=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
