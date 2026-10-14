"""Explicit stage-21 artifact replay. No pipeline or inference engine imports."""
import json
import hashlib
import tempfile
import zipfile
from pathlib import Path

from .core import digest, file_hash
from .export_privacy import safe_path, privacy_findings
from .run_status import DEPENDENCIES

# Pinned historical contract evidence, independent of any development executor.
# Absence remains a blocked historical compatibility check, never an approval.
HISTORICAL_SNAPSHOT = Path(__file__).resolve().parents[2] / 'docs/archive/automation_20261012/execucao/snapshots/LDPORTO_STAGE_63.zip'
HISTORICAL_SNAPSHOT_SHA256 = '8b814c4501eb1441f3025ca635ddd8163de25bbdbab99974a6e4e3d90581d23b'
HISTORICAL_FINGERPRINT = 'f13cb5d27e9b280592247f2d5bd9fc5c10e8debebb359430da6be3f9bf52902f'


def historical_contract(expected):
    provenance = expected.get('execution_provenance', {})
    if (expected.get('status') != 'ok' or expected.get('method') != 'uncached_export'
            or provenance.get('origin') != 'executed'
            or provenance.get('analyzer_build') != 'R4.9-S4-TRACKING-FACIAL'
            or provenance.get('code_fingerprint') != HISTORICAL_FINGERPRINT):
        return 'historical_producer_mismatch'
    try:
        raw = safe_path(HISTORICAL_SNAPSHOT).read_bytes()
        if hashlib.sha256(raw).hexdigest() != HISTORICAL_SNAPSHOT_SHA256:
            return 'historical_snapshot_checksum_mismatch'
        import io
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            hashes = {Path(name).name: hashlib.sha256(archive.read(name)).hexdigest()
                      for name in archive.namelist() if name.startswith('src/ldporto/')
                      and name.count('/') == 2 and name.endswith('.py')}
        fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        if fingerprint != HISTORICAL_FINGERPRINT:
            return 'historical_code_fingerprint_mismatch'
    except (OSError, ValueError, zipfile.BadZipFile):
        return 'historical_snapshot_unavailable'
    return None


def verified_json(folder, path, hashes):
    raw = safe_path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != hashes.get(path.relative_to(folder).as_posix()):
        raise ValueError('upstream_changed_before_validation_read')
    return json.loads(raw.decode('utf-8-sig'))


def handoff_receipt(folder, expected, hashes):
    """Stage 20 is an uncached export in reports.py; verify its artifact receipt.

    Legacy exports without producer-recorded handoff hashes require review;
    generating new hashes now does not prove the original export's integrity.
    """
    path = folder / 'manifest.json'
    if not path.is_file() or expected.get('method') != 'uncached_export':
        return 'missing_handoff_receipt'
    manifest = verified_json(folder, path, hashes)
    checks = manifest.get('artifact_checksums', {})
    reason = historical_contract(expected)
    if reason:
        return reason
    # reports.py signs collection_refs and replay_files. The complete handoff
    # is neither signed by that contract nor consumed by build_core_package.
    essential = {'CHATGPT_ANALYSIS_HANDOFF.compact.json', 'second_curation_package.json'}
    if not essential.issubset(checks) or manifest.get('stage_status', {}).get('20_handoff', {}).get('status') != 'ok':
        return 'uncached_handoff_without_producer_checksums'
    for name, checksum in checks.items():
        path = folder / name
        if Path(name).is_absolute() or '..' in Path(name).parts or path.parent != folder:
            return 'unsafe_handoff_artifact_reference'
        if not path.is_file() or file_hash(safe_path(path)) != checksum:
            return 'handoff_artifact_checksum_mismatch'
    package = verified_json(folder, folder / 'second_curation_package.json', hashes)
    compact = verified_json(folder, folder / 'CHATGPT_ANALYSIS_HANDOFF.compact.json', hashes)
    if (not isinstance(package, dict) or package.get('schema_version') != '3.1'
            or not isinstance(package.get('candidates'), list)
            or not isinstance(compact, dict) or compact.get('schema_version') != '4.2'
            or compact.get('second_curation_package_ref', {}).get('path') != 'second_curation_package.json'):
        return 'handoff_schema_mismatch'
    return None


def snapshot(folder):
    folder = safe_path(folder)
    result = {}
    for p in sorted(folder.rglob('*')):
        safe_path(p)
        if p.is_file():
            name = p.relative_to(folder).as_posix()
            if privacy_findings(name):
                raise ValueError('private_artifact_name')
            result[name] = file_hash(p)
    return result


def plan_recovery(folder, cache):
    folder, cache = safe_path(folder), safe_path(cache)
    before = snapshot(folder)
    if not cache.is_relative_to(folder):
        raise ValueError('cache_outside_analysis')
    document = verified_json(folder, folder / 'analysis.json', before)
    stages = []
    expected = document.get('run_manifest', {}).get('stage_status', {})
    if not expected:
        raise ValueError('missing_stage_dependencies')
    if any(stage not in DEPENDENCIES for stage in expected):
        raise ValueError('unknown_stage_dependency')
    for stage in sorted(expected):
        if stage.startswith('21_'):
            continue
        record_path = cache / (stage + '.json')
        reason = None
        if not record_path.is_file():
            reason = handoff_receipt(folder, expected[stage], before) if stage == '20_handoff' else 'missing_cache_record'
        else:
            record = verified_json(folder, record_path, before)
            if record.get('status') not in ('ok', 'partial', 'skipped'):
                reason = 'invalid_cache_status'
            elif record.get('data_checksum') != digest(record.get('data')):
                reason = 'data_checksum_mismatch'
            elif not record.get('key') or not all(field in record.get('cache_manifest', {}) for field in
                     ('input', 'params', 'code', 'dependencies', 'versions', 'output_version')):
                reason = 'missing_cache_contract'
            elif expected[stage].get('key') != record['key'] or expected[stage].get('status') != record['status']:
                reason = 'stage_receipt_mismatch'
            elif any(record.get(field) != record['cache_manifest'][manifest_field] for field, manifest_field in
                     (('input_hash', 'input'), ('config_hash', 'params'), ('output_version', 'output_version'))):
                reason = 'cache_contract_mismatch'
            elif (record.get('execution_receipt') or {}).get('schema_version') == '2.0':
                from .execution_receipts import verify_receipt
                for artifact in record.get('artifact_checksums', {}):
                    try:
                        path = safe_path(Path(artifact))
                        if not path.is_relative_to(folder):
                            reason = 'artifact_missing_or_outside_analysis'
                    except (OSError, ValueError):
                        reason = 'artifact_missing_or_outside_analysis'
                evidence = verify_receipt(stage, record, artifacts=reason is None)
                if evidence != 'verified' and not (evidence == 'verified_skipped' and stage in {'13_ocr', '14_audio_events', '19b_preview_verifier'}):
                    reason = 'cache_execution_receipt_' + evidence
                else:
                    observed = record['execution_receipt'].get('dependency_fingerprints', {})
                    if set(observed) != set(DEPENDENCIES.get(stage, ())):
                        reason = 'dependency_contract_mismatch'
                    for dependency, receipt in observed.items():
                        rel = (cache / (dependency + '.json')).relative_to(folder).as_posix()
                        if (receipt.get('checkpoint_sha256') != before.get(rel)
                                or receipt.get('key') != expected.get(dependency, {}).get('key')
                                or receipt.get('status') != expected.get(dependency, {}).get('status')
                                or receipt.get('evidence') not in {'verified', 'verified_skipped', 'verified_partial'}):
                            reason = 'dependency_checksum_mismatch'
            elif not record.get('execution_receipt'):
                reason = 'legacy_unattested'
            elif (not record.get('execution_receipt')
                  or record['execution_receipt'].get('module_fingerprint') != digest(record['execution_receipt'].get('module_hashes'))
                  or record['cache_manifest']['code'] != digest(record['execution_receipt'].get('module_hashes'))
                  or record['execution_receipt'].get('source_sha256') != record.get('input_hash')
                  or record['execution_receipt'].get('producer') != 'Context.step'
                  or record['execution_receipt'].get('execution_returncode') != 0):
                reason = 'cache_execution_receipt_mismatch'
            elif any(dependency not in expected for dependency in DEPENDENCIES.get(stage, ())):
                reason = 'missing_stage_dependency'
            elif record['cache_manifest']['dependencies'] != digest({dependency: {
                    'key': expected[dependency].get('key'), 'status': expected[dependency].get('status')}
                    for dependency in DEPENDENCIES.get(stage, ()) if dependency in expected}):
                reason = 'dependency_checksum_mismatch'
            else:
                for name, checksum in record.get('artifact_checksums', {}).items():
                    artifact = Path(name)
                    if not artifact.is_absolute():
                        artifact = Path.cwd() / artifact
                    if not artifact.is_file() or not artifact.absolute().is_relative_to(folder):
                        reason = 'artifact_missing_or_outside_analysis'
                        break
                    if file_hash(safe_path(artifact)) != checksum:
                        reason = 'artifact_checksum_mismatch'
                        break
        if reason is None and any(dependency not in expected for dependency in DEPENDENCIES.get(stage, ())):
            reason = 'missing_stage_dependency'
        stages.append({'stage': stage, 'cache': 'miss' if reason else 'hit', 'reason': reason,
                       'validation_source': 'export_receipt' if not record_path.is_file() and stage == '20_handoff' else 'stage_cache'})
    for key, ref in document.get('collection_refs', {}).items():
        name = ref.get('path', '')
        path = folder / name
        if not name or Path(name).is_absolute() or '..' in Path(name).parts or path.parent != folder:
            raise ValueError('unsafe_collection_reference')
        if not path.is_file() or file_hash(safe_path(path)) != ref.get('sha256'):
            raise ValueError('collection_checksum_mismatch')
    blockers = []
    # The loader consumes inline metadata/gates/subtitle review as well as
    # collections. Signing the latter alone does not authenticate analysis.json.
    receipt_path = cache / '20_handoff.json'
    receipt = verified_json(folder, receipt_path, before) if receipt_path.is_file() else verified_json(folder, folder / 'manifest.json', before) if (folder / 'manifest.json').is_file() else {}
    input_checksum = receipt.get('artifact_checksums', {}).get('analysis.json') or receipt.get('artifact_checksums', {}).get(str(folder / 'analysis.json'))
    if (folder / 'report_execution_receipt.json').is_file():
        from .execution_receipts import verify_report_receipt
        try:
            final_receipt, copies = verify_report_receipt(folder)
            input_checksum = final_receipt['artifact_checksums'].get('analysis.json')
            if hashlib.sha256(copies['analysis.json']).hexdigest() != before.get('analysis.json'):
                blockers.append('analysis_changed_before_receipt_consumption')
            if final_receipt['execution_receipt']['source_sha256'] != document.get('metadata', {}).get('sha256'):
                blockers.append('report_source_identity_mismatch')
        except (OSError, ValueError, KeyError, TypeError):
            blockers.append('final_report_receipt_invalid')
    if input_checksum != before.get('analysis.json'):
        blockers.append('consumed_analysis_document_without_original_checksum')
    if snapshot(folder) != before:
        blockers.append('upstream_changed_during_validation')
    can_replay = not blockers and not any(row['cache'] == 'miss' for row in stages)
    return {'mode': 'dry_run', 'status': 'ready_for_review' if can_replay else 'blocked',
            'target': '21_second_curation_handoff', 'stages': stages,
            'can_replay': can_replay, 'blockers': blockers,
            'hits': sum(row['cache'] == 'hit' for row in stages),
            'misses': sum(row['cache'] == 'miss' for row in stages),
            'previous_reported_hits': 25,
            'would_write': ['SECOND_CURATION_DERIVED/', 'DERIVED_FROM.json'],
            'approval_gates': ['explicit_apply', 'reviewed_snapshot', 'verified_consumed_inputs', 'new_isolated_destination'],
            'risks': ['local_receipts_are_internal_consistency_not_independent_signatures', 'editorial_and_publication_gates_remain_unapproved'],
            'historical_contract': {'snapshot_sha256': HISTORICAL_SNAPSHOT_SHA256,
                                    'producer_fingerprint': HISTORICAL_FINGERPRINT,
                                    'required_signed_artifacts': ['second_curation_package.json', 'CHATGPT_ANALYSIS_HANDOFF.compact.json'],
                                    'complementary_not_consumed': ['CHATGPT_ANALYSIS_HANDOFF.json']},
            'would_invalidate': ['21_second_curation_handoff'], 'upstream_recomputation': False,
            'expensive_inference_executed': False, 'publication_ready': False,
            'reference_hashes': before}


def recover(folder, cache, output=None, *, apply=False, expected_hashes=None,
            review_only=False):
    """Strict verified replay by default; explicit reduced-trust review is separate.

    ``review_only=True`` NEVER claims that stage 21 is restored or that the
    historical cache receipts have been proven. It only creates a sanitized
    local-evidence input from locally consistent exports after explicit apply.
    """
    if review_only:
        from .legacy_review import plan_legacy_review, create_legacy_review_input
        if not apply:
            return plan_legacy_review(folder)
        if output is None:
            raise ValueError('explicit_review_output_required')
        return create_legacy_review_input(folder, output, expected_hashes=expected_hashes)
    plan = plan_recovery(folder, cache)
    if not apply:
        return plan
    if not plan['can_replay'] or expected_hashes != plan['reference_hashes']:
        raise ValueError('replay_blocked_or_snapshot_mismatch')
    if output is None:
        raise ValueError('explicit_output_required')
    folder = Path(folder).absolute()
    output = Path(output).absolute()
    safe_path(output.parent)
    if output.is_relative_to(folder) or folder.is_relative_to(output) or output.exists():
        raise ValueError('unsafe_or_existing_output')
    from .compact_artifacts import load_analysis_artifacts
    from .second_curation_export import build_core_package
    # Consume only bytes verified against the reviewed plan, never re-open
    # original inputs after validation. No media is copied or processed.
    with tempfile.TemporaryDirectory(prefix='curation64_', dir=output.parent) as temporary:
        temporary = Path(temporary)
        inputs, staged = temporary / 'inputs', temporary / 'output'
        inputs.mkdir()
        raw = safe_path(folder / 'analysis.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hashes['analysis.json']:
            raise ValueError('upstream_changed_before_consumption')
        document = json.loads(raw.decode('utf-8-sig'))
        (inputs / 'analysis.json').write_bytes(raw)
        for ref in document.get('collection_refs', {}).values():
            name = ref['path']
            raw = safe_path(folder / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected_hashes.get(name):
                raise ValueError('upstream_changed_before_consumption')
            (inputs / name).write_bytes(raw)
        analysis = load_analysis_artifacts(inputs)
        result = build_core_package(analysis, source=None, output_dir=staged,
                                   package=analysis.get('second_curation_package'),
                                   cfg={'second_curation_visual_candidate_limit': 0,
                                        'include_candidate_previews': False}, directory_only=True)
        if snapshot(folder) != expected_hashes:
            raise ValueError('upstream_changed_during_replay')
        provenance = {'provenance': 'DERIVED_FROM', 'input_sha256': expected_hashes,
                      'target': plan['target'], 'publication_ready': False,
                      'package_checksums': snapshot(Path(result['path']))}
        (staged / 'DERIVED_FROM.json').write_text(json.dumps(provenance, sort_keys=True, indent=2), encoding='utf-8')
        staged.rename(output)
        result['path'] = str(output / 'SECOND_CURATION_DERIVED')
    return {**plan, 'mode': 'apply', 'package': result, 'upstream_unchanged': True}
