"""Real short ASR repair only; no programme-length transcription."""
import json
import logging
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.core import Context
from ldporto.config import load_config, configure_local_mode
from ldporto.targeted_asr import run_targeted_repair


def main():
    folder = ROOT / 'analysis/video_31329be78ca4'
    output = ROOT / '.cache/v44_validation/P0D_targeted_asr'
    cfg = load_config(ROOT / 'config/config.yaml')
    cfg.update(offline=True)
    cfg['transcription'].update(targeted_max_regions=2, targeted_max_audio_seconds=12)
    configure_local_mode(cfg)
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    metadata = read(folder / 'analysis_summary.json')['metadata']
    transcript = {'words': read(folder / 'words.json'), 'segments': read(folder / 'transcript_segments.json')}
    candidates = read(ROOT / '.cache/v44_validation/P0C_commercial_replay/main_moments.json')
    arcs = read(ROOT / '.cache/v44_validation/P0D_story_replay/story_arcs.json')
    ctx = Context(folder / metadata['filename'], output, cfg, metadata['sha256'], logging.getLogger('v44-targeted'))
    result = run_targeted_repair(ctx, {'mono': str(folder / 'audio/original_mono_16k.wav')}, transcript,
                                candidates, arcs, read(folder / 'questions_answers.json'), metadata['duration'])
    output.mkdir(parents=True, exist_ok=True)
    (output / 'targeted_asr_repair.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'alternatives'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
