"""Stage 52 read-only evidence audit. Never extract, render, approve or publish."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import zipfile
from jsonschema.exceptions import ValidationError

from .second_curation_export import validate_core_package
from .second_curation_decisions import compile_decisions

# Supplied historical claims, not measurements performed by this tool.
HISTORICAL_BASELINE = {
    'discovered': 217, 'review_queue': 193, 'shortlist': 0, 'approved': 0,
    'quality_flag_count': 4080, 'speaker_person_mapping_coverage': .0705,
    'active_speaker_coverage': .00058, 'resolved_focus_coverage': .0431,
    'zoom_event_count': 6, 'zoom_delivered_event_count': 0, 'head_clips': 2,
}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def audit_package(path, feedback=None):
    """Inspect a historical core/output ZIP, optionally validate local human feedback.

    Feedback import is validation only, not an editorial approval or remote upload.
    All reported text remains untrusted data; no execution or ZIP output occurs.
    """
    path = Path(path)
    report = {'path': str(path), 'status': 'not_measured', 'sha256': None,
              'reprocessed': False, 'publication_ready': False, 'errors': [],
              'feedback': {'status': 'not_measured', 'remote_upload': False},
              'output_zip': {'generated': False, 'validation': None}}
    if not path.is_file():
        report['errors'] = ['package_missing']
        return report
    report['sha256'] = sha256(path)
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) > 5000 or sum(e.file_size for e in entries) > 256 * 1024 ** 2:
                raise ValueError('archive_budget_exceeded')
            if len(names) != len(set(names)):
                raise ValueError('duplicate_archive_members')
            if len(names) != len({name.casefold() for name in names}):
                raise ValueError('case_colliding_archive_members')
            for entry in entries:
                name = PurePosixPath(entry.filename)
                if (name.is_absolute() or '..' in name.parts or '\\' in entry.filename
                        or ':' in entry.filename or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise ValueError('unsafe_or_symlink_member')
            def read(name, default=None):
                return json.loads(archive.read(name)) if name in names else default
            manifest = read('SECOND_CURATION_MANIFEST.json', {})
            native_manifest = manifest or read('ANALYSIS_EXPORT_MANIFEST.json', {})
            report['origin'] = {k: manifest.get(k) for k in
                ('schema_version', 'analyzer_version', 'analyzer_build', 'created_at', 'source_hash', 'run_id')}
            report['origin'].update(package_type=native_manifest.get('package_type'),
                                    created_at_local=native_manifest.get('created_at_local'))
            hash_errors = []
            files = [r for r in native_manifest.get('files', []) if r.get('included', True)]
            declared = [r['path'] for r in files]
            if len(declared) != len(set(declared)):
                hash_errors.append('duplicate_manifest_paths')
            for item in files:
                name = item['path']
                if name not in names:
                    hash_errors.append('missing_manifest_member:' + name)
                    continue
                payload = archive.read(name)
                if hashlib.sha256(payload).hexdigest() != item.get('sha256') or len(payload) != item.get('bytes'):
                    hash_errors.append('manifest_hash_or_size_mismatch:' + name)
            report['manifest_integrity'] = {'status': ('offline_verified' if not hash_errors else 'blocked')
                if files else 'not_measured', 'checked_files': len(files),
                'checksums_valid': not hash_errors if files else None, 'errors': hash_errors}
            report['errors'].extend(hash_errors)
            report['validation'] = validate_core_package(path)
            report['output_zip']['validation'] = report['validation']
            report['errors'].extend(report['validation']['errors'])
            catalog = read('editorial/candidate_catalog.json')
            rows = (catalog or {}).get('candidates', [])
            ids = [r.get('candidate_id') for r in rows]
            report['ids'] = ({'count': len(ids), 'duplicates': [k for k, v in Counter(ids).items() if v > 1]}
                             if catalog is not None else None)
            groups = Counter(r.get('duplicate_group_id') for r in rows if r.get('duplicate_group_id'))
            report['duplicate_groups'] = {k: v for k, v in groups.items() if v > 1} if catalog is not None else None
            report['queue'] = read('editorial/human_review_queue.json')
            report['queue_status'] = 'available' if report['queue'] is not None else 'not_measured'
            report['workflow'] = manifest.get('workflow')
            report['candidate_states'] = dict(Counter(r.get('candidate_state', 'unknown') for r in rows)) if catalog is not None else None
            report['commercial_openbox_copa'] = [
                {'candidate_id': r.get('candidate_id'), 'classification': r.get('commercial_classification'),
                 'human_approved': r.get('human_approved'), 'publication_ready': r.get('publication_ready')}
                for r in rows if any(word in str(r.get('transcript_literal', '')).casefold()
                                     for word in ('openbox', 'open box', 'copa'))] if catalog is not None else None
            report['ocr'] = read('visual/commercial_ocr_s8.json')
            report['ocr_status'] = (report['ocr'] or {}).get('status', 'not_measured')
            report['contact_sheets_are_ocr_proof'] = False
            report['qa'] = report['validation'].get('question_reference_validation')
            if feedback:
                try:
                    document = json.loads(Path(feedback).read_text(encoding='utf-8-sig'))
                    if document.get('provider') != 'manual_json':
                        raise ValueError('human_feedback_requires_manual_json')
                    if document.get('input_package_sha256') != report['sha256']:
                        raise ValueError('feedback_package_hash_mismatch')
                    proposals = compile_decisions(document,
                        read('editorial/candidate_catalog.json'), read('source/metadata.json'))
                    report['feedback'].update(status='offline_verified', sha256=sha256(feedback),
                                              proposal_count=len(proposals), human_approval=False)
                except (OSError, ValueError, TypeError, KeyError, AttributeError, ValidationError) as exc:
                    report['feedback'].update(status='blocked', reason=str(exc))
                    report['errors'].append('feedback_invalid')
            report['status'] = 'offline_verified' if not report['errors'] else 'requires_review'
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, TypeError, KeyError,
            AttributeError, IndexError) as exc:
        report['status'] = 'blocked'
        report['errors'].append(str(exc))
    return report


def compare_outputs(baseline=None, current=None):
    """Deltas require source SHA and full configuration identity, never titles/URLs.

    Accept full analysis JSONs. configuration_sha256 may be explicitly recorded;
    otherwise hash the complete saved config, never a single stage's parameters.
    """
    def load(path):
        if not path:
            return None
        path = Path(path)
        if path.is_dir():
            path = path / 'analysis.json'
        if not path.is_file():
            return None
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        config = data.get('config')
        config_hash = data.get('configuration_sha256')
        if not config_hash and isinstance(config, dict) and config:
            config_hash = hashlib.sha256(json.dumps(config, sort_keys=True,
                separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        metrics = dict(data.get('analysis_quality') or {})
        metrics.update(data.get('candidate_metrics') or {})
        return {'source_sha256': (data.get('metadata') or {}).get('sha256'),
                'configuration_sha256': config_hash, 'metrics': metrics, 'file_sha256': sha256(path)}
    before, after = load(baseline), load(current)
    comparable = bool(before and after and before['source_sha256'] and
        before['source_sha256'] == after['source_sha256'] and before['configuration_sha256'] and
        before['configuration_sha256'] == after['configuration_sha256'])
    result = {'status': 'measured' if comparable else 'not_measured',
              'reason': None if comparable else 'same_source_and_configuration_not_proven',
              'baseline_evidence': before, 'current_evidence': after, 'metrics': {}}
    for key, claim in HISTORICAL_BASELINE.items():
        a = before['metrics'].get(key) if before else None
        b = after['metrics'].get(key) if comparable else None
        numeric = lambda v: type(v) in (int, float) and math.isfinite(v)
        measured = numeric(a) and numeric(b)
        result['metrics'][key] = {'historical_claim': claim, 'before': a,
            'after': b if numeric(b) else None, 'delta': b-a if measured else None,
            'status': 'measured' if measured else 'not_measured'}
    return result
