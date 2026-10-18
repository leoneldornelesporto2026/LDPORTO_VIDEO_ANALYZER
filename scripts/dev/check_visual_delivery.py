"""Read-only integrity audit for an Analyzer R6.2 EDITORIAL_HANDOFF.zip.

Does not download, run models, approve previews or modify the source archive.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def verify(path, expected_pieces=None):
    problems=[]
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            problems.append('duplicate_zip_member')
        for name in names:
            if name.startswith('/') or '\\' in name or any(p in ('..','') for p in name.split('/')):
                problems.append('unsafe_zip_member:'+name)
        required=['VISUAL_FRAME_HANDOFF/index.json', 'VISUAL_FRAME_HANDOFF/RELATORIO_COBERTURA_VISUAL.json',
                  'VISUAL_FRAME_HANDOFF/REVISAO_VISUAL_POR_CORTE.pdf',
                  'subtitles/visual_piece_caption_preflight.json', 'HANDOFF_MASTER.json']
        for name in required:
            if name not in names:
                problems.append('missing_required:'+name)
        if problems:
            return {'status':'FAILED','errors':problems}
        index=json.loads(archive.read(required[0]))
        coverage=json.loads(archive.read(required[1]))
        captions=json.loads(archive.read(required[3]))
        pdf=archive.read(required[2])
        if not pdf.startswith(b'%PDF-') or not pdf.rstrip().endswith(b'%%EOF'):
            problems.append('atlas_pdf_invalid_magic')
        if hashlib.sha256(pdf).hexdigest()!=index.get('review_atlas_sha256'):
            problems.append('atlas_sha256_mismatch')
        pieces=index.get('pieces') or []
        if expected_pieces is not None and len(pieces)!=expected_pieces:
            problems.append('unexpected_piece_count')
        if len(pieces)!=coverage.get('piece_count') or len(pieces)!=len(coverage.get('pieces') or []):
            problems.append('visual_coverage_piece_count_mismatch')
        ids=set()
        for piece in pieces:
            pid=piece.get('piece_id')
            if pid in ids:
                problems.append('duplicate_piece_id:'+str(pid))
            ids.add(pid)
            prefix='VISUAL_FRAME_HANDOFF/'+str(pid)+'/'
            ref=piece.get('manifest_ref')
            if ref!=prefix+'visual_handoff_manifest.json' or ref not in names:
                problems.append('missing_piece_manifest:'+str(pid))
                continue
            manifest=json.loads(archive.read(ref))
            if manifest.get('source_sha256') != index.get('source_sha256'):
                problems.append('piece_source_sha_mismatch:'+str(pid))
            if manifest.get('preview_approved') is not False or manifest.get('publish_ready') is not False:
                problems.append('unauthorized_approval:'+str(pid))
            for f in manifest.get('files') or []:
                name=prefix+str(f.get('path'))
                if name not in names:
                    problems.append('missing_piece_file:'+name)
                    continue
                data=archive.read(name)
                if len(data)!=f.get('bytes') or hashlib.sha256(data).hexdigest()!=f.get('sha256'):
                    problems.append('piece_integrity_error:'+name)
            branch='reels' if piece.get('piece_type')=='REEL' else 'stories'
            if pid not in captions.get(branch,{}):
                problems.append('missing_caption_status:'+str(pid))
            if piece.get('caption_preflight_ref')!=required[3]+'#/'+branch+'/'+str(pid):
                problems.append('wrong_caption_pointer:'+str(pid))
        return {'status':'VALID' if not problems else 'FAILED','errors':problems,
                'piece_count':len(pieces),'reel_count':sum(x.get('piece_type')=='REEL' for x in pieces),
                'story_count':sum(x.get('piece_type')=='STORY' for x in pieces),
                'captured_frame_count':coverage.get('captured_frames_total'),
                'pieces_without_frames':coverage.get('pieces_without_source_frames'),
                'source_sha256':index.get('source_sha256'),
                'human_review_required':True,'camera_geometry_homologated':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',type=Path)
    parser.add_argument('--expected-pieces',type=int)
    args=parser.parse_args()
    try:
        result=verify(args.zip,args.expected_pieces)
    except (OSError,zipfile.BadZipFile,KeyError,TypeError,ValueError) as exc:
        result={'status':'FAILED','errors':[str(exc)]}
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 0 if result['status']=='VALID' else 2


if __name__=='__main__':
    raise SystemExit(main())
