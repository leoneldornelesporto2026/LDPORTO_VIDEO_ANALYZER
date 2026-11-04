"""Translate the existing Director keyframes to the installed Curator renderer.

This adapter makes no editorial decisions and never clamps unsupported zooms.
The original keyframes and approximation policy remain inspectable.
"""
from copy import deepcopy
import math

from .core import digest


def _at(keys,t):
    if t<=keys[0]['time']:
        return keys[0]
    if t>=keys[-1]['time']:
        return keys[-1]
    for left,right in zip(keys,keys[1:]):
        if left['time']<=t<=right['time']:
            f=(t-left['time'])/(right['time']-left['time'])
            return {'center':[left['center'][i]+f*(right['center'][i]-left['center'][i]) for i in (0,1)],
                    'zoom':left['zoom']+f*(right['zoom']-left['zoom'])}
    raise ValueError('camera_interpolation_unresolved')


def _native_pairs(keys,a,b,width,height,minimum,error_limit=.75):
    """Fit native smoothstep scale; bound error at polynomial extrema, not logs."""
    result=[]
    def fit(left,right,depth=0):
        p,q=_at(keys,left),_at(keys,right); length=right-left
        points={left,right,*[k['time'] for k in keys if left<k['time']<right]}
        dz=q['zoom']-p['zoom']
        if abs(dz)>1e-12:
            for first,last in zip(keys,keys[1:]):
                if first['time']==last['time']:
                    continue
                slope=(last['zoom']-first['zoom'])/(last['time']-first['time'])
                disc=1-4*slope*length/(6*dz)
                if disc>=0:
                    for f in ((1-math.sqrt(disc))/2,(1+math.sqrt(disc))/2):
                        t=left+f*length
                        if max(left,first['time'])<t<min(right,last['time']):
                            points.add(t)
        worst=(0.,left)
        for t in sorted(points):
            source=_at(keys,t); f=(t-left)/length; ease=f*f*(3-2*f)
            scale_error=abs(source['zoom']-(p['zoom']+dz*ease))*height
            error=max(abs(source['center'][i]-(p['center'][i]+f*(q['center'][i]-p['center'][i])))*s+scale_error
                      for i,s in ((0,width),(1,height)))
            worst=max(worst,(error,t))
        if worst[0]<=error_limit:
            result.append((left,right,p,q,worst[0]));return
        splits=[t for t in points if left+minimum<=t<=right-minimum]
        if depth>=12 or not splits or len(result)>=24:
            raise ValueError('native_curve_error_or_segment_budget_exceeded')
        split=min(splits,key=lambda t:abs(t-worst[1]))
        fit(left,split,depth+1);fit(split,right,depth+1)
    fit(a,b)
    return result


def build_curator_camera_plan(timeline,start,end,metadata,*,renderer_max_zoom=1.05):
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (start,end)) or not 0<=start<end<=metadata['duration']:
        raise ValueError('curator_adapter_invalid_source_interval')
    segments=[]; rejected=[]; original=[]; cursor=start
    def fallback(a,b,reason,shot=None):
        if b>a:
            segments.append({'start':a-start,'end':b-start,'mode':'full_frame_blur',
                'source_shot_id':shot,'reason':reason,'source_start':a,'source_end':b})
    for row in sorted(timeline,key=lambda r:r['start']):
        a,b=max(start,row['start']),min(end,row['end'])
        if a>=b:
            continue
        if a<cursor-1e-6:
            raise ValueError('curator_adapter_overlapping_director_intervals')
        fallback(cursor,a,'source_timeline_gap')
        cursor=b
        keys=sorted((deepcopy(k) for k in (row.get('camera') or {}).get('keyframes',[]) if
                     isinstance(k.get('time'),(int,float)) and k.get('center') and isinstance(k.get('zoom'),(int,float))),key=lambda k:k['time'])
        original.append({'director_id':row.get('director_id'),'start':a,'end':b,'camera':deepcopy(row.get('camera')),
                         'crop':deepcopy(row.get('crop')),'camera_mode':row.get('camera_mode')})
        reason=None
        if row.get('layout')!='single_person' or (row.get('crop') or {}).get('safe') is not True or not row.get('focus_person'):
            reason='source_preserve_or_unverified_subject_geometry'
        elif len(keys)<2 or any(not math.isfinite(k['zoom']) or len(k['center'])!=2 or
             any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in k['center']) for k in keys):
            reason='executable_keyframes_unavailable'
        elif any(not 1<=k['zoom']<=renderer_max_zoom for k in keys):
            reason='renderer_zoom_envelope_exceeded_no_clamp'
        if reason:
            fallback(a,b,reason,row.get('source_shot_id'))
            rejected.append({'director_id':row.get('director_id'),'start':a,'end':b,'reason':reason})
            continue
        try:
            pairs=_native_pairs(keys,a,b,metadata['width'],metadata['height'],1/max(1,metadata.get('fps') or 24))
        except ValueError as exc:
            fallback(a,b,str(exc),row.get('source_shot_id'))
            rejected.append({'director_id':row.get('director_id'),'start':a,'end':b,'reason':str(exc)})
            continue
        for left,right,p,q,error in pairs:
            # Native renderer uses smoothstep scale per segment. Centers use
            # linear interpolation. Both policies are explicit in this plan.
            segments.append({'start':left-start,'end':right-start,'source_start':left,'source_end':right,
                'mode':'crop','motion_follow':True,'target_person_id':row['focus_person'],
                'director_id':row.get('director_id'),'source_shot_id':row.get('source_shot_id'),
                'center_x_start':p['center'][0],'center_x_end':q['center'][0],
                'center_y_start':p['center'][1],'center_y_end':q['center'][1],
                'zoom_start':p['zoom'],'zoom_end':q['zoom'],'subject_screen_y':.5,
                'motion_easing':'linear','zoom_transition_duration':right-left,
                'mapping_max_source_pixel_error':error,
                'reason':'existing_director_keyframes_compatible_with_curator_envelope'})
    fallback(cursor,end,'source_timeline_gap')
    if not segments:
        fallback(start,end,'source_timeline_unavailable')
    return {'schema_version':'r6.2','mode':'adaptive_timeline','segments':segments,
        'motion_segments':sum(s.get('motion_follow') is True for s in segments),
        'source_interval':{'start':start,'end':end},'segment_timebase':'clip_relative_seconds',
        'source_timeline_sha256':digest(timeline),'source_keyframes':original,'rejected':rejected,
        'renderer_owner':'VIDEO_CURATOR','renderer_zoom_envelope':[1.,renderer_max_zoom],
        'interpolation_mapping':'source_piecewise_linear_to_native_piecewise_smoothstep_zoom_linear_centers',
        'simplification':{'max_source_pixel_error':.75,'extrema_checked':'piecewise_polynomial_derivative_roots',
                          'minimum_segment_seconds':1/max(1,metadata.get('fps') or 24),
                          'original_keyframes_preserved':True},
        'new_camera_engine':False,'consumed_by_renderer':False,'final_frames_verified':False,
        'preview_approved':False,'publication_ready':False}
