"""Print the latest structured progress event without reading an entire run log."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
logs = sorted((ROOT / '.cache/v44_validation/full_run').glob('RESUME_*_console.log'))
if not logs:
    raise SystemExit('No resumed benchmark log found.')
with logs[-1].open('rb') as stream:
    stream.seek(0, 2)
    stream.seek(max(0, stream.tell() - 32768))
    lines = stream.read().decode('utf-8', errors='replace').splitlines()
for line in reversed(lines):
    if not line.startswith('LDPORTO_EVENT '):
        continue
    event = json.loads(line[len('LDPORTO_EVENT '):])
    row = {key:event.get(key) for key in ('stage', 'status', 'current', 'total', 'elapsed_seconds', 'substage')}
    if row.get('total') and isinstance(row.get('current'), (int,float)):
        row['percent'] = round(100 * row['current'] / row['total'], 1)
    print(json.dumps(row, ensure_ascii=False, separators=(',', ':')))
    break
else:
    print(json.dumps({'last_log_lines':lines[-2:]}, ensure_ascii=False))
