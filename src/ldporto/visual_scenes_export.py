"""Chronological source-scene evidence, independent of editorial selection.

Only missing sparse captures are decoded. This module never invokes perception,
audio, semantics, camera planning, downloads or social-video rendering.
"""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import uuid
import zipfile

from .core import digest,file_hash,stamp
from .project_export import _safe_ancestors,_logical

INDEX='VISUAL_SCENES_INDEX.json'
KNOWN_TIMES={'opencv_decoder_reported','persisted_source_frame_sample'}


def _number(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def _us(seconds):return round(seconds*1000000)
def _write(path,doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(doc,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def _read(path):return json.loads(path.read_text(encoding='utf-8'))


def plan_scene_windows(scenes,duration_s,*,shots=(),max_window_ms=3000):
    if not _number(duration_s) or duration_s<=0 or not _number(max_window_ms) or not 0<max_window_ms<=3000:
        raise ValueError('invalid_visual_scene_duration_or_window')
    duration=_us(duration_s);limit=round(max_window_ms*1000);rows=[];seen=set()
    for scene in scenes:
        ident=scene.get('scene_id') or scene.get('shot_id')
        if not isinstance(ident,str) or len(_logical(ident).parts)!=1 or ident in seen:
            raise ValueError('invalid_or_duplicate_visual_scene_id')
        a,b=scene.get('start'),scene.get('end')
        if not all(_number(t) for t in (a,b)) or not 0<=a<b<=duration_s+1e-9:
            raise ValueError('invalid_visual_scene_interval:'+ident)
        seen.add(ident);rows.append({'scene_id':ident,'a':_us(a),'b':_us(b),'kind':'SCENE','source':scene})
    rows.sort(key=lambda r:(r['a'],r['b'],r['scene_id']))
    complete=[];cursor=0;fallback=0
    for row in rows:
        if row['a']<cursor:raise ValueError('overlapping_visual_scene_catalog')
        if row['a']>cursor:
            fallback+=1;complete.append({'scene_id':'FALLBACK_INTERVAL_%04d'%fallback,'a':cursor,'b':row['a'],'kind':'FALLBACK_INTERVAL','source':{}})
        complete.append(row);cursor=row['b']
    if cursor<duration:
        fallback+=1;complete.append({'scene_id':'FALLBACK_INTERVAL_%04d'%fallback,'a':cursor,'b':duration,'kind':'FALLBACK_INTERVAL','source':{}})
    output=[]
    for row in complete:
        a,b=row['a'],row['b'];bounds={a,b}
        for shot in shots:
            for key in ('start','end'):
                value=shot.get(key)
                if _number(value) and a<_us(value)<b:bounds.add(_us(value))
        micro=[]
        for left,right in zip(sorted(bounds),sorted(bounds)[1:]):
            while left<right:
                end=min(right,left+limit)
                micro.append({'micro_id':row['scene_id']+'_MICRO_%04d'%(len(micro)+1),
                    'start_ms':left/1000,'end_ms':end/1000,'frames':[],'failures':[]})
                left=end
        source=row['source'];description=source.get('visual_description') or source.get('description')
        output.append({'scene_id':row['scene_id'],'kind':row['kind'],'start_ms':a/1000,'end_ms':b/1000,
            'duration_ms':(b-a)/1000,'micro_windows':micro,'frames':[],
            'contact_sheet':None,'contact_sheets':[],'contact_sheet_records':[],
            'description':description if isinstance(description,str) and description.strip() else None,
            'description_status':'PERSISTED_ANALYSIS' if description else 'NOT_ANALYZED',
            'transcript_segment_ids':[]})
    return {'schema_version':'visual_scenes_v1','video_duration_ms':duration/1000,
        'original_scene_count':len(scenes),'original_scene_ids':[r['scene_id'] for r in rows],
        'fallback_interval_count':fallback,'max_micro_window_ms':max_window_ms,'scenes':output,
        'interval_convention':'[start,end)','timestamp_unit':'absolute original source milliseconds; microsecond precision',
        'continuous_frame_analysis':False,'editorial_selection_applied':False}


class _Capture:
    def __init__(self,source):
        import cv2
        self.cv2=cv2;self.cap=cv2.VideoCapture(str(source));self.reads=0
        if not self.cap.isOpened():raise ValueError('visual_source_not_decodable')
    def __call__(self,time,output):
        from .preview_renderer import decode_source_frame
        frame,info=decode_source_frame(self.cap,time)
        self.reads+=1
        if frame is None:return {'captured':False,**info}
        h,w=frame.shape[:2];factor=min(1.,640/w)
        if factor<1:frame=self.cv2.resize(frame,(round(w*factor),round(h*factor)),interpolation=self.cv2.INTER_AREA)
        ok,encoded=self.cv2.imencode('.jpg',frame,[self.cv2.IMWRITE_JPEG_QUALITY,80])
        if not ok:return {'captured':False,'reason':'source_jpeg_encoding_failed'}
        Path(output).write_bytes(encoded.tobytes())
        return {**info,'captured':True,'width':frame.shape[1],'height':frame.shape[0],
            'source_decoded_width':w,'source_decoded_height':h,'capture_method':'opencv_cpu_sparse_source_seek'}
    def close(self):self.cap.release()


def _status(index):
    micros=[m for s in index['scenes'] for m in s['micro_windows']]
    missing=sum(not m['frames'] for m in micros)
    if missing==len(micros):return 'FAILED'
    if missing or any(not s['contact_sheet'] for s in index['scenes']):return 'PARTIAL'
    if index.get('failures'):return 'PARTIAL' if index.get('pdfs') else 'FAILED'
    return 'COMPLETE'


def export_visual_scenes(analysis,source,destination,*,cache_directory=None,resume=True,
                         frame_provider=None,build_pdf=True,progress=None):
    import cv2
    import numpy as np
    from .preview_renderer import _fit
    metadata=analysis['metadata'];source_hash=metadata['sha256']
    if frame_provider is None and source and Path(source).is_file() and file_hash(_safe_ancestors(source))!=source_hash:
        raise ValueError('visual_source_identity_mismatch')
    root=_safe_ancestors(destination);root.mkdir(parents=True,exist_ok=True)
    scenes=analysis.get('scenes') or [{**s,'scene_id':s.get('scene_id') or s['shot_id']} for s in analysis.get('shots',[])]
    signature=digest({'source_metadata':{k:metadata.get(k) for k in ('sha256','duration','width','height','fps','rotation')},'scenes':scenes,'shots':analysis.get('shots',[]),
        'segments':analysis.get('transcript_segments',[]),'profile':'source_scene_micro_3s_2captures_v1','build_pdf':build_pdf})
    previous=root/INDEX
    if resume and previous.is_file():
        old=_read(previous)
        checked=validate_visual_scene_export(root)
        if (old.get('catalog_signature')==signature and checked['status']=='valid' and checked['export_status']=='COMPLETE'
                and old.get('statistics') and (not build_pdf or old.get('pdfs'))):
            old['last_execution']={'new_captures':0,'reused_complete_export':True};return old
    index=plan_scene_windows(scenes,metadata['duration'],shots=analysis.get('shots',[]))
    index.update(source_sha256=source_hash,source_width=metadata['width'],source_height=metadata['height'],
        catalog_signature=signature,export_status='PARTIAL',preview_approved=False,human_approved=False,publication_ready=False)
    cache=_safe_ancestors(cache_directory or root.parent/(root.name+'_capture_cache'));cache.mkdir(parents=True,exist_ok=True)
    def cached_image_valid(path):
        image=cv2.imread(str(path))
        return image is not None and image.size and abs(image.shape[1]/image.shape[0]-metadata['width']/metadata['height'])<=.02
    own=None;new_captures=0;reused=0;content_seen={}
    if frame_provider is None and source and Path(source).is_file():
        source=_safe_ancestors(source)
        if file_hash(source)!=source_hash:raise ValueError('visual_source_identity_mismatch')
        own=_Capture(source);frame_provider=own
    try:
        for number,scene in enumerate(index['scenes'],1):
            if progress:progress('visual_scenes',number,len(index['scenes']))
            scene_frames={};scene_images={}
            for micro in scene['micro_windows']:
                a,b=micro['start_ms']/1000,micro['end_ms']/1000
                for fraction in (.25,.75):
                    requested=a+(b-a)*fraction;key=digest([source_hash,round(requested,6),'scene_capture_v1'])
                    info=None;image=None
                    for record_path in sorted(cache.glob(key+'*.json')) if resume else []:
                        try:
                            record=_read(_safe_ancestors(record_path));candidate=_safe_ancestors(cache/str(_logical(record['image'])))
                            cached_info=record['info'];cached_time=cached_info.get('source_time_s')
                            if (record['source_sha256']==source_hash and record['requested_source_time_s']==requested
                                    and candidate.is_relative_to(cache) and file_hash(candidate)==record['sha256']
                                    and cached_info.get('timestamp_provenance') in KNOWN_TIMES
                                    and _number(cached_time) and a<=cached_time<b
                                    and cached_image_valid(candidate)):
                                info=record['info'];image=candidate;reused+=1;break
                        except (OSError,ValueError,KeyError):continue
                    if info is None:
                        if frame_provider is None:
                            micro['failures'].append({'requested_source_time_s':requested,'reason':'source_media_unavailable'});continue
                        image=cache/(key+'_'+uuid.uuid4().hex[:8]+'.jpg')
                        try:info=frame_provider(requested,image);new_captures+=1
                        except Exception as exc:info={'captured':False,'reason':'source_capture_error:'+type(exc).__name__}
                        if not info.get('captured') or not image.is_file():
                            micro['failures'].append({'requested_source_time_s':requested,'reason':info.get('reason','source_capture_failed')});continue
                        _write(image.with_suffix('.json'),{'source_sha256':source_hash,'requested_source_time_s':requested,
                            'image':image.name,'sha256':file_hash(image),'info':info})
                    time=info.get('source_time_s');provenance=info.get('timestamp_provenance')
                    if not _number(time) or provenance not in KNOWN_TIMES or not a<=time<b:
                        micro['failures'].append({'requested_source_time_s':requested,'source_time_s':time,
                            'reason':'actual_source_timestamp_unknown_or_outside_micro_window','timestamp_provenance':provenance});continue
                    decoded=cv2.imread(str(image))
                    if decoded is None or not decoded.size:
                        micro['failures'].append({'requested_source_time_s':requested,'reason':'cached_image_not_decodable'});continue
                    if abs(decoded.shape[1]/decoded.shape[0]-metadata['width']/metadata['height'])>.02:
                        micro['failures'].append({'requested_source_time_s':requested,'reason':'source_frame_aspect_mismatch'});continue
                    timestamp=_us(time)/1000;frame_key=_us(time)
                    if frame_key in scene_frames:
                        micro.setdefault('duplicate_capture_requests',[]).append({'requested_source_time_s':requested,'timestamp_ms':timestamp});continue
                    sha=file_hash(image);ident='FRAME_'+digest([source_hash,_us(time),sha])[:20]
                    row={'frame_id':ident,'timestamp_ms':timestamp,'source_time_s':time,
                        'source_frame_index':info.get('source_frame_index'),'source_image_sha256':sha,
                        'capture_provenance':provenance,'capture_method':info.get('capture_method'),
                        'timestamp_independently_verified':info.get('timestamp_independently_verified',False)}
                    if sha in content_seen:row['repeated_source_content_of']=content_seen[sha]
                    content_seen.setdefault(sha,ident);scene_frames[frame_key]=row;scene_images[ident]=image
                    micro['frames'].append(row)
                micro['frames'].sort(key=lambda f:f['timestamp_ms'])
                micro['status']='CAPTURED' if micro['frames'] else 'MISSING_CAPTURE'
            scene['frames']=sorted(scene_frames.values(),key=lambda f:f['timestamp_ms'])
            for offset in range(0,len(scene['frames']),6):
                group=scene['frames'][offset:offset+6];canvas=np.full((412,960,3),24,dtype=np.uint8)
                page=offset//6;name='contact_sheet.jpg' if page==0 else 'contact_sheet_%03d.jpg'%(page+1)
                relative='visuals_all/'+scene['scene_id']+'/'+name;target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                for tile,frame in enumerate(group):
                    image=cv2.imread(str(scene_images[frame['frame_id']]))
                    x,y=(tile%3)*320,(tile//3)*206;canvas[y:y+180,x:x+320]=_fit(image,320,180,cv2)
                    cv2.putText(canvas,stamp(frame['source_time_s']),(x+8,y+197),cv2.FONT_HERSHEY_SIMPLEX,.43,(230,230,230),1,cv2.LINE_AA)
                    frame.update(contact_sheet=relative,tile_index=tile)
                ok,encoded=cv2.imencode('.jpg',canvas,[cv2.IMWRITE_JPEG_QUALITY,78])
                if not ok:continue
                blob=encoded.tobytes()
                if not target.is_file() or target.read_bytes()!=blob:target.write_bytes(blob)
                scene['contact_sheets'].append(relative)
                scene['contact_sheet_records'].append({'path':relative,'sha256':file_hash(target),'bytes':target.stat().st_size,
                    'frame_ids':[f['frame_id'] for f in group]})
            scene['contact_sheet']=next(iter(scene['contact_sheets']),None)
            scene['transcript_segment_ids']=[s['segment_id'] for s in analysis.get('transcript_segments',[]) if s.get('segment_id')
                and s['start']*1000<scene['end_ms'] and s['end']*1000>scene['start_ms']]
            scene['word_ids']=[w['word_id'] for w in analysis.get('words',[]) if w.get('word_id')
                and w['start']*1000<scene['end_ms'] and w['end']*1000>scene['start_ms']]
            scene['transcript_reference']='transcript/relevant_segments.jsonl'
            index['export_status']=_status(index);_write(previous,index)
    finally:
        if own:own.close()
    index['export_status']=_status(index)
    index['statistics']={'scene_count':len(index['scenes']),'original_scene_count':len(scenes),
        'micro_window_count':sum(len(s['micro_windows']) for s in index['scenes']),
        'capture_count':sum(len(s['frames']) for s in index['scenes']),
        'missing_micro_windows':sum(not m['frames'] for s in index['scenes'] for m in s['micro_windows']),
        'represented_duration_ms':index['video_duration_ms'] if index['export_status']=='COMPLETE' else sum(
            m['end_ms']-m['start_ms'] for s in index['scenes'] for m in s['micro_windows'] if m['frames']),
        'continuous_video_frame_coverage_claimed':False}
    index['last_execution']={'new_captures':new_captures,'reused_capture_receipts':reused,'reused_complete_export':False}
    if build_pdf:
        from .visual_scenes_atlas import build_visual_scenes_atlas
        index.update(build_visual_scenes_atlas(root,index,analysis.get('transcript_segments',[])))
    _write(previous,index)
    return index


def validate_visual_scene_export(directory):
    try:
        root=_safe_ancestors(directory)
        def read(name):
            path=_safe_ancestors(root/str(_logical(name)))
            if not path.is_relative_to(root):raise ValueError('visual_reference_outside_export')
            return path.read_bytes()
        return validate_visual_scene_index(_read(root/INDEX),read)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {'status':'failed','errors':[type(exc).__name__+':'+str(exc)],'export_status':'FAILED'}


def validate_visual_scene_index(index,read):
    """Validate source coverage and exact indexed bytes without extracting a ZIP."""
    import cv2
    import numpy as np
    errors=[]
    try:
        cursor=0.;originals=[]
        for scene in index['scenes']:
            a,b=scene['start_ms'],scene['end_ms']
            if not 0<=a<b<=index['video_duration_ms'] or abs(a-cursor)>1e-6:errors.append('scene_interval_coverage:'+scene['scene_id'])
            cursor=b
            if scene['kind']=='SCENE':originals.append(scene['scene_id'])
            micro_cursor=a;frames=[]
            for micro in scene['micro_windows']:
                ma,mb=micro['start_ms'],micro['end_ms']
                if abs(ma-micro_cursor)>1e-6 or not ma<mb<=b or mb-ma>3000.000001:errors.append('micro_window_coverage:'+micro['micro_id'])
                micro_cursor=mb
                for frame in micro['frames']:
                    if not ma<=frame['timestamp_ms']<mb or abs(frame['timestamp_ms']-frame['source_time_s']*1000)>.001:
                        errors.append('frame_outside_micro_window:'+frame['frame_id'])
                    if frame['capture_provenance'] not in KNOWN_TIMES:errors.append('unknown_frame_timestamp:'+frame['frame_id'])
                    frames.append(frame['frame_id'])
            if abs(micro_cursor-b)>1e-6:errors.append('scene_micro_tail_gap:'+scene['scene_id'])
            times=[f['timestamp_ms'] for f in scene['frames']]
            if times!=sorted(set(times)) or set(frames)!={f['frame_id'] for f in scene['frames']}:errors.append('frame_order_or_index_mismatch:'+scene['scene_id'])
            records={r['path']:r for r in scene['contact_sheet_records']}
            if len(records)!=len(scene['contact_sheet_records']):errors.append('duplicate_sheet_record')
            if scene['contact_sheets']!=list(records) or scene['contact_sheet']!=(next(iter(records),None)):
                errors.append('contact_sheet_reference_mismatch:'+scene['scene_id'])
            for frame in scene['frames']:
                ref=frame.get('contact_sheet')
                if ref not in records or frame['frame_id'] not in records[ref]['frame_ids']:
                    errors.append('frame_contact_sheet_reference_mismatch:'+frame['frame_id'])
            for record in records.values():
                data=read(str(_logical(record['path'])))
                if hashlib.sha256(data).hexdigest()!=record['sha256'] or cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR) is None:
                    errors.append('invalid_contact_sheet:'+record['path'])
            if scene['frames'] and not scene['contact_sheet']:errors.append('contact_sheet_missing:'+scene['scene_id'])
        if abs(cursor-index['video_duration_ms'])>1e-6:errors.append('video_coverage_gap')
        if len(originals)!=index['original_scene_count'] or set(originals)!=set(index['original_scene_ids']):errors.append('original_scene_catalog_mismatch')
        computed=_status(index)
        if index['export_status']!=computed:errors.append('export_status_disagreement')
        for pdf in index.get('pdfs',[]):
            data=read(str(_logical(pdf['path'])))
            if hashlib.sha256(data).hexdigest()!=pdf['sha256'] or not data.startswith(b'%PDF-'):errors.append('invalid_visual_atlas_pdf')
        return {'status':'valid' if not errors else 'failed','errors':errors,'export_status':computed,
            'scene_count':len(index['scenes']),'original_scene_count':len(originals)}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {'status':'failed','errors':errors+[type(exc).__name__+':'+str(exc)],'export_status':index.get('export_status','FAILED')}


def _refresh_package_ledgers(root,visual_index):
    """Extend the existing core contract; do not recurate any candidate."""
    from .r62_delivery import _reindex
    master=_read(root/'HANDOFF_MASTER.json')
    master.update(visual_scenes_ref=INDEX,visual_scenes_export_status=visual_index['export_status'])
    _write(root/'HANDOFF_MASTER.json',master)
    curation=_read(root/'CURATION_INDEX.json')
    curation.update(visual_scenes_ref=INDEX,visual_scenes_export_status=visual_index['export_status'])
    _write(root/'CURATION_INDEX.json',curation)
    brief=_read(root/'SECOND_CURATOR_BRIEF.json')
    if INDEX not in brief['recommended_entrypoints']:brief['recommended_entrypoints'].append(INDEX)
    _write(root/'SECOND_CURATOR_BRIEF.json',brief)
    manifest=_read(root/'SECOND_CURATION_MANIFEST.json')
    manifest['visual_scenes']={'index_ref':INDEX,'export_status':visual_index['export_status'],
        'statistics':visual_index['statistics'],'packages':visual_index.get('packages',[]),
        'editorial_selection_applied':False,'expensive_inference_executed':False}
    _write(root/'SECOND_CURATION_MANIFEST.json',manifest);_reindex(root)


def _visual_parts(index,assets,output,partition_ms=600000):
    """Optional chronological companions; crossing scenes retain their identity."""
    results=[];duration=index['video_duration_ms']
    if duration<=partition_ms:return results
    start=0.
    while start<duration:
        end=min(duration,start+partition_ms)
        scenes=[s for s in index['scenes'] if s['start_ms']<end and s['end_ms']>start]
        members={r['path'] for s in scenes for r in s['contact_sheet_records']}
        members.update(p['path'] for p in index.get('pdfs',[]) if p['start_ms']<end and p['end_ms']>start)
        name='VISUALS_%03d_%03d_MIN.zip'%(int(start/60000),int((start+partition_ms)/60000))
        target=output/name
        part={'schema_version':'visual_scene_part_v1','source_sha256':index['source_sha256'],
            'start_ms':start,'end_ms':end,'interval_convention':'[start,end)','scenes':scenes,
            'source_scene_bounds_preserved':True,'files':[{'path':n,'sha256':file_hash(assets/n),'bytes':(assets/n).stat().st_size} for n in sorted(members)]}
        with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.writestr('VISUAL_SCENES_PART_INDEX.json',json.dumps(part,ensure_ascii=False,indent=2))
            for member in sorted(members):archive.write(assets/member,member)
        with zipfile.ZipFile(target) as archive:
            if archive.testzip() is not None:raise ValueError('visual_part_crc_failed')
            for record in part['files']:
                if hashlib.sha256(archive.read(record['path'])).hexdigest()!=record['sha256']:raise ValueError('visual_part_checksum_failed')
        results.append({'filename':name,'sha256':file_hash(target),'bytes':target.stat().st_size,
            'start_ms':start,'end_ms':end,'scene_ids':[s['scene_id'] for s in scenes]})
        start=end
    return results


def reexport_all_scenes(analysis_folder,package_path,source,output_dir,*,progress=None):
    """New ZIP revision, original editorial candidates and camera decisions preserved."""
    import io
    from .second_curation_export import snapshot_core_package,validate_core_package
    from .compact_handoff import PersistedArtifacts
    from .preview_renderer import build_contact_sheet
    persisted=PersistedArtifacts(analysis_folder)
    summary=persisted.read('analysis_summary.json');metadata=summary['metadata']
    analysis={'metadata':metadata,'scenes':persisted.read('scenes.json'),
        'shots':persisted.read('shots.json',[]),'transcript_segments':persisted.read('transcript_segments.json',[]),
        'words':persisted.read('words.json',[])}
    raw,baseline=snapshot_core_package(package_path);parent_sha=hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        source_metadata=json.loads(archive.read('source/metadata.json'))
        if any(source_metadata.get(k)!=metadata.get(k) for k in ('sha256','duration','width','height')):
            raise ValueError('visual_package_analysis_identity_mismatch')
    output=_safe_ancestors(output_dir);output.mkdir(parents=True,exist_ok=True)
    assets=output/'visual_assets'
    visual=export_visual_scenes(analysis,source,assets,cache_directory=output/'capture_cache',progress=progress)
    checked=validate_visual_scene_export(assets)
    if checked['status']!='valid':raise ValueError('visual_export_integrity_failed:'+str(checked['errors']))
    revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6]
    delivery=output/('DELIVERY_'+revision);delivery.mkdir(exist_ok=False)
    parts=_visual_parts(visual,assets,delivery)
    core=delivery/'SECOND_CURATION';core.mkdir()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in archive.namelist():
            path=core/str(_logical(name));path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
    for path in assets.rglob('*'):
        if path.is_file() and not any(p.startswith('.') for p in path.relative_to(assets).parts):
            target=core/path.relative_to(assets);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    # The old package only needed candidate-local words. The scene index also
    # references unselected source intervals: add available canonical records,
    # preserving all old projected records and never synthesizing audio/timing.
    for filename,key,canonical in (('transcript/relevant_words.jsonl','word_id',analysis['words']),
                                    ('transcript/relevant_segments.jsonl','segment_id',analysis['transcript_segments'])):
        path=core/filename;rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
        by_id={r[key]:r for r in rows};fields=set().union(*(r.keys() for r in rows)) if rows else set()
        for record in canonical:
            if record[key] not in by_id:
                by_id[record[key]]={k:v for k,v in record.items() if not fields or k in fields}
        path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sorted(by_id.values(),key=lambda r:(r['start'],r[key]))),encoding='utf-8')
    visual={**visual,'packages':parts,'parent_package_sha256':parent_sha}
    _write(core/INDEX,visual)
    # Fix timestamps in the four existing moment sheets too, while keeping their
    # IDs, paths, editorial scores, transcript and camera plan contracts intact.
    catalog=_read(core/'editorial/candidate_catalog.json');timeline=_read(core/'camera/camera_director_timeline.json')
    moment_cache=output/'moment_sheet_cache';moment_cache.mkdir(exist_ok=True);corrected=[]
    for row in catalog['candidates']:
        relative='visuals/'+row['candidate_id']+'/contact_sheet.jpg'
        if not (core/relative).is_file():continue
        key=digest([metadata['sha256'],row['candidate_id'],row['start'],row['end'],digest(timeline),file_hash(Path(__file__).with_name('preview_renderer.py'))])
        cache_image=moment_cache/(key+'.jpg');cache_info=moment_cache/(key+'.json')
        if cache_image.is_file() and cache_info.is_file() and file_hash(cache_image)==_read(cache_info).get('sha256'):
            info=_read(cache_info)['info']
        else:
            info=build_contact_sheet(source,row,cache_image,timeline)
            if cache_image.is_file():_write(cache_info,{'sha256':file_hash(cache_image),'info':info})
        if cache_image.is_file() and info.get('status')=='ok':
            before=file_hash(core/relative);shutil.copyfile(cache_image,core/relative)
            row['visual_metadata']={**info,'provenance':'source_pts_chronology_corrected_new_revision','sha256':file_hash(cache_image)}
            _write(core/('candidates/'+row['candidate_id']+'.json'),row)
            corrected.append({'candidate_id':row['candidate_id'],'path':relative,'previous_sha256':before,'sha256':file_hash(cache_image)})
    _write(core/'editorial/candidate_catalog.json',catalog)
    _refresh_package_ledgers(core,visual)
    validation=validate_core_package(core)
    if validation['status']!='valid':raise ValueError('extended_core_validation_failed:'+str(validation['errors']))
    target=delivery/'00_INICIAR_POR_AQUI.zip';partial=delivery/('.'+target.name+'.partial')
    with zipfile.ZipFile(partial,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(core.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(core).as_posix())
    validation=validate_core_package(partial)
    if validation['status']!='valid':raise ValueError('visual_zip_reopen_failed:'+str(validation['errors']))
    import os
    os.link(partial,target);partial.unlink()
    if file_hash(package_path)!=parent_sha:raise ValueError('parent_package_changed_during_visual_export')
    result={'schema_version':'visual_scene_delivery_v1','path':str(target),'sha256':file_hash(target),'bytes':target.stat().st_size,
        'export_status':visual['export_status'],'editorial_state':_read(core/'CURATION_INDEX.json').get('analysis_status'),
        'original_scene_count':visual['original_scene_count'],'statistics':visual['statistics'],
        'index_path':str(core/INDEX),'pdfs':[{'path':str(core/p['path']),'sha256':p['sha256']} for p in visual.get('pdfs',[])],
        'packages':[{'filename':target.name,'sha256':file_hash(target),'bytes':target.stat().st_size,'start_ms':0,'end_ms':visual['video_duration_ms']},*parts],
        'moment_sheet_corrections':corrected,'candidate_count':len(catalog['candidates']),
        'source_sha256':metadata['sha256'],'parent_package_sha256':parent_sha,'parent_package_preserved':True,
        'last_visual_execution':visual['last_execution'],'validation':validation,'new_model_calls':0,
        'camera_timeline_recomputed':False,'social_previews_rendered':False,'preview_approved':False,'publication_ready':False}
    _write(delivery/'VISUAL_EXPORT_MANIFEST.json',result)
    return result


def main(argv=None):
    import argparse
    from .paths import PACKAGE_OUTPUT_DIR,PROJECT_ROOT
    from .media_library import resolve_existing_media
    parser=argparse.ArgumentParser(description='Reexportar todas as cenas de análise existente, sem inferência.')
    parser.add_argument('--analysis',required=True);parser.add_argument('--package',required=True)
    parser.add_argument('--media');parser.add_argument('--destination')
    args=parser.parse_args(argv)
    metadata=_read(Path(args.analysis)/'analysis_summary.json')['metadata'];source=args.media
    if not source:
        ident=(metadata.get('source') or {}).get('id')
        if ident:
            resolved=resolve_existing_media(ident,expected_sha256=metadata['sha256'],legacy_root=PROJECT_ROOT/'input/youtube')
            if resolved['status']=='FOUND_VERIFIED':source=resolved['path']
    if not source:raise ValueError('Original local não encontrado; informe --media. Nenhum download será executado.')
    destination=args.destination or PACKAGE_OUTPUT_DIR/('VISUAL_ALL_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    result=reexport_all_scenes(args.analysis,args.package,source,destination,
        progress=lambda stage,current,total:print('%s %d/%d'%(stage,current,total),flush=True))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['export_status']=='COMPLETE' else 2


if __name__=='__main__':raise SystemExit(main())
