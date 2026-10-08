"""S6 Camera Director audit on saved stages; no GPU/video reprocessing.

  python scripts/dev/audit_camera_s6.py C:/analyses/MY_RUN --output C:/analyses/s6_audit
  python scripts/dev/audit_camera_s6.py C:/analysis_review.zip --output C:/s6_audit
  python scripts/dev/audit_camera_s6.py C:/analysis --output C:/s6_audit --replay

--replay requires cached metadata, visual observations, source shots and active
speaker intervals. It NEVER recomputes face embeddings, ASR or media decoding.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.analysis_quality import camera_quality_metrics
from ldporto.camera_director import build_camera_director


def load(source, *names):
    source=Path(source)
    for name in names:
        if source.is_dir():
            hits=sorted(source.rglob(name),key=lambda p:(len(p.parts),str(p)))
            if hits:
                return json.loads(hits[0].read_text(encoding='utf-8-sig'))
        elif source.suffix.lower()=='.zip':
            with zipfile.ZipFile(source) as zipfile_:
                hits=sorted((p for p in zipfile_.namelist() if p==name or p.endswith('/'+name)),key=lambda p:(p.count('/'),p))
                if hits:
                    return json.loads(zipfile_.read(hits[0]).decode('utf-8-sig'))
    return None


def bare(value):
    return value.get('data',value) if isinstance(value,dict) else value


def replay(source):
    metadata=bare(load(source,'01_metadata.json','metadata.json') or {})
    vision=bare(load(source,'08_person_reid.json','07_people_tracking.json') or {})
    if not vision.get('observations'):
        analysis=bare(load(source,'analysis.json') or {})
        vision={'frames':(analysis.get('video_analysis') or {}).get('frame_samples') or [],
                'observations':analysis.get('people_observations') or [],
                'broadcast_graphics':analysis.get('broadcast_graphics') or {}}
        metadata=metadata or analysis.get('metadata',{})
    shots=bare(load(source,'11_shots.json','shots.json') or {})
    shots=shots.get('shots',shots.get('timeline',[])) if isinstance(shots,dict) else shots
    active=bare(load(source,'10_active_speaker.json','active_speaker.json') or {})
    active=active.get('intervals',active.get('active_speaker',[])) if isinstance(active,dict) else active
    motion=bare(load(source,'09_person_motion.json','person_motion.json') or {})
    motion=motion.get('people',[]) if isinstance(motion,dict) else motion
    semantic=bare(load(source,'15_semantic.json') or {})
    understanding=bare(load(source,'16_understanding.json') or {})
    camera_plan=bare(load(source,'18b_global_camera_planner.json') or {})
    if not metadata.get('duration') or not vision.get('frames') or not isinstance(shots,list) or not shots:
        raise ValueError('Replay requer 01_metadata, 08_person_reid/frames e 11_shots reais. Não inventar amostras.')
    if not isinstance(active,list):
        raise ValueError('Replay requer lista de intervalos de 10_active_speaker, mesmo quando sem associação confirmada.')
    return build_camera_director(metadata,vision,shots,active,motion,
        questions_answers=semantic.get('questions_answers',[]),
        story_arcs=understanding.get('story_arcs',[]),
        main_moments=understanding.get('main_moments',[]), camera_plan=camera_plan)['data']


def assess(director, duration=None, preview=None):
    timeline=director.get('timeline') or director.get('camera_director_timeline') or []
    duration=duration or max((row['end'] for row in timeline),default=0)
    measured=camera_quality_metrics(timeline,duration)
    metrics={**(director.get('metrics') or {}),**measured}
    roles=Counter()
    seconds=Counter()
    blocked=Counter()
    for row in timeline:
        role=row.get('camera_evidence_role') or 'NOT_MEASURED'
        roles[role]+=1
        seconds[role]+=row['end']-row['start']
        for reason in (row.get('decision') or {}).get('reasons',[]):
            blocked[reason]+=1
    zoom=metrics.get('zoom_zero_root_cause')
    if metrics.get('zoom_event_count',0)==0 and zoom is None:
        zoom='INSUFFICIENT_STAGE_DIAGNOSTICS_FOR_CAUSE'
    causes=[]
    if metrics.get('resolved_focus_coverage',0)<.10:
        causes.append('FOCUS_UNDER_10_PERCENT_REQUIRES_VISUAL_AND_ACTIVE_SPEAKER_AUDIT')
    if not metrics.get('focus_evidence_funnel'):
        causes.append('EARLIER_RUN_NO_PREDECISION_CAUSAL_FUNNEL')
    if metrics.get('zoom_event_count',0)==0:
        causes.append('ZERO_ZOOM_DELIVERED_REVIEW_ZOOM_FUNNEL')
    if preview and any(x.get('issue_type')=='UNEXPECTED_BORDER' for x in preview.get('issues', [])):
        causes.append('PREVIEW_BORDER_WARNING_REQUIRES_RENDERED_FRAME_OR_SOURCE_MATTE_CHECK')
    return {'schema_version':'S6', 'duration_seconds':duration,
            'focus':{key:metrics.get(key) for key in ('resolved_focus_coverage','known_speaker_focus_fraction',
                'dominant_face_coverage','camera_director_coverage','camera_director_visual_sample_coverage',
                'focus_evidence_funnel','evaluation_windows_without_visual_sample','evaluation_windows_with_face_evidence',
                'evaluation_windows_with_grounded_speaker','crop_preflight_blocked_windows','visual_only_fallback_windows')},
            'zoom':{key:metrics.get(key) for key in ('editorial_beat_raw_windows','editorial_beat_eligible_windows',
                'editorial_beat_suppressed_due_to_cut_or_overlap','editorial_beat_without_focus_windows',
                'editorial_beat_with_speaker_focus_windows','zoom_opportunity_window_count','zoom_request_window_count',
                'zoom_accepted_event_count','zoom_delivered_event_count','zoom_aborted_window_count',
                'zoom_block_reason_counts','zoom_zero_root_cause')},
            'camera':{key:metrics.get(key) for key in ('director_switches_per_minute','switches_suppressed',
                'deadzone_suppressed_moves','split_fraction','two_shot_fraction','full_frame_fraction',
                'split_preflight_rejected_windows')},
            'roles_windows':dict(roles),'roles_duration_seconds':dict(seconds),
            'timeline_reason_counts':dict(blocked), 'review_flags':causes,
            'preview_border':{'issues':[x for x in (preview or {}).get('issues',[]) if x.get('issue_type')=='UNEXPECTED_BORDER']},
            'scope':'saved_stage_diagnostics_no_live_video_validation'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--replay',action='store_true',help='Director-only replay using saved data (no decoding)')
    args=parser.parse_args(argv)
    if args.replay:
        director=replay(args.source)
    else:
        director=bare(load(args.source,'19_camera_director.json') or {})
        if not director:
            analysis=bare(load(args.source,'analysis.json') or {})
            director={'timeline':analysis.get('camera_director_timeline',[]),
                      'metrics':(analysis.get('video_understanding') or {}).get('camera_director',{}).get('metrics') or analysis.get('analysis_quality',{})}
        if not director.get('timeline'):
            raise ValueError('Não encontrou 19_camera_director.json ou camera_director_timeline no analysis.json; use --replay quando houver stages completos.')
    preview=bare(load(args.source,'19b_preview_verifier.json','preview_validation.json') or {})
    preview=preview.get('validation',preview) if isinstance(preview,dict) else {}
    report=assess(director,preview=preview)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'camera_s6_diagnostic.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.replay:
        (args.output/'camera_director_s6_timeline.json').write_text(json.dumps(director['timeline'],ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'focus':report['focus']['resolved_focus_coverage'],
                      'zoom_zero_root_cause':report['zoom']['zoom_zero_root_cause'],
                      'review_flags':report['review_flags'],
                      'report':str(args.output/'camera_s6_diagnostic.json')},ensure_ascii=False,indent=2))
    return report

if __name__=='__main__':
    main()
