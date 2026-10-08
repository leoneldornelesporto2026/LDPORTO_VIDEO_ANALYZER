"""S5 diagnostic and optional human goldset evaluation (no GPU/Whisper needed).

Examples:
  python scripts/dev/audit_speaker_s5.py C:/my_analysis --output C:/s5_audit
  python scripts/dev/audit_speaker_s5.py C:/review.zip --output C:/s5_audit
  python scripts/dev/audit_speaker_s5.py C:/analysis --output C:/s5_audit --evaluate C:/s5_audit/speaker_annotations.csv

Optional --neural-predictions JSON: pilot prediction list of
{speaker_id,start,end,person_id}; benchmark only, NEVER auto-merges.
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from ldporto.config import DEFAULTS
from ldporto.active_speaker import build_active_speaker
from ldporto.speaker_goldset import (choose_review_windows, export_csv,
                                     load_csv, evaluate_goldset)


def load(source, *names):
    source = Path(source)
    for name in names:
        if source.is_dir():
            matching = sorted(source.rglob(name), key=lambda p: (len(p.parts), str(p)))
            if matching:
                return json.loads(matching[0].read_text(encoding='utf-8-sig'))
        elif source.suffix.lower() == '.zip':
            with zipfile.ZipFile(source) as z:
                matching = sorted([n for n in z.namelist() if n == name or n.endswith('/'+name)], key=lambda n: (n.count('/'), n))
                if matching:
                    return json.loads(z.read(matching[0]).decode('utf-8-sig'))
    return None


def bare(obj):
    return obj.get('data', obj) if isinstance(obj, dict) else obj


def replay(source, cfg=None):
    diarization = bare(load(source, '05_diarization.json') or {})
    if not diarization.get('turns'):
        diarization = {'turns': bare(load(source, 'speaker_turns.json') or []),
                       'speakers': bare(load(source, 'speakers.json') or [])}
    vision = bare(load(source, '08_person_reid.json') or load(source, '07_people_tracking.json') or {})
    if not vision.get('observations'):
        vision = {'people': bare(load(source, 'people.json') or []),
                  'observations': bare(load(source, 'people_observations.json') or []),
                  'frames': (bare(load(source, 'video_analysis.json') or {}).get('frame_samples') or []),
                  'scene_intervals': bare(load(source, 'scenes.json') or [])}
    evidence = bare(load(source, '10_active_speaker.json') or {})
    evidence = evidence.get('active_speaker_evidence') or evidence.get('mappings') or []
    if not evidence:
        evidence = bare(load(source, 'active_speaker_evidence.json') or [])
    if not diarization.get('turns'):
        raise ValueError('Nao foram encontrados turnos de diarizacao; necessario 05_diarization.json ou speaker_turns.json.')
    if not evidence:
        raise ValueError('Nao foram encontradas janelas boca/audio. Reprocessar etapa 10 ou fornecer active_speaker_evidence.json.')
    if not vision.get('observations'):
        raise ValueError('Nao foram encontradas observacoes visuais. Fornecer 08_person_reid.json ou people_observations.json.')
    return build_active_speaker(diarization, vision, evidence, cfg or DEFAULTS['active_speaker'])['data']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--evaluate', type=Path, help='Goldset CSV anotado e revisado manualmente')
    parser.add_argument('--neural-predictions', type=Path, help='Predicoes de piloto externo para comparar, sem integrar')
    options = parser.parse_args(argv)
    data = replay(options.source)
    options.output.mkdir(parents=True, exist_ok=True)
    diagnostics = data['speaker_person_diagnostics']
    unresolved = [row for row in diagnostics if not row.get('person_id') or not row.get('confirmed_intervals')]
    report = {'schema_version':'S5', 'speaker_count':len(diagnostics),
              'global_unresolved_speakers':sum(not row.get('person_id') for row in diagnostics),
              'active_unconfirmed_speakers':len(unresolved),
              'speaker_diagnostics':diagnostics, 'metrics':data['metrics'],
              'important_note':'Diagnostico de artefatos fornecidos; nao prova identidade fisica ou sync fora das janelas observadas.'}
    (options.output/'speaker_s5_diagnostics.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (options.output/'active_speaker_s5.json').write_text(json.dumps(data['intervals'],indent=2,ensure_ascii=False),encoding='utf-8')
    csv_path = options.output/'speaker_annotations.csv'
    if not csv_path.exists():
        export_csv(choose_review_windows(diagnostics, data['intervals']), csv_path)
    if options.evaluate:
        truth = load_csv(options.evaluate)
        results = {'heuristic_consensus':evaluate_goldset(truth)}
        if options.neural_predictions:
            predictions = json.loads(options.neural_predictions.read_text(encoding='utf-8-sig'))
            inferred = {}
            for item in predictions:
                key = (item.get('speaker_id'), round(float(item['start']),6), round(float(item['end']),6))
                if key in inferred:
                    raise ValueError('Predicoes externas duplicadas para uma janela')
                inferred[key] = item.get('person_id') or None
            results['neural_pilot'] = evaluate_goldset(truth, other_predictions=inferred)
        (options.output/'speaker_goldset_metrics.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'global_unresolved_speakers':report['global_unresolved_speakers'],
                      'active_unconfirmed_speakers':report['active_unconfirmed_speakers'],
                      'annotation_csv':str(csv_path), 'path':str(options.output)},ensure_ascii=False,indent=2))
    return report


if __name__ == '__main__':
    main()
