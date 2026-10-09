"""Separate observed execution provenance from the code doing a cheap export."""
import hashlib
import json
from pathlib import Path

from . import __build__, __version__


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
    build = manifest.get('analyzer_build') or metadata.get('analyzer_build') or provenance.get('build_label')
    fingerprint = manifest.get('code_fingerprint') or metadata.get('code_fingerprint') or provenance.get('code_fingerprint')
    reasons = []
    if build and build != exporter['analyzer_build']:
        reasons.append('analysis_build_differs_from_exporter')
    if fingerprint and fingerprint != exporter['code_fingerprint']:
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
        }
        if state.get('artifact_snapshot_reused'):
            reasons.append('snapshot_reused:' + name)
        if origin.get('analyzer_build') and origin['analyzer_build'] != exporter['analyzer_build']:
            reasons.append('stage_build_differs_from_exporter:' + name)
        if origin.get('code_fingerprint') and origin['code_fingerprint'] != exporter['code_fingerprint']:
            reasons.append('stage_code_differs_from_exporter:' + name)
    # A new contract/schema or a successful export cannot prove source execution.
    unknown = [name for name, row in rows.items() if not row['code_fingerprint']]
    return {'schema_version': '1.0', 'analyzer_build': build,
            'code_fingerprint': fingerprint, 'exporter': exporter, 'stages': rows,
            'build_mismatch': True if reasons else None if not build or not fingerprint or unknown else False,
            'mismatch_reasons': reasons, 'unverified_stages': unknown,
            'execution_complete': False if reasons else None,
            'completion_scope': 'stage_status_only',
            'execution_evidence_reason': 'mismatch_or_snapshot' if reasons else 'full_execution_not_attested'}


def analysis_provenance(analysis):
    manifest = analysis.get('run_manifest') or {}
    stages = dict(manifest.get('stage_status') or {})
    for name, state in (analysis.get('stage_status') or {}).items():
        stages[name] = {**stages.get(name, {}), **state}
    return build_provenance(analysis.get('metadata') or {},
                            stages,
                            manifest, analysis.get('provenance'))
