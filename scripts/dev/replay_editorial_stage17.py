"""Deterministic offline comparison of recorded S4 decisions and current gates.

Scores and intervals are reused, not re-inferred. No perception or publication.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

try:
    from .review_editorial_s3 import evaluate, ROOT
except ImportError:
    from review_editorial_s3 import evaluate, ROOT


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'


def index(rows, field):
    result = {}
    for row in rows:
        cid = row.get(field)
        if not isinstance(cid, str) or not cid or cid in result:
            raise ValueError('Missing or duplicate candidate ID')
        result[cid] = row
    return result


def compare(review_package, curation_package, max_items=12, min_score=.5):
    """Read both archives in place; return deterministic artifacts without writes."""
    inputs = []
    def load_package(path, reader):
        with ZipFile(path) as archive:
            members = {}
            def read(name):
                info = archive.getinfo(name)
                if info.file_size > 48_000_000:
                    raise ValueError('Offline member size limit exceeded')
                data = archive.read(name)
                members[name] = sha(data)
                return json.loads(data)
            result = reader(archive, read)
        inputs.append({'sha256': sha(Path(path).read_bytes()), 'members': members})
        return result

    def snapshot(archive, read):
        roots = [n[:-len('main_moments.json')] for n in archive.namelist()
                 if n.startswith('analysis/') and n.endswith('/main_moments.json')]
        if len(roots) != 1:
            raise ValueError('Exactly one snapshot candidate collection required')
        root = roots[0]
        rows = read(root + 'main_moments.json')
        upstream = []
        missing = []
        for name in ('transcript_segments.json', 'story_arcs.json', 'questions_answers.json'):
            if root + name in archive.namelist():
                upstream.append(read(root + name))
            else:
                upstream.append([])
                missing.append(name)
        return rows, upstream, read(root + 'run_manifest.json'), missing

    rows, upstream, run, missing = load_package(review_package, snapshot)
    def recorded(archive, read):
        return (read('SECOND_CURATION_MANIFEST.json'),
                read('editorial/candidate_catalog.json')['candidates'],
                read('editorial/default_shortlist.json')['candidate_ids'],
                read('editorial/selection_report_s3.json')['selection_report'])
    manifest, catalog, old_selected, old_report = load_package(curation_package, recorded)
    source = index(rows, 'moment_id')
    exported = index(catalog, 'candidate_id')
    if run.get('run_id') != manifest.get('run_id') or not run.get('run_id'):
        raise ValueError('Packages do not identify the same run')
    extras = exported.keys() - source.keys()
    if (source.keys() - exported.keys() or any(
            exported[cid].get('alternate_of') not in source for cid in extras)):
        raise ValueError('Candidate IDs differ between packages')
    for cid, row in source.items():
        if (row.get('ideal_start'), row.get('ideal_end')) != (exported[cid].get('start'), exported[cid].get('end')):
            raise ValueError('Candidate intervals differ between packages: ' + cid)
    rejected = index(old_report.get('rejected', []), 'moment_id')
    if (len(set(old_selected)) != len(old_selected) or set(old_selected) & rejected.keys()
            or set(old_selected) | rejected.keys() != source.keys()):
        raise ValueError('Recorded decisions do not cover each candidate exactly once')
    ready = manifest.get('readiness', {}).get('editorial_ready') is True and not missing
    after = evaluate(rows, *upstream, ready, max_items=max_items, min_score=min_score)
    diagnostics = index(after['selection']['candidate_diagnostics'], 'moment_id')
    if diagnostics.keys() != source.keys():
        raise ValueError('Current audit lost candidate IDs')
    current = index(after['candidate_diagnostics'], 'moment_id')
    arcs = {a['story_arc_id']: a for a in upstream[1] if a.get('story_arc_id')}
    diff = []
    for cid, row in sorted(source.items()):
        diag = diagnostics[cid]
        arc = arcs.get(row.get('story_arc_id'), {})
        payoff = arc.get('payoff')
        old_reasons = rejected[cid]['reasons'] if cid in rejected else ['selected_in_historical_export']
        old_state = 'selected' if cid in old_selected else 'rejected'
        new_state = diag['selection_status'] if ready or diag['selection_status'] != 'selected' else 'pending'
        diff.append({'candidate_id': cid, 'old_state': old_state, 'new_state': new_state,
                     'old_reasons': old_reasons, 'new_reasons': diag['selection_reasons'],
                     'new_blockers': current[cid]['editorial_blockers'],
                     'start': row.get('ideal_start'), 'end': row.get('ideal_end'),
                     'historical_score_reused': row.get('editorial_score_final'),
                     'payoff_recorded': payoff if payoff else None,
                     'payoff_confirmed': None,
                     'decision': diag['selection_disposition'] if new_state != 'pending' else 'pending',
                     'changed': old_state != new_state or old_reasons != diag['selection_reasons'],
                     'publish_ready': False})
    code_paths = ['scripts/dev/replay_editorial_stage17.py', 'scripts/dev/review_editorial_s3.py',
                  'src/ldporto/editorial_intelligence.py', 'src/ldporto/editorial.py']
    report = {'schema_version': 'stage17.1', 'source_build': manifest.get('analyzer_build'),
              'source_run_id': run['run_id'], 'source_analysis_status': run.get('analysis_status'),
              'inputs': inputs, 'code_sha256': {p: sha((ROOT / p).read_bytes()) for p in code_paths},
              'parameters': {'max_items': max_items, 'min_score': min_score},
              'scope': 'recorded_S4_baseline_vs_current_editorial_gates_on_same_candidates',
              'limitations': ['Historical scores and boundaries reused; no current perception or score recomputation.',
                              'Recorded readiness is historical, not current pipeline certification.',
                              'Payoff objects are recorded proposals, not confirmed outcomes.'] + missing,
              'candidate_count': len(diff), 'before': old_report, 'after': after, 'diff': diff,
              'catalog_count': len(exported),
              'catalog_alternates_outside_replay': [
                  {'candidate_id': cid, 'alternate_of': exported[cid]['alternate_of']}
                  for cid in sorted(extras)],
              'old_shortlist_ids': old_selected, 'publish_ready': False}
    shortlist = {'status': after['status'], 'candidate_ids': after['shortlist_ids'],
                 'hypothetical_diagnostic_ids_not_shortlist': after['hypothetical_diagnostic_ids_not_shortlist'],
                 'homologated': False, 'human_review_required': True, 'publish_ready': False}
    return report, shortlist


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-package', type=Path, required=True)
    parser.add_argument('--curation-package', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    # Only create a fresh artifact directory; never overwrite existing analyses.
    if args.output_dir.exists():
        parser.error('--output-dir must be a new directory')
    report, shortlist = compare(args.review_package, args.curation_package)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / 'comparison.json').write_text(encoded(report), encoding='utf-8')
    (args.output_dir / 'shortlist_candidate.json').write_text(encoded(shortlist), encoding='utf-8')
    with (args.output_dir / 'candidates.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(report['diff'][0]) if report['diff'] else ['candidate_id'])
        writer.writeheader()
        for row in report['diff']:
            writer.writerow({k: v if isinstance(v, str) else json.dumps(
                v, ensure_ascii=False, sort_keys=True, allow_nan=False) for k, v in row.items()})
    outputs = {name: sha((args.output_dir / name).read_bytes()) for name in
               ('comparison.json', 'shortlist_candidate.json', 'candidates.csv')}
    (args.output_dir / 'output_hashes.json').write_text(encoded(outputs), encoding='utf-8')
    print(encoded({'candidate_count': report['candidate_count'], 'source_build': report['source_build'],
                   'old_shortlist_ids': report['old_shortlist_ids'], 'shortlist': shortlist, 'output_hashes': outputs}))


if __name__ == '__main__':
    main()
