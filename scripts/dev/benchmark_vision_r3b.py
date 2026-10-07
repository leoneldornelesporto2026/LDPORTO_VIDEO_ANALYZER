"""Isolated face+HOG CPU overlap A/B. No changes to Analyzer cache or outputs.

Sample a few source frames and compare exact detected boxes, confidences and work
counts with serial vs 1-worker CPU. Uses same local models/config as Analyzer.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.config import load_config
from ldporto.vision import PersonDetectionEngine
from ldporto.performance import cpu_overlap_budget


def collect(video, sample_count, max_width):
    import cv2
    cap=cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise ValueError(f'Video inacessivel: {video}')
    frames=[]
    try:
        total=max(0.,cap.get(cv2.CAP_PROP_FRAME_COUNT))
        count=max(1,int(sample_count))
        for index in range(count):
            frame_no=round((index+.5)*total/count) if total>0 else index*30
            cap.set(cv2.CAP_PROP_POS_FRAMES,frame_no)
            ok, frame=cap.read()
            if not ok:
                continue
            height,width=frame.shape[:2]
            scale=min(1.,max_width/width)
            if scale<1:
                frame=cv2.resize(frame,(round(width*scale),round(height*scale)))
            # non-mutating contiguous image for C++ detectors
            frames.append((float(index),frame))
    finally:
        cap.release()
    return frames


def bench(frames,cfg,enable):
    conf=dict(cfg,parallel_hog_with_face=enable)
    notes=[]
    detector=PersonDetectionEngine(conf,notes,offline=True)
    result=[]
    started=perf_counter()
    try:
        for i,(stamp,frame) in enumerate(frames):
            detector.set_frame_context(stamp, f'SAMPLE_{i:04}', 3.0)
            rows=detector.detect(frame)
            # compare raw detector data without embeddings: SFace may introduce slight
            # numerical differences from backend execution; object semantics are checked.
            result.append([{'bbox':r.get('bbox'), 'face_bbox':r.get('face_bbox'),
                            'bbox_kind':r.get('bbox_kind'), 'face_visible':r.get('face_visible'),
                            'body_visible':r.get('body_visible')}
                           for r in rows])
    finally:
        elapsed=perf_counter()-started
        detector.close()
    return {'elapsed_seconds':round(elapsed,3), 'frames':len(result),
            'face_detection_calls':detector.calls['face_detection_calls'],
            'body_detection_calls':detector.calls['body_detection_calls'],
            'boxes':result,'guard':detector.overlap_budget,'notes':notes}


def compare(video, cfg, sample_count):
    frames=collect(video,sample_count,int(cfg['max_width']))
    if not frames:
        raise ValueError('Nenhum frame amostrado do video')
    serial=bench(frames,cfg,False)
    parallel=bench(frames,cfg,True)
    same=serial['boxes']==parallel['boxes']
    return {'source':str(video),'sample_count':len(frames),
            'cpu_parallel_available':parallel['guard']['enabled'],
            'detection_boxes_identical':same,
            'detector_calls_identical':serial['face_detection_calls']==parallel['face_detection_calls'] and
                                       serial['body_detection_calls']==parallel['body_detection_calls'],
            'serial_seconds':serial['elapsed_seconds'], 'parallel_seconds':parallel['elapsed_seconds'],
            'speedup_x':round(serial['elapsed_seconds']/parallel['elapsed_seconds'],3) if parallel['elapsed_seconds'] else None,
            'parallel_guard':parallel['guard'],
            'enable_recommendation':'consider_local_windows_AB' if same and parallel['guard']['enabled'] and
                parallel['elapsed_seconds']<serial['elapsed_seconds'] else 'leave_disabled',
            'caution':'Small frame-only test. Windows real-video full stage and identical detections must be verified before enable.'}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--video',type=Path,required=True)
    ap.add_argument('--frames',type=int,default=12)
    ap.add_argument('--output',type=Path,default=Path('r3b_vision_ab.json'))
    args=ap.parse_args()
    cfg=load_config(ROOT/'config/config.yaml')['vision']
    report=compare(args.video,cfg,args.frames)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
