"""New additive package revision from verified sparse evidence; no media decoding."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.core import file_hash
from ldporto.r62_delivery import _read,_write,_reindex,_zip_directory
from ldporto.visual_frame_handoff import validate_visual_frame_handoff


def main():
    report=Path(__file__).parent
    parent=Path(sys.argv[1]);receipt=_read(parent/'DELIVERY_MANIFEST.json')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output=parent.parent/('R6_2_FINAL_'+stamp)
    output.mkdir(exist_ok=False)
    work=output/'editorial_directory'
    shutil.copytree(parent/'editorial_directory',work)
    index=_read(work/'VISUAL_FRAME_HANDOFF/index.json')
    canonical=_read(work/'subtitles/caption_preflight_r6.json')['candidates']
    captions=_read(work/'subtitles/visual_piece_caption_preflight.json')
    for piece in index['pieces']:
        if piece['piece_type']=='REEL':
            captions['stories'][piece['piece_id']]=canonical[piece['piece_id']]
        else:
            piece['editorial_origin']='canonical_standalone_story' if not piece['series_ids'] else 'provisional_source_story_unit'
            piece['narrative_complete']=False
    _write(work/'subtitles/visual_piece_caption_preflight.json',captions)
    _write(work/'VISUAL_FRAME_HANDOFF/index.json',index)
    manifests=[];unique_images=set()
    for piece in index['pieces']:
        folder=(work/piece['manifest_ref']).parent
        validation=validate_visual_frame_handoff(folder)
        if not validation['valid']:
            raise ValueError(str(validation))
        manifest=_read(folder/'visual_handoff_manifest.json');manifests.append(manifest)
        frame_index=_read(folder/'frame_index.json')
        unique_images.update(f['sha256'] for f in frame_index['frames'])
    visual_summary={'pieces':len(manifests),'reels':70,'provisional_source_units':86,'standalone_stories':1,
        'captured_frame_references':sum(m['coverage']['captured_frames'] for m in manifests),
        'distinct_image_hashes':len(unique_images),'pieces_with_real_frames':sum(m['coverage']['captured_frames']>0 for m in manifests),
        'missing_frame_requests':sum(m['coverage']['missing_frames'] for m in manifests),
        'max_piece_artifact_bytes':max(sum(r['bytes'] for r in m['files']) for m in manifests),
        'source_sha256':receipt['source_sha256'],'editorial_state':'PARTIAL',
        'new_decoded_frames_in_this_revision':0,'continuous_visual_coverage_verified':False,
        'caption_candidate_counts':dict(Counter(r['status'] for r in canonical.values())),
        'human_approved':False,'preview_approved':False,'publication_ready':False}
    _write(report/'VISUAL_DELIVERY_MEASUREMENTS.json',visual_summary)
    for name in ('DIAGNOSTICO_CAUSA_RAIZ.md','CAMERA_VISUAL_VALIDATION.md','VISUAL_FRAME_HANDOFF_SPEC.md',
                 'CAPTION_PREFLIGHT_REPORT.md','STORIES_NARRATIVE_QA.md','MEDIA_LIBRARY_MIGRATION.md',
                 'MEDIA_LIBRARY_RECEIPT.json','VISUAL_DELIVERY_MEASUREMENTS.json','BASELINE.json'):
        source=report/name
        if source.is_file():
            target=work/'diagnostics'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    camera=report/'camera_samples'
    for name in ('ALL_RENDER_INDEX.json','FIVE_SAMPLE_RENDER_INDEX.json','FULL_DECODE_CHECK.json','CAMERA_SAMPLE_ARTIFACT_INDEX.json'):
        target=work/'camera/validation'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(camera/name,target)
    acceptance={'schema_version':'r6.2','state':'PARTIAL','source_sha256':receipt['source_sha256'],
        'five_real_scenario_renders':'SOURCE_FIT_VERIFIED_IN_SAMPLED_FRAMES',
        'digital_zoom_motion_observed':True,'digital_zoom_editorial_result':'REJECTED_HANDS_CLIPPED',
        'zoom_delivered_approved_count':0,'camera_validation_ref':'camera/validation/ALL_RENDER_INDEX.json',
        'protected_hands_instruments_geometry':'UNKNOWN_IN_AUTOMATED_TRACKING',
        'future_camera_changes_require_curator_render_verification':True,
        'narrative_complete_supported':0,'caption_candidate_counts':visual_summary['caption_candidate_counts'],
        'curator_compatibility':{'legacy_package_import_preserved':True,
            'visual_frame_handoff_import':'EDITORIAL_EVIDENCE_CURRENT_CURATOR_DOES_NOT_AUTOMATICALLY_CONSUME',
            'camera_adapter':'NATIVE_ADAPTIVE_TIMELINE_REQUIRES_EXPLICIT_SELECTION_AND_REVIEW'},
        'preview_approved':False,'human_approved':False,'publication_ready':False}
    _write(work/'R6_2_ACCEPTANCE.json',acceptance)
    master=_read(work/'HANDOFF_MASTER.json');idx=_read(work/'CURATION_INDEX.json')
    master.pop('full_audit_ref',None);idx.pop('full_audit_ref',None)
    master.update(package_revision=stamp,evidence_snapshot_revision=index['revision'],
        acceptance_ref='R6_2_ACCEPTANCE.json',camera_validation_ref=acceptance['camera_validation_ref'],
        visual_piece_index=index['pieces'],r62_acceptance_state='PARTIAL')
    by_id={p['piece_id']:p for p in index['pieces']}
    for group,key in (('candidates','candidate_id'),('stories','story_id')):
        for item in master.get(group,[]):
            if item.get(key) in by_id:
                item['visual_handoff_ref']=by_id[item[key]]['manifest_ref']
    idx['r62_acceptance_ref']='R6_2_ACCEPTANCE.json'
    _write(work/'HANDOFF_MASTER.json',master);_write(work/'CURATION_INDEX.json',idx);_reindex(work)
    # Retain exact raw evidence, selective source excerpts, plans and render proofs
    # in FULL only; the show original is never included in either archive.
    raw_names=('raw_tracks.json','tracklet_observations.json','people_observations.json','reid_merge_decisions.json',
        'speaker_person_mapping.json','person_motion.json','shots.json','audio_analysis.json','analysis_quality.json',
        'camera_director_timeline.json','run_manifest.json','report_execution_receipt.json')
    analysis=ROOT/'analysis/video_8adc6609911a'
    extra=[(analysis/name,'raw_analysis/'+name) for name in raw_names if (analysis/name).is_file()]
    extra.extend((p,'camera_samples/'+p.relative_to(camera).as_posix()) for p in camera.rglob('*')
        if p.is_file() and p.suffix.lower() in {'.mp4','.json','.png','.jpg','.ass','.py'})
    print('FULL_AUDIT: ledger, evidence and sparse excerpts',flush=True)
    full=_zip_directory(work,output/'FULL_AUDIT.zip',extra)
    reference={'filename':'FULL_AUDIT.zip','sha256':full['sha256'],'bytes':full['bytes']}
    master=_read(work/'HANDOFF_MASTER.json');master['full_audit_ref']=reference
    idx=_read(work/'CURATION_INDEX.json');idx['full_audit_ref']=reference
    _write(work/'HANDOFF_MASTER.json',master);_write(work/'CURATION_INDEX.json',idx);_reindex(work)
    print('EDITORIAL_HANDOFF: staged validation and atomic publication',flush=True)
    editorial=_zip_directory(work,output/'EDITORIAL_HANDOFF.zip')
    result={**receipt,'revision':stamp,'evidence_snapshot_revision':index['revision'],
        'editorial':editorial,'full_audit':full,'visual_measurements':visual_summary,
        'preliminary_delivery_ref':{'revision':receipt['revision'],'editorial_sha256':receipt['editorial']['sha256'],
            'reason_superseded':'Correct Reel caption limit and add real camera rejection evidence'},
        'originals_modified':False,'new_model_calls':0,'full_pipeline_executed':False,
        'state':'PARTIAL','preview_approved':False,'human_approved':False,'publication_ready':False}
    _write(output/'DELIVERY_MANIFEST.json',result)
    _write(report/'FINAL_DELIVERY_POINTER.json',{'delivery_manifest':str(output/'DELIVERY_MANIFEST.json'),
        'sha256':file_hash(output/'DELIVERY_MANIFEST.json'),'editorial':editorial,'full_audit':full})
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
