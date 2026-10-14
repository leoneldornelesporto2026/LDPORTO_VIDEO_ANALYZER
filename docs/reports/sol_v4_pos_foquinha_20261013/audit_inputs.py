"""Verify the existing Foquinha package and extract small editorial evidence views."""
from collections import Counter
from pathlib import Path, PurePosixPath
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
SOURCE = ROOT / 'pacotes_para_enviar/SECOND_CURATION_PARTIAL_7laRa_F3FbA_20261013_140239_076346_6beb9d.zip'


def save(name, data):
    (REPORT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    with zipfile.ZipFile(SOURCE) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        issues = []
        if archive.testzip() is not None:
            issues.append('crc_failure')
        if len({n.casefold() for n in names}) != len(names):
            issues.append('duplicate_or_case_collision')
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
                issues.append('unsafe_path:' + name)
        files = manifest['files']
        for item in files:
            data = archive.read(item['path'])
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                issues.append('checksum_or_size:' + item['path'])
        save('original_zip_integrity.json', {'state': 'VERIFIED' if not issues else 'FAILED',
            'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'members': len(names),
            'declared_files': len(files), 'files_verified': len(files) - len(issues), 'issues': issues})
        if issues:
            raise ValueError('original_package_integrity_failed')
        def load(name):
            return json.loads(archive.read(name))
        catalog = load('editorial/candidate_catalog.json')['candidates']
        selection = load('editorial/selection_report_s3.json')['selection_report']
        queue = load('editorial/human_review_queue.json')
        gate = load('summary/final_quality_gate.json')
        index = load('CURATION_INDEX.json')
        rejected = {r['moment_id']: r for r in selection.get('rejected', [])}
        top = sorted(catalog, key=lambda r: (-r.get('editorial_score_final', 0), r['rank']))[:10]
        traces = []
        for row in top:
            cid = row['candidate_id']
            ranking = row.get('ranking_uncertainty') or {}
            reasons = list(rejected.get(cid, {}).get('reasons') or [])
            traces.append({'candidate_id': cid, 'rank': row['rank'], 'start': row['start'], 'end': row['end'],
                'duration': row['duration'], 'editorial_score_final': row.get('editorial_score_final'),
                'score_floor': selection.get('min_score'), 'selection_reasons': reasons,
                'editorial_blockers': row.get('editorial_blockers', []),
                'missing_required_components': ranking.get('missing_required_components', []),
                'score_components': row.get('score_components'), 'duration_contract': row.get('duration_contract'),
                'duration_exception': row.get('duration_exception'),
                'duration_exception_reason': row.get('duration_exception_reason'),
                'clean_opening': row.get('clean_opening'), 'clean_ending': row.get('clean_ending'),
                'context_requirement': row.get('context_requirement'), 'context_dependency': row.get('context_dependency'),
                'commercial_review_state': row.get('commercial_review_state'),
                'commercial_evidence_state': row.get('commercial_evidence_state'),
                'commercial_gate_reason': row.get('commercial_gate_reason'),
                'editorial_verified': row.get('editorial_verified'),
                'eligible_for_human_review': row.get('eligible_for_human_review'),
                'default_shortlist_eligible': row.get('default_shortlist_eligible'),
                'official_shortlist_selected': cid in selection.get('selected_ids', []),
                'person_resolution_reason': row.get('person_resolution_reason'),
                'source_quality_status': gate.get('status'), 'editorial_integrity_ready': gate.get('editorial_integrity_ready'),
                'global_status_named_in_local_reasons': any('P1_DEGRADED' in r or 'active_speaker' in r for r in reasons),
                'human_approved': row.get('human_approved'), 'preview_approved': gate.get('preview_approved'),
                'publication_ready': row.get('publication_ready'),
                'provenance': {'catalog_ref': 'editorial/candidate_catalog.json',
                    'candidate_ref': 'candidates/' + cid + '.json', 'selection_ref': 'editorial/selection_report_s3.json',
                    'input_zip_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest()}})
        save('top10_gate_matrix_before.json', traces)
        qas = load('editorial/qa_pairs.json')
        stories = load('editorial/story_arcs.json')
        save('original_editorial_metrics.json', {'catalog': len(catalog), 'queue_entries': len(queue['entries']),
            'evaluated': selection.get('candidates_evaluated'), 'shortlist': index.get('default_shortlist_count'),
            'alternates': sum(bool(r.get('alternate_of')) for r in catalog),
            'rejection_counts': dict(Counter(r for v in selection.get('rejected', []) for r in set(v.get('reasons', [])))),
            'qa_count': len(qas), 'qa_statuses': dict(Counter(r.get('answer_status') for r in qas)),
            'qa_unresolved_reasons': dict(Counter(r.get('unresolved_reason') for r in qas if r.get('answer_status') == 'unresolved')),
            'story_count': len(stories), 'narrative_supported': sum(r.get('narrative_supported') is True for r in stories),
            'quality_gate_status': gate.get('status'), 'preview_approved': gate.get('preview_approved'),
            'publication_ready': gate.get('publication_ready')})
        packet = []
        for row, trace in zip(top, traces):
            packet.append({'kind': 'candidate', 'candidate_id': row['candidate_id'],
                'start': row['start'], 'end': row['end'], 'literal_text': row.get('transcript_literal', ''),
                'segment_ids': row.get('segment_ids', []), 'context_before': row.get('context_before', []),
                'context_after': row.get('context_after', []), 'measured_gate_reasons': trace['selection_reasons'],
                'assessment_scope': 'recorded_selection_gates_not_human_content_annotation',
                'annotation_status': 'PENDING_HUMAN', 'complete_conversation': None,
                'independent_clarity': None, 'audio_verified': False, 'publication_ready': False})
        unresolved = [r for r in qas if r.get('answer_status') == 'unresolved']
        qa_examples = [r for r in qas if r.get('answer_status') == 'linked_candidate'][:1]
        qa_examples += [next(r for r in unresolved if r.get('unresolved_reason') == reason)
                        for reason in sorted({r.get('unresolved_reason') for r in unresolved})]
        qa_examples += [r for r in qas if r.get('answer_status') == 'not_expected'][:1]
        for row in qa_examples[:6]:
            packet.append({'kind': 'qa', 'question_id': row['question_id'],
                'start': row.get('question_start'), 'end': row.get('answer_end') or row.get('question_end'),
                'literal_question': row.get('question'), 'literal_answer_candidate': row.get('answer'),
                'segment_ids': row.get('evidence_segment_ids', []), 'recorded_status': row.get('answer_status'),
                'recorded_reason': row.get('unresolved_reason'), 'annotation_status': 'PENDING_HUMAN',
                'question_answer_ground_truth': None, 'audio_verified': False, 'publication_ready': False})
        for row in stories[:4]:
            packet.append({'kind': 'story', 'story_arc_id': row.get('story_arc_id'),
                'start': row.get('start'), 'end': row.get('end'),
                'setup': row.get('setup'), 'development': row.get('development'), 'payoff': row.get('payoff'),
                'recorded_narrative_supported': row.get('narrative_supported'),
                'annotation_status': 'PENDING_HUMAN', 'narrative_ground_truth': None, 'publication_ready': False})
        save('manual_review_packet_20.json', {'schema_version': '1.0',
            'annotation_status': 'PENDING_HUMAN', 'precision_recall': None, 'entries': packet,
            'source_zip_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'scope': '20 source text windows for reproducible human review; no visual identity or audio approval inferred.'})
        print(json.dumps({'original_zip': 'VERIFIED', 'members': len(names), 'declared_files': len(files),
                          'top10': len(traces), 'manual_review_entries': len(packet)}))


if __name__ == '__main__':
    main()
