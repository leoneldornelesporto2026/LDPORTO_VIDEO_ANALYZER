"""Validate one delivered R6.3 ZIP, using only the ZIP bytes (no models/media)."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.compact_handoff_reader import inspect_compact_handoff


def _hash_file(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()

def audit(archive, *, expected_source=None, expected_scenes=None, expected_reels=None,
          expected_story_parts=None, expected_series=None):
    path=Path(archive)
    result=inspect_compact_handoff(path,reconstruct=False)
    errors=list(result.get('errors') or [])
    counts=result.get('counts') or {}
    source=result.get('source') or {}
    expectations={'source_sha256': (source.get('sha256'),expected_source),
                  'scene_count':(counts.get('scene_count'),expected_scenes),
                  'reel_count':(counts.get('reel_count'),expected_reels),
                  'story_part_count':(counts.get('story_part_count'),expected_story_parts),
                  'series_count':(counts.get('series_count'),expected_series)}
    for key,(observed,expected) in expectations.items():
        if expected is not None and observed!=expected:
            errors.append('expected_%s_mismatch:%s!=%s'%(key,observed,expected))
    pdf_test='NOT_RUN'
    if result.get('status')=='valid':
        with zipfile.ZipFile(path) as z:
            pdf=z.read('08_REPORTS/VISUAL_ATLAS.pdf')
            if not pdf.startswith(b'%PDF-') or not pdf.rstrip().endswith(b'%%EOF'):
                errors.append('invalid_pdf_magic_or_footer')
            try:
                import fitz
            except ImportError:
                pdf_test='NOT_RUN_FITZ_NOT_INSTALLED'
            else:
                try:
                    doc=fitz.open(stream=pdf,filetype='pdf')
                    extracted=''.join(page.get_text() for page in doc)
                    pdf_test='PASS' if doc.page_count>0 and len(extracted.strip())>=20 else 'FAIL'
                    if pdf_test!='PASS':errors.append('pdf_not_searchable_or_empty')
                    doc.close()
                except Exception as exc:
                    pdf_test='FAIL'
                    errors.append('pdf_decode_failed:'+type(exc).__name__)
    return {'schema_version':'r6.3-delivery-audit-1',
            'status':'VALID_WITH_PDF_TEXT_NOT_TESTED' if not errors and pdf_test.startswith('NOT_RUN') else 'VALID' if not errors else 'FAILED',
            'errors':errors,'file':str(path.resolve()),'bytes':path.stat().st_size,'mib':round(path.stat().st_size/1048576,3),
            'sha256':_hash_file(path),
            'counts':counts,'source_sha256':source.get('sha256'),
            'pdf_searchable_test':pdf_test,'independent_zip_reader':'PASS' if result.get('status')=='valid' else 'FAIL',
            'models_executed':False,'source_media_accessed':False,
            'publication_ready':False,'human_second_curation_completed':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',required=True,type=Path)
    p.add_argument('--expected-source');p.add_argument('--expected-scenes',type=int)
    p.add_argument('--expected-reels',type=int);p.add_argument('--expected-story-parts',type=int)
    p.add_argument('--expected-series',type=int);p.add_argument('--report',type=Path)
    a=p.parse_args(argv)
    report=audit(a.archive,expected_source=a.expected_source,expected_scenes=a.expected_scenes,
        expected_reels=a.expected_reels,expected_story_parts=a.expected_story_parts,expected_series=a.expected_series)
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        if a.report.exists():p.error('Report destination already exists; historical reports cannot be overwritten')
        a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['status'].startswith('VALID') else 2

if __name__=='__main__':raise SystemExit(main())
