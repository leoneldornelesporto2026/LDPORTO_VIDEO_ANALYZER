"""Read existing measurements, compare protected hashes, and index final evidence."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent


def read(name):
    return json.loads((REPORT/name).read_text(encoding='utf-8'))


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):
            digest.update(data)
    return digest.hexdigest()


def main():
    initial=read('inventory_before.json')
    baseline_files=read('backup.json')['files']
    protected={name:{'before':value,'after':sha(ROOT/name)}
               for name,value in initial['protected_package_sha256'].items()}
    for row in protected.values():
        row['unchanged']=row['before']==row['after']
    history=read('runtime_historical_replay.json')
    archives={row['archive']:{'before':row['archive_sha256'],
        'after':sha(ROOT/'pacotes_para_enviar'/row['archive'])} for row in history['recorded_runs']}
    for row in archives.values():
        row['unchanged']=row['before']==row['after']
    video=sha(ROOT/'input/youtube/jNQXAC9IVRw/jNQXAC9IVRw.mp4')
    branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    frozen=read('source_before_final_tests.json')
    drift=[name for name,value in frozen.items() if not (ROOT/name).is_file() or sha(ROOT/name)!=value]
    code_deltas={name:{'before':(baseline_files.get(name) or {}).get('sha256'),'after':value}
                 for name,value in frozen.items()
                 if (baseline_files.get(name) or {}).get('sha256') != value}
    removed=[name for name in baseline_files if not (ROOT/name).is_file()]
    files=sorted(ROOT.glob('*.py'))+sorted((ROOT/'src').rglob('*.py'))+sorted((ROOT/'scripts').rglob('*.py'))
    introduced=[path.relative_to(ROOT).as_posix() for path in files
                if path.relative_to(ROOT).as_posix() not in baseline_files and '__pycache__' not in path.parts]
    packages={name:importlib.metadata.version(name) for name in ('torch','torchaudio','torchvision','ultralytics',
        'opencv-python','opencv-contrib-python','faster-whisper','ctranslate2','psutil','polars','ultralytics-thop')}
    integrity={'schema_version':'1.0','branch':branch,'head':head,
        'branch_and_head_unchanged':branch==initial['branch'] and head==initial['head'],
        'protected_package_files':protected,'reference_packages':archives,
        'source_video_sha256':video,'source_matches_reference':video==history['recorded_runs'][0]['source_sha256'],
        'source_drift_since_final_test_freeze':drift,'source_deltas_from_sol_v3_inventory':code_deltas,
        'files_removed_this_round':removed,'introduced_code_paths':introduced,'installed_package_versions':packages,
        'retired_orchestrator_absent':not (ROOT/'orquestrador.py').exists(),
        'retired_automation_absent':not (ROOT/'automacao').exists(),
        'scope':'hashed known protected artifacts and frozen code; does not claim a before hash for unrecorded directories'}
    (REPORT/'final_integrity.json').write_text(json.dumps(integrity,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[json.loads(path.read_text(encoding='utf-8')) for path in sorted((REPORT/'qwen_ab').glob('[123]_*.json'))]
    pair_times={mode:[sum(row['wall_seconds'] for row in rows if row['mode']==mode and row['repetition']==repetition)
                       for repetition in (1,2,3)] for mode in ('legacy','compact')}
    output_shapes={mode:[{'stage':row['stage'],'repetition':row['repetition'],
        'counts':{key:len(value) for key,value in row.get('response',{}).items() if isinstance(value,list)}}
        for row in rows if row['mode']==mode] for mode in ('legacy','compact')}
    resource_rows=[json.loads(line) for line in (REPORT/'qwen_resource_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    gpu_rows=[row['gpu']['csv'].split(',') for row in resource_rows if row.get('gpu') and row['gpu'].get('exit_code')==0]
    decision={'schema_version':'1.0','completed_model_calls':len(rows),
        'all_schema_and_references_valid':all(row['schema_references_and_coverage_valid'] for row in rows),
        'pair_wall_seconds':pair_times,'pair_median_seconds':{mode:statistics.median(values) for mode,values in pair_times.items()},
        'compact_pair_change_percent':(statistics.median(pair_times['compact'])/statistics.median(pair_times['legacy'])-1)*100,
        'output_shapes':output_shapes,'adopt_compact_by_default':False,
        'reason':'compact chunk changed editorial output count; global became slower; pair median did not improve; human quality unverified',
        'measurement_scope':'fixed source input and max preset; background user processes not suspended',
        'resources':{'samples':len(resource_rows),'sampling_started_after_first_pair':True,
            'gpu_used_mib_min':min(float(row[2]) for row in gpu_rows),
            'gpu_used_mib_max':max(float(row[2]) for row in gpu_rows),
            'gpu_utilization_percent_min':min(float(row[3]) for row in gpu_rows),
            'gpu_utilization_percent_max':max(float(row[3]) for row in gpu_rows),
            'ram_available_bytes_min':min(row['ram_available_bytes_system'] for row in resource_rows),
            'ram_available_bytes_max':max(row['ram_available_bytes_system'] for row in resource_rows),
            'logical_cpu_percent_system_max':max(row['logical_cpu_percent_system'] for row in resource_rows),
            'model_exclusive_ram_bytes':None,'model_exclusive_gpu_utilization_percent':None,
            'scope':'system shared GPU/RAM; observed Ollama named-process RSS is not model RAM'}}
    (REPORT/'qwen_ab/assessment.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2),encoding='utf-8')
    status=subprocess.check_output(['git','status','--short','--untracked-files=normal'],cwd=ROOT,text=True)
    (REPORT/'git_final_status.txt').write_text(status,encoding='utf-8')
    print(json.dumps({'source_drift':drift,'removed':removed,'new_code_files':len(introduced),
        'protected_unchanged':all(row['unchanged'] for row in protected.values()),'qwen_pair_medians':decision['pair_median_seconds']}))


if __name__=='__main__':
    main()
