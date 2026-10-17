"""Selective visual evidence and two complementary packages; no inference pipeline."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

from .core import file_hash
from .export_privacy import sanitize_export
from .project_export import _safe_ancestors, _logical
from .second_curation_export import snapshot_core_package, validate_core_package


def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(sanitize_export(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _reindex(root):
    master=_read(root/'HANDOFF_MASTER.json')
    master['artifacts']=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':file_hash(p)}
        for p in sorted(root.rglob('*')) if p.is_file() and p.name not in {'HANDOFF_MASTER.json','SECOND_CURATION_MANIFEST.json'}]
    _write(root/'HANDOFF_MASTER.json',master)
    manifest=_read(root/'SECOND_CURATION_MANIFEST.json')
    manifest['files']=[{'path':p.relative_to(root).as_posix(),'bytes':p.stat().st_size,'sha256':file_hash(p)}
        for p in sorted(root.rglob('*')) if p.is_file() and p.name!='SECOND_CURATION_MANIFEST.json']
    manifest.update(file_count=len(manifest['files'])+1,uncompressed_bytes=sum(r['bytes'] for r in manifest['files']))
    _write(root/'SECOND_CURATION_MANIFEST.json',manifest)


def _pieces(root):
    pieces=[]
    catalog=_read(root/'editorial/candidate_catalog.json')['candidates']
    for row in catalog:
        pieces.append({'piece_id':row['candidate_id'],'piece_type':'REEL','candidate':row,
            'intervals':[{'start':row['start'],'end':row['end']}],'series_ids':[]})
    sequence_path=root/'editorial/story_sequence_candidates.json'
    sequences=_read(sequence_path).get('sequences',[]) if sequence_path.exists() else []
    units_path=root/'editorial/story_units.json'
    units=_read(units_path).get('units',[]) if units_path.exists() else []
    series_path=root/'editorial/story_series_proposals.json'
    if series_path.exists():
        for series in _read(series_path).get('series',[]):
            for story in series.get('stories') or []:
                pieces.append({'piece_id':story['story_id'],'piece_type':'STORY','candidate':story,
                    'intervals':story['source_intervals'],'series_ids':[series['series_id']]})
    else:
        for unit in units:
            pieces.append({'piece_id':unit['unit_id'],'piece_type':'STORY','candidate':{**unit,'story_id':unit['unit_id']},
                'intervals':unit.get('source_intervals') or [{'start':unit['start'],'end':unit['end']}],
                'series_ids':[s['sequence_id'] for s in sequences if unit['unit_id'] in (s.get('unit_ids') or [])]})
    classic=root/'social/stories_manifest.json'
    if classic.exists():
        for story in _read(classic).get('stories') or []:
            pieces.append({'piece_id':story['story_id'],'piece_type':'STORY','candidate':story,
                'intervals':story.get('source_intervals') or [{'start':story['start'],'end':story['end']}],'series_ids':[]})
    ids=[p['piece_id'] for p in pieces]
    if len(ids)!=len(set(ids)):
        raise ValueError('visual_piece_id_collision')
    for item in pieces:
        _logical(item['piece_id'])
        if '/' in item['piece_id']:
            raise ValueError('visual_piece_id_must_be_component')
    return pieces


def _zip_directory(root,target,extra_raw=()):
    records=[]
    staged=target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.partial')
    with zipfile.ZipFile(staged,'x',zipfile.ZIP_DEFLATED,compresslevel=4) as archive:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                _safe_ancestors(path)
                name=path.relative_to(root).as_posix()
                archive.write(path,name)
                records.append({'path':name,'bytes':path.stat().st_size,'sha256':file_hash(path)})
        for path,name in extra_raw:
            _logical(name); path=_safe_ancestors(path)
            # Hash the exact bytes written, avoiding validation/copy pathname races.
            digest=hashlib.sha256(); size=0
            with path.open('rb') as incoming,archive.open(name,'w',force_zip64=True) as outgoing:
                for chunk in iter(lambda:incoming.read(4*1024**2),b''):
                    outgoing.write(chunk);digest.update(chunk);size+=len(chunk)
            records.append({'path':name,'bytes':size,'sha256':digest.hexdigest()})
        profile='FULL_AUDIT' if extra_raw else 'EDITORIAL_HANDOFF'
        # A profile ledger is inside FULL only; EDITORIAL uses its canonical manifest.
        if extra_raw:
            archive.writestr('FULL_AUDIT_MANIFEST.json',json.dumps({'schema_version':'r6.2','profile':profile,
                'files':records,'source_video_included':False,'preview_approved':False,'publication_ready':False},ensure_ascii=False,indent=2))
    checked=verify_full_audit(staged) if extra_raw else validate_core_package(staged)
    if checked.get('status')!='valid':
        raise ValueError('staged_profile_validation_failed:'+str(checked.get('errors')))
    # Publish only the completed/verified archive; partials stay task-owned.
    import os
    os.link(staged,target)
    staged.unlink()
    return {'path':str(target),'bytes':target.stat().st_size,'sha256':file_hash(target),
            'members':len(records)+(1 if extra_raw else 0),'uncompressed_bytes':sum(r['bytes'] for r in records)}


def build_visual_delivery(package_path,analysis_folder,media_path,output_root,*,camera_timeline_path=None,
                          max_frames=6,global_frames=384,global_frame_bytes=40*1024**2,progress=None):
    """Keep all canonical candidates; add evidence in an exclusive derived revision."""
    from .compact_artifacts import load_analysis_artifacts
    from .visual_frame_handoff import (VisualEvidenceIndex,SparseFrameProvider,
        build_visual_frame_handoff,validate_visual_frame_handoff,plan_frame_times)
    from .subtitle_review import build_story_interval_preflight,build_caption_preflight
    raw,validation=snapshot_core_package(package_path)
    parent_hash=hashlib.sha256(raw).hexdigest()
    base=_safe_ancestors(output_root)
    revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6]
    output=base/('R6_2_DELIVERY_'+revision)
    work=output/'editorial_directory'
    work.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            p=work/str(_logical(name));p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.read(name))
    metadata=_read(work/'source/metadata.json');source_hash=metadata['sha256']
    if file_hash(_safe_ancestors(media_path))!=source_hash:
        raise ValueError('visual_delivery_media_identity_mismatch')
    def emit(stage,current=0,total=1):
        if progress:progress(stage,current,total)
    emit('load_cached_evidence')
    analysis=load_analysis_artifacts(analysis_folder,collections=['people_observations','tracklet_observations',
        'raw_tracks','shots','scenes','camera_director_timeline','words','transcript_segments','participants','person_identities'])
    if (analysis.get('metadata') or {}).get('sha256')!=source_hash:
        raise ValueError('visual_delivery_analysis_identity_mismatch')
    # The package is the canonical transcript revision. Hydration adds visual evidence only.
    analysis['words']=[json.loads(s) for s in (work/'transcript/relevant_words.jsonl').read_text(encoding='utf-8').splitlines() if s]
    analysis['transcript_segments']=[json.loads(s) for s in (work/'transcript/relevant_segments.jsonl').read_text(encoding='utf-8').splitlines() if s]
    analysis['metadata']=metadata
    if camera_timeline_path:
        analysis['camera_director_timeline']=_read(Path(camera_timeline_path))
    analysis['camera_timeline_artifact_ref']='camera/r62_camera_timeline.json'
    original_master=(work/'HANDOFF_MASTER.json').read_bytes()
    parent_ref='provenance/parent_handoff_master_'+hashlib.sha256(original_master).hexdigest()[:16]+'.json'
    (work/parent_ref).parent.mkdir(parents=True,exist_ok=True)
    (work/parent_ref).write_bytes(original_master)
    analysis['person_tracks']=_read(work/'people/person_tracks.json')
    analysis['person_appearances']=_read(work/'people/person_appearances.json')
    pieces=_pieces(work);index=VisualEvidenceIndex(analysis)
    visual_results=[];caption_reviews={}
    canonical_captions_path=work/'subtitles/caption_preflight_r6.json'
    canonical_captions=_read(canonical_captions_path).get('candidates',{}) if canonical_captions_path.exists() else {}
    with SparseFrameProvider(media_path,metadata=metadata,max_frames=global_frames,max_bytes=global_frame_bytes) as provider:
        # Reserve sparse anchors for every independent piece before adaptive extras.
        for number,piece in enumerate(pieces,1):
            emit('reserve_piece_frames',number,len(pieces))
            plan=plan_frame_times(analysis,piece['candidate'],intervals=piece['intervals'],evidence_index=index,max_frames=2)
            for request in plan['requests']:
                provider.get(request['requested_source_time_s'])
        for number,piece in enumerate(pieces,1):
            emit('visual_frame_handoff',number,len(pieces))
            directory=work/'VISUAL_FRAME_HANDOFF'/piece['piece_id']
            result=build_visual_frame_handoff(analysis,piece['candidate'],directory,source_sha256=source_hash,
                package_sha256=parent_hash,revision=revision,intervals=piece['intervals'],
                frame_provider=provider,evidence_index=index,max_frames=max_frames)
            checked=validate_visual_frame_handoff(directory)
            if checked.get('valid') is not True:
                raise ValueError('visual_handoff_validation_failed:'+piece['piece_id']+':'+str(checked))
            result=result if isinstance(result,dict) else {}
            visual_results.append({'piece_id':piece['piece_id'],'piece_type':piece['piece_type'],
                'series_ids':piece['series_ids'],'source_intervals':piece['intervals'],
                'manifest_ref':'VISUAL_FRAME_HANDOFF/'+piece['piece_id']+'/visual_handoff_manifest.json',
                'status':result.get('status',result.get('state','PARTIAL'))})
            if piece['piece_type']=='REEL':
                canonical=canonical_captions.get(piece['piece_id'])
                if canonical:
                    caption_reviews[piece['piece_id']]=canonical
                else:
                    caption=build_caption_preflight(analysis['words'],analysis['transcript_segments'],
                        [{**piece['candidate'],'candidate_id':piece['piece_id']}],duration=metadata['duration'])
                    caption_reviews.update(caption['candidates'])
            else:
                caption=build_story_interval_preflight(analysis['words'],analysis['transcript_segments'],
                    [{'story_id':piece['piece_id'],'source_intervals':piece['intervals']}],duration=metadata['duration'])
                caption_reviews.update(caption.get('stories') or {})
            visual_results[-1]['caption_preflight_ref']='subtitles/visual_piece_caption_preflight.json#/stories/'+piece['piece_id']
    _write(work/'subtitles/visual_piece_caption_preflight.json',{'schema_version':'r6.2','stories':caption_reviews,
        'new_asr_calls':0,'human_approved':False,'publication_ready':False})
    from .paths import SCHEMA_DIR
    schema=SCHEMA_DIR/'visual_frame_handoff.schema.json'
    if schema.is_file():
        (work/'schemas'/schema.name).write_bytes(schema.read_bytes())
    from .camera_handoff import build_camera_handoff
    _write(work/'camera/r62_camera_timeline.json',analysis.get('camera_director_timeline') or [])
    _write(work/'camera/r62_shared_camera_handoff.json',build_camera_handoff(analysis))
    _write(work/'MEDIA_REFERENCE.json',{'schema_version':'r6.2','video_id':(metadata.get('source') or {}).get('id'),
        'source_sha256':source_hash,'duration':metadata['duration'],'source_video_included':False,
        'locator':{'type':'configured_media_library','relative_path':(metadata.get('source') or {}).get('id','source')+'/original'+Path(media_path).suffix},
        'resolution_priority':['explicit_selection','project_reference','media_library','legacy_input','registered_search'],
        'observed_origin':'legacy_input' if 'input' in Path(media_path).parts else 'explicit_selection',
        'download_needed':False,'path_is_reference_not_included_media':True,'publication_ready':False})
    _write(work/'VISUAL_FRAME_HANDOFF/index.json',{'schema_version':'r6.2','revision':revision,'source_sha256':source_hash,
        'parent_package_sha256':parent_hash,'pieces':visual_results,'profile':'EDITORIAL_HANDOFF',
        'camera_timeline_ref':'camera/r62_camera_timeline.json','new_model_calls':0,
        'status':'PARTIAL','human_review_required':True,'preview_approved':False,'publication_ready':False})
    master=_read(work/'HANDOFF_MASTER.json')
    master.update(derivation={'scope':'visual_frame_handoff','parent_master_ref':parent_ref,
        'parent_master_sha256':hashlib.sha256(original_master).hexdigest(),'parent_package_sha256':parent_hash},
        visual_frame_handoff_ref='VISUAL_FRAME_HANDOFF/index.json',video_id=(metadata.get('source') or {}).get('id'),
        analysis_revision=(_read(Path(analysis_folder)/'run_manifest.json')).get('run_id'),package_revision=revision,
        media_reference_ref='MEDIA_REFERENCE.json',active_camera_ref='camera/r62_shared_camera_handoff.json',
        package_profiles=['FULL_AUDIT','EDITORIAL_HANDOFF'],r62_acceptance_state='PARTIAL')
    _write(work/'HANDOFF_MASTER.json',master)
    idx=_read(work/'CURATION_INDEX.json')
    idx.update(delivery_profile='EDITORIAL_HANDOFF',visual_frame_handoff_ref='VISUAL_FRAME_HANDOFF/index.json',
               r62_acceptance_state='PARTIAL',active_camera_ref='camera/r62_shared_camera_handoff.json')
    _write(work/'CURATION_INDEX.json',idx)
    _reindex(work)
    # Raw audit data is copied only into FULL, once per artifact, never once per Reel.
    raw_names=('raw_tracks.json','tracklet_observations.json','people_observations.json','reid_merge_decisions.json',
        'speaker_person_mapping.json','person_motion.json','shots.json','audio_analysis.json','analysis_quality.json',
        'camera_director_timeline.json','run_manifest.json','report_execution_receipt.json')
    extra=[(Path(analysis_folder)/name,'raw_analysis/'+name) for name in raw_names if (Path(analysis_folder)/name).is_file()]
    emit('full_audit_zip')
    full=_zip_directory(work,output/'FULL_AUDIT.zip',extra)
    idx.update(full_audit_ref={'filename':'FULL_AUDIT.zip','sha256':full['sha256'],'bytes':full['bytes']})
    _write(work/'CURATION_INDEX.json',idx)
    master=_read(work/'HANDOFF_MASTER.json');master['full_audit_ref']=idx['full_audit_ref'];_write(work/'HANDOFF_MASTER.json',master)
    _reindex(work)
    emit('editorial_validation')
    validation=validate_core_package(work)
    if validation.get('status')!='valid':
        raise ValueError('editorial_profile_core_validation_failed:'+str(validation.get('errors')))
    uncompressed=sum(p.stat().st_size for p in work.rglob('*') if p.is_file())
    if uncompressed>256*1024**2:
        raise ValueError('editorial_profile_exceeds_existing_256MiB_budget')
    editorial=_zip_directory(work,output/'EDITORIAL_HANDOFF.zip')
    result={'schema_version':'r6.2','revision':revision,'source_sha256':source_hash,'parent_package_sha256':parent_hash,
        'state':'PARTIAL','editorial':editorial,'full_audit':full,'piece_count':len(pieces),
        'reel_count':sum(p['piece_type']=='REEL' for p in pieces),'story_piece_count':sum(p['piece_type']=='STORY' for p in pieces),
        'media_reference':_read(work/'MEDIA_REFERENCE.json'),'new_model_calls':0,
        'full_pipeline_executed':False,'preview_approved':False,'human_approved':False,'publication_ready':False}
    _write(output/'DELIVERY_MANIFEST.json',result)
    emit('complete',len(pieces),len(pieces))
    return result


def verify_full_audit(path):
    errors=[]
    try:
        with zipfile.ZipFile(path) as archive:
            names=archive.namelist()
            if len(names)!=len(set(names)) or len(names)>10000:
                raise ValueError('full_audit_member_budget_or_duplicates')
            for name in names:
                _logical(name)
            manifest=json.loads(archive.read('FULL_AUDIT_MANIFEST.json'))
            if not isinstance(manifest,dict) or manifest.get('schema_version')!='r6.2' or manifest.get('profile')!='FULL_AUDIT':
                raise ValueError('full_audit_unknown_contract')
            if any(manifest.get(flag) is not False for flag in ('source_video_included','preview_approved','publication_ready')):
                raise ValueError('full_audit_unsafe_approval_or_media_flag')
            if not isinstance(manifest.get('files'),list) or not all(isinstance(r,dict) for r in manifest['files']):
                raise ValueError('full_audit_invalid_ledger')
            ledger_names=[r.get('path') for r in manifest['files']]
            if not all(isinstance(n,str) for n in ledger_names) or len(ledger_names)!=len(set(ledger_names)):
                raise ValueError('full_audit_invalid_or_duplicate_ledger_paths')
            for info in archive.infolist():
                if info.flag_bits&1 or ((info.external_attr>>16)&0o170000)==0o120000:
                    raise ValueError('full_audit_encrypted_or_link_member')
            if sum(info.file_size for info in archive.infolist())>2*1024**3:
                raise ValueError('full_audit_uncompressed_budget_exceeded')
            for row in manifest['files']:
                if type(row.get('bytes')) is not int or row['bytes']<0 or not isinstance(row.get('sha256'),str):
                    raise ValueError('full_audit_invalid_ledger_record')
                digest=hashlib.sha256();size=0
                with archive.open(row['path']) as source:
                    for data in iter(lambda:source.read(4*1024**2),b''):
                        digest.update(data);size+=len(data)
                if size!=row['bytes'] or digest.hexdigest()!=row['sha256']:
                    errors.append('full_audit_checksum:'+row['path'])
            if set(names)!={r['path'] for r in manifest['files']}|{'FULL_AUDIT_MANIFEST.json'}:
                errors.append('full_audit_file_set')
        return {'status':'valid' if not errors else 'failed','errors':errors,'publication_ready':False}
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as exc:
        return {'status':'failed','errors':[type(exc).__name__+':'+str(exc)],'publication_ready':False}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Visual Frame Handoff seletivo, sem executar modelos.')
    parser.add_argument('--package',required=True);parser.add_argument('--analysis',required=True)
    parser.add_argument('--media',required=True);parser.add_argument('--destination',required=True)
    parser.add_argument('--camera-timeline');parser.add_argument('--max-frames',type=int,default=6)
    args=parser.parse_args(argv)
    result=build_visual_delivery(args.package,args.analysis,args.media,args.destination,
        camera_timeline_path=args.camera_timeline,max_frames=args.max_frames,
        progress=lambda s,c,t:print('%s %d/%d'%(s,c,t),flush=True))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
