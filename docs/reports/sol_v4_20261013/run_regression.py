"""Capture an actual pytest run and its test identities without changing sources."""
from pathlib import Path
import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('label')
    args = parser.parse_args()
    log = REPORT / (args.label + '.log')
    xml = REPORT / (args.label + '.xml')
    command = [sys.executable, '-m', 'pytest', '-q', '--junitxml=' + str(xml)]
    started = time.perf_counter()
    with log.open('wb') as handle:
        result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    record = {'command': command, 'returncode': result.returncode,
              'wall_seconds': time.perf_counter() - started}
    if xml.is_file():
        tree = ET.parse(xml)
        cases = tree.findall('.//testcase')
        record.update(test_count=len(cases),
                      passed=sum(not any(case.find(k) is not None for k in ('failure','error','skipped')) for case in cases),
                      failed=sum(case.find('failure') is not None for case in cases),
                      errors=sum(case.find('error') is not None for case in cases),
                      skipped=sum(case.find('skipped') is not None for case in cases),
                      test_identities=sorted(case.get('classname','') + '.' + case.get('name','') for case in cases))
    (REPORT / (args.label + '.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k != 'test_identities'}))
    raise SystemExit(result.returncode)
