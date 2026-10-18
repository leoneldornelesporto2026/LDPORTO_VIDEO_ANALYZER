"""Publish a new derived compact revision from an exact-byte verified work tree.

Only task-owned derivatives are copied. Source analysis/media and prior revisions
remain untouched; frames can be reprofiled from the original sparse cache.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.compact_handoff import _write,_read,_finish_archive
from ldporto.compact_frames import reprofile_shared_atlas
from ldporto.compact_atlas import build_compact_atlas
from ldporto.project_export import _safe_ancestors,_logical
from ldporto.core import file_hash


def _frame_reference_remap(old_atlas, new_atlas):
    """Map old IDs to new IDs whether the original atlas was raw or reprofiled.

    A first-pass atlas does not yet contain source_frame_id_map. A reprofiled
    atlas does, and may have merged multiple source IDs into one physical frame.
    Never silently drop an original frame ID or accept an ambiguous remapping.
    """
    old_frames=old_atlas.get('frames') or []
    old_ids=[row['frame_id'] for row in old_frames]
    if len(old_ids)!=len(set(old_ids)):
        raise ValueError('duplicate_old_atlas_frame_id')
    old_map=old_atlas.get('source_frame_id_map')
    if old_map is None:
        old_map={ident:ident for ident in old_ids}
    new_map=new_atlas.get('source_frame_id_map') or {}
    result={}
    for original_id,old_id in old_map.items():
        if original_id not in new_map:
            raise ValueError('reprofile_source_frame_id_missing:'+str(original_id))
        new_id=new_map[original_id]
        if old_id in result and result[old_id]!=new_id:
            raise ValueError('ambiguous_reprofile_frame_mapping:'+str(old_id))
        result[old_id]=new_id
    if set(result)!=set(old_ids):
        raise ValueError('frame_reference_remap_incomplete')
    if not set(result.values()) <= {row['frame_id'] for row in new_atlas.get('frames') or []}:
        raise ValueError('remapped_frame_missing_from_final_atlas')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,type=Path);parser.add_argument('--analysis',required=True,type=Path)
    parser.add_argument('--atlas-cache',required=True,type=Path);parser.add_argument('--image-quality',type=int,default=50)
    parser.add_argument('--contact-width',type=int,default=512);parser.add_argument('--contact-quality',type=int,default=40)
    parser.add_argument('--full-audit',action='store_true')
    args=parser.parse_args();source=_safe_ancestors(args.directory)
    old=_read(source/'MANIFEST.json');ledger=_read(source/'FILE_INDEX.json')
    # This is integrity verification of an unfinished local revision, not an
    # assertion that its semantics passed. The new archive must pass the reader.
    for record in ledger['files']:
        path=_safe_ancestors(source/str(_logical(record['path'])))
        if not path.is_relative_to(source) or path.stat().st_size!=record['bytes'] or file_hash(path)!=record['sha256']:
            raise ValueError('derived_revision_input_ledger_mismatch:'+record['path'])
    revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6]
    output=source.parent.parent/('COMPACT_HANDOFF_R6_3_FINAL_'+revision)
    work=output/'editorial_directory';work.mkdir(parents=True,exist_ok=False)
    old_atlas=_read(source/'06_VISUAL_ATLAS/atlas_index.json')
    scenes=_read(source/'01_TIMELINE/scene_index.json')['scenes']
    original_scenes=json.loads((args.analysis/'scenes.json').read_text(encoding='utf-8'))
    metadata=old['source']
    atlas=reprofile_shared_atlas(args.atlas_cache,work,metadata,original_scenes,analysis_folder=args.analysis,
        navigation_width=320,analysis_width=640,jpeg_quality=args.image_quality,
        contact_width=args.contact_width,contact_quality=args.contact_quality)
    remap=_frame_reference_remap(old_atlas,atlas)
    def rewrite(value):
        if isinstance(value,str):return remap.get(value,value)
        if isinstance(value,list):return [rewrite(x) for x in value]
        if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
        return value
    for record in ledger['files']:
        name=record['path']
        if name.startswith('06_VISUAL_ATLAS/') or name=='08_REPORTS/VISUAL_ATLAS.pdf':continue
        if name.endswith('.json'):_write(work,name,rewrite(_read(source/name)))
        else:
            target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,target)
    coverage=_read(work/'08_REPORTS/COVERAGE_REPORT.json')
    coverage.update(frame_count=len(atlas['frames']),unique_image_count=atlas['statistics']['unique_image_files'],
        contact_sheet_count=len(atlas['contact_sheets']),image_deduplication=atlas['statistics'])
    _write(work,'08_REPORTS/COVERAGE_REPORT.json',coverage)
    overview=_read(work/'00_OVERVIEW/video_summary.json')
    overview.update(package_revision=revision,derived_from_compact_revision=old['revision'])
    _write(work,'00_OVERVIEW/video_summary.json',overview)
    limitations=_read(work/'08_REPORTS/LIMITATIONS.json')
    limitations['image_encoding']={'navigation_width':320,'analysis_width':640,'jpeg_quality':args.image_quality,
        'contact_width':args.contact_width,'contact_quality':args.contact_quality,
        'image_count_preserved':True,'canonical_words_geometry_not_reduced_for_size':True}
    _write(work,'08_REPORTS/LIMITATIONS.json',limitations)
    reel_rows=_read(work/'04_REELS/reels_index.json')['reels'];story_doc=_read(work/'05_STORIES/series_index.json')
    pdf=build_compact_atlas(work,metadata=metadata,scenes=_read(work/'01_TIMELINE/scene_index.json')['scenes'],
        reels=reel_rows,stories=story_doc['parts'],series=story_doc['series'],atlas_index=atlas,
        coverage=coverage,limitations=limitations,revision=revision)
    manifest={**old,'revision':revision,'derivation':{'source_revision':old['revision'],
        'source_file_index_sha256':file_hash(source/'FILE_INDEX.json'),
        'changes':['categorical_confidence_label','image_encoding_after_legibility_review','regenerated_searchable_atlas'],
        'canonical_source_mutated':False,'new_media_decode':False}}
    archive=_finish_archive(work,output,manifest)
    summary={'schema_version':'r6.3','revision':revision,'archive':archive,'coverage':coverage,'pdf':pdf,
        'source_sha256':metadata['sha256'],'source_metadata':metadata,
        'parent_package':overview['parent_package'],'state':'PARTIAL','sufficiency':'PARTIAL_VISUAL_EVIDENCE',
        'preferred_40MiB_budget_met':archive['bytes']<=40*1024**2,'initial_15_to_30MiB_target_met':15<=archive['mib']<=30,
        'new_model_calls':0,'new_media_decode':False,'full_pipeline_executed':False,'canonical_sources_modified':False,
        'preview_approved':False,'human_approved':False,'publication_ready':False}
    if args.full_audit:
        from ldporto.r62_delivery import _zip_directory
        raw_names=('people_observations.json','tracklet_observations.json','raw_tracks.json','reid_merge_decisions.json',
            'person_motion.json','person_tracks.json','person_identities.json','active_speaker.json','speaker_person_mapping.json',
            'camera_director_timeline.json','shots.json','scenes.json','words.json','transcript_segments.json','audio_analysis.json',
            'analysis_summary.json','run_manifest.json','report_execution_receipt.json','manifest.json')
        extra=[(args.analysis/name,'raw_analysis/'+name) for name in raw_names if (args.analysis/name).is_file()]
        summary['full_audit']=_zip_directory(work,output/'FULL_AUDIT.zip',extra)
    _write(output,'COMPACT_DELIVERY.json',summary)
    # A derived revision must not modify source-controlled docs/reports or
    # historic checkpoints. Keep the pointer beside the new ZIP only.
    _write(output,'FINAL_ARTIFACT_POINTER.json',{'delivery_manifest':str(output/'COMPACT_DELIVERY.json'),
        'delivery_manifest_sha256':file_hash(output/'COMPACT_DELIVERY.json'),'archive':archive,
        'full_audit':summary.get('full_audit'),'state':'PARTIAL'})
    print(json.dumps({k:v for k,v in summary.items() if k!='coverage'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
