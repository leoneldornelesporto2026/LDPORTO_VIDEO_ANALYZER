"""Producer receipts: local integrity evidence, never independent signatures."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

from .core import digest, file_hash, write_json

SCHEMA = '2.0'
TRUST = 'local_producer_consistency_not_independent_signature'


def snapshot_json(path, expected=None):
    """Parse precisely the isolated bytes whose digest was verified."""
    from .export_privacy import safe_path
    raw = safe_path(Path(path)).read_bytes()
    checksum = hashlib.sha256(raw).hexdigest()
    if expected is not None and checksum != expected:
        raise ValueError('snapshot_checksum_mismatch')
    value = json.loads(raw.decode('utf-8-sig'),
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite_json')))
    # Reject exponents which overflow even though they are syntactically JSON.
    from .core import sanitize_json_numbers
    if sanitize_json_numbers(value) != value:
        raise ValueError('nonfinite_json')
    return value, checksum


def module_hashes(selected=None):
    root = Path(__file__).parent
    paths = selected or sorted(root.glob('*.py'))
    hashes = {}
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if not path.suffix:
            path = path.with_suffix('.py')
        if not path.is_file():
            raise ValueError('producer_module_unavailable')
        hashes[str(value) if selected else path.name] = file_hash(path)
    return hashes


def receipt_digest(receipt):
    return digest({k: v for k, v in receipt.items() if k != 'receipt_sha256'})


def create_receipt(stage, record, modules, dependencies, *, producer='Context.step',
                   input_fingerprint=None):
    status = record['status']
    receipt = {
        'schema_version': SCHEMA, 'stage_id': stage, 'producer': producer,
        'execution_mode': 'not_executed' if status == 'blocked' else 'skipped' if status == 'skipped' else 'executed',
        'status': status, 'execution_returncode': 0 if status in {'ok', 'partial', 'skipped'} else None,
        'source_sha256': record['input_hash'], 'input_fingerprint': input_fingerprint or record['input_hash'],
        'config_fingerprint': record['config_hash'], 'checkpoint_key': record['key'],
        'cache_manifest_fingerprint': digest(record.get('cache_manifest', {})),
        'dependency_fingerprints': deepcopy(dependencies),
        'module_hashes': modules, 'module_fingerprint': digest(modules),
        'output_checksums': {'data': record['data_checksum'],
                             'artifacts': deepcopy(record.get('artifact_checksums', {}))},
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'method': 'producer_finalization_before_atomic_checkpoint', 'trust_scope': TRUST,
    }
    receipt['receipt_sha256'] = receipt_digest(receipt)
    return receipt


def verify_receipt(stage, record, *, artifacts=True):
    try:
        if record.get('data_checksum') != digest(record['data']):
            return 'corrupted'
        if artifacts and any(file_hash(path) != sha for path, sha in record.get('artifact_checksums', {}).items()):
            return 'corrupted'
    except (KeyError, TypeError, OSError, AttributeError):
        return 'corrupted'
    receipt = record.get('execution_receipt')
    if receipt is not None and not isinstance(receipt, dict):
        return 'corrupted'
    if not receipt or receipt.get('schema_version') == '1.0':
        return 'legacy_unattested'
    try:
        modules = receipt['module_hashes']
        if (receipt['schema_version'] != SCHEMA or receipt['stage_id'] != stage
                or receipt['producer'] not in {'Context.step', 'ReportEngine.run'}
                or receipt['receipt_sha256'] != receipt_digest(receipt)
                or receipt['status'] != record['status']
                or receipt['execution_mode'] != ('not_executed' if record['status'] == 'blocked' else 'skipped' if record['status'] == 'skipped' else 'executed')
                or receipt['execution_returncode'] != (0 if record['status'] in {'ok', 'partial', 'skipped'} else None)
                or receipt['source_sha256'] != record['input_hash']
                or receipt['config_fingerprint'] != record['config_hash']
                or not isinstance(receipt['dependency_fingerprints'], dict)
                or receipt['producer'] == 'Context.step' and receipt['input_fingerprint'] != record['config_hash']
                or receipt['checkpoint_key'] != record['key']
                or receipt['cache_manifest_fingerprint'] != digest(record.get('cache_manifest', {}))
                or not modules or not all(isinstance(v, str) and len(v) == 64
                                          and set(v) <= set('0123456789abcdef') for v in modules.values())
                or receipt['module_fingerprint'] != digest(modules)
                or receipt['trust_scope'] != TRUST
                or receipt['method'] != 'producer_finalization_before_atomic_checkpoint'
                or datetime.fromisoformat(receipt['timestamp']).tzinfo is None
                or receipt['output_checksums'] != {'data': digest(record['data']),
                                                   'artifacts': record.get('artifact_checksums', {})}
                or record['data_checksum'] != digest(record['data'])):
            return 'corrupted'
        if artifacts and any(file_hash(path) != sha for path, sha in record.get('artifact_checksums', {}).items()):
            return 'corrupted'
        manifest = record.get('cache_manifest') or {}
        if manifest and (manifest.get('input') != record['input_hash']
                         or manifest.get('params') != record['config_hash']
                         or manifest.get('output_version') != record.get('output_version')):
            return 'corrupted'
        if manifest and receipt['producer'] == 'Context.step':
            # JSON schemas are recorded separately because the legacy cache key
            # hashes Python implementation files only.
            cache_modules = {Path(name).with_suffix('.py').name: sha for name, sha in modules.items()
                             if Path(name).suffix in {'.py', ''}}
            if manifest.get('code') != digest(cache_modules):
                return 'corrupted'
        return 'verified' if record['status'] == 'ok' else 'verified_' + record['status']
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        return 'corrupted'


def dependency_snapshots(ctx, names):
    snapshots = {}
    for name in names:
        path = ctx.cache / (name + '.json')
        state = ctx.states.get(name, {})
        try:
            record, sha = snapshot_json(path)
            identity = verify_receipt(name, record)
            if state and (record.get('key') != state.get('key') or record.get('status') != state.get('status')):
                raise ValueError('dependency_identity_mismatch')
            if identity == 'corrupted':
                raise ValueError('dependency_receipt_corrupted')
            snapshots[name] = {'checkpoint_sha256': sha, 'key': record.get('key'),
                               'status': record.get('status'), 'data_checksum': record.get('data_checksum'),
                               'receipt_sha256': (record.get('execution_receipt') or {}).get('receipt_sha256'),
                               'evidence': identity if state else 'unverified'}
        except FileNotFoundError:
            snapshots[name] = {'evidence': 'unverified', 'reason': 'missing_dependency'}
    return snapshots


def _report_member_path(folder, member):
    """Only canonical, relative POSIX names from the report's own directory.

    In particular reject Windows paths even when reviewing artifacts on POSIX.
    Never follow links to verify a report whose bytes have left the output tree.
    """
    if not isinstance(member, str) or not member or "\\" in member or "\x00" in member:
        raise ValueError('unsafe_report_reference')
    posix = PurePosixPath(member)
    windows = PureWindowsPath(member)
    if (posix.is_absolute() or windows.is_absolute() or windows.drive or
            posix.as_posix() != member or
            any(part in {'.', '..'} for part in member.split('/'))):
        raise ValueError('unsafe_report_reference')
    root = Path(folder).resolve()
    target = root.joinpath(*posix.parts)
    if not target.resolve().is_relative_to(root):
        raise ValueError('unsafe_report_reference')
    if not target.is_file():
        raise ValueError('report_reference_missing')
    from .export_privacy import safe_path
    safe_path(target)
    return target


def finalize_report_receipt(ctx, files, *, status='ok', dependencies=None, name='report_execution_receipt.json'):
    """External index finalized after serialization; no document hashes itself."""
    root = Path(ctx.output).resolve()
    checks = {}
    for source in files:
        path = Path(source).resolve()
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError('unsafe_report_reference') from exc
        checked = _report_member_path(root, rel)
        checks[rel] = file_hash(checked)
    record = {'status': status, 'key': digest(checks), 'input_hash': ctx.signature,
              'config_hash': digest(ctx.config.get('export', {})), 'data': {}, 'data_checksum': digest({}),
              'artifact_checksums': checks}
    record['execution_receipt'] = create_receipt('20_handoff', record,
        module_hashes(['reports.py', 'compact_artifacts.py', 'execution_receipts.py']), dependencies or {},
        producer='ReportEngine.run')
    write_json(ctx.output / name, record)
    return record


def verify_report_receipt(folder, name='report_execution_receipt.json'):
    folder = Path(folder)
    record, _ = snapshot_json(folder / name)
    if verify_receipt('20_handoff', record, artifacts=False) != 'verified':
        raise ValueError('report_receipt_invalid')
    if not {'analysis.json', 'run_manifest.json', 'manifest.json'} <= set(record['artifact_checksums']):
        raise ValueError('report_receipt_incomplete')
    snapshots = {}
    for rel, sha in record['artifact_checksums'].items():
        path = _report_member_path(folder, rel)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('report_output_checksum_mismatch')
        snapshots[rel] = raw
    return record, snapshots
