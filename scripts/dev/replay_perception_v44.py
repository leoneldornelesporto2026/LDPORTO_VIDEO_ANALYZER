"""Replay mouth/audio from cached observations and WAV; never reruns visual inference."""
import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.active_speaker import build_active_speaker
from ldporto.config import load_config
from ldporto.core import Context
from ldporto.perception_diagnostics import tracking_profile
from ldporto.vision import ActiveSpeakerEngine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refresh-audio-evidence', action='store_true')
    args = parser.parse_args()
    def read(name):
        return json.loads((args.folder / name).read_text(encoding='utf-8-sig'))
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = read('analysis_summary.json')['metadata']
    vision = {'people': read('people.json'), 'observations': read('people_observations.json'),
              'frames': read('video_analysis.json')['frame_samples'], 'scene_intervals': read('scenes.json')}
    diarization = {'turns': read('speaker_turns.json'), 'speakers': read('speakers.json'),
                   'overlaps': read('speech_overlaps.json')}
    cfg = load_config()
    started = time.monotonic()
    if args.refresh_audio_evidence:
        mono = args.folder / 'audio' / 'original_mono_16k.wav'
        if not mono.is_file():
            raise FileNotFoundError('Cached mono.wav required for audio-evidence replay')
        ctx = Context(args.folder / metadata['filename'], args.output, cfg, metadata['sha256'], logging.getLogger('v44-perception'))
        evidence = ActiveSpeakerEngine().run(ctx, {'mono': str(mono)}, diarization, vision, metadata)['data']['mappings']
    else:
        evidence = read('active_speaker_evidence.json')
    result = build_active_speaker(diarization, vision, evidence, cfg['active_speaker'])['data']
    profile = tracking_profile(read('tracklet_observations.json'), read('shots.json'), metadata['duration'])
    for name, value in [('speaker_person_diagnostics.json', result['speaker_person_diagnostics']),
                        ('active_speaker_metrics.json', result['metrics']), ('tracking_fragmentation_profile.json', profile),
                        ('active_speaker.json', result['intervals']), ('speaker_person_summary.json', result['mapping_summary']),
                        ('active_speaker_evidence.json', evidence)]:
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    import cv2
    import numpy as np
    density = np.array([[row['tracks_created_per_minute'] for row in profile['bins']],
                        [row['micro_tracks_per_minute'] for row in profile['bins']]], dtype=float)
    normalized = np.uint8(np.minimum(255, density * 255 / max(1, density.max())))
    heatmap = cv2.applyColorMap(cv2.resize(normalized, (len(profile['bins']) * 8, 80), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_INFERNO)
    cv2.imwrite(str(args.output / 'tracking_fragmentation_heatmap.png'), heatmap)
    report = {'execution_scope': 'audio_evidence_replay' if args.refresh_audio_evidence else 'speaker_person_snapshot_replay',
              'asr_rerun': False, 'vision_rerun': False, 'llm_rerun': False,
              'elapsed_seconds': time.monotonic() - started, 'metrics': result['metrics'],
              'diagnosed_speakers': len(result['speaker_person_diagnostics'])}
    (args.output / 'replay_provenance.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
