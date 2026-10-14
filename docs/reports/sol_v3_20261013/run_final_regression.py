"""Record frozen source hashes and execute the actual complete regression once."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent


def sources():
    paths = set(ROOT.glob('*.py'))
    for directory, pattern in [('src','*.py'),('scripts','*.py'),('config','*.yaml'),('schemas','*.json')]:
        paths.update((ROOT/directory).rglob(pattern))
    paths.update((ROOT/'src/tests/fixtures').rglob('*.json'))
    return {path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if '__pycache__' not in path.parts}


def main():
    frozen = sources()
    (REPORT/'source_before_final_tests.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    command=[sys.executable,'-m','pytest','-q','-rs','--junitxml='+str(REPORT/'after_full.xml')]
    started=time.monotonic()
    with (REPORT/'after_full.log').open('x',encoding='utf-8') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
            encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    after=sources()
    drift=sorted(key for key in set(frozen)|set(after) if frozen.get(key)!=after.get(key))
    tree=ET.parse(REPORT/'after_full.xml')
    suites=tree.getroot().findall('testsuite')
    skipped=[{'name':case.get('classname')+'.'+case.get('name'), 'reason':case.find('skipped').get('message')}
             for case in tree.iter('testcase') if case.find('skipped') is not None]
    record={'command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-started,
            'scope':'complete current suite after SOL V3, frozen code and installed optional YOLO dependencies',
            'source_drift':drift, 'suites':[suite.attrib for suite in suites], 'skipped':skipped}
    (REPORT/'after_full_run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(record,ensure_ascii=False),flush=True)
    return result.returncode or bool(drift)


if __name__=='__main__':
    raise SystemExit(main())
