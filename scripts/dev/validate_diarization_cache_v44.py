"""Verify cached community-1 inference on twenty seconds of original audio."""
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
import soundfile as sf
from ldporto.config import load_config
from ldporto.diarization import DiarizationEngine

output = ROOT / '.cache/v44_validation/diarization_cache_fix'
output.mkdir(parents=True, exist_ok=True)
source = ROOT / 'analysis/video_31329be78ca4_v44_full_20261006/audio/original_mono_16k.wav'
with sf.SoundFile(source) as audio:
    audio.seek(3200 * audio.samplerate)
    samples = audio.read(20 * audio.samplerate, dtype='float32')
    rate = audio.samplerate
clip = output / 'original_3200_3220.wav'
sf.write(clip, samples, rate, subtype='PCM_16')
started = time.perf_counter()
result = DiarizationEngine().run(SimpleNamespace(config=load_config()), {'mono': str(clip)}, {'duration': 20})
result['validation'] = {'source_window': [3200, 3220], 'duration_seconds': 20,
                        'execution_scope': 'short_real_inference', 'wall_seconds': time.perf_counter() - started}
(output / 'DIARIZATION_CACHE_FIX_VALIDATION.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'status': result['status'], 'speaker_count': result['data']['speaker_count'],
                  'turn_count': len(result['data']['turns']), 'validation': result['validation']}), flush=True)
