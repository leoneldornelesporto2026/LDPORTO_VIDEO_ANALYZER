"""Measure a completed checkpoint in a fresh process; never rewrite the source."""
from pathlib import Path
import argparse
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('label')
    parser.add_argument('--encoded',action='store_true')
    parser.add_argument('--input',type=Path)
    parser.add_argument('--read-only',action='store_true')
    args=parser.parse_args()
    from ldporto.core import digest,file_hash,write_json
    from ldporto.execution_receipts import snapshot_json,verify_receipt
    from ldporto.runtime_metrics import resource_snapshot
    source=args.input or ROOT/'analysis/video_1da839aad175/cache/0231c20cfd8147d9/10_active_speaker.json'
    output=REPORT/args.label
    output.mkdir(exist_ok=False)
    started=time.perf_counter()
    record,physical_sha=snapshot_json(source)
    read_seconds=time.perf_counter()-started
    started=time.perf_counter()
    receipt_state=verify_receipt('10_active_speaker',record)
    verify_seconds=time.perf_counter()-started
    logical_sha=digest(record)
    packing_seconds=0.
    physical=record
    if args.encoded:
        from ldporto.checkpoint_storage import encode_checkpoint
        started=time.perf_counter()
        physical=encode_checkpoint(record,stage='10_active_speaker')
        packing_seconds=time.perf_counter()-started
    destination=output/'10_active_speaker.json'
    write_seconds=None
    if not args.read_only:
        started=time.perf_counter()
        write_json(destination,physical)
        write_seconds=time.perf_counter()-started
    result={'source':str(source),'source_physical_sha256':physical_sha,'source_bytes':source.stat().st_size,
            'source_logical_sha256':logical_sha,'read_seconds':read_seconds,'verify_seconds':verify_seconds,
            'packing_seconds':packing_seconds,'write_seconds':write_seconds,'receipt_state':receipt_state,
            'output_bytes':destination.stat().st_size if destination.is_file() else None,
            'output_physical_sha256':file_hash(destination) if destination.is_file() else None,
            'mappings':len(record['data']['mappings']),'intervals':len(record['data']['intervals']),
            'resources':resource_snapshot(),
            'measurement_scope':'Fresh process completed checkpoint only; read+integrity+write, no inference. Peak RAM is process lifetime.'}
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
