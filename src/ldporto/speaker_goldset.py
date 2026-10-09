"""S5: human verification of speaker/person mapping without implicit guessing."""
import csv
import math
from pathlib import Path

FIELDS = ('speaker_id', 'start', 'end', 'predicted_person_id', 'predicted_active_person',
          'predicted_state', 'human_person_id', 'human_role', 'annotation_status', 'notes')


def choose_review_windows(diagnostics, intervals, limit_per_speaker=8):
    result = []
    for diagnostic in diagnostics:
        if diagnostic.get('person_id') is not None and diagnostic.get('confirmed_intervals', 0):
            continue
        speaker = diagnostic['speaker_id']
        rows = [row for row in intervals if row.get('speaker_id') == speaker]
        # Prefer ambiguity, overlap and gaps to a redundant run of identical windows.
        rows.sort(key=lambda row: (0 if row.get('overlap') else 1,
                        0 if row.get('active_speaker_state') in ('UNCERTAIN', 'OFFSCREEN') else 1,
                        row['start']))
        seen = set()
        selected = []
        for row in rows:
            key = (round(row['start'], 1), row.get('state'))
            if key in seen:
                continue
            seen.add(key)
            selected.append({**row})
            if len(selected) >= limit_per_speaker:
                break
        for row in sorted(selected, key=lambda r:r['start']):
            result.append({'speaker_id':speaker, 'start': row['start'], 'end': row['end'],
                           'predicted_person_id':row.get('person_id') or '',
                           'predicted_active_person':row.get('active_person') or '',
                           'predicted_state':row.get('active_speaker_state') or '',
                           'human_person_id':'', 'human_role':'',
                           'annotation_status':'unreviewed', 'notes':''})
    return result


def export_csv(rows, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError('Anotacoes existentes nao podem ser sobrescritas; use outra pasta.')
    with dest.open('w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, FIELDS)
        writer.writeheader()
        writer.writerows({key: row.get(key, '') for key in FIELDS} for row in rows)
    return dest


def load_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def evaluate_goldset(rows, *, other_predictions=None):
    """Evaluate only explicit human verified windows; blanks must be explicit.

    Labels: speaking, listening, reacting, offscreen, uncertain. Null is not a
    negative example unless human labeled a non-speaking role.
    """
    permitted = {'speaking', 'listening', 'reacting', 'offscreen', 'uncertain'}
    verified = []
    for row in rows:
        if row.get('annotation_status') != 'verified':
            continue
        role = str(row.get('human_role', '')).strip().lower()
        if role not in permitted:
            raise ValueError('human_role precisa ser speaking, listening, reacting, offscreen ou uncertain')
        if role == 'speaking' and not row.get('human_person_id'):
            raise ValueError('human_person_id obrigatorio para human_role=speaking')
        try:
            a, b = float(row.get('start')), float(row.get('end'))
        except (TypeError, ValueError):
            raise ValueError('Intervalos anotados invalidos') from None
        if not math.isfinite(a) or not math.isfinite(b) or a >= b:
            raise ValueError('Intervalos anotados invalidos')
        if any(previous.get('speaker_id') == row.get('speaker_id') and
               min(b, stop) > max(a, start) for previous, _, start, stop in verified):
            raise ValueError('Janelas anotadas do mesmo locutor devem ser independentes, sem duplicacao ou overlap')
        verified.append((row, role, a, b))
    errors, eligible, tps, fps, fns, abstentions = [], 0, 0, 0, 0, 0
    wrong_person, speaking, predictions = 0, 0, 0
    for row, role, a, b in verified:
        if role == 'uncertain':
            continue
        eligible += 1
        expected = row['human_person_id'] if role == 'speaking' else None
        speaking += expected is not None
        prediction = row.get('predicted_active_person') or None
        if other_predictions is not None:
            key = (row.get('speaker_id'), round(a, 6), round(b, 6))
            prediction = other_predictions.get(key)
        predictions += bool(prediction)
        abstentions += not bool(prediction)
        if prediction and prediction == expected:
            tps += 1
        elif prediction and prediction != expected:
            fps += 1
            wrong_person += expected is not None
            errors.append({'speaker_id': row['speaker_id'], 'start':a, 'end':b,
                           'error':'false_positive_or_wrong_person', 'predicted':prediction,'human':expected})
        elif not prediction and expected:
            fns += 1
            errors.append({'speaker_id': row['speaker_id'], 'start':a, 'end':b,
                           'error':'missed_speaking_window', 'predicted':None,'human':expected})
    precision = tps/(tps+fps) if tps+fps else None
    recall = tps/speaking if speaking else None
    f1 = 2*precision*recall/(precision+recall) if precision is not None and recall is not None and precision+recall else None
    return {'schema_version':'1.0', 'verified_windows':len(verified),
            'eligible_windows':eligible, 'excluded_uncertain':len(verified)-eligible,
            'true_correct_identifications':tps, 'false_positive_or_wrong_person':fps,
            'missed_speaking_windows':fns, 'correct_abstentions':eligible-tps-fps-fns,
            'abstained_windows':abstentions, 'abstention_rate':abstentions/eligible if eligible else None,
            'prediction_coverage':predictions/eligible if eligible else None,
            'wrong_person_windows':wrong_person,
            'error_rate_when_predicting':fps/predictions if predictions else None,
            'precision':precision, 'recall':recall, 'f1':f1,
            'review_errors':errors,
            'important_note':'Interval-level snapshot; use representative independent manually labeled windows. Not a benchmark unless annotations are complete and representative.'}
