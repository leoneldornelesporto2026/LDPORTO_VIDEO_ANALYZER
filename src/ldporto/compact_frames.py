"""Shared, sparse source images for the compact editorial package (CPU only)."""
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

from .core import file_hash
from .project_export import _safe_ancestors,_logical
from .visual_frame_handoff import SparseFrameProvider


def _inside(time,intervals):
    return any(i['start']<=time<i['end'] for i in intervals)


def _number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def _cached_time(scene,cached):
    for key in ('keyframe_time_s','keyframe_time','keyframe_timestamp'):
        time=scene.get(key)
        if _number(time) and scene['start']<=time<scene['end']:
            return time,'persisted_scene_explicit_timestamp_not_independently_verified'
    # Canonical producer: vision.py stores SCENE_ID_{sample_time:.3f}.jpg,
    # pipeline.enrich_scenes binds that exact path to the scene. This is a
    # rounded persisted sampling timestamp, not an independent decoder receipt.
    match=re.fullmatch(re.escape(scene['scene_id'])+r'_(\d+(?:\.\d+)?)\.(?:jpe?g|png|webp)',Path(cached).name,re.I)
    if match:
        time=float(match[1])
        if scene['start']<=time<scene['end']:
            return time,'persisted_canonical_filename_timestamp_rounded_not_independently_verified'
    return None,None


def _write_contact_sheets(root,frames,*,width=640,quality=50):
    from PIL import Image,ImageDraw,ImageFont
    folder=root/'06_VISUAL_ATLAS/contact_sheets';folder.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',11) if Path('C:/Windows/Fonts/arial.ttf').is_file() else ImageFont.load_default()
    columns=4;tile_width=width//columns
    image_height=round(tile_width*9/16);tile_height=image_height+35
    sheets=[]
    for offset in range(0,len(frames),16):
        group=frames[offset:offset+16];height=math.ceil(len(group)/columns)*tile_height
        canvas=Image.new('RGB',(width,height),'#10141c');draw=ImageDraw.Draw(canvas)
        for position,row in enumerate(group):
            x,y=position%columns*tile_width,position//columns*tile_height
            with Image.open(root/row['path']) as image:
                image.thumbnail((tile_width-6,image_height));canvas.paste(image,(x+3,y))
            draw.text((x+3,y+image_height+2),str(row.get('scene_id') or 'UNKNOWN'),fill='white',font=font)
            draw.text((x+3,y+image_height+17),'%.3fs | %s'%(row['source_time_s'],row['frame_id'][-6:]),fill='#dfe5ee',font=font)
        sid='SHEET_%04d'%(offset//16);path=folder/(sid+'.jpg')
        canvas.save(path,'JPEG',quality=quality,optimize=True)
        sheets.append({'sheet_id':sid,'path':path.relative_to(root).as_posix(),'sha256':file_hash(path),
            'width':width,'height':height,'frame_ids':[row['frame_id'] for row in group],
            'scene_ids':sorted({row['scene_id'] for row in group if row.get('scene_id')})})
    return sheets


def build_shared_visual_atlas(analysis_folder,metadata,scenes,pieces,destination,*,media_path=None,
                              max_frames=2600,max_bytes=60*1024**2,progress=None,navigation_width=320,
                              analysis_width=640,jpeg_quality=62,contact_width=640,contact_quality=50):
    """Reuse persisted scene images; sparsely decode only explicitly planned times.

    One navigation frame per scene plus start/middle/end anchors for each piece.
    Actual decoded timestamps and cache timestamp limitations remain explicit.
    Identical JPEG bytes have one physical path, regardless of editorial reuse.
    """
    import cv2
    import numpy as np
    from PIL import Image
    if (not re.fullmatch(r'[a-f0-9]{64}',str(metadata.get('sha256'))) or
            not _number(metadata.get('duration')) or metadata['duration']<=0 or
            any(not _number(metadata.get(k)) or metadata[k]<=0 for k in ('width','height')) or
            any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in (max_frames,max_bytes))):
        raise ValueError('compact_frames_identity_metadata_or_budget_invalid')
    if (any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in (navigation_width,analysis_width,contact_width))
            or analysis_width<navigation_width or contact_width<320
            or any(not isinstance(v,int) or isinstance(v,bool) or not 1<=v<=95 for v in (jpeg_quality,contact_quality))):
        raise ValueError('compact_frames_profile_invalid')
    root=_safe_ancestors(destination);root.mkdir(parents=True,exist_ok=True)
    source=_safe_ancestors(analysis_folder)
    source_manifest=source/'manifest.json'
    cache_source_bound=False
    if source_manifest.is_file():
        manifest=json.loads(_safe_ancestors(source_manifest).read_text(encoding='utf-8'))
        recorded=manifest.get('video_sha256') or manifest.get('source_sha256') or manifest.get('sha256')
        if recorded!=metadata['sha256']:
            raise ValueError('compact_frames_analysis_manifest_source_mismatch')
        cache_source_bound=True
    scenes=sorted(scenes,key=lambda row:row['start'])
    seen_scenes=set()
    for scene in scenes:
        if (not scene.get('scene_id') or scene['scene_id'] in seen_scenes or
                not all(_number(scene.get(k)) for k in ('start','end')) or
                not 0<=scene['start']<scene['end']<=metadata['duration']+1e-6):
            raise ValueError('compact_frames_scene_id_or_interval_invalid')
        seen_scenes.add(scene['scene_id'])
    if any(b['start']<a['end']-1e-6 for a,b in zip(scenes,scenes[1:])):
        raise ValueError('compact_frames_source_scene_overlap')
    piece_intervals={}
    for piece in pieces:
        ident=piece.get('piece_id');intervals=piece.get('source_intervals') or []
        if (not ident or ident in piece_intervals or not intervals or any(
                not all(_number(row.get(k)) for k in ('start','end')) or
                not 0<=row['start']<row['end']<=metadata['duration']+1e-6 for row in intervals)
                or any(b['start']<a['end']-1e-6 for a,b in zip(intervals,intervals[1:]))):
            raise ValueError('compact_frames_piece_id_or_interval_invalid')
        piece_intervals[ident]=intervals
    image_root=root/'06_VISUAL_ATLAS/frames';image_root.mkdir(parents=True,exist_ok=True)
    requests=[];cache_rejections=[]
    for scene in scenes:
        cached=scene.get('keyframe')
        cache_time,cache_provenance=None,None
        if cached:
            candidate=source/str(_logical(cached))
            cached=str(_safe_ancestors(candidate)) if candidate.is_file() else None
        if cached and cache_source_bound:
            cache_time,cache_provenance=_cached_time(scene,cached)
        if cached and (not cache_source_bound or cache_time is None):
            cache_rejections.append({'scene_id':scene['scene_id'],'reason':
                'persisted_frame_source_manifest_missing' if not cache_source_bound else 'persisted_frame_timestamp_unavailable'})
            cached=None
        original_sha=file_hash(cached) if cached else None
        registered=(manifest.get('artifact_checksums') or {}).get(scene.get('keyframe')) if cached else None
        if cached and registered and registered!=original_sha:
            cache_rejections.append({'scene_id':scene['scene_id'],'reason':'persisted_frame_registered_checksum_mismatch'})
            cached=None
        requests.append({'requested_source_time_s':cache_time if cached else (scene['start']+scene['end'])/2,
            'scene_id':scene['scene_id'],'piece_ids':[],'reason':'scene_reference','cached_path':cached,
            'cache_timestamp_provenance':cache_provenance,'cached_original_sha256':original_sha,
            'cache_image_integrity':'registered_artifact_hash_verified' if registered else 'current_image_hashed_no_original_image_checksum_in_manifest',
            'width':navigation_width})
    for piece in pieces:
        duration=sum(i['end']-i['start'] for i in piece['source_intervals'])
        fps=metadata.get('fps')
        tail_margin=1./fps+1e-6 if _number(fps) and fps>0 else .05
        tail_margin=min(tail_margin,(piece['source_intervals'][-1]['end']-piece['source_intervals'][-1]['start'])/2)
        for fraction,reason in ((0.,'piece_start'),(.5,'piece_middle'),(1.,'piece_end')):
            offset=min(duration-tail_margin,max(0.,duration*fraction));cursor=0.
            for interval in piece['source_intervals']:
                span=interval['end']-interval['start']
                if offset<cursor+span:
                    time=interval['start']+offset-cursor
                    requests.append({'requested_source_time_s':time,'scene_id':None,'piece_ids':[piece['piece_id']],
                        'reason':reason,'cached_path':None,'width':analysis_width})
                    break
                cursor+=span
    # Merge the same timestamp and preserve all requesting pieces/reasons.
    planned={}
    for request in requests:
        key=round(request['requested_source_time_s'],6)
        if key not in planned:
            planned[key]={**request,'reasons':[request['reason']]}
        else:
            row=planned[key];row['piece_ids']=sorted(set(row['piece_ids']+request['piece_ids']))
            row['reasons']=sorted(set(row['reasons']+[request['reason']]))
            row['width']=max(row['width'],request['width'])
    frames=[];missing=[];physical={};frame_by_id={};stored_bytes=0;decoded=0;merged_requests=0;cached_reused=0
    boundaries=[s['start'] for s in scenes]
    def add(request,blob,info):
        nonlocal stored_bytes,merged_requests
        time=info.get('source_time_s')
        if not _number(time) or not 0<=time<metadata['duration']:
            missing.append({**request,'reason':'decoded_timestamp_outside_source'});return
        pos=bisect_right(boundaries,time)-1
        scene=scenes[pos] if pos>=0 and scenes[pos]['start']<=time<scenes[pos]['end'] else None
        if request['scene_id'] and (not scene or scene['scene_id']!=request['scene_id']):
            missing.append({**request,'reason':'decoded_timestamp_outside_requested_scene'});return
        good_pieces=[pid for pid in request['piece_ids'] if _inside(time,piece_intervals[pid])]
        bad_pieces=sorted(set(request['piece_ids'])-set(good_pieces))
        if bad_pieces:
            missing.append({**request,'piece_ids':bad_pieces,'reason':'decoded_timestamp_outside_requested_piece'})
        if not request['scene_id'] and not good_pieces:
            return
        sha=hashlib.sha256(blob).hexdigest()
        frame_id='FRAME_'+hashlib.sha256((metadata['sha256']+':'+format(time,'.6f')+':'+sha).encode()).hexdigest()[:20]
        if frame_id in frame_by_id:
            existing=frame_by_id[frame_id]
            existing['piece_ids']=sorted(set(existing['piece_ids']+good_pieces))
            existing['sampling_reasons']=sorted(set(existing['sampling_reasons']+request['reasons']))
            existing['requested_source_times_s']=sorted(set(existing['requested_source_times_s']+[request['requested_source_time_s']]))
            merged_requests+=1
            return
        if sha not in physical:
            if stored_bytes+len(blob)>max_bytes:
                missing.append({**request,'reason':'shared_image_byte_budget_exhausted'});return
            path=image_root/(sha+'.jpg')
            if path.exists() and file_hash(path)!=sha:
                raise ValueError('compact_frames_existing_image_checksum_mismatch')
            if not path.exists():path.write_bytes(blob)
            physical[sha]=path.relative_to(root).as_posix();stored_bytes+=len(blob)
        record={**info,'captured':True,'frame_id':frame_id,'source_sha256':metadata['sha256'],'path':physical[sha],'sha256':sha,
            'requested_source_time_s':request['requested_source_time_s'],'scene_id':scene['scene_id'] if scene else None,
            'requested_source_times_s':[request['requested_source_time_s']],
            'piece_ids':good_pieces,'sampling_reasons':request['reasons'],'final_render_frame':False}
        frames.append(record);frame_by_id[frame_id]=record
    # A decoder is opened only for missing cached frames and requires a hash-bound original.
    provider=None
    source_ratio=metadata['width']/metadata['height']
    if abs(metadata.get('rotation') or 0)%180:source_ratio=1./source_ratio
    try:
        for number,request in enumerate(sorted(planned.values(),key=lambda r:r['requested_source_time_s']),1):
            if progress and (number%25==0 or number==len(planned)):progress('shared_frames',number,len(planned))
            if len(frames)>=max_frames:
                missing.append({**request,'reason':'shared_frame_count_budget_exhausted'});continue
            blob=None;info=None
            if request['cached_path']:
                try:
                    with Image.open(request['cached_path']) as im:
                        if abs(im.width/im.height-source_ratio)>.01:
                            cache_rejections.append({'scene_id':request['scene_id'],'reason':'persisted_frame_aspect_mismatch'})
                        else:
                            im=im.convert('RGB');im.thumbnail((request['width'],round(request['width']*im.height/im.width)))
                            import io
                            encoded=io.BytesIO();im.save(encoded,'JPEG',quality=jpeg_quality,optimize=True)
                            blob=encoded.getvalue()
                            info={'source_time_s':request['requested_source_time_s'],'source_frame_index':None,
                                'timestamp_provenance':request['cache_timestamp_provenance'],
                                'capture_method':'persisted_analysis_scene_image','original_image_sha256':file_hash(request['cached_path']),
                                'cache_source_identity':'analysis_manifest_video_sha256',
                                'cache_image_integrity':request['cache_image_integrity'],
                                'width':im.width,'height':im.height,'timestamp_independently_verified':False}
                            cached_reused+=1
                except (OSError,ValueError) as exc:
                    cache_rejections.append({'scene_id':request['scene_id'],'reason':'persisted_frame_decode_failed','error':type(exc).__name__})
            if blob is None and media_path:
                if provider is None:
                    provider=SparseFrameProvider(media_path,metadata=metadata,max_frames=max_frames,max_bytes=max_bytes*2,
                        max_width=analysis_width,jpeg_quality=80)
                    provider.__enter__()
                with tempfile.TemporaryDirectory(prefix='.compact_frame_',dir=root) as temp:
                    output=Path(temp)/'frame.jpg'
                    info=provider(request['requested_source_time_s'],output)
                    if info.get('captured') and output.is_file():
                        image=cv2.imdecode(np.frombuffer(output.read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
                        if image is not None and image.size:
                            scale=min(1.,request['width']/image.shape[1])
                            if scale<1:image=cv2.resize(image,(round(image.shape[1]*scale),round(image.shape[0]*scale)),interpolation=cv2.INTER_AREA)
                            import io
                            encoded=io.BytesIO()
                            Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)).save(encoded,'JPEG',quality=jpeg_quality,optimize=True)
                            blob=encoded.getvalue();info.update(width=image.shape[1],height=image.shape[0])
                    if blob is None:missing.append({**request,'reason':info.get('reason','frame_encode_failed')})
            elif blob is None:
                missing.append({**request,'reason':'source_media_not_selected_no_cached_frame'})
            if blob is not None:add(request,blob,info)
        decoded=provider.decoded_frames if provider else 0
    finally:
        if provider:provider.close()
    frames.sort(key=lambda f:(f['source_time_s'],f['frame_id']))
    sheets=_write_contact_sheets(root,frames,width=contact_width,quality=contact_quality)
    result={'schema_version':'r6.3','source_sha256':metadata['sha256'],'frames':frames,'contact_sheets':sheets,
        'missing_requests':[{k:v for k,v in row.items() if k!='cached_path'} for row in missing],
        'cache_rejections':cache_rejections,
        'sampling_policy':{'navigation_width':navigation_width,'analysis_width':analysis_width,'source_aspect_preserved':True,
            'jpeg_quality':jpeg_quality,'jpeg_optimize':True,'contact_width':contact_width,'contact_quality':contact_quality,
            'scene_navigation':'one persisted or midpoint frame per detected scene',
            'piece_anchors':'first, middle, last of assembled source intervals; source gaps are never sampled as content',
            'adaptive_density':'additional piece interval anchors; source cuts split all coverage',
            'max_frames':max_frames,'max_image_bytes':max_bytes},
        'statistics':{'planned_requests':len(planned),'captured_frame_records':len(frames),'unique_image_files':len(physical),
            'identical_content_deduplicated':len(frames)-len(physical),'stored_image_bytes':stored_bytes,
            'duplicate_frame_requests_merged':merged_requests,'cached_scene_images_reused':sum(
                row.get('capture_method')=='persisted_analysis_scene_image' for row in frames),
            'cache_rejections':len(cache_rejections),'indexed_scene_count':len(scenes),
            'scene_ids_without_frames':sorted(seen_scenes-{row['scene_id'] for row in frames if row.get('scene_id')}),
            'new_decoder_reads':decoded,'continuous_visual_coverage_verified':False},
        'preview_approved':False,'publication_ready':False}
    (root/'06_VISUAL_ATLAS/atlas_index.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return result


def reprofile_shared_atlas(cache,destination,metadata,scenes,*,navigation_width=320,analysis_width=640,
                           jpeg_quality=62,contact_width=640,contact_quality=50,analysis_folder=None):
    """Re-encode an immutable harvested atlas into a fresh, smaller revision.

    This function opens only indexed images/JSONs, never the source video or a
    decoder. Cached scene timestamps are reconciled only when their original
    analysis manifest and original image hash match the recorded evidence.
    """
    import io
    from copy import deepcopy
    from PIL import Image,ImageDraw,ImageFont
    source_path=_safe_ancestors(cache)
    if source_path.is_file():
        index_path=source_path
        source_root=source_path.parent.parent if source_path.parent.name=='06_VISUAL_ATLAS' else source_path.parent
    else:
        source_root=source_path;index_path=source_root/'06_VISUAL_ATLAS/atlas_index.json'
    source_index=json.loads(_safe_ancestors(index_path).read_text(encoding='utf-8'))
    source_sha=metadata.get('sha256')
    if (not re.fullmatch(r'[a-f0-9]{64}',str(source_sha)) or source_index.get('source_sha256')!=source_sha
            or not _number(metadata.get('duration')) or metadata['duration']<=0):
        raise ValueError('compact_reprofile_source_identity_invalid')
    if (any(not isinstance(v,int) or isinstance(v,bool) or v<=0 for v in
            (navigation_width,analysis_width,contact_width)) or analysis_width<navigation_width
            or contact_width<320 or any(not isinstance(v,int) or isinstance(v,bool) or not 1<=v<=95
                for v in (jpeg_quality,contact_quality))):
        raise ValueError('compact_reprofile_dimensions_or_quality_invalid')
    root=_safe_ancestors(destination)
    if root==source_root or root.is_relative_to(source_root):
        raise ValueError('compact_reprofile_destination_inside_immutable_cache')
    atlas_root=root/'06_VISUAL_ATLAS'
    if atlas_root.exists() and any(atlas_root.iterdir()):
        raise FileExistsError('compact_reprofile_destination_already_contains_atlas')
    scene_by_id={row['scene_id']:row for row in scenes}
    original_root=_safe_ancestors(analysis_folder) if analysis_folder else None
    if original_root:
        original_manifest=json.loads(_safe_ancestors(original_root/'manifest.json').read_text(encoding='utf-8'))
        bound=original_manifest.get('video_sha256') or original_manifest.get('source_sha256') or original_manifest.get('sha256')
        if bound!=source_sha:
            raise ValueError('compact_reprofile_analysis_manifest_identity_mismatch')
    # Verify all indexed image bytes before creating the derived atlas.
    verified_images={};seen_ids=set()
    for row in source_index.get('frames') or []:
        if row.get('source_sha256')!=source_sha or not row.get('frame_id') or row['frame_id'] in seen_ids:
            raise ValueError('compact_reprofile_frame_identity_or_id_invalid')
        seen_ids.add(row['frame_id'])
        logical=str(_logical(row['path']));path=_safe_ancestors(source_root/logical)
        if not path.is_relative_to(source_root) or not path.is_file():
            raise ValueError('compact_reprofile_frame_asset_missing')
        if logical not in verified_images:
            verified_images[logical]=file_hash(path)
        if verified_images[logical]!=row.get('sha256'):
            raise ValueError('compact_reprofile_frame_checksum_mismatch')
        if not _number(row.get('source_time_s')) or not 0<=row['source_time_s']<metadata['duration']:
            raise ValueError('compact_reprofile_frame_timestamp_invalid')
    image_root=atlas_root/'frames';image_root.mkdir(parents=True,exist_ok=True)
    frames=[];physical={};by_id={};id_map={};corrections=[];unresolved=[]
    original_image_hashes={}
    for original in source_index.get('frames') or []:
        row=deepcopy(original);old_id=row['frame_id'];old_time=row['source_time_s']
        if row.get('capture_method')=='persisted_analysis_scene_image':
            scene=scene_by_id.get(row.get('scene_id')) or {}
            keyframe=scene.get('keyframe')
            actual_time,provenance=_cached_time(scene,keyframe) if scene.get('scene_id') and keyframe else (None,None)
            original_hash=None
            if original_root and keyframe:
                original_path=_safe_ancestors(original_root/str(_logical(keyframe)))
                if original_path.is_relative_to(original_root) and original_path.is_file():
                    if keyframe not in original_image_hashes:
                        original_image_hashes[keyframe]=file_hash(original_path)
                    original_hash=original_image_hashes[keyframe]
            if actual_time is not None and original_hash and original_hash==row.get('original_image_sha256'):
                row.update(source_time_s=actual_time,source_frame_index=None,timestamp_provenance=provenance,
                    timestamp_independently_verified=False,cache_source_identity='analysis_manifest_and_original_image_hash',
                    timestamp_correction_state='PERSISTED_SAMPLING_TIME_RECONCILED_NOT_DECODER_VERIFIED',
                    source_time_before_reprofile_s=old_time)
                corrections.append({'source_frame_id':old_id,'scene_id':row.get('scene_id'),
                    'old_source_time_s':old_time,'source_time_s':actual_time,'original_image_sha256':original_hash})
            else:
                row['timestamp_correction_state']='UNVERIFIED_ORIGINAL_CACHE_IDENTITY_OR_TIMESTAMP'
                unresolved.append({'source_frame_id':old_id,'scene_id':row.get('scene_id'),
                    'reason':'original_cached_image_identity_or_sampling_timestamp_not_verified'})
        width=analysis_width if (row.get('width',0)>480 or any(
            str(reason).startswith('piece_') for reason in row.get('sampling_reasons') or [])) else navigation_width
        with Image.open(source_root/str(_logical(row['path']))) as image:
            image=image.convert('RGB')
            image.thumbnail((width,max(1,round(width*image.height/image.width))),Image.Resampling.LANCZOS)
            output=io.BytesIO();image.save(output,'JPEG',quality=jpeg_quality,optimize=True)
            blob=output.getvalue();row.update(width=image.width,height=image.height)
        checksum=hashlib.sha256(blob).hexdigest()
        if checksum not in physical:
            target=image_root/(checksum+'.jpg');target.write_bytes(blob)
            physical[checksum]=target.relative_to(root).as_posix()
        frame_id='FRAME_'+hashlib.sha256((source_sha+':'+format(row['source_time_s'],'.6f')+':'+checksum).encode()).hexdigest()[:20]
        id_map[old_id]=frame_id
        row.update(frame_id=frame_id,path=physical[checksum],sha256=checksum,
            original_frame_id=old_id,original_frame_sha256=original['sha256'],
            jpeg_quality=jpeg_quality,reprofile_width_limit=width,final_render_frame=False)
        if frame_id in by_id:
            previous=by_id[frame_id]
            previous['piece_ids']=sorted(set((previous.get('piece_ids') or [])+(row.get('piece_ids') or [])))
            previous['sampling_reasons']=sorted(set((previous.get('sampling_reasons') or [])+(row.get('sampling_reasons') or [])))
            previous.setdefault('merged_source_frame_ids',[previous['original_frame_id']]).append(old_id)
        else:
            by_id[frame_id]=row;frames.append(row)
    frames.sort(key=lambda row:(row['source_time_s'],row['frame_id']))
    sheets=_write_contact_sheets(root,frames,width=contact_width,quality=contact_quality)
    result={**deepcopy(source_index),'frames':frames,'contact_sheets':sheets,'source_frame_id_map':id_map,
        'sampling_policy':{**deepcopy(source_index.get('sampling_policy') or {}),
            'navigation_width':navigation_width,'analysis_width':analysis_width,'source_aspect_preserved':True,
            'jpeg_quality':jpeg_quality,'jpeg_optimize':True,'contact_width':contact_width,
            'contact_quality':contact_quality,'reprofile_without_new_source_reads':True},
        'reprofile':{'source_atlas_sha256':file_hash(index_path),'source_frame_count':len(source_index.get('frames') or []),
            'navigation_width':navigation_width,'analysis_width':analysis_width,'jpeg_quality':jpeg_quality,
            'contact_width':contact_width,'contact_quality':contact_quality,'new_decoder_reads':0,
            'cached_timestamp_reconciliations':corrections,'unresolved_cached_timestamps':unresolved,
            'original_cache_mutated':False,'all_source_frame_ids_preserved_or_mapped':len(id_map)==len(seen_ids)},
        'statistics':{**deepcopy(source_index.get('statistics') or {}),'captured_frame_records':len(frames),
            'unique_image_files':len(physical),'identical_content_deduplicated':len(frames)-len(physical),
            'source_cache_decoder_reads':(source_index.get('statistics') or {}).get('new_decoder_reads'),
            'new_decoder_reads':0,'stored_image_bytes':sum((root/path).stat().st_size for path in physical.values()),
            'contact_sheet_bytes':sum((root/row['path']).stat().st_size for row in sheets),
            'timestamp_reconciliations':len(corrections),'unresolved_cached_timestamps':len(unresolved),
            'indexed_scene_count':len(scenes),
            'scene_ids_without_frames':sorted(set(scene_by_id)-{row['scene_id'] for row in frames if row.get('scene_id')}),
            'continuous_visual_coverage_verified':False},'preview_approved':False,'publication_ready':False}
    (atlas_root/'atlas_index.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    return result
