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


def editorial_replay_provenance(analysis, checkpoint_paths, input_artifact_paths,
                               output_fields, executed_stages):
    """Describe a CPU editorial replay separately from source model execution."""
    from pathlib import Path, PurePosixPath
    import hashlib
    allowed = {'editorial_potential', 'boundary_review_proposals', 'review_media_binding',
               'second_curation_export', 'narrative_analysis', 'question_answer_proposals',
               'narrative_handoff', 'commercial_context_review', 'targeted_repair_plan'}
    if not executed_stages or not set(executed_stages) <= allowed:
        raise ValueError('non_editorial_replay_stage')
    def hashes(paths):
        rows = {}
        for name, value in sorted(paths.items()):
            logical = PurePosixPath(name)
            if logical.is_absolute() or '..' in logical.parts or ':' in name or '\\' in name:
                raise ValueError('private_or_unsafe_replay_reference')
            path = Path(value)
            result = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                    result.update(block)
            rows[name] = {'sha256': result.hexdigest(), 'bytes': path.stat().st_size}
        return rows
    modules = ('editorial_review.py', 'review_media.py', 'second_curation.py',
               'integrity_contracts.py', 'second_curation_export.py', 'build_provenance.py',
               'narrative_handoff.py', 'narrative_relations.py', 'narrative_replay.py',
               'commercial_context.py', 'editorial.py', 'understanding.py', 'story_recovery.py')
    source_identity = analysis_provenance(analysis)
    return {'schema_version': '1.0', 'scope': 'editorial_replay_only',
            'source_sha256': (analysis.get('metadata') or {}).get('sha256'),
            'perception_run_identity': source_identity,
            'replay_exporter': exporter_identity(),
            'replay_code': hashes({name: Path(__file__).parent / name for name in modules}),
            'reused_checkpoints': hashes(checkpoint_paths), 'reused_artifacts': hashes(input_artifact_paths),
            'executed_components': list(executed_stages), 'output_fields': list(output_fields),
            'new_audiovisual_inference': False, 'new_model_calls': 0,
            'full_pipeline_execution_attested': False, 'publication_ready': False}


def validate_editorial_replay(replay, source_sha256, identity):
    """Validate replay claims; this is not an attestation of model execution."""
    import re
    from pathlib import PurePosixPath
    if (not isinstance(replay, dict) or replay.get('schema_version') != '1.0' or
            replay.get('scope') != 'editorial_replay_only' or replay.get('source_sha256') != source_sha256 or
            replay.get('new_audiovisual_inference') is not False or type(replay.get('new_model_calls')) is not int or
            replay['new_model_calls'] != 0 or replay.get('full_pipeline_execution_attested') is not False or
            replay.get('publication_ready') is not False):
        return ['invalid_editorial_replay_claim']
    allowed = {'editorial_potential', 'boundary_review_proposals', 'review_media_binding', 'second_curation_export',
               'narrative_analysis', 'question_answer_proposals', 'narrative_handoff',
               'commercial_context_review', 'targeted_repair_plan'}
    if not replay.get('executed_components') or not set(replay['executed_components']) <= allowed:
        return ['non_editorial_replay_stage']
    if (replay.get('replay_exporter') != identity.get('exporter') or
            any((replay.get('perception_run_identity') or {}).get(key) != identity.get(key)
                for key in ('analyzer_build', 'code_fingerprint'))):
        return ['editorial_replay_identity_disagreement']
    for key in ('replay_code', 'reused_checkpoints', 'reused_artifacts'):
        records = replay.get(key)
        if not isinstance(records, dict) or not records:
            return ['editorial_replay_hashes_missing:' + key]
        for name, row in records.items():
            path = PurePosixPath(name)
            if (path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name or
                    not isinstance(row, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256'))) or
                    type(row.get('bytes')) is not int or row['bytes'] < 0):
                return ['invalid_editorial_replay_hash:' + key]
    return []


def classify_provenance_mismatch(identity, editorial_replay=None, *, source_sha256=None,
                                 verified_checkpoint_sha256=None, compatible_schema=True):
    """Explain version boundaries without clearing historical mismatch or stage 20.

    ``expected`` means a recognized exporter/replay boundary with verification
    still pending; ``explained`` additionally requires independently verified
    checkpoint hashes. Unknown reasons remain unresolved. A checksum, source,
    receipt or schema conflict is incompatible, even alongside expected drift.
    This pure classifier does not verify files or attest new source inference.
    """
    from pathlib import PurePosixPath
    identity = identity or {}
    reasons = list(identity.get('mismatch_reasons') or [])
    replay = editorial_replay or {}
    checkpoints = replay.get('reused_checkpoints') or {}
    stages = identity.get('stages') or {}

    def observed(mapping, stage):
        values = []
        for name, value in (mapping or {}).items():
            if name == stage or PurePosixPath(str(name).replace('\\', '/')).name == stage + '.json':
                values.append(value.get('sha256') if isinstance(value, dict) else value)
        return list(dict.fromkeys(values))

    hard = ('source_sha256_mismatch', 'attestation_hash_mismatch', 'stage_identity_mismatch',
            'checkpoint_hash_mismatch', 'checkpoint_receipt_mismatch', 'producer_receipt_invalid',
            'dependency_contract_mismatch', 'artifact_hash_mismatch', 'execution_policy_mismatch',
            'execution_code_hashes_invalid', 'optional_policy_mismatch', 'invalid_attestation_contract')
    expected = {'analysis_code_differs_from_exporter', 'analysis_build_differs_from_exporter',
                'stage_code_differs_from_exporter:20_handoff', 'stage_build_differs_from_exporter:20_handoff',
                'mixed_replay_not_full_execution'}
    conflicts, pending = [], []
    if compatible_schema is False:
        conflicts.append('incompatible_schema')
    elif compatible_schema is not True:
        pending.append('schema_compatibility_unresolved')
    if replay:
        if source_sha256 is None:
            pending.append('source_hash_unresolved')
        else:
            conflicts.extend(validate_editorial_replay(replay, source_sha256, identity))
    elif reasons:
        pending.append('editorial_replay_evidence_missing')
    for name, row in checkpoints.items():
        stage = PurePosixPath(name).stem
        expected_hash = row.get('sha256') if isinstance(row, dict) else None
        original = stages.get(stage, {}).get('checkpoint_sha256')
        verified = observed(verified_checkpoint_sha256, stage)
        if original and original != expected_hash or verified and verified != [expected_hash]:
            conflicts.append('reused_checkpoint_hash_conflict:' + stage)
        elif not verified:
            pending.append('checkpoint_verification_pending:' + stage)
    details = []
    for reason in reasons:
        if reason.startswith(hard):
            status = 'incompatible'
        elif reason not in expected:
            status = 'unresolved'
        elif not replay or source_sha256 is None or compatible_schema is not True:
            status = 'unresolved'
        else:
            status = 'expected' if pending else 'explained'
        if reason.endswith(':20_handoff') and not observed(checkpoints, '20_handoff'):
            status = 'unresolved'
        details.append({'reason': reason, 'classification': status,
                        'scope': 'historical_20_handoff' if reason.endswith(':20_handoff') else
                                 'original_source_vs_current_exporter'})
    if conflicts or any(row['classification'] == 'incompatible' for row in details):
        classification = 'incompatible'
    elif any(row['classification'] == 'unresolved' for row in details) or identity.get('build_mismatch') is None:
        classification = 'unresolved'
    elif not reasons and identity.get('build_mismatch') is True:
        classification = 'unresolved'
        pending.append('mismatch_reason_missing')
    elif not details:
        classification = 'expected'
    elif all(row['classification'] == 'explained' for row in details):
        classification = 'explained'
    else:
        classification = 'expected'
    return {'schema_version': '1.0', 'classification': classification,
            'original_build_mismatch': identity.get('build_mismatch'), 'original_mismatch_reasons': reasons,
            'reason_classifications': details, 'conflicts': list(dict.fromkeys(conflicts)),
            'pending_verification': list(dict.fromkeys(pending)),
            'stage20': {'original': stages.get('20_handoff'), 'reused_sha256': observed(checkpoints, '20_handoff'),
                        'verified_sha256': observed(verified_checkpoint_sha256, '20_handoff')},
            'original_execution_complete': identity.get('execution_complete'),
            'original_unverified_stages': list(identity.get('unverified_stages') or []),
            'changes_original_flags': False, 'full_pipeline_execution_attested': False,
            'scope': 'compatibility_explanation_only; not_source_inference_proof'}


def semantic_text_provenance(source_sha256, calls, *, run_id, purpose, input_sha256=None,
                             code_sha256=None, prompt_sha256=None):
    """Record observed textual requests separately from CPU replay and history.

    Each new request needs call_id/model/status, origin=new_textual_inference,
    execution_mode=executed and request_sent=True. Historical/cache metadata never
    counts as a new request. Missing measurements stay null. Caller observations
    are not an independent attestation of a running model or human correctness.
    """
    import math
    import re
    from .core import digest
    if not re.fullmatch(r'[0-9a-f]{64}', str(source_sha256)) or not run_id or not purpose:
        raise ValueError('invalid_semantic_text_run_identity')
    if not isinstance(calls, list) or any(not isinstance(row, dict) for row in calls):
        raise ValueError('invalid_semantic_text_call_records')
    measurements = ('duration_seconds', 'server_total_seconds', 'load_seconds', 'prompt_seconds',
                    'generation_seconds', 'prompt_eval_count', 'eval_count', 'request_bytes')
    rows, issues, new, cache, historical = [], [], [], [], []
    identifiers = set()
    for index, original in enumerate(calls):
        row = {key: original.get(key) for key in ('call_id', 'request_id', 'model', 'status',
               'origin', 'execution_mode', 'request_sent', 'request_sha256', 'response_sha256')}
        if original.get('modality', 'text') != 'text':
            raise ValueError('non_textual_inference_record')
        sent = row['request_sent']
        if row['execution_mode'] == 'cache_reused' and sent is True:
            raise ValueError('cache_reuse_cannot_claim_request_sent')
        valid = (isinstance(row['call_id'], str) and bool(row['call_id']) and row['call_id'] not in identifiers
                 and isinstance(row['model'], str) and bool(row['model']) and
                 row['status'] in {'ok', 'failed', 'timeout', 'cancelled'} and type(sent) is bool)
        identifiers.add(str(row['call_id']))
        if valid and row['origin'] == 'new_textual_inference' and row['execution_mode'] == 'executed' and sent:
            new.append(row)
        elif valid and row['origin'] == 'historical_source_inference':
            historical.append(row)
        elif valid and row['execution_mode'] == 'cache_reused' and not sent:
            cache.append(row)
        else:
            issues.append({'index': index, 'reason': 'request_origin_or_execution_unverified'})
        for key in measurements:
            value = original.get(key)
            row[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None
        rows.append(row)
    totals = {key: sum(row[key] for row in new if row[key] is not None)
              if any(row[key] is not None for row in new) else None for key in measurements}
    block = {'schema_version': '1.0', 'scope': 'semantic_text_analysis_only',
             'source_sha256': source_sha256, 'run_id': run_id, 'purpose': purpose,
             'input_sha256': input_sha256, 'code_sha256': code_sha256, 'prompt_sha256': prompt_sha256,
             'calls': rows, 'record_count': len(rows), 'observed_new_textual_model_calls': len(new),
             'new_textual_model_calls': None if issues else len(new), 'cache_reuse_count': len(cache),
             'historical_record_count': len(historical), 'unverified_records': issues,
             'failed_new_textual_model_calls': sum(row['status'] != 'ok' for row in new),
             'new_textual_measurements': totals,
             'measurement_coverage': {key: sum(row[key] is not None for row in new) for key in measurements},
             'new_asr_calls': 0, 'new_asd_calls': 0, 'new_audiovisual_inference': False,
             'overwrites_editorial_replay': False, 'full_pipeline_execution_attested': False,
             'publication_ready': False, 'evidence_scope': 'caller_observed_request_records_not_independent_attestation'}
    block['provenance_sha256'] = digest(block)
    return block


def validate_semantic_text_provenance(document, source_sha256):
    """Check the separate textual-run contract without invoking a model."""
    from .core import digest
    try:
        if (document.get('schema_version') != '1.0' or document.get('scope') != 'semantic_text_analysis_only'
                or document.get('source_sha256') != source_sha256 or
                document.get('provenance_sha256') != digest({key: value for key, value in document.items()
                                                           if key != 'provenance_sha256'})):
            return ['invalid_semantic_text_provenance']
        expected = semantic_text_provenance(source_sha256, document['calls'], run_id=document['run_id'],
                    purpose=document['purpose'], input_sha256=document.get('input_sha256'),
                    code_sha256=document.get('code_sha256'), prompt_sha256=document.get('prompt_sha256'))
        return [] if expected == document else ['semantic_text_counters_or_scope_disagree']
    except (AttributeError, KeyError, TypeError, ValueError):
        return ['invalid_semantic_text_provenance']
