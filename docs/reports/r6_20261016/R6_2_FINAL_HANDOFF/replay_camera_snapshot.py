"""Read existing evidence and replay only Camera Director, never source inference."""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.camera_director import replan_camera_from_snapshot

SOURCE = ROOT / 'analysis/video_8adc6609911a'
OUT = Path(__file__).resolve().parent / 'camera_replay_r62_v2'


def read(name):
    return json.loads((SOURCE / name).read_text(encoding='utf-8'))


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--curator-compatible', action='store_true',
                        help='Explicit compatible zoom profile 1.04, preserving every other gate.')
    args = parser.parse_args()
    started = time.perf_counter()
    video = read('video_analysis.json')
    cfg = read('cache/5d089e1825b396da/19_camera_director.json')['data']['config']
    cfg['debug_output'] = False
    overrides = []
    if args.curator_compatible:
        OUT = Path(__file__).resolve().parent / 'camera_replay_r62_curator_compat'
        overrides.append({'path': 'smart_zoom.max_zoom_factor',
                          'previous_value': cfg['smart_zoom']['max_zoom_factor'], 'value': 1.04,
                          'reason': 'explicit_compatibility_profile_for_curator_1_to_1_05_renderer_not_silent_clamp'})
        cfg['smart_zoom']['max_zoom_factor'] = 1.04
    snapshot = {'metadata': video['metadata'], 'frame_samples': video['frame_samples'],
                'people_observations': read('people_observations.json'), 'shots': read('shots.json'),
                'active_speaker': read('active_speaker.json'), 'person_motion': read('person_motion.json'),
                'main_moments': read('main_moments.json'), 'questions_answers': read('questions_answers.json')
                    if (SOURCE / 'questions_answers.json').is_file() else read('qa_pairs.json'),
                'story_arcs': read('story_arcs.json'), 'camera_plan': read('camera_plan.json'),
                'camera_director_config': cfg}
    print('Loaded existing evidence; replaying only shared camera engine.', flush=True)
    data = replan_camera_from_snapshot(snapshot)['data']
    OUT.mkdir(parents=True, exist_ok=True)
    for filename, key in [('timeline.json', 'timeline'), ('metrics.json', 'metrics'),
                           ('zoom_events.json', 'zoom_events'), ('config.json', 'config')]:
        write(filename, data[key])
    with gzip.open(OUT / 'focus_window_audit.json.gz', 'wt', encoding='utf-8') as handle:
        json.dump(data['focus_window_audit'], handle, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    paths = ['video_analysis.json', 'people_observations.json', 'shots.json', 'active_speaker.json',
             'person_motion.json', 'main_moments.json', 'story_arcs.json', 'camera_plan.json']
    provenance = {**data['snapshot_replay'], 'source_analysis': str(SOURCE),
                  'input_sha256': {name: sha(SOURCE / name) for name in paths},
                  'code_sha256': {name: sha(ROOT / 'src/ldporto' / name)
                                    for name in ['camera_director.py', 'camera_evidence.py', 'camera_geometry.py',
                                                 'camera_preflight.py', 'camera_motion.py']},
                  'debug_output_disabled_only_for_size': True, 'elapsed_seconds': time.perf_counter()-started,
                  'explicit_config_overrides': overrides,
                  'preview_approved': False, 'publish_ready': False}
    write('provenance.json', provenance)
    write('artifact_integrity.json', {path.name: {'sha256': sha(path), 'bytes': path.stat().st_size}
                                    for path in OUT.iterdir() if path.is_file() and path.name != 'artifact_integrity.json'})
    print(json.dumps({'coverage': data['metrics']['camera_director_coverage'],
                     'timeline_intervals': len(data['timeline']), 'proposed_zoom_events': len(data['zoom_events']),
                     'delivered_zoom_events': data['metrics']['zoom_delivered_event_count'],
                     'elapsed_seconds': provenance['elapsed_seconds'],
                     'longest_focused_intervals': [{'start': row['start'], 'end': row['end'],
                         'person': row['focus_person'], 'shot': row['source_shot_id']}
                         for row in sorted((r for r in data['timeline'] if r['focus_person']),
                                           key=lambda r: r['end']-r['start'], reverse=True)[:12]]}, indent=2), flush=True)


if __name__ == '__main__':
    main()
