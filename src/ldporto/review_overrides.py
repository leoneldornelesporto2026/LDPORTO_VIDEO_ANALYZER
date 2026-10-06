"""Non-destructive manual override contract and dependency invalidation."""
from copy import deepcopy
from datetime import datetime, timezone

ALLOWED={'person_label','speaker_person_mapping','focus','layout','forbid_split','forbid_zoom','max_zoom','force_source','candidate_approve','candidate_reject','candidate_boundary'}
INVALIDATES={
 'person_label':['speaker_person_mapping','active_speaker','global_camera_planner','camera_director','handoff'],
 'speaker_person_mapping':['active_speaker','global_camera_planner','camera_director','handoff'],
 'focus':['camera_director','handoff'], 'layout':['camera_director','handoff'],
 'forbid_split':['global_camera_planner','camera_director','handoff'], 'forbid_zoom':['camera_director','handoff'],
 'max_zoom':['camera_director','handoff'], 'force_source':['global_camera_planner','camera_director','handoff'],
 'candidate_approve':['second_curation_package'], 'candidate_reject':['second_curation_package'],
 'candidate_boundary':['second_curation_package','handoff'],
}

def new_document():
    return {'schema_version':'1.0','overrides':[],'redo_stack':[]}

def add_override(document, kind, start, end, value, version=1):
    if kind not in ALLOWED or not isinstance(start,(int,float)) or not isinstance(end,(int,float)) or not start < end:
        raise ValueError('Override inválido.')
    out=deepcopy(document or new_document())
    out.setdefault('overrides',[]).append({'origin':'manual','timestamp':datetime.now(timezone.utc).isoformat(),
        'interval':{'start':float(start),'end':float(end)},'kind':kind,'value':value,'version':version})
    out['redo_stack']=[]
    return out

def undo(document):
    out=deepcopy(document); rows=out.setdefault('overrides',[])
    if rows: out.setdefault('redo_stack',[]).append(rows.pop())
    return out

def redo(document):
    out=deepcopy(document); redo_rows=out.setdefault('redo_stack',[])
    if redo_rows: out.setdefault('overrides',[]).append(redo_rows.pop())
    return out

def reset(document):
    return new_document()

def invalidated_stages(document):
    result=[]
    for row in (document or {}).get('overrides',[]):
        for stage in INVALIDATES.get(row.get('kind'),[]):
            if stage not in result: result.append(stage)
    return result
