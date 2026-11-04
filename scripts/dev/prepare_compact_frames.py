"""Prepare shared sparse frames from an explicit persisted analysis/package."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.compact_frames import build_shared_visual_atlas
from ldporto.core import file_hash
from ldporto.project_export import _safe_ancestors
from ldporto.paths import videos_directory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',required=True,type=Path);parser.add_argument('--package',required=True,type=Path)
    parser.add_argument('--media',required=True,type=Path);parser.add_argument('--destination',type=Path)
    args=parser.parse_args()
    analysis=_safe_ancestors(args.analysis)
    persisted=json.loads((analysis/'manifest.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(args.package) as archive:
        metadata=json.loads(archive.read('source/metadata.json'))
        assert metadata['sha256']==persisted['video_sha256']
        manifest=json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        # Exact-byte verification before using any catalog intervals.
        for row in manifest['files']:
            data=archive.read(row['path'])
            assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
        catalog=json.loads(archive.read('editorial/candidate_catalog.json'))['candidates']
        units=json.loads(archive.read('editorial/story_units.json'))['units']
        stories=json.loads(archive.read('social/stories_manifest.json'))['stories']
    scene_bytes=(analysis/'scenes.json').read_bytes()
    assert hashlib.sha256(scene_bytes).hexdigest()==persisted['artifact_checksums']['scenes.json']
    pieces=[{'piece_id':c['candidate_id'],'source_intervals':[{'start':c['start'],'end':c['end']}]} for c in catalog]
    pieces +=[{'piece_id':c['unit_id'],'source_intervals':c['source_intervals']} for c in units]
    pieces +=[{'piece_id':c['story_id'],'source_intervals':c.get('source_intervals') or [{'start':c['start'],'end':c['end']}]} for c in stories]
    root=args.destination or videos_directory()/'LDPORTO_VIDEO_ANALYZER'/('R6_3_SHARED_FRAMES_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    root=_safe_ancestors(root);root.mkdir(parents=True,exist_ok=False)
    report=ROOT/'docs/reports/r63_20261017';report.mkdir(parents=True,exist_ok=True)
    pointer={'atlas_directory':str(root),'analysis':str(analysis),'package':str(args.package.absolute()),
        'package_sha256':file_hash(args.package),'source_sha256':metadata['sha256'],'status':'IN_PROGRESS'}
    (report/'FRAME_PREPARATION_POINTER.json').write_text(json.dumps(pointer,indent=2),encoding='utf-8')
    result=build_shared_visual_atlas(analysis,metadata,json.loads(scene_bytes),pieces,root,media_path=args.media,
        progress=lambda stage,current,total: print('%s %d/%d'%(stage,current,total),flush=True))
    pointer.update(status='COMPLETE',statistics=result['statistics'],atlas_index_sha256=file_hash(root/'06_VISUAL_ATLAS/atlas_index.json'))
    (report/'FRAME_PREPARATION_POINTER.json').write_text(json.dumps(pointer,indent=2),encoding='utf-8')
    print(json.dumps(pointer,indent=2))


if __name__=='__main__':
    main()
