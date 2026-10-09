"""Offline Session-3 review of an existing analysis or SECOND_CURATION core ZIP.

No model/ASR/video dependency; no changes to source; no publication approval.
usage: py -3.11 scripts/dev/review_editorial_s3.py --package X.zip --out report.json
       py -3.11 scripts/dev/review_editorial_s3.py --analysis analysis.json --out report.json
"""
import argparse
import json
import math
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from ldporto.editorial_intelligence import (narrative_integrity, humor_integrity,
                                           select_editorial_shortlist)


def _load(path, package=False):
    if not package:
        analysis = json.loads(Path(path).read_text('utf-8-sig'))
        candidates = [dict(m) for m in analysis.get('main_moments') or []]
        segments = analysis.get('transcript_segments') or (analysis.get('transcript') or {}).get('segments') or []
        arcs = analysis.get('story_arcs') or []
        qas = analysis.get('questions_answers') or []
        try:
            from ldporto.integrity_contracts import audit_editorial_contract
            integrity = audit_editorial_contract(analysis).get('editorial_integrity_ready', False)
        except (KeyError, TypeError, ValueError):
            integrity = False
        metrics = analysis.get('qa_metrics') or {}
        for m in candidates:
            m['moment_id'] = m.get('moment_id') or m.get('candidate_id')
            m['ideal_start'] = m.get('ideal_start', m.get('start', 0))
            m['ideal_end'] = m.get('ideal_end', m.get('end', 0))
        return candidates, segments, arcs, qas, integrity, metrics
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        def read(name, default):
            if name not in names:
                return default
            info = z.getinfo(name)
            if info.file_size > 48_000_000:
                raise ValueError('Input member exceeds offline reviewer size limit: ' + name)
            return json.loads(z.read(name))
        manifest = read('SECOND_CURATION_MANIFEST.json', {})
        catalog = read('editorial/candidate_catalog.json', {})
        candidates = [dict(m) for m in catalog.get('candidates', [])]
        segments = [json.loads(line) for line in z.read('transcript/relevant_segments.jsonl').decode('utf-8-sig').splitlines() if line.strip()] if 'transcript/relevant_segments.jsonl' in names else []
        arcs = read('editorial/story_arcs.json', [])
        qas = read('editorial/qa_pairs.json', [])
        for m in candidates:
            m['moment_id'] = m.get('moment_id') or m.get('candidate_id')
            m['ideal_start'], m['ideal_end'] = m.get('start', 0), m.get('end', 0)
            m['core_moment'] = {'text': m.get('transcript_literal') or ''}
            m['evidence_segment_ids'] = m.get('segment_ids') or []
            m['topic_id'] = m.get('primary_topic_id')
            m['story_arc_id'] = m.get('story_arc')
        metrics = read('summary/analysis_summary.json', {}).get('candidate_metrics') or {}
        return candidates, segments, arcs, qas, bool((manifest.get('readiness') or {}).get('editorial_ready')), metrics


def evaluate(candidates, segments, arcs, qas, editorial_ready, max_items=12, min_score=.50):
    by_arc = {a['story_arc_id']: a for a in arcs if isinstance(a, dict) and a.get('story_arc_id')}
    ids = {s.get('segment_id') for s in segments if isinstance(s, dict)}
    review = []
    for m in candidates:
        begin, finish = m.get('ideal_start'), m.get('ideal_end')
        if (isinstance(begin, bool) or isinstance(finish, bool)
                or not isinstance(begin, (int, float)) or not isinstance(finish, (int, float))
                or not math.isfinite(begin) or not math.isfinite(finish) or begin < 0 or begin >= finish):
            item = dict(m)
            item['editorial_blockers'] = sorted(set((m.get('editorial_blockers') or []) + ['invalid_source_interval']))
            item['default_shortlist_eligible'] = False
            review.append(item)
            continue
        evidence = m.get('evidence_segment_ids') or []
        narrative = narrative_integrity(by_arc.get(m.get('story_arc_id')), evidence)
        humor = humor_integrity(segments, begin, finish,
                                bool(set(m.get('categories') or []) & {'punchline', 'humor'}))
        dangling_question = any(q.get('answer_expected') and q.get('question_start') is not None
            and begin <= q['question_start'] < finish and
            (not q.get('question_answer_complete') or not q.get('answer_end') or q['answer_end'] > finish)
            for q in qas if isinstance(q, dict))
        blockers = sorted(set((m.get('editorial_blockers') or []) + narrative['blockers'] + humor['blockers'] +
                              (['question_without_complete_answer'] if dangling_question else []) +
                              (['source_segments_unavailable'] if not evidence or not set(evidence) <= ids else [])))
        item = dict(m)
        item['editorial_blockers'] = blockers
        item['narrative_integrity'] = narrative
        item['humor_integrity'] = humor
        item['default_shortlist_eligible'] = bool(m.get('default_shortlist_eligible', False)) and not blockers
        review.append(item)
    chosen, report = select_editorial_shortlist(review, max_items=max_items, min_score=min_score)
    brief = {'schema_version': 's3.1', 'input_candidate_count': len(candidates),
             'evaluated_candidate_count': len(review), 'editorial_integrity_ready': editorial_ready,
             'status': 'REVIEW_REQUIRED' if editorial_ready else 'PROVISIONAL_UPSTREAM_INCOMPLETE',
             'shortlist_ids': [c['moment_id'] for c in chosen] if editorial_ready else [],
             'hypothetical_diagnostic_ids_not_shortlist': [] if editorial_ready else [c['moment_id'] for c in chosen],
             'selection': report,
             'candidate_diagnostics': [{'moment_id': c.get('moment_id'), 'score': c.get('editorial_score_final'),
                 'topic_id': c.get('topic_id'), 'editorial_blockers': c.get('editorial_blockers', []),
                 'eligible_for_review': c.get('default_shortlist_eligible', False),
                 'narrative_status': c.get('narrative_integrity', {}).get('status'),
                 'laughter_segment_ids': c.get('humor_integrity', {}).get('laughter_segment_ids', [])}
                 for c in review],
             'note': 'Historical scores are reused, not recomputed. Shortlist is a human-review proposal, not render or publication approval.'}
    return brief


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--analysis', type=Path)
    source.add_argument('--package', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-items', type=int, default=12)
    parser.add_argument('--min-score', type=float, default=.50)
    args = parser.parse_args(argv)
    if not (0 <= args.min_score <= 1):
        parser.error('--min-score must be 0..1')
    data = _load(args.package or args.analysis, package=bool(args.package))
    result = evaluate(*data[:5], max_items=args.max_items, min_score=args.min_score)
    result['historical_metrics'] = data[5]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'input_candidate_count', 'evaluated_candidate_count', 'shortlist_ids')}, ensure_ascii=False))
    print('Report:', args.out)


if __name__ == '__main__':
    main()
