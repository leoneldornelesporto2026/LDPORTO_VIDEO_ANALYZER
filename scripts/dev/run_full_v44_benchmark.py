"""One fresh full-pipeline benchmark, isolated from the preserved V4.3 artifacts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
folder=ROOT/'analysis/video_31329be78ca4_v44_full_20261006'
validation=ROOT/'.cache/v44_validation/full_run'
validation.mkdir(parents=True,exist_ok=True)
if folder.exists():
    raise SystemExit('Fresh benchmark destination already exists; do not overwrite or clean it.')
command=[sys.executable,str(ROOT/'analyze.py'),'https://www.youtube.com/watch?v=yZ78vCgiPZk',
         '--config',str(ROOT/'config/config.yaml'),'--output',str(folder)]
started=time.perf_counter()
record={'execution_scope':'full_pipeline','cache_policy':'fresh_analysis_directory_existing_local_models_and_source',
        'started_at':datetime.now(timezone.utc).isoformat(),'output':str(folder),'command':command,
        'baseline_preserved':str(ROOT/'analysis/video_31329be78ca4')}
(validation/'FULL_RUN_INVOCATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
with (validation/'full_run_console.log').open('w',encoding='utf-8') as log:
    process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    record['pid']=process.pid
    (validation/'FULL_RUN_INVOCATION.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    result=process.wait()
record.update(return_code=result,wall_seconds=time.perf_counter()-started,finished_at=datetime.now(timezone.utc).isoformat())
(validation/'FULL_RUN_RESULT.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record),flush=True)
raise SystemExit(result)
