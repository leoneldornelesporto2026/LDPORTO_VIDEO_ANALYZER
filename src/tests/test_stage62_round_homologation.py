import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
import jsonschema
from ldporto.round62_audit import build_report, junit_summary
from test_stage55_commercial_evidence import CASES, run_case


def test_actual_synthetic_commercial_receipt(tmp_path, monkeypatch):
    rows = []
    for case in CASES:
        with monkeypatch.context() as patch:
            result, calls = run_case(case, tmp_path, patch)
        state = result['main_moments'][0]['commercial_risk']['state']
        assert state == case['expected']
        rows.append({'id': case['id'], 'expected_ad': case['expected_ad'],
                     'observed_state': state, 'mocked_ocr_calls': len(calls)})
    measured = [r for r in rows if isinstance(r['expected_ad'], bool)
                and r['observed_state'] in {'confirmed_ad', 'probable_ad', 'measured_no_ad_evidence'}]
    receipt = {'scope': 'synthetic_mocked_ocr_not_real_accuracy', 'cases': rows,
               'decision_rule': 'confirmed/probable positive; measured_no_ad_evidence negative; all others abstain',
               'false_positives': [r['id'] for r in measured if r['expected_ad'] is False and r['observed_state'] != 'measured_no_ad_evidence'],
               'false_negatives': [r['id'] for r in measured if r['expected_ad'] is True and r['observed_state'] == 'measured_no_ad_evidence'],
               'abstentions': [r['id'] for r in rows if r not in measured],
               'precision': None, 'recall': None}
    if os.environ.get('LDPORTO_STAGE62_RECEIPT'):
        with Path(os.environ['LDPORTO_STAGE62_RECEIPT']).open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, indent=2)


def test_junit_counts_and_failure(tmp_path):
    path = tmp_path / 'cases.xml'
    path.write_text('<testsuites><testsuite><testcase classname="test_stage53_ocr_diagnostics" name="ok"/><testcase name="skip"><skipped message="GPU unavailable"/></testcase><testcase name="xf"><skipped type="pytest.xfail"/></testcase><testcase name="bad"><failure/></testcase><testcase name="error"><error/></testcase></testsuite></testsuites>')
    result = junit_summary(path, 1)
    assert [result[k] for k in ('passed', 'skipped', 'xfail', 'failed', 'errors')] == [1, 1, 1, 1, 1]
    assert not result['passed_check']


def test_empty_or_nonzero_cannot_pass(tmp_path):
    path = tmp_path / 'empty.xml'
    path.write_text('<testsuite/>')
    assert not junit_summary(path, 0)['passed_check']
    path.write_text('<testsuite><testcase name="pass"/></testsuite>')
    assert not junit_summary(path, 2)['passed_check']


def test_missing_proof_stays_null_and_schema(tmp_path):
    report = build_report(tmp_path, [], {'status': 'DISABLED'}, {})
    schema = json.loads((Path(__file__).resolve().parents[2] / 'schemas/round62_homologation.schema.json').read_text())
    jsonschema.validate(report, schema)
    assert not report['technical_tests_passed']
    assert report['baseline']['post'] is None
    assert report['runtime']['cuda_available'] is None
    assert report['ab_provenance']['source_sha256'] is None
    assert all(c['technical_status'] == 'not_measured' for c in report['checks'])
    report['publication_approved'] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ab_cli_missing_provenance_and_preserves_output(tmp_path):
    baseline = tmp_path / 'before.json'
    current = tmp_path / 'after.json'
    baseline.write_text(json.dumps({'metadata': {'sha256': 'a' * 64}, 'config': {'device': 'cpu'}}))
    current.write_text(json.dumps({'metadata': {'sha256': 'b' * 64}, 'config': {'device': 'cpu'}}))
    output = tmp_path / 'ab.json'
    cli = Path(__file__).resolve().parents[2] / 'scripts/dev/compare_benchmark62.py'
    command = [sys.executable, str(cli), '--baseline', str(baseline), '--current', str(current), '--output', str(output)]
    assert subprocess.run(command, capture_output=True, timeout=10).returncode == 0
    result = json.loads(output.read_text())
    assert result['comparison']['status'] == 'not_measured'
    assert not result['provenance_complete']
    assert result['current']['effective_prompts'] is None
    assert result['current']['model_fingerprints'] is None
    original = output.read_bytes()
    assert subprocess.run(command, capture_output=True, timeout=10).returncode != 0
    assert output.read_bytes() == original


def test_windows_powershell_json_encoding(tmp_path):
    import importlib.util
    path = Path(__file__).resolve().parents[2] / 'scripts/dev/audit_round62.py'
    spec = importlib.util.spec_from_file_location('audit62_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for encoding in ('utf-16', 'utf-8-sig', 'utf-8'):
        receipt = tmp_path / 'receipt.json'
        receipt.write_text('{"status": "não medido"}', encoding=encoding)
        assert module.read_json(receipt) == {'status': 'não medido'}
