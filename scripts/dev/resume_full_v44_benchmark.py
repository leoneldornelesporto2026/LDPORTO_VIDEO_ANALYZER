"""Resume only this interrupted V4.4 benchmark, retaining every attempt record."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
folder = ROOT / 'analysis/video_31329be78ca4_v44_full_20261006'
validation = ROOT / '.cache/v44_validation/full_run'
prior = validation / 'FULL_RUN_RESULT.json'
if not prior.is_file() or not folder.is_dir():
    raise SystemExit('The original attempt must finish before its checkpoints can be resumed.')
if (folder / 'CANCEL_REQUESTED').exists() or (folder / 'RUNNING.lock').exists():
    raise SystemExit('Cancellation or active output lock remains; do not resume concurrently.')
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
stem = 'RESUME_' + stamp
command = [sys.executable, str(ROOT / 'analyze.py'), 'https://www.youtube.com/watch?v=yZ78vCgiPZk',
           '--config', str(ROOT / 'config/config.yaml'), '--output', str(folder)]
record = {'execution_scope': 'full_pipeline_resumed_own_fresh_checkpoints',
          'reason': 'runtime incorrectly rejected verified HF cache without token; fixed and short-inference verified',
          'cache_policy': 'reuse_completed_stages_from_initial_v44_attempt_only',
          'prior_attempt': json.loads(prior.read_text(encoding='utf-8')),
          'started_at': datetime.now(timezone.utc).isoformat(), 'output': str(folder), 'command': command}
started = time.perf_counter()
invocation = validation / (stem + '_INVOCATION.json')
invocation.write_text(json.dumps(record, indent=2), encoding='utf-8')
with (validation / (stem + '_console.log')).open('w', encoding='utf-8') as log:
    process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
    record['pid'] = process.pid
    invocation.write_text(json.dumps(record, indent=2), encoding='utf-8')
    result = process.wait()
record.update(return_code=result, wall_seconds=time.perf_counter() - started,
              finished_at=datetime.now(timezone.utc).isoformat())
(validation / (stem + '_RESULT.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record), flush=True)
raise SystemExit(result)
