"""Reproducible synthetic package + installed Curator read-only import smoke."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
CURATOR = ROOT.parent / 'LDPORTO_VIDEO_CURATOR'
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'src/tests'), str(CURATOR)]

from test_r6_caption_handoff import package_fixture
from ldporto.second_curation_export import build_core_package, validate_core_package
from ldporto_curator.second_curation_import import read_package
from ldporto_curator.import_smoke import smoke_import


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    modules = ['ldporto_curator/second_curation_import.py', 'ldporto_curator/import_smoke.py',
               'ldporto_curator/evidence_source.py', 'ldporto_curator/subtitles.py']
    before = {name: sha(CURATOR/name) for name in modules}
    with tempfile.TemporaryDirectory(prefix='r6_caption_curator_') as temporary:
        analysis = package_fixture()
        result = build_core_package(analysis, output_dir=temporary)
        package = Path(result['path'])
        before_package = sha(package)
        parsed = read_package(package)
        _, _, report = smoke_import(package)
        validation = validate_core_package(package)
        evidence = {'source': 'synthetic_fixture_not_real_show', 'source_media_accessed': False,
            'curator_read_package': {'status': 'passed', 'candidate_count': len(parsed['catalog']['candidates'])},
            'curator_smoke_import': report, 'analyzer_validation': validation,
            'input_package_unchanged': before_package == sha(package),
            'curator_source_hashes_before': before,
            'curator_source_hashes_after': {name: sha(CURATOR/name) for name in modules},
            'independent_renderer_tested': False,
            'r6_fields_consumed_by_installed_curator': False,
            'limitation': 'Installed importers accept additive fields; they do not enforce R6 preflight or HANDOFF_MASTER.'}
    assert validation['status'] == 'valid'
    assert evidence['input_package_unchanged']
    assert evidence['curator_source_hashes_before'] == evidence['curator_source_hashes_after']
    destination = Path(__file__).with_name('caption_curator_import_r6.json')
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'read_package': 'passed', 'smoke_import': 'passed',
        'candidate_count': evidence['curator_read_package']['candidate_count'],
        'analyzer_validation': validation['status'], 'curator_sources_unchanged': True,
        'models_executed': report['models_executed'], 'render_executed': report['render_executed'],
        'evidence': destination.name}, ensure_ascii=False))


if __name__ == '__main__':
    main()
