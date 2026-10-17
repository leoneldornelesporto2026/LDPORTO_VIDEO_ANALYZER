"""Call installed Curator's real read-only package/import APIs, preserving inputs."""
import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import inspect
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CURATOR = ROOT.parent / 'LDPORTO_VIDEO_CURATOR'
sys.path[:0] = [str(ROOT/'src'), str(CURATOR)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curator_sources():
    return {p.relative_to(CURATOR).as_posix(): sha(p)
            for p in sorted((CURATOR/'ldporto_curator').rglob('*.py')) if '__pycache__' not in p.parts}


def main(package, label):
    before = curator_sources()
    package_before = sha(package)
    from ldporto_curator.second_curation_import import read_package
    from ldporto_curator.import_smoke import smoke_import
    report = {'schema_version': 'r6.2-import-audit-1', 'package': str(package.resolve()),
        'package_sha256': package_before, 'APIs': {
            'read_package': str(inspect.signature(read_package)),
            'smoke_import': str(inspect.signature(smoke_import))},
        'Curator_source_hashes_before': before, 'source_media_accessed': False,
        'models_executed': False, 'render_executed_by_import': False,
        'approval_created': False, 'publication_ready': False}
    try:
        parsed = read_package(package)
        report['read_package'] = {'status': 'PASS', 'candidate_count': len(parsed['catalog']['candidates']),
            'source_sha256': parsed['metadata']['sha256'], 'file_count': len(parsed['files'])}
        evidence, plan, smoke_report = smoke_import(package)
        report['smoke_import'] = {'status': 'PASS', 'report': smoke_report,
            'candidate_ids': [r['candidate_id'] for r in evidence['candidates']],
            'document_count': len(evidence['documents']),
            'visual_handoff_document_count': sum('visual_frame_handoff' in n.casefold() for n in evidence['documents']),
            'image_asset_count': len(evidence['asset_inventory']),
            'unresolved_reference_count': len(evidence['unresolved_references']),
            'episode_count': len(plan['episodes']), 'extra_count': len(plan['extras'])}
        report['installed_Curator_consumption_limits'] = (
            'Package documents and image assets are loaded; this smoke does not prove semantic application '
            'of new Visual Frame Handoff decisions by the Curator UI or renderer. Native camera adapter '
            'execution is tested separately in CAMERA_VISUAL_VALIDATION.md.')
        assert len(parsed['catalog']['candidates']) == len(evidence['candidates']) == 70
        assert smoke_report['models_executed'] is False and smoke_report['render_executed'] is False
        assert smoke_report['approved_count'] == 0
        report['status'] = 'PASS'
    except Exception as error:
        report['status'] = 'FAIL'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    report['package_preserved'] = package_before == sha(package)
    report['Curator_source_hashes_after'] = curator_sources()
    report['Curator_sources_preserved'] = before == report['Curator_source_hashes_after']
    report['Curator_source_file_count'] = len(before)
    destination = HERE/f'CURATOR_IMPORT_{label}.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({k: report[k] for k in ['status', 'package_preserved',
        'Curator_sources_preserved', 'Curator_source_file_count']}, ensure_ascii=False))
    assert report['package_preserved'] and report['Curator_sources_preserved']
    if report['status'] != 'PASS':
        raise RuntimeError(report['error']['message'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--label', choices=['baseline', 'editorial'], required=True)
    args = parser.parse_args()
    main(args.package, args.label)
