"""Read-only diagnosis; reports hashes/pointers/counts, never evidence strings."""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ldporto.core import file_hash
from ldporto.export_privacy import privacy_findings, sanitize_export


def main():
    root = Path('analysis/video_31329be78ca4')
    out = Path('automacao/execucao/etapa64')
    read = lambda name: json.loads((root/name).read_text(encoding='utf-8-sig'))
    package, analysis = read('second_curation_package.json'), read('analysis.json')
    sources = [(f"candidates/{c['candidate_id']}.json", c, 'second_curation_package.json')
               for c in package['candidates'] if c['candidate_id'] in ('MOMENT_00004_0003', 'MOMENT_00028_0004')]
    sources += [('editorial/candidate_catalog.json', {'candidates': package['candidates']}, 'second_curation_package.json'),
                ('visual/commercial_ocr_s8.json', read('commercial_visual_s8.json'), 'commercial_visual_s8.json')]
    legacy = re.compile(r'\\\\[^\s]+')
    def walk(value, pointer=''):
        if isinstance(value, dict):
            for key, item in value.items():
                yield from walk(item, pointer+'/'+key.replace('~', '~0').replace('/', '~1'))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                yield from walk(item, pointer+'/'+str(i))
        elif isinstance(value, str) and legacy.search(json.dumps(value, ensure_ascii=False)):
            yield {'pointer': pointer, 'type': 'str', 'pattern': 'JSON_escaped_backslash',
                   'rule': 'legacy_PRIVATE_PATH_UNC', 'classification': 'false_positive' if value == '\\' else 'indeterminate',
                   'length': len(value), 'sha256': hashlib.sha256(value.encode()).hexdigest()}
    diagnosis = []
    for name, value, source in sources:
        findings = list(walk(sanitize_export(value)))
        diagnosis.append({'path': name, 'local_source': source, 'source_sha256': file_hash(root/source),
                          'origin': 'reconstructed_JSON_projection_not_retained_failed_staging_bytes',
                          'findings': findings, 'count': len(findings),
                          'decoded_privacy_findings': [{'classification': 'indeterminate',
                            'export_action': 'redacted', **finding} for finding in privacy_findings(value)]})
    candidates = [c for c in package['candidates'] if c.get('alternate_of') is None]
    moments = read('main_moments.json')
    metric_keys = ('candidates_before_dedup', 'candidates_after_dedup', 'final_shortlist_count',
                   'complete_story_arc_count', 'partial_story_arc_count', 'qa_arc_count')
    audit = {'analysis_sha256': file_hash(root/'analysis.json'), 'candidate_count': len(candidates),
             'metrics': {k: analysis['candidate_metrics'].get(k) for k in metric_keys},
             'commercial_risk_states': dict(Counter((c.get('commercial_risk') or {}).get('state') for c in candidates)),
             'missing_standalone_clarity': sum(c.get('editorial_scores', {}).get('standalone_clarity', c.get('score_components', {}).get('standalone_clarity')) is None for c in candidates),
             'missing_hook_strength': sum(c.get('hook_strength') is None for c in candidates),
             'missing_hook_score': sum(c.get('hook_score') is None for c in moments),
             'catalog_including_alternates': len(package['candidates']),
             'shortlist_count': len(analysis.get('editorial_shortlist', [])),
             'story_arc_count': len(read('story_arcs.json')),
             'selected_stories': len(analysis.get('social_output', {}).get('stories', [])),
             'question_candidates': len(read('question_candidates.json')),
             'qa_pairs': len(read('question_answer_pairs.json')),
             'qa_complete': sum(c.get('question_answer_complete') is True for c in read('question_answer_pairs.json')),
             'qa_status_counts': dict(Counter(c.get('answer_status') for c in read('question_answer_pairs.json'))),
             'resolved_focus_coverage': analysis['analysis_quality'].get('resolved_focus_coverage'),
             'active_speaker_coverage': analysis['analysis_quality'].get('active_speaker_coverage'),
             'blocker_counts': dict(Counter(str(reason) for c in candidates for reason in c.get('editorial_blockers', []))),
             'commercial_gate_counts': dict(Counter(c.get('commercial_gate_reason') for c in candidates)),
             'publication_ready': False, 'gate_changes': False, 'heavy_inference_executed': False}
    for name, document in [('root_cause.json', diagnosis), ('editorial_audit.json', audit)]:
        out.mkdir(parents=True, exist_ok=True)
        (out/name).write_text(json.dumps(sanitize_export(document), ensure_ascii=False, sort_keys=True, indent=2), encoding='utf-8')
    print(json.dumps({'diagnosed_paths': len(diagnosis), 'detection_counts': [r['count'] for r in diagnosis],
                      'shortlist': audit['shortlist_count'], 'stories': audit['selected_stories']}))


if __name__ == '__main__':
    main()
