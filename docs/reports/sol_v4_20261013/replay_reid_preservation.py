"""Recompute only Re-ID from immutable existing visual evidence, without inference."""
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def project(reference,value):
    if isinstance(reference,dict):return {key:project(item,value[key]) for key,item in reference.items()}
    if isinstance(reference,list):
        if len(value)!=len(reference):raise ValueError('legacy_collection_count_changed')
        return [project(old,new) for old,new in zip(reference,value)]
    return value

def main():
    from ldporto.core import read_json,digest
    from ldporto.config import load_config
    from ldporto.person_reid import build_person_identities
    base=ROOT/'analysis/video_1da839aad175/cache/0231c20cfd8147d9'
    old=read_json(base/'08_person_reid.json')
    vision=read_json(base/'07_people_tracking.json')['data']
    config=load_config(ROOT/'config/config.yaml')['vision']
    keys=('reid_threshold','reid_margin','track_max_gap_seconds','tracklet_min_visual_seconds',
          'tracklet_min_observations','identity_min_visual_seconds','reid_candidate_limit',
          'micro_reid_threshold','micro_reid_margin')
    cfg={key:config[key] for key in keys}
    if digest(cfg)!=old['config_hash']:raise ValueError('Re-ID config differs from the original producer')
    started=time.perf_counter()
    fresh=build_person_identities(vision,cfg)['data']
    seconds=time.perf_counter()-started
    checks={}
    for key,value in old['data'].items():
        before=digest(value); after=digest(project(value,fresh[key]))
        checks[key]={'before_sha256':before,'after_sha256':after,'identical':before==after}
    result={'scope':'Re-ID only on saved original visual observations; no media decode, model, GPU, ASR, Qwen or full pipeline.',
            'config_sha256':old['config_hash'],'current_builder_seconds':seconds,
            'legacy_fields':checks,'outcome_diagnostics':fresh.get('outcome_diagnostics'),
            'persistent_person_count_before':old['data']['metrics']['persistent_person_count'],
            'persistent_person_count_after':fresh['metrics']['persistent_person_count'],
            'fragmentation_proxy_before':old['data']['metrics']['identity_fragmentation_score'],
            'fragmentation_proxy_after':fresh['metrics']['identity_fragmentation_score'],
            'human_identity_accuracy':None,'id_switches_ground_truth':None}
    (REPORT/'reid_preservation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('outcome_diagnostics','legacy_fields')}))
    if not all(row['identical'] for row in checks.values()):raise SystemExit('Re-ID legacy output changed')

if __name__=='__main__':main()
