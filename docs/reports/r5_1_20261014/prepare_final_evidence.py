"""Attach measured test evidence to the final, additive semantic package."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return {c.get('classname', '') + '.' + c.get('name', ''):
            'skip' if c.find('skipped') is not None else
            'fail' if c.find('failure') is not None or c.find('error') is not None else 'pass'
            for c in ET.parse(path).findall('.//testcase')}


if __name__ == '__main__':
    tests = json.loads((REPORT/'final_validation.json').read_text(encoding='utf-8'))
    assert tests['returncode'] == 0 and tests['failed'] == 0 and tests['errors'] == 0
    old = rows(ROOT/'docs/reports/r5_20261014/release_full.xml')
    new = rows(REPORT/'final_validation.xml')
    missing = sorted(set(old)-set(new))
    old_pass_not_reproduced = sorted(k for k, v in old.items() if v == 'pass' and new.get(k) != 'pass')
    assert not missing and not old_pass_not_reproduced
    evidence = {k: v for k, v in tests.items() if k != 'test_identities'}
    evidence.update({
        'status': 'PASSED',
        'scope': 'full local regression; heavy pipelines mocked by existing fixtures; no new AV inference',
        'baseline_R5_passed': sum(v == 'pass' for v in old.values()),
        'baseline_R5_test_identities': len(old),
        'missing_R5_test_identities': missing,
        'old_pass_not_reproduced': old_pass_not_reproduced,
        'skipped_test_identities': sorted(k for k, v in new.items() if v == 'skip'),
        'evidence_files': [
            {'path_relative_to_project': str(p.relative_to(ROOT)).replace('\\', '/'),
             'bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in (REPORT/'final_validation.json', REPORT/'final_validation.xml',
                      REPORT/'final_validation.log', REPORT/'sources_before_release.json')],
        'human_review_completed': False, 'publication_ready': False,
    })
    (REPORT/'test_evidence_final.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    path = REPORT/'CHECKPOINT_A.json'
    checkpoint = json.loads(path.read_text(encoding='utf-8'))
    actual = 'provenance_focus_01.junit.xml'
    assert (REPORT/actual).is_file()
    if checkpoint['provenance_test_ref'] != actual:
        checkpoint['corrected_reference_from'] = checkpoint['provenance_test_ref']
        checkpoint['provenance_test_ref'] = actual
        path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: evidence[k] for k in ('status', 'passed', 'skipped', 'failed', 'errors',
                                              'baseline_R5_passed', 'old_pass_not_reproduced')}))
