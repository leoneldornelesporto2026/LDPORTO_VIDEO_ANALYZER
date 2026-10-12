"""Safe, artifact-only review of a legacy analysis lacking original receipts.

This is deliberately *not* stage-21 replay or historical authentication.  It
can reconstruct a review input from locally checksummed exports without
promoting it to a verified execution or publishing-ready result.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .compact_artifacts import COLLECTION_FILES
from .export_privacy import safe_path, sanitize_export, privacy_findings

# Explicit producer-defined mapping, not arbitrary user-selected JSON pointers.
SUMMARY_INLINE_FIELDS = {
    'metadata': 'metadata', 'analysis_status': 'analysis_status',
    'analysis_quality': 'analysis_quality', 'quality_gate': 'quality_gate',
    'candidate_metrics': 'candidate_metrics', 'semantic_metrics': 'semantic_metrics',
    'stage_runtime': 'stage_runtime', 'editorial_shortlist': 'editorial_shortlist',
    'issues': 'warnings',
}
REQUIRED_EXPORTS = (
    'analysis_summary.json', 'second_curation_package.json',
    'CHATGPT_ANALYSIS_HANDOFF.compact.json',
)
CAMERA_OUTPUTS = ('camera_plan.json', 'camera_director_timeline.json')


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path):
    return json.loads(safe_path(path).read_bytes().decode('utf-8-sig'),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite_json')))


def _read_verified(folder: Path, filename: str, signed: dict, *, required=True):
    if filename not in signed:
        if required:
            raise ValueError('missing_local_artifact_checksum:' + filename)
        return None
    if filename not in set(COLLECTION_FILES.values()) | set(REQUIRED_EXPORTS) | set(CAMERA_OUTPUTS):
        raise ValueError('unexpected_legacy_artifact')
    path = safe_path(folder / filename)
    if path.parent != folder or not path.is_file():
        raise ValueError('missing_or_unsafe_legacy_artifact:' + filename)
    raw = path.read_bytes()
    if _hash(raw) != signed[filename]:
        raise ValueError('legacy_artifact_checksum_mismatch:' + filename)
    return raw


def _inventory(folder: Path) -> dict:
    """Inventory only inputs consumed here; never hash/copy the source MP4."""
    raw = {}
    for filename in ('manifest.json', 'analysis.json'):
        path = safe_path(folder / filename)
        raw[filename] = _hash(path.read_bytes())
    return raw


def plan_legacy_review(folder) -> dict:
    folder = safe_path(folder)
    starting = _inventory(folder)
    manifest = _read_json(folder / 'manifest.json')
    signed = manifest.get('artifact_checksums')
    if not isinstance(signed, dict):
        raise ValueError('missing_artifact_checksums')
    # Don't trust arbitrary hash records in a self-referential manifest.
    if any(not isinstance(k, str) or '/' in k or '\\' in k or k.startswith('.') or
           not isinstance(v, str) or len(v) != 64 or
           any(c not in '0123456789abcdef' for c in v.lower())
           for k, v in signed.items()):
        raise ValueError('invalid_artifact_checksum_inventory')
    summary = json.loads(_read_verified(folder, 'analysis_summary.json', signed))
    package = json.loads(_read_verified(folder, 'second_curation_package.json', signed))
    handoff = json.loads(_read_verified(folder, 'CHATGPT_ANALYSIS_HANDOFF.compact.json', signed))
    if (not isinstance(summary, dict) or not isinstance(package, dict) or
        not isinstance(handoff, dict) or
        str(package.get('schema_version')) != '3.1' or
        str(handoff.get('schema_version')) != '4.2' or
        handoff.get('second_curation_package_ref', {}).get('path') != 'second_curation_package.json'):
        raise ValueError('invalid_legacy_export_schema')
    original = _read_json(folder / 'analysis.json')
    if original.get('collection_storage') != 'references':
        raise ValueError('noncompact_source_document')
    refs = original.get('collection_refs')
    if not isinstance(refs, dict):
        raise ValueError('invalid_collection_refs')
    fields = {}
    for field, source in SUMMARY_INLINE_FIELDS.items():
        exists = field in original and source in summary
        fields[field] = ('consistent_with_local_export' if exists and original[field] == summary[source]
                         else 'not_verifiable_from_local_export')
    statuses = summary.get('stage_status')
    original_statuses = (original.get('run_manifest') or {}).get('stage_status')
    stages_match = isinstance(statuses, dict) and bool(statuses) and statuses == original_statuses
    # Read/check only authoritative producer filenames; no traversal, no links.
    verified_refs = {}
    for field, ref in refs.items():
        if field not in COLLECTION_FILES or not isinstance(ref, dict):
            raise ValueError('unknown_collection_reference')
        name = COLLECTION_FILES[field]
        if ref.get('path') != name:
            raise ValueError('unexpected_collection_location')
        raw = _read_verified(folder, name, signed)
        if ref.get('sha256') != _hash(raw):
            raise ValueError('collection_reference_checksum_mismatch')
        verified_refs[field] = {'path': name, 'sha256': _hash(raw)}
    for name in CAMERA_OUTPUTS:
        _read_verified(folder, name, signed)
    if _inventory(folder) != starting:
        raise ValueError('local_inventory_changed_during_validation')
    blockers = []
    if not all(v == 'consistent_with_local_export' for v in fields.values()):
        blockers.append('inline_fields_not_reconstructible')
    if not stages_match:
        blockers.append('run_manifest_stage_status_not_reconstructible')
    if len(verified_refs) != len(refs):
        blockers.append('collection_inventory_incomplete')
    # Explicitly separate review usability from historical execution authenticity.
    return {
        'mode': 'legacy_artifact_review',
        'status': 'review_input_possible' if not blockers else 'blocked',
        'review_input_possible': not blockers,
        'can_replay_verified_stage21': False,
        'publication_ready': False,
        'historical_authentication': 'not_established',
        'trust_scope': 'local_manifest_consistency_only',
        'inline_fields': fields,
        'run_manifest_stage_status': ('consistent_with_local_export' if stages_match else 'unverified'),
        'collection_count': len(verified_refs),
        'checked_camera_outputs': list(CAMERA_OUTPUTS),
        'cache_receipts': {'18b_global_camera_planner': 'not_attested',
                           '19_camera_director': 'not_attested'},
        'blockers': blockers,
        'source_reference_hashes': starting,
        'signed_export_hashes': {name: signed[name] for name in REQUIRED_EXPORTS + CAMERA_OUTPUTS},
        'risks': ['manifest_and_files_share_local_trust_boundary',
                  'missing_historical_analysis_checksum', 'missing_camera_execution_receipts',
                  'review_only_not_a_stage21_recovery'],
    }


def create_legacy_review_input(folder, output, *, expected_hashes: dict):
    """Explicitly create a *review-only* sanitized input in a new directory.

    Requires a previously reviewed plan and will not call models or modify the
    source. The material is untrusted as a historical execution attestation.
    """
    folder = safe_path(folder)
    output = Path(output).absolute()
    safe_path(output.parent)
    if (output.exists() or output.is_relative_to(folder) or folder.is_relative_to(output)
            or expected_hashes is None):
        raise ValueError('unsafe_or_existing_review_output')
    plan = plan_legacy_review(folder)
    if not plan['review_input_possible'] or expected_hashes != plan['source_reference_hashes']:
        raise ValueError('unapproved_or_changed_review_source')
    manifest = _read_json(folder / 'manifest.json')
    signed = manifest['artifact_checksums']
    summary = json.loads(_read_verified(folder, 'analysis_summary.json', signed))
    original = _read_json(folder / 'analysis.json')
    analysis = {field: summary[source] for field, source in SUMMARY_INLINE_FIELDS.items()}
    analysis.update({
        'schema_version': '4.2', 'collection_storage': 'references',
        'run_manifest': {
            'stage_status': summary['stage_status'],
            'analysis_status': summary.get('analysis_status'),
            'root_cause_stage': summary.get('root_cause_stage'),
            'execution_attestation': None,
            'publication_ready': False,
            'provenance': 'DERIVED_LOCAL_REVIEW_ONLY',
        },
        'collection_refs': {}, 'publication_ready': False,
        'derived_review_only': True,
    })
    refs = original['collection_refs']
    with tempfile.TemporaryDirectory(prefix='ldporto_review64_', dir=output.parent) as tmp:
        temp = Path(tmp) / 'result'
        temp.mkdir()
        checksums = {}
        for field, ref in sorted(refs.items()):
            name = COLLECTION_FILES[field]
            value = json.loads(_read_verified(folder, name, signed))
            cleaned = sanitize_export(value)
            if privacy_findings(cleaned):
                raise ValueError('review_redaction_incomplete')
            raw = (json.dumps(cleaned, ensure_ascii=False, sort_keys=True, allow_nan=False,
                              separators=(',', ':')) + '\n').encode('utf-8')
            (temp / name).write_bytes(raw)
            checksums[name] = _hash(raw)
            analysis['collection_refs'][field] = {'path': name, 'sha256': _hash(raw),
                                                   'source_sha256': ref['sha256']}
        # Not merely copied: reconstructed from checked summary fields.
        cleaned_analysis = sanitize_export(analysis)
        if privacy_findings(cleaned_analysis):
            raise ValueError('review_redaction_incomplete')
        raw = (json.dumps(cleaned_analysis, ensure_ascii=False, sort_keys=True,
                          allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
        (temp / 'analysis.json').write_bytes(raw)
        checksums['analysis.json'] = _hash(raw)
        for name in ('analysis_summary.json', 'second_curation_package.json',
                     'CHATGPT_ANALYSIS_HANDOFF.compact.json'):
            cleaned = sanitize_export(json.loads(_read_verified(folder, name, signed)))
            if privacy_findings(cleaned):
                raise ValueError('review_redaction_incomplete')
            raw = (json.dumps(cleaned, ensure_ascii=False, sort_keys=True,
                              allow_nan=False, separators=(',', ':')) + '\n').encode('utf-8')
            (temp / name).write_bytes(raw)
            checksums[name] = _hash(raw)
        # No raw text/key material in the audit, only metadata and hashes.
        receipt = {
            'schema_version': '1.0', 'type': 'LOCAL_REVIEW_NOT_VERIFIED_REPLAY',
            'publication_ready': False, 'historical_authentication': 'not_established',
            'source_reference_hashes': expected_hashes,
            'original_local_export_hashes': plan['signed_export_hashes'],
            'derived_file_sha256': checksums,
        }
        (temp / 'DERIVED_FROM.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        # Recheck source bytes after assembly (no source writes).
        if _inventory(folder) != expected_hashes or not plan_legacy_review(folder)['review_input_possible']:
            raise ValueError('review_source_changed_during_assembly')
        # Re-read all finalized bytes before atomic promotion.
        if any(_hash((temp / name).read_bytes()) != sha for name, sha in checksums.items()):
            raise ValueError('derived_review_checksum_mismatch')
        os.replace(temp, output)
    return {'status': 'review_only_created', 'publication_ready': False,
            'historical_authentication': 'not_established',
            'output': str(output), 'file_count': len(checksums) + 1}
