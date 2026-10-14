"""CPU-only, bounded replay of three audited SOL V4 mouth/audio slices.

Reads existing audio and verified observation projections. No visual model,
diarizer, ASR, GPU, Ollama or full pipeline is executed. Output is exclusive.
"""
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SLICES = ((86.26221875, 89.83971875),
          (105.47203333333334, 112.82346875),
          (164.51159375, 168.56159375000001))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_projected_observations(analysis, slices):
    """Read only relevant bounded chunks; verify every consumed chunk hash."""
    root = Path(analysis).resolve()
    summary = json.loads((root/'people_summary.json').read_text(encoding='utf-8'))
    projection = summary.get('observation_projection') or {}
    records, consumed = [], []
    for chunk in projection.get('chunks') or []:
        if not any(min(chunk['end'], b) >= max(chunk['start'], a) for a, b in slices):
            continue
        path = (root/chunk['path']).resolve()
        path.relative_to(root)
        blob = path.read_bytes()
        measured = hashlib.sha256(blob).hexdigest()
        if measured != chunk.get('sha256'):
            raise ValueError('Observation projection hash mismatch: ' + chunk['path'])
        document = json.loads(blob)
        rows = document.get('records') if isinstance(document, dict) else document
        if not isinstance(rows, list) or len(rows) != chunk['record_count']:
            raise ValueError('Observation projection record count mismatch')
        records.extend(row for row in rows if any(a <= row['time'] < b for a, b in slices))
        consumed.append({'path': chunk['path'], 'sha256': measured, 'bytes': len(blob),
                         'record_count': len(rows)})
    if not consumed or not records:
        raise ValueError('No verified projected observations in the three audited slices')
    records.sort(key=lambda row: (row['time'], row.get('person_id') or ''))
    return records, consumed


def benchmark(analysis, config):
    sys.path.insert(0, str(ROOT/'src'))
    import soundfile as sf
    from ldporto.config import load_config
    from ldporto.vision import ActiveSpeakerEngine
    from ldporto.audiovisual_diagnostics import window_signal_diagnostics

    root = Path(analysis).resolve()
    audio = root/'audio/original_mono_16k.wav'
    info = sf.info(audio)
    if info.channels != 1 or info.samplerate != 16000 or info.duration < SLICES[-1][1]:
        raise ValueError('Expected existing 16 kHz mono source covering the bounded slices')
    cfg = load_config(config)
    if cfg['vision'].get('manual_mapping_file'):
        raise ValueError('This signal benchmark requires no manual speaker mapping')
    raw_path = root/'active_speaker_evidence.json'
    raw = json.loads(raw_path.read_text(encoding='utf-8'))
    turns, selected_raw = [], []
    for a, b in SLICES:
        rows = [row for row in raw if min(row['end'], b) > max(row['start'], a)]
        if (not rows or abs(rows[0]['start']-a) > 1e-9 or abs(rows[-1]['end']-b) > 1e-9 or
                len({row['turn_id'] for row in rows}) != 1 or any(row.get('overlap') for row in rows)):
            raise ValueError('The fixed slices no longer match audited nonoverlap source evidence')
        turns.append({'start': a, 'end': b, 'speaker': rows[0]['speaker_id'],
                      'turn_id': rows[0]['turn_id']})
        selected_raw.extend(rows)
    observations, chunks = load_projected_observations(root, SLICES)
    scenes_path, shots_path = root/'scenes.json', root/'shots.json'
    scenes = json.loads(scenes_path.read_text(encoding='utf-8'))
    shots = json.loads(shots_path.read_text(encoding='utf-8'))
    stamps = {t for row in selected_raw for t in row['visual_measurement']['sampled_frame_times']}
    # Include actual earlier shot-first samples so a sliced input does not invent
    # an extra scene boundary at its first local observation.
    stamps.update(t for shot in shots
                  if isinstance(t := (shot.get('sampling_coverage') or {}).get('first_sample_at'), (int, float))
                  and t < SLICES[-1][1])
    frames = []
    for stamp in sorted(stamps):
        scene = next((row for row in scenes if row['start'] <= stamp < row['end']), None)
        if scene is None:
            raise ValueError('Recorded frame timestamp has no recorded source scene')
        frames.append({'time': stamp, 'scene_id': scene['scene_id'],
                       'visible_people': sorted({row['person_id'] for row in observations if row['time'] == stamp})})
    people = sorted({row['person_id'] for row in observations})
    vision = {'observations': observations, 'frames': frames, 'scene_intervals': scenes,
              'people': [{'person_id': person} for person in people]}
    diarization = {'turns': turns, 'overlaps': [],
                   'speakers': [{'speaker_id': speaker} for speaker in sorted({t['speaker'] for t in turns})]}
    metadata = {key: selected_raw[0]['visual_measurement'].get('source_'+key)
                for key in ('width', 'height', 'fps')}
    metadata['duration'] = info.duration
    results = {}
    for policy in ('legacy', 'balanced_tail', 'tail_anchor'):
        current = deepcopy(cfg)
        current['active_speaker']['evidence_window_policy'] = policy
        started = perf_counter()
        measured = ActiveSpeakerEngine().run(SimpleNamespace(config=current), {'mono': audio},
                                             diarization, vision, metadata)['data']
        windows = measured['mappings']
        for window in windows:
            window['signal_diagnostic'] = window_signal_diagnostics(window, current['active_speaker'])
        results[policy] = {'elapsed_seconds': perf_counter()-started,
            'window_count': len(windows),
            'audio_windows_read': sum(w['audio_measurement']['status'] == 'audio_window_read' for w in windows),
            'candidate_count': sum(len(w['candidates']) for w in windows),
            'qualified_local_candidate_count': sum(w['signal_diagnostic']['qualified_local_candidate_count'] for w in windows),
            'window_planning': measured['window_planning'],
            'measurement_failure_counts': measured['measurement_failure_counts'],
            'windows': windows}
    expected = [(row['start'], row['end']) for row in selected_raw]
    actual = [(row['start'], row['end']) for row in results['legacy']['windows']]
    if actual != expected:
        raise ValueError('Legacy benchmark geometry differs from the audited producer')
    files = ['vision.py', 'speaker_windows.py', 'speaker_signals.py',
             'speaker_roles.py', 'audiovisual_diagnostics.py', 'config.py']
    return {'schema_version': '1.0', 'benchmark': 'bounded_cpu_mouth_audio_recalculation',
        'slices': [list(row) for row in SLICES], 'gpu_calls': 0, 'ollama_calls': 0,
        'visual_model_calls': 0, 'asr_calls': 0, 'audio': {'path': str(audio), 'sha256': sha256(audio),
            'sample_rate': info.samplerate, 'source_duration_seconds': info.duration},
        'input_files': {name: sha256(root/name) for name in
            ('active_speaker_evidence.json', 'people_summary.json', 'scenes.json', 'shots.json')},
        'observation_chunks': chunks, 'projected_observation_count': len(observations),
        'source_code_sha256': {name: sha256(ROOT/'src/ldporto'/name) for name in files},
        'versions': {name: importlib.metadata.version(name) for name in ('numpy', 'soundfile')},
        'config': {'vision_association_min_correlation': cfg['vision']['association_min_correlation'],
                   'vision_association_min_margin': cfg['vision']['association_min_margin'],
                   'active_speaker': cfg['active_speaker']},
        'scope': 'Three bounded source slices; existing visual observations reused. Local signal quality only.',
        'human_identity_accuracy_measured': False, 'ASD_confirmed': False,
        'legacy_geometry_matches_recorded_source': True, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=ROOT/'config/config.yaml')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError('Refusing to overwrite an existing benchmark')
    report = benchmark(args.analysis, args.config)
    report['command_argv'] = [sys.executable, *sys.argv]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'output': str(args.output.resolve()), 'results': {
        mode: {key: row[key] for key in ('window_count', 'audio_windows_read', 'candidate_count',
                                       'qualified_local_candidate_count')}
        for mode, row in report['results'].items()}}, indent=2))


if __name__ == '__main__':
    main()
