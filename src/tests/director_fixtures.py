"""Explicit synthetic annotations. These are NOT outputs from face or ASR models."""
import math


def fixture(duration=40., pair=False, distant=False, moving=False, jitter=False, cuts=(), kind='medium'):
    shots = []
    edges = [0., *cuts, duration]
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        shots.append({'shot_id': f'SHOT_{i}', 'scene_id': f'SCENE_{i}', 'start': a, 'end': b,
                      'shot_type': kind, 'camera_score': .9,
                      'transition_in': 'hard_cut' if i else None})
    frames, observations = [], []
    for i in range(math.ceil(duration*4)):
        t = i/4
        shot = next(s for s in shots if s['start'] <= t < s['end'])
        ids = ['PERSON_A', 'PERSON_B'] if pair else ['PERSON_A']
        frames.append({'time': t, 'scene_id': shot['scene_id'], 'visible_people': ids,
                       'blur_laplacian_variance': 160, 'possible_black_frame': False})
        for p in ids:
            x = (.3 if p == 'PERSON_A' else .7) if distant else (.44 if p == 'PERSON_A' else .56)
            if moving:
                x = .3+.3*t/duration
            if jitter:
                x += .004*math.sin(t*13)
            face = {'x': x-.035, 'y': .20, 'width': .07, 'height': .17}
            observations.append({'time': t, 'person_id': p, 'track_id': f'{p}_{shot["shot_id"]}',
                'scene_id': shot['scene_id'], 'face_bbox': face, 'bbox': face,
                'bbox_kind': 'face', 'face_visible': True, 'body_visible': False,
                'center': {'x': x, 'y': .285}, 'head_center': {'x': x, 'y': .285},
                'face_height': .17, 'face_area': .0119, 'safe_crop_possible': True,
                'sharpness': 150., 'detection_confidence': .99})
    return {'duration': duration, 'width': 3840, 'height': 2160, 'fps': 30}, {
        'frames': frames, 'observations': observations,
        'people': [{'person_id': p, 'first_seen': 0, 'last_seen': duration-.25,
                    'observation_count': int(duration*4)} for p in (['PERSON_A', 'PERSON_B'] if pair else ['PERSON_A'])]}, shots


def turn(start, end, person='PERSON_A', speaker=None, confidence=.95, overlap=False):
    return {'start': start, 'end': end, 'speaker_id': speaker or ('SPEAKER_A' if person == 'PERSON_A' else 'SPEAKER_B'),
            'person_id': person, 'confidence': confidence, 'overlap': overlap}
