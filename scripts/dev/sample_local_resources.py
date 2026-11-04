"""Passive finite sampler of local Ollama processes and system GPU usage."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=900)
    args = parser.parse_args()
    if not 0 < args.seconds <= 2400:
        parser.error('finite duration must be 1..2400 seconds')
    import psutil
    executable = shutil.which('nvidia-smi')
    started = time.monotonic()
    with args.output.open('x', encoding='utf-8') as stream:
        while time.monotonic()-started < args.seconds:
            row = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'elapsed_seconds': time.monotonic()-started,
                   'logical_cpu_percent_system': psutil.cpu_percent(),
                   'ram_available_bytes_system': psutil.virtual_memory().available,
                   'processes': [], 'gpu': None,
                   'scope': 'observed_named_processes_and_system_gpu_not_exclusive_model_usage'}
            for process in psutil.process_iter(['name','pid','ppid','memory_info','cpu_times']):
                try:
                    info = process.info
                    if 'ollama' in (info['name'] or '').lower():
                        row['processes'].append({'pid': info['pid'],'parent_pid':info['ppid'],
                            'name': info['name'], 'rss_bytes': info['memory_info'].rss,
                            'vms_bytes': info['memory_info'].vms,
                            'cpu_user_seconds': info['cpu_times'].user,
                            'cpu_system_seconds': info['cpu_times'].system})
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            if executable:
                try:
                    result = subprocess.run([executable,'--query-gpu=name,memory.total,memory.used,utilization.gpu',
                        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    row['gpu'] = {'csv_fields':['name','memory_total_mib','memory_used_mib','utilization_gpu_percent'],
                                  'exit_code':result.returncode,'csv':result.stdout.strip()}
                except Exception as exc:
                    row['gpu'] = {'error_type':type(exc).__name__}
            stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            stream.flush()
            time.sleep(min(5, max(0, args.seconds-(time.monotonic()-started))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
