"""Separate observed execution provenance from the code doing a cheap export."""
import hashlib
import json
from pathlib import Path

from . import __build__, __version__
from .core import Context


OPTIONAL_STAGES = {'13_ocr', '14_audio_events', '19b_preview_verifier'}


class ProvenanceContext(Context):
    """Commit receipt and result together, before exposing completion."""

    def step(self, name, params, call, **kwargs):
        from .execution_receipts import module_hashes, dependency_snapshots
        from .core import digest
        from .run_status import DEPENDENCIES
        names = DEPENDENCIES.get(name, kwargs.get('requires') or [])
        self._receipt_inputs = (kwargs.get('code_files'), module_hashes(kwargs.get('code_files')),
                               dependency_snapshots(self, names), list(names), digest(params))
        result = super().step(name, params, call, **kwargs)
        from .execution_receipts import snapshot_json, verify_receipt
        record, _ = snapshot_json(self.cache / (name + '.json'))
        self.stage_metrics.setdefault(name, {}).update(
            execution_mode='cached' if self.stage_metrics.get(name, {}).get('cache_hit') else
                'not_executed' if record['status'] == 'blocked' else 'skipped' if record['status'] == 'skipped' else 'executed',
            receipt_evidence=verify_receipt(name, record))
        return result

    def _validate_cached_receipt(self, name, record):
        from .execution_receipts import verify_receipt
        state = verify_receipt(name, record)
        if state == 'corrupted':
            raise ValueError('corrupted_execution_receipt')
        # Reading an old cache is compatibility only. Never add a receipt to it.
        receipt = record.get('execution_receipt') or {}
        if receipt.get('schema_version') == '2.0':
            from .execution_receipts import dependency_snapshots
            if (receipt.get('dependency_fingerprints') != self._receipt_inputs[2]
                    or receipt.get('module_hashes') != self._receipt_inputs[1]
                    or dependency_snapshots(self, self._receipt_inputs[3]) != self._receipt_inputs[2]):
                raise ValueError('dependency_content_changed')

    def _cache_dependency_identity(self, name, dependencies):
        # Preserve stage 21's selective key; its receipt separately binds every
        # observed byte of stage 20. A changed dependency still rejects the hit.
        if name == '21_second_curation_handoff' and '20_handoff' in dependencies:
            return {'20_handoff': {'status': dependencies['20_handoff']['status'], 'method': 'uncached_export'}}
        return dependencies

    def _finalize_execution_receipt(self, name, record):
        from .execution_receipts import module_hashes, dependency_snapshots, create_receipt
        selected, hashes, dependencies, names, inputs = self._receipt_inputs
        if module_hashes(selected) != hashes or dependency_snapshots(self, names) != dependencies:
            raise ValueError('producer_inputs_changed_during_execution')
        from .core import file_hash
        record['artifact_checksums'] = {path: file_hash(path) for path in record.get('artifacts', [])}
        record['execution_receipt'] = create_receipt(name, record, hashes, dependencies, input_fingerprint=inputs)


def attestation_digest(proof):
    """Hash evidence, excluding private locators that exports may redact.

    Changing a locator cannot substitute evidence: file contents must still hash
    to the committed SHA. Exported/redacted locators yield unknown on revalidation.
    """
    from .core import digest
    evidence = {k: v for k, v in proof.items() if k not in ('attestation_sha256', 'source_path')}
    evidence['checkpoints'] = {name: {k: v for k, v in row.items() if k != 'path'}
                               for name, row in proof['checkpoints'].items()}
    return digest(evidence)


def execution_stages():
    from .run_status import DEPENDENCIES
    return set(DEPENDENCIES) - {'20_handoff', '21_second_curation_handoff'}


def attest_execution(ctx):
    """Full pipeline producer only; never called by replay or exporters.

    This is a locally verifiable receipt, not a signed third-party certificate.
    Missing legacy receipts do not trigger recomputation of expensive caches.
    """
    from .core import digest, file_hash, read_json
    required = execution_stages() - OPTIONAL_STAGES
    disabled = {'13_ocr': not ctx.config['ocr']['enabled'],
                '14_audio_events': not ctx.config['audio_events']['enabled'],
                '19b_preview_verifier': not ctx.config['preview']['enabled']}
    evidence = {}
    for name in sorted(execution_stages()):
        path = ctx.cache / (name + '.json')
        try:
            from .execution_receipts import snapshot_json
            record, checksum = snapshot_json(path)
        except (OSError, ValueError):
            return None
        evidence[name] = {'path': str(path.resolve()), 'sha256': checksum,
                          'key': record.get('key'), 'status': record.get('status'),
                          'receipt': record.get('execution_receipt')}
    proof = {'schema_version': '1.0', 'producer': 'ldporto.pipeline',
             'scope': 'full_analysis_stages', 'execution_returncode': 0,
             'source_sha256': ctx.signature, 'source_path': str(ctx.video.resolve()),
             'required_stages': sorted(required),
             'optional_disabled': disabled,
             'execution_code_hashes': {name: file_hash(Path(__file__).parent / name)
                                       for name in ('pipeline.py', 'core.py', 'build_provenance.py')},
             'optional_policy': {name: 'disabled_skip_allowed' if disabled[name] else 'required_ok'
                                 for name in sorted(OPTIONAL_STAGES)},
             'checkpoints': evidence}
    proof['attestation_sha256'] = attestation_digest(proof)
    status, _ = verify_execution(proof, {'sha256': ctx.signature}, ctx.states)
    return proof if status == 'proof' else None


def verify_execution(proof, metadata, stages):
    """Re-read source and checkpoints independently; absence stays unknown."""
    from .core import digest, file_hash, read_json
    if not proof:
        return 'unknown', 'full_execution_not_attested'
    try:
        if proof.get('attestation_sha256') != attestation_digest(proof):
            return 'mismatch', 'attestation_hash_mismatch'
        if (proof['schema_version'] != '1.0' or proof['producer'] != 'ldporto.pipeline'
                or proof['scope'] != 'full_analysis_stages' or proof['execution_returncode'] != 0
                or set(proof['required_stages']) != execution_stages() - OPTIONAL_STAGES
                or set(proof['optional_policy']) != OPTIONAL_STAGES
                or set(proof['optional_disabled']) != OPTIONAL_STAGES
                or set(proof['execution_code_hashes']) != {'pipeline.py', 'core.py', 'build_provenance.py'}
                or set(proof['checkpoints']) != execution_stages()):
            return 'mismatch', 'execution_policy_mismatch'
        def valid_hashes(values):
            return isinstance(values, dict) and bool(values) and all(
                isinstance(value, str) and len(value) == 64 and
                all(char in '0123456789abcdef' for char in value) for value in values.values())
        if not valid_hashes(proof['execution_code_hashes']):
            return 'mismatch', 'execution_code_hashes_invalid'
        if metadata.get('execution_scope') == 'downstream_replay' or any(s.get('artifact_snapshot_reused') for s in stages.values()):
            return 'mismatch', 'mixed_replay_not_full_execution'
        if metadata.get('sha256') != proof['source_sha256']:
            return 'mismatch', 'source_sha256_mismatch'
        if file_hash(proof['source_path']) != proof['source_sha256']:
            return 'mismatch', 'source_sha256_mismatch'
        for name, row in proof['checkpoints'].items():
            state = stages.get(name, {})
            if state.get('key') != row['key'] or state.get('status') != row['status']:
                return 'mismatch', 'stage_identity_mismatch:' + name
            from .execution_receipts import snapshot_json, verify_receipt
            try:
                record, _ = snapshot_json(row['path'], row['sha256'])
            except ValueError:
                return 'mismatch', 'checkpoint_hash_mismatch:' + name
            receipt = record.get('execution_receipt') or {}
            allowed = {'ok'}
            if name in OPTIONAL_STAGES:
                policy = proof['optional_policy'][name]
                if (type(proof['optional_disabled'][name]) is not bool or
                        policy != ('disabled_skip_allowed' if proof['optional_disabled'][name] else 'required_ok')):
                    return 'mismatch', 'optional_policy_mismatch:' + name
                if policy == 'disabled_skip_allowed':
                    allowed.add('skipped')
            if (record.get('status') not in allowed or record.get('status') != row['status']
                    or record.get('key') != row['key'] or record.get('input_hash') != proof['source_sha256']
                    or record.get('data_checksum') != digest(record['data'])
                    or receipt != row['receipt'] or receipt.get('source_sha256') != proof['source_sha256']
                    or receipt.get('schema_version') != '2.0'
                    or receipt.get('producer') != 'Context.step' or receipt.get('execution_returncode') != 0
                    or not valid_hashes(receipt.get('module_hashes'))
                    or receipt.get('module_fingerprint') != digest(receipt['module_hashes'])):
                return 'mismatch', 'checkpoint_receipt_mismatch:' + name
            verified = verify_receipt(name, record)
            if verified not in {'verified', 'verified_skipped'}:
                return 'mismatch', 'producer_receipt_invalid:' + name
            from .run_status import DEPENDENCIES
            dependencies = receipt.get('dependency_fingerprints', {})
            if set(dependencies) != set(DEPENDENCIES.get(name, ())):
                return 'mismatch', 'dependency_contract_mismatch:' + name
            for dependency, observed in dependencies.items():
                expected = proof['checkpoints'].get(dependency, {})
                if (observed.get('checkpoint_sha256') != expected.get('sha256')
                        or observed.get('key') != expected.get('key')
                        or observed.get('status') != expected.get('status')
                        or observed.get('receipt_sha256') != (expected.get('receipt') or {}).get('receipt_sha256')
                        or observed.get('data_checksum') != ((expected.get('receipt') or {}).get('output_checksums') or {}).get('data')
                        or observed.get('evidence') not in {'verified', 'verified_skipped', 'verified_partial'}):
                    return 'unknown', 'dependency_unverified:' + name
            for path, checksum in record.get('artifact_checksums', {}).items():
                if file_hash(path) != checksum:
                    return 'mismatch', 'artifact_hash_mismatch:' + name
        return 'proof', 'source_and_checkpoints_verified'
    except (OSError, ValueError):
        return 'unknown', 'verification_files_unavailable'
    except (KeyError, TypeError, AttributeError):
        return 'mismatch', 'invalid_attestation_contract'


def exporter_identity():
    # These hashes describe the exporter environment, never historical inference.
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(Path(__file__).parent.glob('*.py'))}
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'analyzer_version': __version__, 'analyzer_build': __build__,
            'code_fingerprint': fingerprint, 'source_file_hashes': files}


def build_provenance(metadata, stages, manifest=None, provenance=None):
    manifest, provenance = manifest or {}, provenance or {}
    exporter = exporter_identity()
    proof = manifest.get('execution_attestation')
    evidence, evidence_reason = verify_execution(proof, metadata, stages)
    build = manifest.get('analyzer_build') or metadata.get('analyzer_build') or provenance.get('build_label')
    fingerprint = manifest.get('code_fingerprint') or metadata.get('code_fingerprint') or provenance.get('code_fingerprint')
    reasons = []
    inference_states = [state for name, state in stages.items() if name in execution_stages()]
    compatible_cache = bool(inference_states) and all(
        (state.get('execution_provenance') or {}).get('cache_compatible_verified') is True
        and not state.get('artifact_snapshot_reused') for state in inference_states)
    if not proof and not compatible_cache and build and build != exporter['analyzer_build']:
        reasons.append('analysis_build_differs_from_exporter')
    if not proof and not compatible_cache and fingerprint and fingerprint != exporter['code_fingerprint']:
        reasons.append('analysis_code_differs_from_exporter')
    rows = {}
    for name, state in stages.items():
        origin = state.get('execution_provenance') or {}
        rows[name] = {
            'status': state.get('status'), 'checkpoint_key': state.get('key'),
            'origin': 'snapshot' if state.get('artifact_snapshot_reused') else origin.get('origin'),
            'analyzer_build': origin.get('analyzer_build'),
            'code_fingerprint': origin.get('code_fingerprint'),
            'checkpoint_sha256': origin.get('checkpoint_sha256'),
            'effective_module_fingerprint': origin.get('effective_module_fingerprint') or
                (((proof or {}).get('checkpoints') or {}).get(name, {}).get('receipt') or {}).get('module_fingerprint'),
        }
        if state.get('artifact_snapshot_reused'):
            reasons.append('snapshot_reused:' + name)
        if not proof and not origin.get('cache_compatible_verified') and origin.get('analyzer_build') and origin['analyzer_build'] != exporter['analyzer_build']:
            reasons.append('stage_build_differs_from_exporter:' + name)
        if not proof and not origin.get('cache_compatible_verified') and origin.get('code_fingerprint') and origin['code_fingerprint'] != exporter['code_fingerprint']:
            reasons.append('stage_code_differs_from_exporter:' + name)
    # A new contract/schema or a successful export cannot prove source execution.
    unknown = [name for name, row in rows.items()
               if evidence != 'proof' and (not row['code_fingerprint'] and not row['effective_module_fingerprint']
                   or (stages[name].get('execution_provenance') or {}).get('receipt_evidence') in
                       {'legacy_unattested', 'corrupted', 'verified_partial', 'unverified'})]
    if evidence == 'mismatch':
        reasons.append(evidence_reason)
    if reasons:
        evidence = 'mismatch'
    return {'schema_version': '1.0', 'analyzer_build': build,
            'code_fingerprint': fingerprint, 'exporter': exporter, 'stages': rows,
            'build_mismatch': True if reasons else False if evidence == 'proof' else None if not build or not fingerprint or unknown else False,
            'mismatch_reasons': reasons, 'unverified_stages': unknown,
            'execution_complete': True if evidence == 'proof' else False if evidence == 'mismatch' else None,
            'execution_evidence': evidence,
            'execution_attestation': proof,
            'completion_scope': 'full_analysis_stages' if evidence == 'proof' else 'stage_status_only',
            'execution_evidence_reason': evidence_reason if not reasons else ';'.join(reasons)}


def analysis_provenance(analysis):
    manifest = analysis.get('run_manifest') or {}
    stages = dict(manifest.get('stage_status') or {})
    for name, state in (analysis.get('stage_status') or {}).items():
        stages[name] = {**stages.get(name, {}), **state}
    return build_provenance(analysis.get('metadata') or {},
                            stages,
                            manifest, analysis.get('provenance'))
