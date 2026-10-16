"""Read-only qualification of the real show ZIP with the adjacent Curator."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
CURATOR = ROOT.parent/'LDPORTO_VIDEO_CURATOR'
sys.path[:0] = [str(ROOT/'src'),str(CURATOR)]

from ldporto_curator.second_curation_import import read_package
from ldporto_curator.import_smoke import smoke_import


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder=Path(__file__).parent
    package=next((folder/'show_package').rglob('SECOND_CURATION*.zip'))
    modules=['ldporto_curator/second_curation_import.py','ldporto_curator/import_smoke.py',
             'ldporto_curator/evidence_source.py','ldporto_curator/subtitles.py']
    before={name:sha(CURATOR/name) for name in modules}
    checksum=sha(package)
    parsed=read_package(package)
    _,_,report=smoke_import(package)  # No media path: no source lookup or hash/read.
    result={'source_kind':'real_show_existing_analysis_package_rebuild_only',
        'package':str(package.relative_to(ROOT)),'package_sha256':checksum,
        'read_package_candidates':len(parsed['catalog']['candidates']),
        'smoke_import':report,'source_media_accessed':False,'independent_renderer_tested':False,
        'r6_fields_consumed_by_installed_curator':False,
        'package_preserved':sha(package)==checksum,
        'curator_sources_preserved':before=={name:sha(CURATOR/name) for name in modules},
        'curator_source_hashes':before}
    assert result['package_preserved'] and result['curator_sources_preserved']
    assert result['read_package_candidates']==70
    assert report['models_executed'] is False and report['render_executed'] is False
    (folder/'show_curator_import_r6.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'read_package':'passed','smoke_import':'passed','candidates':result['read_package_candidates'],
        'models_executed':False,'render_executed':False,'source_media_accessed':False,
        'package_preserved':result['package_preserved'],'curator_sources_preserved':result['curator_sources_preserved']},ensure_ascii=False))


if __name__=='__main__':
    main()
