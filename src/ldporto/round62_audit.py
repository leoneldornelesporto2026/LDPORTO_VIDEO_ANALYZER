"""Read-only round audit. Test evidence never grants editorial approval."""
from pathlib import Path
import hashlib
import platform
import sys
import xml.etree.ElementTree as ET
from importlib import metadata

SNAPSHOT_TEST = 'src/tests/test_v4_final.py::test_work_package_has_single_derived_manifest_files'
STAGES = {53: 'ocr_diagnostics', 54: 'ocr_gui', 55: 'commercial_evidence',
          56: 'ocr_replay_audit', 57: 'local_yolo', 58: 'body_ab',
          59: 'resource_budget', 60: 'inference_smoke', 61: 'curation_canary',
          62: 'round_homologation'}


def reference(root, relative):
    path = root / relative
    return {'path': relative, 'exists': path.is_file(),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


def junit_summary(path, exit_code):
    """Count actual case outcomes, including pytest xfail/xpass representations."""
    counts = dict(passed=0, skipped=0, xfail=0, xpass=0, failed=0, errors=0)
    cases = []
    for case in ET.parse(path).getroot().iter('testcase'):
        skip = case.find('skipped')
        if case.find('error') is not None:
            outcome = 'errors'
        elif case.find('failure') is not None:
            outcome = 'failed'
        elif skip is not None:
            outcome = 'xfail' if 'xfail' in skip.get('type', '').lower() else 'skipped'
        else:
            outcome = 'passed'
        counts[outcome] += 1
        cases.append({'id': case.get('classname', '') + '::' + case.get('name', ''),
                      'outcome': outcome, 'reason': skip.get('message') if skip is not None else None})
    return {**counts, 'exit_code': exit_code,
            'passed_check': exit_code == 0 and not counts['failed'] and not counts['errors'] and bool(cases),
            'cases': cases, 'xpass_limitation': 'Non-strict XPASS is indistinguishable from pass in JUnit; consult pytest -r sxX log.'}


def build_report(root, runs, ocr, commercial):
    root = Path(root)
    checks = []
    for stage, name in STAGES.items():
        matched = [case for run in runs for case in run['cases']
                   if f'test_stage{stage}_{name}' in case['id']]
        checkpoints = reference(root, f'docs/archive/automation_20261012/execucao/checkpoints/CHECKPOINT_ETAPA_{stage}.md')
        checks.append({'stage': stage, 'checkpoint': checkpoints,
                       'test_module': reference(root, f'src/tests/test_stage{stage}_{name}.py'),
                       'tested_cases': len(matched),
                       'technical_status': 'passed' if matched and all(c['outcome'] == 'passed' for c in matched)
                       else 'partial' if matched else 'not_measured',
                       'real_media_status': 'not_measured'})
    versions = {}
    for package in ('torch', 'pyannote.audio', 'faster-whisper', 'ollama', 'ultralytics', 'pytesseract'):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {'schema_version': '62.1', 'evidence_scope': 'offline_tests_and_historical_references',
            'technical_tests_passed': bool(runs) and all(r['passed_check'] for r in runs),
            'real_media_homologated': False, 'publication_approved': False,
            'publication_ready': False, 'preview_approved': None,
            'opusclip_superiority': None, 'checks': checks, 'test_runs': runs,
            'runtime': {'python': sys.version.split()[0], 'platform': platform.platform(),
                        'package_versions': versions, 'cuda_available': None,
                        'actual_devices': None, 'pyannote_inference': 'not_measured',
                        'whisper_inference': 'not_measured', 'ollama_service': 'not_measured',
                        'ollama_inference': 'not_measured'},
            'ocr': {'current_readiness': ocr, 'disabled_contract': 'tested_with_fixtures',
                    'episode_executed': None, 'episode_languages': None},
            'vision': {'yolo_real_execution': None, 'real_episode_device': None,
                       'hog_synthetic_history': reference(root, 'docs/archive/automation_20261012/execucao/etapa59/PERFORMANCE_REPORT_VERIFIED_59.json')},
            'replay_17c': {'observed_episode_execution': None, 'status': 'not_measured',
                           'contract_test': reference(root, 'src/tests/test_stage56_ocr_replay_audit.py')},
            'commercial': {'synthetic': commercial, 'real_false_positives': None,
                           'real_false_negatives': None, 'real_precision': None, 'real_recall': None},
            'goldset': {'body_precision': None, 'body_recall': None, 'speaker_person': None,
                        'active_speaker': None, 'editorial_benefit': None, 'status': 'not_measured'},
            'canary': {'real_status': 'real_canary_not_run',
                       'historical_receipt': reference(root, 'docs/archive/automation_20261012/execucao/etapa61/real_not_run.json'),
                       'synthetic_receipt': reference(root, 'docs/archive/automation_20261012/execucao/etapa61/fixture_receipt.json'),
                       'human_approval': False},
            'baseline': {'scope': 'historical_supplied_not_remeasured',
                         'reference': reference(root, 'docs/archive/automation_20261012/execucao/checkpoints/CHECKPOINT_ETAPA_52.md'),
                         'supplement_reference': reference(root, 'docs/archive/automation_20261012/execucao/etapa58/REPORT_ETAPA_58.json'),
                         'supplement_supplied': {'flagged_denominator': 19299, 'ollama_minutes_approx': 90},
                         'post': None, 'delta': None},
            'ab_provenance': {'source_sha256': None, 'model_fingerprints': None,
                              'config_hashes': None, 'effective_prompts': None,
                              'status': 'not_measured'},
            'costs': {'paid_services': 0, 'real_media_inference_seconds': None,
                      'gpu_kernel_seconds': None, 'test_time_source': 'JUnit/logs',
                      'installations': 0, 'downloads': 0}}
