"""Compare all legacy visual fields, excluding explicitly variable telemetry."""
from pathlib import Path
import json

REPORT = Path(__file__).resolve().parent

BACKEND_VARIABLE_FIELDS = {'benchmark_frame_seconds','body_inference_seconds','peak_vram_mb',
                           'vram_free_min_mb','vram_free_max_mb'}
PREFLIGHT_VARIABLE_FIELDS = {'free_vram_mb','measured_at_utc','query_seconds'}

def stable_visual(value):
    if isinstance(value,list):return [stable_visual(row) for row in value]
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            if key=='body_backend_execution' and isinstance(item,dict):
                item={k:v for k,v in item.items() if k not in BACKEND_VARIABLE_FIELDS}
                preflight=item.get('device_preflight')
                if isinstance(preflight,dict):
                    item={**item,'device_preflight':{k:v for k,v in preflight.items() if k not in PREFLIGHT_VARIABLE_FIELDS}}
            result[key]=stable_visual(item)
        return result
    return value

def project(reference, value):
    if isinstance(reference, dict):
        return {key:project(item, value[key]) for key,item in reference.items()}
    if isinstance(reference, list):
        if not isinstance(value, list) or len(reference)!=len(value):
            raise ValueError('legacy_collection_count_changed')
        return [project(item,new) for item,new in zip(reference,value)]
    return value

def compare(before='before_visual', after='after_visual'):
    from sys import path
    path.insert(0,str(REPORT.parents[2]/'src'))
    from ldporto.core import digest
    old=json.loads((REPORT/before/'vision.json').read_text(encoding='utf-8'))['data']
    new=json.loads((REPORT/after/'vision.json').read_text(encoding='utf-8'))['data']
    reference=stable_visual({k:v for k,v in old.items() if k not in ('performance','quality')})
    new=stable_visual(new)
    errors=[]
    records={}
    for key,value in reference.items():
        try:
            projected=project(value,new[key])
            records[key]={'legacy_sha256':digest(value),'after_projected_sha256':digest(projected),
                          'identical':digest(value)==digest(projected),'count':len(value) if isinstance(value,list) else None}
        except (KeyError,ValueError,TypeError) as exc:
            errors.append({'collection':key,'error':str(exc)})
    a=json.loads((REPORT/before/'result.json').read_text(encoding='utf-8'))
    b=json.loads((REPORT/after/'result.json').read_text(encoding='utf-8'))
    same_work=a['clip_sha256']==b['clip_sha256'] and a['configuration_sha256']==b['configuration_sha256']
    result={'same_source_and_configuration':same_work,'legacy_visual_fields':records,'errors':errors,
            'scene_boundaries_identical':a['scene_data']['scenes']==b['scene_data']['scenes'],
            'scene_seconds_before':a['scene_seconds'],'scene_seconds_after':b['scene_seconds'],
            'vision_seconds_before':a['vision_seconds'],'vision_seconds_after':b['vision_seconds'],
            'vision_speedup_x':a['vision_seconds']/b['vision_seconds'] if same_work else None,
            'peak_ram_bytes_before':a['resources']['peak_process_memory_bytes'],
            'peak_ram_bytes_after':b['resources']['peak_process_memory_bytes'],
            'precision_recall':'NOT_MEASURED_no_human_identity_or_speaker_ground_truth',
            'excluded_variable_backend_fields':sorted(BACKEND_VARIABLE_FIELDS),
            'excluded_variable_preflight_fields':sorted(PREFLIGHT_VARIABLE_FIELDS),
            'scope':'One cold-process pair. All legacy geometry/IDs/embeddings/landmarks/quality gates compared. Only timings, sampled free memory and query timestamps excluded; human correctness not asserted.'}
    (REPORT/'perception_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':compare()
