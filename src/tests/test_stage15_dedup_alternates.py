from copy import deepcopy
import json
import zipfile

from ldporto.editorial import deduplicate_candidates
from ldporto.second_curation import build_second_curation_package
from ldporto.second_curation_export import build_core_package, validate_core_package
from test_v43_handoff import analysis_fixture


def row(mid, start=30, end=90, **extra):
    base = deepcopy(analysis_fixture()['main_moments'][0])
    base.update(moment_id=mid, ideal_start=start, ideal_end=end,
                editorial_score_final=.6, evidence_coverage=None)
    base['core_moment'].update(start=start, end=end)
    base.update(extra)
    return base


def test_complete_boundaries_win_over_high_score_without_mutating_input():
    incomplete = row('A', clean_ending=False, editorial_score_final=.99)
    complete = row('B', 28, 92, editorial_score_final=.5)
    original = deepcopy([incomplete, complete])
    groups, metrics = deduplicate_candidates([incomplete, complete])
    assert [incomplete, complete] == original
    assert groups[0]['moment_id'] == 'B'
    assert groups[0]['dedup_selection']['alternate_reasons']['A'] == 'confirmed_clean_boundaries'
    assert groups[0]['alternates'][0]['moment_id'] == 'A'
    assert groups[0]['evidence_coverage'] is None
    assert groups[0]['dedup_selection']['member_evidence'][0]['evidence_coverage'] is None
    assert metrics['id_migration_map'] == {}


def test_blockers_and_evidence_break_ties_and_stable_ids():
    a = row('A', editorial_blockers=['missing_payoff'], editorial_score_final=.99)
    b = row('B', evidence_coverage=.8)
    c = row('C', evidence_coverage=.9)
    for inputs in ([a, b, c], [c, b, a]):
        groups, _ = deduplicate_candidates(inputs)
        assert groups[0]['moment_id'] == 'C'
    groups, _ = deduplicate_candidates([row('B'), row('A')])
    assert groups[0]['moment_id'] == 'A'


def test_same_guest_topic_distinct_discourse_survives():
    a = row('A', story_arc_id='STORY_A', person_id='P1')
    b = row('B', story_arc_id='STORY_B', person_id='P1')
    assert len(deduplicate_candidates([a, b])[0]) == 2
    a.pop('story_arc_id'); b.pop('story_arc_id')
    a['question_answer_linkage'] = ['Q1']; b['question_answer_linkage'] = ['Q2']
    assert len(deduplicate_candidates([a, b])[0]) == 2
    a.pop('question_answer_linkage'); b.pop('question_answer_linkage')
    a['core_moment'].update(start=35, end=45)
    b['core_moment'].update(start=60, end=70)
    assert len(deduplicate_candidates([a, b])[0]) == 2


def test_nearby_subjects_without_equivalent_evidence_survive():
    a, b = row('A'), row('B', 32, 92)
    a['core_moment']['text'] = 'Carreira musical inicio banda'
    b['core_moment']['text'] = 'Carreira musical viagens turne'
    b['evidence_segment_ids'] = ['S2']
    assert len(deduplicate_candidates([a, b])[0]) == 2


def test_temporal_threshold_and_no_transitive_bridge():
    a, b, c = row('A', 0, 60), row('B', 12, 72), row('C', 24, 84)
    groups, _ = deduplicate_candidates([c, b, a])
    assert len(groups) == 2
    assert {m['moment_id'] for g in groups for m in [g, *g['alternates']]} == {'A', 'B', 'C'}
    assert len(deduplicate_candidates([a, row('D', 12.01, 72.01)])[0]) == 2


def test_nested_alternates_survive_primary_replacement_and_repeated_dedup():
    a, b, c, d = row('A'), row('B'), row('C'), row('D', editorial_score_final=.9)
    a['alternates'] = [b]
    d['alternates'] = [c]
    groups, metrics = deduplicate_candidates([a, d])
    assert groups[0]['moment_id'] == 'D'
    assert {r['moment_id'] for r in groups[0]['alternates']} == {'A', 'B', 'C'}
    assert metrics['input_member_count'] == 4
    assert deduplicate_candidates(groups)[0] == groups


def test_all_alternates_navigable_in_second_curation(tmp_path):
    analysis = analysis_fixture()
    primary, metrics = deduplicate_candidates([row('A'), row('B', 28, 92, editorial_score_final=.9), row('C', 32, 88)])
    analysis['main_moments'] = primary
    analysis['editorial_shortlist'] = ['B']
    analysis['candidate_metrics'] = metrics
    package = build_second_curation_package(analysis)
    assert set(package['resolvable_index']) == {'A', 'B', 'C'}
    for candidate in package['candidates']:
        assert candidate['dedup_selection']['primary_moment_id'] == 'B'
        if candidate['candidate_id'] != 'B':
            assert candidate['alternate_of'] == 'B'
    result = build_core_package(analysis, output_dir=tmp_path)
    assert validate_core_package(result['path'])['status'] == 'valid'
    with zipfile.ZipFile(result['path']) as archive:
        groups = json.loads(archive.read('editorial/alternate_groups.json'))
        assert groups[0]['primary_candidate'] == 'B'
        assert set(groups[0]['alternates']) == {'A', 'C'}
        for cid, path in groups[0]['candidate_files'].items():
            candidate = json.loads(archive.read(path))
            assert candidate['candidate_id'] == cid
            assert candidate['alternate_of'] == 'B'
        catalog = json.loads(archive.read('editorial/candidate_catalog.json'))
        assert all(candidate['publication_ready'] is False for candidate in catalog['candidates'])
        gates = json.loads(archive.read('editorial/final_gate_report.json'))
        assert gates['publication_ready'] is False


def test_lexical_equivalence_requires_specific_core_and_no_shared_topic_shortcut():
    a, b = row('A'), row('B', 32, 92)
    a['evidence_segment_ids'] = []; b['evidence_segment_ids'] = []
    text = 'Festival gravacao instrumento palco viagem contrato ensaio produtor'
    a['core_moment']['text'] = text; b['core_moment']['text'] = text
    assert len(deduplicate_candidates([a, b])[0]) == 1
    a['core_moment']['text'] = 'Carreira musical'
    b['core_moment']['text'] = 'Carreira musical'
    assert len(deduplicate_candidates([a, b])[0]) == 2
