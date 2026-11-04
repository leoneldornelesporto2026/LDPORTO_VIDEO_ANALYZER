"""Measured downstream camera replay, without ASR/visual/LLM inference."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.camera_director import build_camera_director
from ldporto.analysis_quality import camera_quality_metrics
from ldporto.config import load_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--active-folder', type=Path)
    args = parser.parse_args()
    def read(name):
        return json.loads((args.folder / name).read_text(encoding='utf-8-sig'))
    metadata = read('analysis_summary.json')['metadata']
    active = json.loads((args.active_folder / 'active_speaker.json').read_text(encoding='utf-8-sig')) if args.active_folder else read('active_speaker.json')
    result = build_camera_director(metadata, {'frames': read('video_analysis.json')['frame_samples'],
                                            'observations': read('people_observations.json')},
                                   read('shots.json'), active, read('person_motion.json'), load_config()['camera_director'],
                                   read('questions_answers.json'), read('story_arcs.json'), read('main_moments.json'))['data']
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'execution_scope': 'camera_snapshot_replay', 'asr_rerun': False, 'vision_rerun': False, 'llm_rerun': False,
              'metrics': {**result['metrics'], **camera_quality_metrics(result['timeline'], metadata['duration'])}}
    for name, data in [('camera_director_timeline.json', result['timeline']), ('camera_replay_metrics.json', report)]:
        (args.output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
