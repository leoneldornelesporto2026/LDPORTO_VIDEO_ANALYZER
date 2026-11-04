"""R6.3 evidence-only post-processing of persisted analysis and editorial contracts.

The compact format is for a human/ChatGPT second curation. It is deliberately
distinct from executable Curator deliveries and preserves the source revisions.
"""
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid
import zipfile

from .core import file_hash,digest
from .export_privacy import sanitize_export
from .paths import PROJECT_ROOT,videos_directory
from .project_export import _safe_ancestors,_logical


def _write(root,name,value):
    path=root/str(_logical(name));path.parent.mkdir(parents=True,exist_ok=True)
    def portable(item):
        references={'transcript/relevant_words.jsonl':'02_TRANSCRIPT/words_timestamps.json',
            'transcript/relevant_segments.jsonl':'02_TRANSCRIPT/transcript_segments.json',
            'subtitles/caption_preflight_r6.json':'02_TRANSCRIPT/caption_quality.json',
            'editorial/human_review_queue.json':'08_REPORTS/HUMAN_REVIEW_QUEUE.json',
            'editorial/story_units.json':'05_STORIES/series_index.json#/parts',
            'editorial/story_sequence_candidates.json':'05_STORIES/series_index.json#/series',
            'editorial/narrative_graph.json':'05_STORIES/narrative_graph.json'}
        if isinstance(item,dict):return {('confidence_label' if k=='confidence' and isinstance(v,str) else k):
            (references.get(v,v) if k.endswith('_ref') and isinstance(v,str) else portable(v)) for k,v in item.items()}
        if isinstance(item,list):return [portable(x) for x in item]
        return item
    path.write_text(json.dumps(sanitize_export(portable(value)),ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')


def _read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


class PersistedArtifacts:
    """Read each requested artifact once, checking its existing exact-byte ledger."""
    def __init__(self,folder):
        self.root=_safe_ancestors(folder);self.manifest=_read(self.root/'manifest.json');self.receipts={}
        self.source_sha256=self.manifest['video_sha256'];self.hashes=self.manifest.get('artifact_checksums',{})

    def read(self,name,default=None):
        path=_safe_ancestors(self.root/str(_logical(name)))
        if not path.is_file():
            if default is not None:return default
            raise ValueError('required_persisted_artifact_missing:'+name)
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if self.hashes.get(name)!=sha:
            raise ValueError('persisted_artifact_checksum_mismatch:'+name)
        self.receipts[name]={'path':name,'bytes':len(raw),'sha256':sha}
        return json.loads(raw)


def _overlap(a,b):
    return a['start']<b['end'] and b['start']<a['end']


def _intervals(values):
    output=[];cursor=0.
    for row in values:
        a,b=row['start'],row['end']
        if not 0<=a<b or output and a<output[-1]['end']:
            raise ValueError('invalid_or_overlapping_piece_intervals')
        output.append({**row,'clip_start':cursor,'clip_end':cursor+b-a});cursor+=b-a
    return output


def _gaps(intervals,duration):
    merged=[]
    for a,b in sorted((max(0.,i['start']),min(duration,i['end'])) for i in intervals if i['start']<i['end']):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    cursor=0.;gaps=[]
    for a,b in merged:
        if a>cursor:gaps.append({'start':cursor,'end':a})
        cursor=max(cursor,b)
    if cursor<duration:gaps.append({'start':cursor,'end':duration})
    return gaps,sum(b-a for a,b in merged)


def _discover_package(source_sha256):
    choices=[]
    for path in (PROJECT_ROOT/'pacotes_para_enviar').glob('SECOND_CURATION*.zip'):
        try:
            with zipfile.ZipFile(path) as archive:metadata=json.loads(archive.read('source/metadata.json'))
            if metadata.get('sha256')==source_sha256:choices.append(path)
        except (OSError,ValueError,KeyError,zipfile.BadZipFile):continue
    if not choices:raise ValueError('no_package_with_matching_metadata_identity_use_package_option')
    return max(choices,key=lambda p:(p.stat().st_mtime_ns,p.name))


def _camera_rows(timeline):
    from .camera_handoff import build_camera_handoff
    # Keep observations separate: this projection contains recommendations only.
    decisions=[]
    for index,row in enumerate(timeline):
        crop=row.get('crop') or {};camera=row.get('camera') or {}
        safe=crop.get('safe') is True
        mode='FOCUS_PERSON_9X16' if safe and row.get('layout')=='single_person' else 'SOURCE_FIT_BLUR'
        decisions.append({'decision_id':row.get('director_id') or 'DECISION_%06d'%index,
            'start':row['start'],'end':row['end'],'source_shot_id':row.get('source_shot_id'),
            'mode':mode,'source_camera_mode':row.get('camera_mode'),'layout':row.get('layout'),
            'target_person_ids':[row['focus_person']] if row.get('focus_person') else [],
            'crop':{k:v for k,v in crop.items() if k in ('safe','rect_start','rect_end','reason','protected_bbox','safety_margin','preflight_sample_count')},
            'camera':{k:v for k,v in camera.items() if k in ('keyframes','start_center','end_center','start_zoom','end_zoom','easing','motion_limits')},
            'reason_codes':(row.get('decision') or {}).get('reasons') or [],
            'fallback':'SOURCE_FIT_BLUR','terminal_fallback':'SOURCE_PRESERVE',
            'evidence':{'visual_observed_at_start':row.get('visual_observed_at_start'),
                'visual_observed_at_end':row.get('visual_observed_at_end'),'geometry_is_sampled':True,
                'hands_instrument_preservation':'UNKNOWN','speaker_identity_confirmed':row.get('speaker_identity_confirmed') is True},
            'execution_status':'SUGGESTION_UNVERIFIED','preview_approved':False,'publication_ready':False})
    return decisions


def _write_geometry_shards(work,geometry,maximum_bytes=1024**2,maximum_trajectories=250):
    """One copy of each trajectory; small global ID lookup plus bounded shards."""
    shards=[];lookup={};batch=[]
    envelope_bytes=len(json.dumps({'schema_version':'r6.3','trajectories':[]},separators=(',',':')).encode('utf-8'))
    size=envelope_bytes
    def flush():
        nonlocal batch,size
        if not batch:return
        path='03_PEOPLE/trajectories/TRAJECTORIES_%05d.json'%len(shards)
        _write(work,path,{'schema_version':'r6.3','trajectories':batch})
        ids=[t['trajectory_id'] for t in batch]
        shards.append({'path':path,'sha256':file_hash(work/path),'bytes':(work/path).stat().st_size,'trajectory_ids':ids})
        for ident in ids:lookup[ident]=path
        batch=[];size=envelope_bytes
    for trajectory in geometry['trajectories']:
        encoded=len(json.dumps(trajectory,ensure_ascii=False,separators=(',',':')).encode('utf-8'))
        if batch and (size+encoded+1>maximum_bytes or len(batch)>=maximum_trajectories):flush()
        size+=encoded+(1 if batch else 0);batch.append(trajectory)
    flush()
    _write(work,'03_PEOPLE/visual_trajectories.json',{k:v for k,v in geometry.items() if k!='trajectories'}|{
        'storage':'indexed_shards','shards':shards,'trajectory_index':lookup,
        'lookup_instructions':'Use candidate camera_geometry.trajectory_shard_refs, then resolve trajectory_ids in those shards.',
        'shard_budget':{'max_bytes':maximum_bytes,'max_trajectories':maximum_trajectories,
            'single_trajectory_is_never_split_or_silently_dropped':True}})
    return lookup


def _copy_atlas(cache,work,source_hash,*,metadata=None,scenes=None,analysis_folder=None):
    if metadata is not None and scenes is not None:
        from .compact_frames import reprofile_shared_atlas
        return reprofile_shared_atlas(cache,work,metadata,scenes,analysis_folder=analysis_folder)
    cache=_safe_ancestors(cache);index=_read(cache/'06_VISUAL_ATLAS/atlas_index.json')
    if index.get('source_sha256')!=source_hash:raise ValueError('compact_atlas_source_identity_mismatch')
    copied=set()
    for row in index['frames']+index['contact_sheets']:
        name=str(_logical(row['path']));source=_safe_ancestors(cache/name)
        if not source.is_relative_to(cache) or file_hash(source)!=row['sha256']:
            raise ValueError('compact_atlas_asset_checksum_mismatch:'+name)
        if name not in copied:
            target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);copied.add(name)
    _write(work,'06_VISUAL_ATLAS/atlas_index.json',index)
    return index


def _finish_archive(work,output,manifest):
    rows=[{'path':p.relative_to(work).as_posix(),'bytes':p.stat().st_size,'sha256':file_hash(p),
        'category':p.relative_to(work).parts[0]} for p in sorted(work.rglob('*')) if p.is_file()]
    categories={}
    for row in rows:
        category=categories.setdefault(row['category'],{'files':0,'uncompressed_bytes':0})
        category['files']+=1;category['uncompressed_bytes']+=row['bytes']
    _write(work,'FILE_INDEX.json',{'schema_version':'r6.3','files':rows,'categories':categories,
        'index_scope':'all_payload_files_excluding_MANIFEST_FILE_INDEX_and_checksums'})
    manifest.update(file_index_ref='FILE_INDEX.json',file_index_sha256=file_hash(work/'FILE_INDEX.json'),checksums_ref='checksums.sha256')
    _write(work,'MANIFEST.json',manifest)
    checks=[file_hash(p)+'  '+p.relative_to(work).as_posix() for p in sorted(work.rglob('*')) if p.is_file()]
    (work/'checksums.sha256').write_text('\n'.join(checks)+'\n',encoding='utf-8')
    target=output/'SECOND_CURATION_READY_R6_3.zip';partial=output/('.'+target.name+'.'+uuid.uuid4().hex+'.partial')
    with zipfile.ZipFile(partial,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(work.rglob('*')):
            if path.is_file():archive.write(_safe_ancestors(path),path.relative_to(work).as_posix())
    from .compact_handoff_reader import inspect_compact_handoff
    result=inspect_compact_handoff(partial)
    if result.get('status')!='valid':raise ValueError('compact_zip_reopen_failed:'+str(result.get('errors')))
    os.link(partial,target);partial.unlink()
    with zipfile.ZipFile(target) as archive:
        for category in categories:
            categories[category]['compressed_bytes']=sum(i.compress_size for i in archive.infolist() if i.filename.startswith(category+'/'))
    return {'path':str(target),'sha256':file_hash(target),'bytes':target.stat().st_size,'mib':target.stat().st_size/1024**2,
        'categories':categories,'independent_zip_validation':{k:v for k,v in result.items() if k!='reconstructed'}}


def build_compact_handoff(analysis_folder,package_path=None,*,media_path=None,destination=None,
                          atlas_cache=None,max_error_px=2.,max_gap_s=1.,progress=None):
    """Export all source scenes/candidates and the full persisted transcript without models."""
    from .second_curation_export import snapshot_core_package
    from .compact_geometry import simplify_visual_trajectories
    from .compact_frames import build_shared_visual_atlas
    from .compact_atlas import build_compact_atlas
    from .subtitle_review import build_story_interval_preflight
    import io
    source=PersistedArtifacts(analysis_folder)
    summary=source.read('analysis_summary.json');metadata=summary['metadata']
    if metadata.get('sha256')!=source.source_sha256:raise ValueError('analysis_metadata_identity_disagreement')
    selected=_safe_ancestors(package_path or _discover_package(source.source_sha256))
    def emit(stage,current=0,total=1):
        if progress:progress(stage,current,total)
    emit('validate_parent_package')
    package_bytes,parent_validation=snapshot_core_package(selected);package_hash=hashlib.sha256(package_bytes).hexdigest()
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as package:
        def read(name,default=None):
            return json.loads(package.read(name)) if name in package.namelist() else default
        parent_metadata=read('source/metadata.json')
        if (parent_metadata.get('sha256')!=source.source_sha256 or parent_metadata['duration']!=metadata['duration']
                or any(parent_metadata.get(k)!=metadata.get(k) for k in ('width','height'))
                or (parent_metadata.get('rotation') or 0)!=(metadata.get('rotation') or 0)
                or (parent_metadata.get('fps') is not None and metadata.get('fps') is not None
                    and abs(parent_metadata['fps']-metadata['fps'])>max(.001,abs(metadata['fps'])*1e-6))):
            raise ValueError('compact_package_analysis_identity_mismatch')
        candidates=read('editorial/candidate_catalog.json')['candidates']
        units=read('editorial/story_units.json',{}).get('units',[])
        sequences=read('editorial/story_sequence_candidates.json',{}).get('sequences',[])
        standalone=read('social/stories_manifest.json',{}).get('stories',[])
        words=source.read('words.json');segments=source.read('transcript_segments.json')
        for filename,full,key,text in (('transcript/relevant_words.jsonl',words,'word_id','word'),
                                      ('transcript/relevant_segments.jsonl',segments,'segment_id','text')):
            by_id={r[key]:r for r in full}
            for row in [json.loads(line) for line in package.read(filename).decode('utf-8').splitlines() if line]:
                if row[key] not in by_id or any(row.get(k)!=by_id[row[key]].get(k) for k in ('start','end',text)):
                    raise ValueError('canonical_transcript_revision_conflict:'+row[key])
        scenes_raw=source.read('scenes.json');shots=source.read('shots.json')
        appearances=read('people/person_appearances.json',[])
        identities=read('people/person_identities.json',[])
        instruments=read('people/instrument_observations.json',[])
        mappings=read('people/speaker_person_mapping.json',[])
        captions=read('subtitles/caption_preflight_r6.json',{})
        narrative=read('editorial/narrative_graph.json',{})
        audio=read('audio/sound_events.json',{'events':[]})
        chapters=read('editorial/program_sections.json',[])
        timeline=read('camera/camera_director_timeline.json',[])
        quality=read('summary/quality_summary.json',{})
        original_shortlist=read('editorial/default_shortlist.json',{})
    duration=metadata['duration'];revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6]
    base=_safe_ancestors(destination or videos_directory()/'LDPORTO_VIDEO_ANALYZER')
    output=base/('COMPACT_HANDOFF_R6_3_'+revision);work=output/'editorial_directory';work.mkdir(parents=True,exist_ok=False)
    source_info={**parent_metadata,'title':(parent_metadata.get('source') or {}).get('title'),
        'video_id':(parent_metadata.get('source') or {}).get('id'),
        'identity_status':'SOURCE_HASH_VERIFIED_METADATA_NAMES_UNAVAILABLE' if not (parent_metadata.get('source') or {}).get('id') else 'PACKAGE_METADATA',
        'identity_provenance':{'parent_package_sha256':package_hash,'analysis_metadata_sha256':metadata['sha256'],
            'filename_or_hash_prefix_used_as_identity':False}}
    _write(work,'00_OVERVIEW/video_summary.json',{'source':source_info,'analysis_status':summary.get('analysis_status'),
        'parent_package':{'filename':selected.name,'sha256':package_hash,'bytes':len(package_bytes)},
        'analysis_revision':source.manifest.get('run_id'),'package_revision':revision,'original_shortlist':original_shortlist,
        'new_model_calls':0,'full_pipeline_executed':False,'final_second_curation_performed':False})
    pieces=[]
    for row in candidates:
        pieces.append({'piece_id':row['candidate_id'],'kind':'REEL','original':row,
            'source_intervals':_intervals([{'start':row['start'],'end':row['end']}]),'series_ids':[]})
    for row in units:
        pieces.append({'piece_id':row['unit_id'],'kind':'STORY','original':row,'source_unit_id':row['unit_id'],
            'source_intervals':_intervals(row['source_intervals']),
            'series_ids':[s['sequence_id'] for s in sequences if row['unit_id'] in s.get('unit_ids',[])]})
    for row in standalone:
        pieces.append({'piece_id':row['story_id'],'kind':'STORY','original':row,'source_unit_id':None,
            'source_intervals':_intervals(row.get('source_intervals') or [{'start':row['start'],'end':row['end']}]),'series_ids':[]})
    if len({p['piece_id'] for p in pieces})!=len(pieces):raise ValueError('duplicate_compact_piece_id')
    for piece in pieces:
        if len(_logical(piece['piece_id']).parts)!=1:raise ValueError('unsafe_piece_identifier')
    emit('simplify_geometry')
    geometry=simplify_visual_trajectories(appearances,shots,source_width=metadata['width'],source_height=metadata['height'],
        max_error_px=max_error_px,max_gap_s=max_gap_s)
    trajectory_lookup=_write_geometry_shards(work,geometry)
    emit('shared_visual_atlas')
    atlas=_copy_atlas(atlas_cache,work,source.source_sha256,metadata=metadata,scenes=scenes_raw,analysis_folder=source.root) if atlas_cache else build_shared_visual_atlas(
        source.root,metadata,scenes_raw,pieces,work,media_path=media_path,progress=progress)
    frames=atlas['frames'];frame_by_scene=defaultdict(list)
    for frame in frames:
        if frame.get('scene_id'):frame_by_scene[frame['scene_id']].append(frame['frame_id'])
    trajectories=geometry['trajectories'];by_shot=defaultdict(list)
    for trajectory in trajectories:by_shot[trajectory.get('source_shot_id')].append(trajectory)
    decisions=_camera_rows(timeline);decisions_by_shot=defaultdict(list)
    for row in decisions:decisions_by_shot[row['source_shot_id']].append(row)
    scenes=[];shot_by_scene=defaultdict(list)
    for shot in shots:shot_by_scene[shot.get('scene_id')].append(shot)
    transcript_gaps,transcript_seconds=_gaps(segments,duration)
    word_gaps,word_seconds=_gaps(words,duration)
    for scene in scenes_raw:
        scene_shots=shot_by_scene[scene['scene_id']];ts=[t for shot in scene_shots for t in by_shot[shot['shot_id']]]
        people=sorted({t['person_id'] for t in ts if t.get('person_id')})
        related=[p['piece_id'] for p in pieces if p['kind']=='REEL' and any(_overlap(scene,i) for i in p['source_intervals'])]
        related_stories=[p['piece_id'] for p in pieces if p['kind']=='STORY' and any(_overlap(scene,i) for i in p['source_intervals'])]
        scene_decisions=[d for shot in scene_shots for d in decisions_by_shot[shot['shot_id']]]
        scenes.append({'scene_id':scene['scene_id'],'start':scene['start'],'end':scene['end'],'duration':scene['end']-scene['start'],
            'shot_ids':[s['shot_id'] for s in scene_shots],
            'shot_type':scene.get('scene_type') or 'UNKNOWN','shot_type_evidence_state':'INFERRED' if scene.get('shot_type_inference') else 'UNKNOWN',
            'person_ids':people,'source_reported_people_ids':scene.get('visible_people') or [],
            'instrument_ids':[],'frame_ids':frame_by_scene[scene['scene_id']],'candidate_ids':related,'story_ids':related_stories,
            'trajectory_ids':[t['trajectory_id'] for t in ts],'decision_ids':[d['decision_id'] for d in scene_decisions],
            'geometry_state':'OBSERVED_SPARSE' if ts else 'UNKNOWN','continuous_tracking_verified':False,
            'visual_quality':{k:scene_shots[0].get(k) if scene_shots else None for k in ('sharpness_score','motion_blur_score','headroom_score')},
            'transcript_gap_intervals':[{'start':max(scene['start'],g['start']),'end':min(scene['end'],g['end'])} for g in transcript_gaps if _overlap(scene,g)],
            'missing_evidence':['hands_instrument_geometry_unavailable','continuous_visibility_unverified']+([] if frame_by_scene[scene['scene_id']] else ['source_frame_missing'])})
    scene_starts=[s['start'] for s in scenes]
    regions=[{'region_id':'PROTECTED_'+t['trajectory_id'],'trajectory_id':t['trajectory_id'],
        'kind':'FACE' if t['class']=='face' else 'BODY','evidence_state':'OBSERVED','validity':'sampled_keyframe_times_only',
        'start':t['start'],'end':t['end'],'protection':'avoid_clipping_observed_region',
        'geometry_ref':'03_PEOPLE/visual_trajectories.json','source_shot_id':t['source_shot_id']} for t in trajectories]
    _write(work,'07_CAMERA/safe_areas.json',{'regions':regions,'unobserved_regions':[
        {'kind':kind,'evidence_state':'UNKNOWN','recommendation':'SOURCE_FIT_BLUR_UNTIL_SOURCE_INSPECTION'}
        for kind in ('HEAD_FULL_EXTENT','HANDS','INSTRUMENTS','MICROPHONE','SOURCE_TEXT','SCREENS')],
        'overlay_positions':{'state':'UNKNOWN','platform_margins_are_guidelines_not_spatial_evidence':True},
        'crop_transform_ref':'07_CAMERA/camera_contract.json','safe_area_approved':False})
    _write(work,'07_CAMERA/camera_contract.json',{'schema_version':'r6.3','coordinate_contract':geometry['coordinate_contract'],
        'source_width':metadata['width'],'source_height':metadata['height'],'target_width':1080,'target_height':1920,
        'crop_transform':{'source_normalized_to_pixel':'[x*source_width,y*source_height]',
            'source_to_crop':'[(x-crop.x)/crop.width,(y-crop.y)/crop.height]',
            'source_fit_blur':'foreground contain with original aspect ratio; centered padding belongs to background',
            'crop_rect_basis':'normalized original source; camera keyframe timestamps absolute source seconds'},
        'interval_convention':'[start,end); trajectory start/end are sampled extents, not continuous visibility',
        'modes':['FOCUS_PERSON_9X16','MEDIUM_SHOT','INSTRUMENT_FOCUS','DUO_STAGE','SOURCE_FIT_BLUR','SOURCE_PRESERVE'],
        'mode_availability':'instrument/duo proposals require measured geometry and a new Curator render',
        'curator_executable_package':False,'next_contract':'LDPORTO_CURATOR_READY_V1_AFTER_HUMAN_SECOND_CURATION'})
    _write(work,'07_CAMERA/camera_decisions.json',{'decisions':decisions,'producer':'existing_camera_director_projection',
        'observed_geometry_ref':'03_PEOPLE/visual_trajectories.json','observations_preserved_independently_of_decision':True})
    _write(work,'02_TRANSCRIPT/transcript_segments.json',{'segments':segments,'source_sha256':source.source_sha256,
        'canonical_records_sha256':digest(segments),'canonical_source_artifact':source.receipts['transcript_segments.json']})
    _write(work,'02_TRANSCRIPT/words_timestamps.json',{'words':words,'source_sha256':source.source_sha256,
        'canonical_records_sha256':digest(words),'canonical_source_artifact':source.receipts['words.json'],
        'word_timing_reliability':'inspect alignment_verified/timestamp_method per word; no artificial timing'})
    _write(work,'02_TRANSCRIPT/audio_events.json',{**audio,'audio_categories_not_inferred_from_missing_words':True})
    _write(work,'02_TRANSCRIPT/caption_quality.json',captions)
    _write(work,'03_PEOPLE/people_index.json',{'people':identities,'nominal_identity_inferred_from_show_title':False,
        'instrument_geometry_state':'OBSERVED' if instruments else 'UNKNOWN','fragmentation_statistics':geometry['statistics']})
    _write(work,'03_PEOPLE/speaker_mapping.json',{'mappings':mappings,'active_speaker_required_for_geometric_camera':False})
    _write(work,'03_PEOPLE/instruments.json',{'observations':instruments,'evidence_state':'OBSERVED' if instruments else 'UNKNOWN',
        'absence_of_observations_does_not_prove_absence_of_instruments':True})
    _write(work,'01_TIMELINE/scene_index.json',{'scenes':scenes,'source_sha256':source.source_sha256})
    _write(work,'01_TIMELINE/shot_transitions.json',{'shots':shots,'interpolation_across_source_cuts_allowed':False})
    _write(work,'01_TIMELINE/complete_timeline.json',{'duration':duration,'scenes':[{'scene_id':s['scene_id'],'start':s['start'],'end':s['end']} for s in scenes],
        'chapters':chapters,'scene_index_ref':'01_TIMELINE/scene_index.json','audio_events_ref':'02_TRANSCRIPT/audio_events.json'})
    _write(work,'01_TIMELINE/source_to_clip_map.json',{'pieces':[{'piece_id':p['piece_id'],'intervals':p['source_intervals']} for p in pieces]})
    scene_gaps,_=_gaps(scenes,duration)
    _write(work,'01_TIMELINE/uncovered_intervals.json',{'scene_index_gaps':scene_gaps,'transcript_gaps':transcript_gaps,
        'word_timestamp_gaps':word_gaps,'tracking_gaps':geometry.get('gaps',[]),
        'visual_sampling_scope':'discrete timestamps; no continuous image coverage is claimed'})
    reel_rows=[];story_rows=[];reels_with_observed_geometry=0;reels_with_crop_suggestions=0
    for number,piece in enumerate(pieces,1):
        emit('piece_indices',number,len(pieces));ident=piece['piece_id'];intervals=piece['source_intervals'];original=piece['original']
        related_scenes=[s for s in scenes if any(_overlap(s,i) for i in intervals)]
        relevant_trajectories=[t for s in related_scenes for sid in s['shot_ids'] for t in by_shot[sid]
            if any(t['start']<i['end'] and i['start']<=t['end'] for i in intervals)]
        trajectory_ids=sorted({t['trajectory_id'] for t in relevant_trajectories})
        observed_people=sorted({t['person_id'] for t in relevant_trajectories if t.get('person_id') and any(
            i['start']<=k['source_time_s']<i['end'] for k in t['keyframes'] for i in intervals)})
        decision_ids=sorted({d['decision_id'] for s in related_scenes for sid in s['shot_ids'] for d in decisions_by_shot[sid]
            if any(_overlap(d,i) for i in intervals)})
        if piece['kind']=='REEL':
            reels_with_observed_geometry+=bool(trajectory_ids)
            reels_with_crop_suggestions+=any(d['mode']=='FOCUS_PERSON_9X16' and any(_overlap(d,i) for i in intervals) for d in decisions)
        selected_frames=[f for f in frames if any(i['start']<=f['source_time_s']<i['end'] for i in intervals)]
        associated_segments=[s for s in segments if any(_overlap(s,i) for i in intervals)]
        associated_words=[w for w in words if any(_overlap(w,i) for i in intervals)]
        directory=('04_REELS/' if piece['kind']=='REEL' else '05_STORIES/')+ident
        row={'candidate_id':ident} if piece['kind']=='REEL' else {'story_id':ident,'source_unit_id':piece['source_unit_id'],'series_ids':piece['series_ids']}
        row.update(rank_original=original.get('rank',original.get('original_rank')),
            source_intervals=intervals,scene_ids=[s['scene_id'] for s in related_scenes],frame_ids=[f['frame_id'] for f in selected_frames],
            transcript_segment_ids=[s['segment_id'] for s in associated_segments],word_ids=[w['word_id'] for w in associated_words],
            person_ids=observed_people,person_presence_scope='observed_keyframe_inside_piece_source_intervals',
            instrument_ids=[],review_state='NEEDS_SOURCE_INSPECTION')
        for field,filename in (('editorial','editorial.json'),('source_intervals','source_intervals.json'),
                ('visual_storyboard','visual_storyboard.json'),('camera_geometry','camera_geometry.json'),
                ('caption_evidence','caption_evidence.json'),('thumbnail_candidates','thumbnail_candidates.json')):
            row[field+'_ref']=directory+'/'+filename
        titles=original.get('title_suggestions') or original.get('title_alternatives') or []
        _write(work,row['editorial_ref'],{'piece_id':ident,'piece_type':piece['kind'],'source_unit_id':piece.get('source_unit_id'),
            'summary':original.get('summary') or original.get('topic_summary'),'summary_evidence_state':'ORIGINAL_ANALYSIS_HYPOTHESIS_REQUIRES_TRANSCRIPT_REVIEW',
            'title_proposals':titles,'original_title':original.get('title'),'original_hook':original.get('hook'),
            'original_scores':{k:v for k,v in original.items() if 'score' in k or k.endswith('_quality') or k in ('rank','original_rank','criteria','quality')},
            'original_editorial_metadata':{k:original.get(k) for k in ('content_type','categories','editorial_format',
                'hook_type','hook_strength','context_dependency','context_requirement','context_reason','context_required',
                'default_shortlist_eligible','publication_eligible','candidate_state','candidate_state_reason',
                'visual_viability','camera_feasibility','audio_quality','quality_issues','uncertainty',
                'commercial_evidence_state','commercial_review_state','narrative_evaluation','review_state',
                'review_milestones','duration_contract','duration_exception','duration_exception_reason','missing_field_reasons') if k in original},
            'original_blockers':original.get('blockers') or original.get('editorial_blockers') or [],
            'narrative_role':original.get('narrative_role'),'narrative_state':'PARTIAL_STORY' if piece['series_ids'] else 'INDEPENDENT_MOMENT',
            'context_segment_ids': [s['segment_id'] for s in segments if intervals[0]['start']-15<=s['end']<=intervals[0]['start'] or intervals[-1]['end']<=s['start']<=intervals[-1]['end']+15],
            'transcript_ref':'02_TRANSCRIPT/transcript_segments.json','transcript_segment_ids':row['transcript_segment_ids'],
            'human_review_required':True,'human_approved':False,'publication_ready':False})
        _write(work,row['source_intervals_ref'],{'piece_id':ident,'intervals':intervals,'source_sha256':source.source_sha256})
        _write(work,row['camera_geometry_ref'],{'piece_id':ident,'scene_ids':row['scene_ids'],'trajectory_ids':trajectory_ids,
            'trajectory_shard_refs':sorted({trajectory_lookup[t] for t in trajectory_ids}),
            'decision_ids':decision_ids,'safe_area_ids':['PROTECTED_'+t for t in trajectory_ids],
            'coordinate_contract_ref':'07_CAMERA/camera_contract.json','geometry_scope':'source-shot observations; filter by piece intervals before use',
            'sufficiency':'NEEDS_SOURCE_INSPECTION','hands_and_instruments':'UNKNOWN','final_render_verified':False})
        beats=[]
        for beat_number,interval in enumerate(intervals):
            beats.append({'beat_id':ident+'_BEAT_%03d'%beat_number,'start':interval['start'],'end':interval['end'],
                'clip_start':interval['clip_start'],'clip_end':interval['clip_end'],
                'scene_ids':[s['scene_id'] for s in related_scenes if _overlap(s,interval)],
                'frame_ids':[f['frame_id'] for f in selected_frames if interval['start']<=f['source_time_s']<interval['end']],
                'segment_ids':[s['segment_id'] for s in associated_segments if _overlap(s,interval)],
                'word_ids':[w['word_id'] for w in associated_words if _overlap(w,interval)],
                'action_evidence_state':'UNKNOWN','action_description':None,'emotion_hypothesis':None,
                'narrative_function':original.get('narrative_role'),'overlay_placement':'UNKNOWN_REQUIRES_SOURCE_INSPECTION'})
        _write(work,row['visual_storyboard_ref'],{'piece_id':ident,'beats':beats,'geometry_ref':row['camera_geometry_ref'],
            'continuous_action_not_inferred_from_still_frames':True})
        if piece['kind']=='REEL':review=(captions.get('candidates') or {}).get(ident,{})
        else:review=build_story_interval_preflight(words,segments,[{'story_id':ident,'source_intervals':intervals}],duration=duration)['stories'][ident]
        _write(work,row['caption_evidence_ref'],{'piece_id':ident,**review,'canonical_segment_ids':row['transcript_segment_ids'],
            'canonical_word_ids':row['word_ids'],'new_asr_calls':0,'human_approved':False,'publication_ready':False})
        _write(work,row['thumbnail_candidates_ref'],{'piece_id':ident,'frame_ids':row['frame_ids'],
            'selection_status':'UNRANKED_SOURCE_REFERENCES','legibility_requires_human_review':True,'viral_title_promised':False})
        if piece['kind']=='STORY':
            row['continuity_ref']=directory+'/continuity.json'
            _write(work,row['continuity_ref'],{'story_id':ident,'series_ids':piece['series_ids'],
                'status':'CONTINUITY_UNVERIFIED' if piece['series_ids'] else 'INDEPENDENT_MOMENT',
                'source_presentation_order_is_not_proof_of_narrative_continuity':True,'completed_ending_invented':False,
                'source_unit_id':piece.get('source_unit_id'),'previous_next_proposals_ref':'05_STORIES/series_index.json'})
        (reel_rows if piece['kind']=='REEL' else story_rows).append(row)
    series=[{'series_id':s['sequence_id'],'title':s.get('title'),'part_ids':s.get('unit_ids',[]),
        'continuity_status':'CONTINUITY_UNVERIFIED','narrative_state':'PARTIAL_STORY',
        'original_completeness':s.get('completeness'),'original_narrative_support':s.get('narrative_support'),
        'missing_components':s.get('missing_components',[]),'blockers':s.get('blockers',[]),
        'ordering_scope':s.get('ordering_scope'),'assembly_disclosure_required':s.get('assembly_disclosure_required',True),
        'complete_supported':s.get('complete_supported') is True,'human_approved':False,'publication_ready':False} for s in sequences]
    _write(work,'04_REELS/reels_index.json',{'reels':reel_rows,'original_ranking_preserved':True})
    _write(work,'05_STORIES/series_index.json',{'series':series,'parts':story_rows,
        'provisional_unit_count':len(units),'standalone_story_count':len(standalone),'parts_are_not_final_story_renders':True})
    _write(work,'05_STORIES/narrative_graph.json',{**narrative,'continuity_requires_evidence':True})
    sampled_scene_seconds=sum(s['duration'] for s in scenes if s['frame_ids'])
    coverage={'scene_count':len(scenes),'shot_count':len(shots),'reel_count':len(reel_rows),'story_part_count':len(story_rows),
        'series_count':len(series),'frame_count':len(frames),'unique_image_count':atlas['statistics']['unique_image_files'],
        'contact_sheet_count':len(atlas['contact_sheets']),'trajectory_count':len(trajectories),
        'segment_count':len(segments),'word_count':len(words),'scenes_with_thumbnails':sum(bool(s['frame_ids']) for s in scenes),
        'scenes_with_tracking':sum(bool(s['trajectory_ids']) for s in scenes),
        'scenes_with_camera_decisions':sum(bool(s['decision_ids']) for s in scenes),
        'scenes_with_camera_geometry':sum(any(d['crop'].get('safe') is True and d['crop'].get('rect_end')
            for sid in s['shot_ids'] for d in decisions_by_shot[sid]) for s in scenes),
        'scenes_with_people':sum(bool(s['person_ids']) for s in scenes),'scenes_with_proven_instruments':0,
        'reels_with_transcript':sum(bool(r['transcript_segment_ids']) for r in reel_rows),
        'reels_with_observed_geometry':reels_with_observed_geometry,
        'reels_with_geometric_crop_suggestions':reels_with_crop_suggestions,
        'reels_with_geometry_sufficient_for_automatic_execution':0,
        'reels_with_verified_title_caption_safe_zones':0,
        'reels_with_reliable_alignment':sum((captions.get('candidates') or {}).get(r['candidate_id'],{}).get('status')=='CAPTION_READY' for r in reel_rows),
        'stories_with_proven_continuity':sum(s['complete_supported'] for s in series),
        'caption_candidate_status_counts':dict(Counter(r.get('status','UNKNOWN') for r in captions.get('candidates',{}).values())),
        'transcript_seconds':transcript_seconds,'transcript_coverage_ratio':transcript_seconds/duration,
        'word_evidence_seconds':word_seconds,'word_evidence_coverage_ratio':word_seconds/duration,
        'scene_intervals_represented_by_stills_seconds':sampled_scene_seconds,'scene_interval_representation_ratio':sampled_scene_seconds/duration,
        'continuous_visual_coverage_seconds':None,'continuous_visual_coverage_verified':False,
        'visual_timestamp_count':len({round(f['source_time_s'],6) for f in frames}),
        'scenes_without_images':[s['scene_id'] for s in scenes if not s['frame_ids']],
        'candidates_requiring_visual_review':[r['candidate_id'] for r in reel_rows],
        'pieces_without_frames':[p.get('candidate_id',p.get('story_id')) for p in reel_rows+story_rows if not p['frame_ids']],
        'additional_source_inspection_required':'hands/instrument extents, active performer roles and safe text placement',
        'geometry':geometry['statistics'],'image_deduplication':atlas['statistics'],'sufficiency':'PARTIAL_VISUAL_EVIDENCE',
        'state':'PARTIAL','preview_approved':False,'human_approved':False,'publication_ready':False}
    limitations={'state':'PARTIAL','sufficiency':'PARTIAL_VISUAL_EVIDENCE','source_identity':source_info['identity_status'],
        'nominal_people_identified':0,'instrument_observations':len(instruments),'new_model_calls':0,
        'canonical_transcript_complete_as_available':True,'transcript_is_not_complete_work_coverage':True,
        'raw_geometry_simplification_error_bound_px':max_error_px,'unobserved_hands_instruments_not_fabricated':True,
        'precise_inspection_times_ref':'06_VISUAL_ATLAS/atlas_index.json#missing_requests',
        'source_geometry_is_preserved_when_camera_uses_full_frame':True,
        'omissions':[{'data':'raw duplicate detections/debug logs/embeddings','reason':'technical audit, not needed for indexed editorial reading','location':'persisted analysis artifacts; exact hashes in source_artifacts.json'},
            {'data':'candidate repeated transcript text/frames/geometry','reason':'shared ID references; no canonical information removed'},
            {'data':'full source video/audio/models','reason':'excluded by compact evidence contract'}],
        'curator_ready_package_produced':False,'curator_execution_compatibility':'NOT_ATTESTED_FOR_THIS_EVIDENCE_FORMAT',
        'preview_approved':False,'publication_ready':False}
    _write(work,'08_REPORTS/COVERAGE_REPORT.json',coverage);_write(work,'08_REPORTS/LIMITATIONS.json',limitations)
    _write(work,'08_REPORTS/HUMAN_REVIEW_QUEUE.json',{'schema_version':'r6.3','items':[
        {'piece_id':p['piece_id'],'piece_type':p['kind'],'source_intervals':p['source_intervals'],
            'caption_status':(captions.get('candidates') or {}).get(p['piece_id'],{}).get('status','REVIEW_REQUIRED'),
            'tasks':['inspect_source_geometry_hands_instruments','review_caption_alignment','review_context_and_rights'],
            'review_completed':False,'preview_approved':False,'publication_ready':False} for p in pieces],
        'source_queue':'parent package editorial/human_review_queue.json; details retained in source package',
        'queue_is_projection_not_completion':True})
    _write(work,'00_OVERVIEW/quality_report.json',{'original_quality_report':quality,'compact_sufficiency':'PARTIAL_VISUAL_EVIDENCE',
        'original_score_criteria_not_changed':True,'review_state':'PARTIAL'})
    _write(work,'07_CAMERA/quality_gates.json',{'geometry_bounds_verified':True,'temporal_indices_verified_at_export':True,
        'zoom_final_render_verified':False,'heads_hands_instruments_continuously_verified':False,
        'safe_areas_approved':False,'second_curation_completed':False,'preview_approved':False,'publication_ready':False})
    emit('searchable_visual_atlas')
    pdf=build_compact_atlas(work,metadata=source_info,scenes=scenes,reels=reel_rows,stories=story_rows,series=series,
        atlas_index=atlas,coverage=coverage,limitations=limitations,revision=revision)
    entries={'video_summary':'00_OVERVIEW/video_summary.json','quality_report':'00_OVERVIEW/quality_report.json',
        'scene_index':'01_TIMELINE/scene_index.json','shot_transitions':'01_TIMELINE/shot_transitions.json',
        'timeline':'01_TIMELINE/complete_timeline.json','source_to_clip_map':'01_TIMELINE/source_to_clip_map.json',
        'uncovered_intervals':'01_TIMELINE/uncovered_intervals.json','segments':'02_TRANSCRIPT/transcript_segments.json',
        'words':'02_TRANSCRIPT/words_timestamps.json','audio_events':'02_TRANSCRIPT/audio_events.json','caption_quality':'02_TRANSCRIPT/caption_quality.json',
        'people_index':'03_PEOPLE/people_index.json','speaker_mapping':'03_PEOPLE/speaker_mapping.json','instruments':'03_PEOPLE/instruments.json',
        'trajectories':'03_PEOPLE/visual_trajectories.json','reels_index':'04_REELS/reels_index.json','series_index':'05_STORIES/series_index.json',
        'narrative_graph':'05_STORIES/narrative_graph.json','atlas_index':'06_VISUAL_ATLAS/atlas_index.json',
        'camera_contract':'07_CAMERA/camera_contract.json','camera_decisions':'07_CAMERA/camera_decisions.json','safe_areas':'07_CAMERA/safe_areas.json',
        'quality_gates':'07_CAMERA/quality_gates.json','coverage':'08_REPORTS/COVERAGE_REPORT.json','limitations':'08_REPORTS/LIMITATIONS.json',
        'atlas_pdf':'08_REPORTS/VISUAL_ATLAS.pdf'}
    _write(work,'00_OVERVIEW/navigation_index.json',{'schema_version':'r6.3','entries':entries,
        'reading_order':['video_summary','coverage','reels_index','timeline','scene_index','atlas_index','series_index','trajectories','camera_decisions','atlas_pdf'],
        'candidate_detail_lookup':'reels_index.reels[].*_ref; series_index.parts[].*_ref',
        'images_stored_once':'06_VISUAL_ATLAS/frames/<image-sha256>.jpg; IDs shared by scenes/Reels/Stories',
        'source_sha256':source.source_sha256})
    _write(work,'00_OVERVIEW/source_artifacts.json',{'source_sha256':source.source_sha256,'analysis_revision':source.manifest.get('run_id'),
        'parent_package_sha256':package_hash,'consumed_artifacts':list(source.receipts.values()),
        'canonical_transcript':{'segments_count':len(segments),'words_count':len(words),'segments_digest':digest(segments),'words_digest':digest(words)},
        'raw_audit_artifact_checksums':source.hashes,'source_files_modified':False})
    instructions=work/'00_OVERVIEW/COMO_ANALISAR.md'
    instructions.write_text('''# Segunda curadoria R6.3\n\nLeia navigation_index.json e COVERAGE_REPORT.json. Todos os planos detectados constam em scene_index.json, inclusive sem imagem ou geometria. Depois consulte o ranking original de Reels e as propostas de séries.\n\nA transcrição canônica completa disponível está em 02_TRANSCRIPT; candidatos referenciam IDs, sem duplicar palavras. Frames e geometrias são compartilhados globalmente. Cada peça tem intervalos absolutos/relativos, storyboard e referências de câmera.\n\nTrajetórias são observações esparsas, separadas por cortes e perdas de tracking. Nunca trate interpolação como visibilidade comprovada. Safe areas de mãos/instrumentos permanecem UNKNOWN quando ausentes. Consulte o timestamp exato da decisão antes de propor um crop arriscado.\n\nO atlas PDF é pesquisável e auxilia a leitura. JSONs são as evidências estruturadas. Este ZIP não é LDPORTO_CURATOR_READY_V1. Após revisão humana, produza decisões próprias com autoria, revisão, source SHA256, camera_timeline, camera_keyframes, source_segments, safe_areas, caption_plan, editorial, title_overlay, thumbnail_plan e audio_plan conforme os schemas reais do Curator. Nenhuma aprovação é criada por este export.\n''',encoding='utf-8')
    manifest={'schema_version':'r6.3','profile':'SECOND_CURATION_COMPACT','revision':revision,'source':source_info,
        'parent_package_sha256':package_hash,'analysis_revision':source.manifest.get('run_id'),
        'declared_counts':{k:coverage[k] for k in ('scene_count','shot_count','reel_count','story_part_count','series_count','frame_count','contact_sheet_count','trajectory_count','segment_count','word_count')},
        'canonical_transcript':{'segments_digest':digest(segments),'words_digest':digest(words)},
        'state':'PARTIAL','sufficiency':'PARTIAL_VISUAL_EVIDENCE','new_model_calls':0,'full_pipeline_executed':False,
        'preview_approved':False,'human_approved':False,'publication_ready':False}
    emit('archive_integrity')
    archive=_finish_archive(work,output,manifest)
    result={'schema_version':'r6.3','revision':revision,'archive':archive,'source_sha256':source.source_sha256,
        'parent_package':{'path':str(selected),'sha256':package_hash,'bytes':len(package_bytes),'mib':len(package_bytes)/1024**2},
        'coverage':coverage,'pdf':pdf,'state':'PARTIAL','sufficiency':'PARTIAL_VISUAL_EVIDENCE',
        'preferred_40MiB_budget_met':archive['bytes']<=40*1024**2,'initial_15_to_30MiB_target_met':15<=archive['mib']<=30,
        'size_change_bytes':archive['bytes']-len(package_bytes),'new_model_calls':0,'full_pipeline_executed':False,
        'source_artifacts_modified':False,'preview_approved':False,'publication_ready':False}
    _write(output,'COMPACT_DELIVERY.json',result)
    emit('complete',len(pieces),len(pieces))
    return result


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='R6.3: export independente de evidências persistidas, sem modelos/download.')
    parser.add_argument('--analysis',required=True);parser.add_argument('--package');parser.add_argument('--media')
    parser.add_argument('--destination');parser.add_argument('--atlas-cache');parser.add_argument('--geometry-error-px',type=float,default=2.)
    parser.add_argument('--tracking-max-gap',type=float,default=1.)
    args=parser.parse_args(argv)
    result=build_compact_handoff(args.analysis,args.package,media_path=args.media,destination=args.destination,
        atlas_cache=args.atlas_cache,max_error_px=args.geometry_error_px,max_gap_s=args.tracking_max_gap,
        progress=lambda stage,current,total:print('%s %d/%d'%(stage,current,total),flush=True))
    print(json.dumps({k:v for k,v in result.items() if k not in ('coverage',)},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
