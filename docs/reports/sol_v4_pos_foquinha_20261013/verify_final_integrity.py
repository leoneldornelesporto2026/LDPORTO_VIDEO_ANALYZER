"""Read-only final verification; outputs only the V4 audit record and Git text."""
from collections import Counter
from datetime import datetime
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def checked(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('audit_path_outside_expected_directory')
    return path


def main():
    initial = json.loads((REPORT / 'initial_state.json').read_text(encoding='utf-8'))
    original = json.loads((REPORT / 'preservation_before.json').read_text(encoding='utf-8'))
    frozen = json.loads((REPORT / 'sources_frozen_final.json').read_text(encoding='utf-8'))
    analysis = ROOT / 'analysis' / 'video_1da839aad175'
    failures = []
    total = 0
    for name, meta in original['analysis_files'].items():
        path = checked(analysis, name)
        if not path.is_file() or path.stat().st_size != meta['bytes'] or sha(path) != meta['sha256']:
            failures.append({'scope': 'original_analysis', 'path': name})
        total += meta['bytes']
    current_names = {p.relative_to(analysis).as_posix() for p in analysis.rglob('*') if p.is_file()}
    unexpected = sorted(current_names - set(original['analysis_files']))
    package = checked(ROOT, original['package'])
    if package.stat().st_size != original['package_bytes'] or sha(package) != original['package_sha256']:
        failures.append({'scope': 'original_package', 'path': original['package']})
    for name, expected in initial['protected_package'].items():
        path = Path(name).resolve()
        if not path.is_relative_to((ROOT / '.package').resolve()) or sha(path) != expected:
            failures.append({'scope': 'protected_export', 'path': name})
    source = ROOT / 'input' / 'youtube' / '7laRa_F3FbA' / '7laRa_F3FbA.mp4'
    expected_source = '0231c20cfd8147d92926bda4f452777f3803c38b248064e65548f0b12a5fb98b'
    if sha(source) != expected_source or source.stat().st_size != 480580282:
        failures.append({'scope': 'original_media', 'path': str(source)})
    model = ROOT / 'models' / 'body' / 'yolo11n.pt'
    expected_model = '0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1'
    if sha(model) != expected_model or model.stat().st_size != 5613764:
        failures.append({'scope': 'existing_yolo_model', 'path': str(model)})
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if head != initial['head']:
        failures.append({'scope': 'git_head', 'value': head})
    for name, expected in frozen.items():
        path = checked(ROOT, name)
        if not path.is_file() or sha(path) != expected:
            failures.append({'scope': 'frozen_source_drift', 'path': name})
    before = json.loads((REPORT / 'before_full.json').read_text(encoding='utf-8'))
    after = json.loads((REPORT / 'after_full.json').read_text(encoding='utf-8'))
    a, b = Counter(after['test_identities']), Counter(before['test_identities'])
    missing = list((b - a).elements())
    added = list((a - b).elements())
    if missing or after['returncode'] or after['failed'] or after['errors']:
        failures.append({'scope': 'regression', 'missing': missing, 'returncode': after['returncode']})
    test_comparison = {'before_count': before['test_count'], 'after_count': after['test_count'],
                       'old_test_cases_preserved': not missing, 'missing': missing, 'added_count': len(added),
                       'added_cases': added, 'before_passed': before['passed'], 'after_passed': after['passed'],
                       'before_skipped': before['skipped'], 'after_skipped': after['skipped']}
    (REPORT / 'test_case_comparison.json').write_text(json.dumps(test_comparison, indent=2), encoding='utf-8')
    status = subprocess.check_output(['git', 'status', '--short'], cwd=ROOT, text=True, encoding='utf-8')
    (REPORT / 'git_after.txt').write_text(status, encoding='utf-8')
    packages = {}
    for package_name in ['torch', 'torchaudio', 'torchvision', 'ultralytics', 'opencv-python',
                         'opencv-contrib-python', 'av', 'scenedetect']:
        try:
            packages[package_name] = importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            packages[package_name] = None
    record = {'timestamp': datetime.now().astimezone().isoformat(),
              'state': 'VERIFIED' if not failures and not unexpected else 'FAILED',
              'failures': failures, 'unexpected_original_analysis_files': unexpected,
              'original_analysis_files_verified': len(original['analysis_files']),
              'original_analysis_bytes_verified': total,
              'completed_checkpoints_in_original_manifest': len(initial['completed_checkpoints']),
              'original_package_sha256': original['package_sha256'], 'original_media_sha256': expected_source,
              'existing_yolo_weight_sha256': expected_model, 'protected_exports_verified': len(initial['protected_package']),
              'head': head, 'head_unchanged': head == initial['head'], 'frozen_source_count': len(frozen),
              'test_comparison': test_comparison, 'packages': packages, 'python': sys.version,
              'scope': 'Read-only hashes after final regression; no inference, downloads, installations or cleanup.'}
    (REPORT / 'final_integrity.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in record.items() if k not in ('test_comparison', 'python', 'packages')}, indent=2))
    print(json.dumps({k: v for k, v in test_comparison.items() if k != 'added_cases'}))
    return 0 if record['state'] == 'VERIFIED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
