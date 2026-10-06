"""Generate toy visuals + explicit annotations; never claims learned face/ASR accuracy."""
from pathlib import Path
import argparse
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/tests'))
from director_fixtures import fixture, turn


def generate(folder):
    import cv2
    import numpy as np
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    metadata, vision, shots = fixture(24, pair=True, distant=True, cuts=(8,16))
    shots[0]['shot_type'] = 'two_shot'
    shots[1]['shot_type'] = 'medium'
    shots[2]['shot_type'] = 'broll'
    by_time = {}
    for o in vision['observations']:
        if 8 <= o['time'] < 16 and o['person_id'] == 'PERSON_A':
            shift = (o['time']-8)*.02
            for name in ('bbox','face_bbox'):
                # fixture's bbox/face_bbox may share identity; replace independently.
                o[name] = dict(o[name])
                o[name]['x'] = .265+shift
            o['center'] = o['head_center'] = {'x':.3+shift,'y':.285}
        by_time.setdefault(o['time'], []).append(o)
    path = folder/'synthetic_director_silent.mp4'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 4, (640,360))
    if not writer.isOpened():
        raise RuntimeError('MP4 writer unavailable')
    try:
        for f in vision['frames']:
            frame = np.zeros((360,640,3),dtype=np.uint8)
            frame[:] = (36,26,20)
            if f['time'] < 16:
                for o in by_time[f['time']]:
                    b = o['face_bbox']; x,y = int((b['x']+b['width']/2)*640),int((b['y']+b['height']/2)*360)
                    color = (70,170,250) if o['person_id']=='PERSON_A' else (210,130,80)
                    cv2.circle(frame,(x,y),25,color,-1)
                    cv2.rectangle(frame,(x-28,y+26),(x+28,y+110),color,-1)
                    cv2.putText(frame,o['person_id'],(x-50,y+135),cv2.FONT_HERSHEY_SIMPLEX,.4,(255,255,255),1)
            else:
                cv2.putText(frame,'B-ROLL / LOGO - SYNTHETIC',(50,180),cv2.FONT_HERSHEY_SIMPLEX,.7,(255,255,255),2)
            cv2.putText(frame,f'SYNTHETIC ANNOTATIONS - {f["time"]:.2f}s',(12,25),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1)
            writer.write(frame)
    finally:
        writer.release()
    # Observation annotations must match the drawn B-roll, never retain invisible people.
    vision['observations'] = [o for o in vision['observations'] if o['time'] < 16]
    for f in vision['frames']:
        if f['time'] >= 16:
            f['visible_people'] = []
    metadata.update(width=640,height=360,fps=4)
    turns = [turn(i,i+1,'PERSON_A' if i%2==0 else 'PERSON_B') for i in range(8)]
    turns += [turn(8,16), turn(16,24,person=None)]
    artifact={'synthetic':True,'annotation_source':'explicit_fixture_not_model_output',
              'metadata':metadata,'vision':vision,'shots':shots,'active_speaker':turns}
    (folder/'synthetic_annotations.json').write_text(json.dumps(artifact,indent=2),encoding='utf-8')
    return path


if __name__ == '__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',required=True)
    print(generate(ap.parse_args().output))
