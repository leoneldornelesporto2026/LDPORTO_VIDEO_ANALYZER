"""Retry an already exported second-curation ZIP without new model inference."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from ldporto.local_curator_handoff import auto_delivery  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Retry safe local Curator inbox handoff")
    parser.add_argument("--analysis-dir", required=True, help="Existing Analyzer analysis output directory")
    parser.add_argument("--curator-root", help="Optional local Curator repository folder")
    args = parser.parse_args(argv)
    run_folder = Path(args.analysis_dir).resolve()
    record = json.loads((run_folder / "second_curation_export.json").read_text(encoding="utf-8"))
    result = auto_delivery(record, curator_root=args.curator_root)
    (run_folder / "curator_delivery.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["delivery_status"] in ("DELIVERED", "ALREADY_DELIVERED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
