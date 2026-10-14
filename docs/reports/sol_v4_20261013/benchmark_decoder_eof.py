"""Check the actual original source EOF using bounded sequential CPU decodes."""
from pathlib import Path
import hashlib
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))

def main():
    import cv2
    import numpy as np
    from scenedetect import open_video, FrameTimecode
    from ldporto.runtime_metrics import resource_snapshot
    source=ROOT/'input/youtube/7laRa_F3FbA/7laRa_F3FbA.mp4'
    cap=cv2.VideoCapture(str(source))
    fps=cap.get(cv2.CAP_PROP_FPS)
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    start=max(0,total-120)
    cap.release()
    measurements={}
    final_reference=None
    for backend,threads in [('opencv',None),('pyav','SLICE'),('pyav','AUTO')]:
        started=time.perf_counter()
        kwargs={} if backend=='opencv' else {'threading_mode':threads,'suppress_output':False}
        video=open_video(str(source),backend=backend,**kwargs)
        rows=[]
        final_frame=None
        try:
            video.seek(FrameTimecode(start, fps=fps))
            for _ in range(240):
                frame=video.read()
                if frame is False or frame is None:break
                final_frame=frame
                stamp=video.position.get_seconds()
                rows.append({'pts_seconds':stamp,'frame_number':video.frame_number,
                             'shape':list(frame.shape),'sha256':hashlib.sha256(frame.tobytes()).hexdigest()})
            else:raise RuntimeError('EOF was not reached within the bounded read budget')
        finally:
            if getattr(video,'_container',None) is not None:video._container.close()
            if getattr(video,'_cap',None) is not None:video._cap.release()
        if final_reference is None:final_reference=final_frame
        delta=final_frame.astype(np.int16)-final_reference.astype(np.int16)
        pixels={'max_absolute_channel_difference':int(np.abs(delta).max()),
                'mean_absolute_channel_difference':float(np.abs(delta).mean()),
                'rms_channel_difference':float(np.sqrt(np.mean(delta.astype(float)**2))),
                'fraction_changed_channels':float(np.mean(delta!=0))}
        measurements[backend+'_'+str(threads)]={'wall_seconds':time.perf_counter()-started,
            'frames':rows,'count':len(rows),'monotonic_pts':all(b['pts_seconds']>a['pts_seconds'] for a,b in zip(rows,rows[1:])),
            'resources':resource_snapshot(),'final_frame_pixel_difference_from_opencv':pixels}
    reference=measurements['opencv_None']['frames']
    comparisons={}
    for mode,measurement in measurements.items():
        rows=measurement['frames']
        comparisons[mode]={'same_frame_count':len(rows)==len(reference),
                          'same_final_pixel_sha256':bool(rows and reference and rows[-1]['sha256']==reference[-1]['sha256']),
                          'final_pts_delta_seconds':rows[-1]['pts_seconds']-reference[-1]['pts_seconds'] if rows and reference else None}
    record={'source':str(source),'source_frame_count':total,'fps':fps,'requested_start_frame':start,
            'measurements':measurements,'comparisons':comparisons,
            'scope':'EOF and pixel/time equivalence only; CPU decoder; no inference or scene detector.'}
    (REPORT/'decoder_eof_quantified.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'comparisons':comparisons,'counts':{k:v['count'] for k,v in measurements.items()},
                     'pixels':{k:v['final_frame_pixel_difference_from_opencv'] for k,v in measurements.items()}},ensure_ascii=False))

if __name__=='__main__':main()
