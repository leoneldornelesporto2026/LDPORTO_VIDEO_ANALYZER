"""Offline Re-ID replay from 07_people_tracking.json or a ZIP containing it.

No original video, GPU, speech models, downloads, renders, or cache mutations.
Metrics are descriptive proxies, not identity accuracy without annotations.
"""
import argparse
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.config import DEFAULTS
from ldporto.person_reid import build_person_identities


def _read(path, filename):
    if path.is_file() and path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            if filename not in archive.namelist():
                return None
            return json.loads(archive.read(filename))
    if path.is_dir():
        file = path / filename
        return json.loads(file.read_text(encoding='utf-8-sig')) if file.exists() else None
    if path.name == filename:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    return None


def replay(path, *, cfg=None):
    raw = _read(Path(path), '07_people_tracking.json')
    if not isinstance(raw, dict):
        raise ValueError('Arquivo 07_people_tracking.json não encontrado.')
    vision = raw.get('data', raw)
    if not isinstance(vision, dict) or not isinstance(vision.get('observations'), list):
        raise ValueError('Checkpoint sem data.observations.')
    settings = dict(DEFAULTS['vision'])
    if cfg:
        settings.update(cfg)
    before = _read(Path(path), '08_person_reid.json') or {}
    started = time.monotonic()
    result = build_person_identities(vision, settings)
    metrics = result['data']['metrics']
    previous = (before.get('data') or before).get('metrics') or {}
    return {
        'scope': 'offline_reid_replay_only', 'source': str(path),
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'video_rerun': False, 'vision_rerun': False, 'asr_rerun': False,
        'uses_ground_truth': False, 'identity_accuracy_verified': False,
        'identity_decisions_are_not_published': True,
        'original_checkpoint_metrics': {k: previous.get(k) for k in (
            'raw_track_count', 'persistent_person_count', 'reid_merge_count',
            'micro_track_count', 'micro_reid_attachment_count')},
        'replayed_metrics': {k: metrics.get(k) for k in (
            'raw_track_count', 'valid_track_count', 'micro_track_count',
            'micro_track_ratio', 'persistent_person_count', 'reid_merge_count',
            'stable_exact_fallback_accepted', 'micro_reid_attachment_count',
            'micro_reid_attached_one_sample_count', 'micro_with_embedding_count',
            'micro_without_embedding_count', 'micro_face_attachment_fraction',
            'micro_track_mapped_fraction', 'simultaneous_identity_conflict_count')},
        'warnings': [
            'Re-ID offline nao prova que os mesmos rostos foram associados corretamente.',
            'O teste nao mede speaker-person, active speaker ou camera: exigem replay downstream.',
            'Micro-tracklets continuam preservados na evidencia bruta.'
        ]
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='ZIP ou pasta com 07_people_tracking.json')
    parser.add_argument('--output', type=Path, required=True, help='Caminho JSON do relatório')
    args=parser.parse_args()
    report=replay(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
