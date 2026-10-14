"""SOL V3: source-grounded grouping and review handoff, without model calls."""
from copy import deepcopy
import hashlib
import json
import zipfile

import pytest

from ldporto.config import DEFAULTS
from ldporto.editorial import topic_hierarchy
from ldporto.editorial_outcome import classify_editorial_outcome
from ldporto.ollama_local import profile_options
from ldporto.semantic import contextual_program_sections
from ldporto.second_curation_export import build_core_package, validate_core_package


def short_discourse():
    """Recorded AFTER source excerpts/timestamps, used only as source fixtures."""
    segments = [
        {'segment_id': 'S0', 'start': .94, 'end': 1.38, 'text': 'Alright,'},
        {'segment_id': 'S1', 'start': 1.44, 'end': 3.08, 'text': 'so here we are in front of the elephants.'},
        {'segment_id': 'S2', 'start': 4.6, 'end': 12.32, 'text': 'The cool thing about these guys is that they have really, really, really long trunks.'},
        {'segment_id': 'S3', 'start': 12.42, 'end': 13.5, 'text': "And that's cool."},
        {'segment_id': 'S4', 'start': 16.48, 'end': 18.34, 'text': "And that's pretty much all there is to say."},
    ]
    labels = ['Introducao ao contexto do video', 'Caracteristica dos elefantes',
              'Reforco da caracteristica mencionada', 'Conclusao do comentario sobre os elefantes']
    groups = [segments[:2], segments[2:3], segments[3:4], segments[4:]]
    topics = [{'topic_id': f'T{i}', 'topic': labels[i], 'summary': labels[i],
               'start': group[0]['start'], 'end': group[-1]['end'],
               'evidence_segment_ids': [row['segment_id'] for row in group],
               'speakers': ['SP0'], 'method': 'ollama', 'context_required': 'none'} for i, group in enumerate(groups)]
    return segments, topics


def test_short_referential_discourse_keeps_topics_but_groups_major_sections():
    segments, topics = short_discourse(); original = deepcopy(segments)
    topics, sections, *_ = topic_hierarchy(topics, segments)
    assert len(sections) == 4
    grouped, report = contextual_program_sections(topics, sections, segments)
    assert len(grouped) == 1 and len(topics) == 4
    assert grouped[0]['evidence_segment_ids'] == ['S0', 'S1', 'S2', 'S3', 'S4']
    assert grouped[0]['topic_ids'] == ['T0', 'T1', 'T2', 'T3']
    assert {topic['parent_section_id'] for topic in topics} == {grouped[0]['section_id']}
    assert report['topic_rows_preserved'] and not report['story_inference_created']
    assert segments == original


@pytest.mark.parametrize('reason', ['topic_change', 'speaker_change', 'commercial_boundary', 'large_gap', 'source_gap', 'degraded_boundary'])
def test_context_grouping_preserves_real_or_unresolved_boundaries(reason):
    segments, topics = short_discourse()
    if reason == 'topic_change':
        segments[2]['text'] = 'Changing the subject, these guys discuss another topic.'
    elif reason == 'speaker_change':
        topics[1]['speakers'] = ['SP1']
    elif reason == 'commercial_boundary':
        segments[2]['text'] = 'These guys sell products. Compre agora com cupom TESTE, link na bio!'
    elif reason == 'large_gap':
        segments[2].update(start=10, end=20); topics[1].update(start=10, end=20)
    elif reason == 'source_gap':
        segments.insert(2, {'segment_id': 'UNLINKED', 'start': 3.2, 'end': 4., 'text': 'Intervening evidence.'})
    elif reason == 'degraded_boundary':
        topics[1]['degraded_reason'] = ['technical_fixture_failure']
    topics, sections, *_ = topic_hierarchy(topics, segments)
    grouped, report = contextual_program_sections(topics, sections, segments)
    assert report['decisions'][1]['decision'] == 'keep_separate'
    assert grouped[0]['topic_ids'] == ['T0']


def test_context_grouping_cannot_hide_an_internal_source_gap():
    segments, topics = short_discourse()
    topics, sections, *_ = topic_hierarchy(topics, segments)
    sections[1]['evidence_segment_ids'] = ['S2', 'S4']
    _, report = contextual_program_sections(topics, sections, segments)
    assert report['decisions'][1]['decision'] == 'keep_separate'


def test_global_compact_schema_preserves_max_and_invalidates_mode_cache(tmp_path, monkeypatch):
    from ldporto import semantic
    from test_v43_semantic import review_candidate, review_row, envelope
    candidate = review_candidate(); quote = next(iter(semantic.prepare_quote_catalog([candidate])))
    captured = []
    def request(url, model, messages, schema, cfg):
        captured.append((messages[0]['content'], deepcopy(schema), profile_options(cfg)))
        return envelope([review_row('M1', quote)]), {}
    monkeypatch.setattr(semantic, 'ollama_chat', request)
    cfg = {**DEFAULTS['semantic_analysis'], '_global_cache_dir': str(tmp_path)}
    semantic.call_global_review(cfg, [], [candidate])
    semantic.call_global_review({**cfg, 'compact_prompt': True}, [], [candidate])
    _, cached = semantic.call_global_review({**cfg, 'compact_prompt': True}, [], [candidate])
    assert len(captured) == 2 and cached['cache_hit']
    assert 'Schema obrigatório:' in captured[0][0] and 'Schema obrigatório:' not in captured[1][0]
    assert captured[0][1:] == captured[1][1:]
    assert captured[1][2]['num_ctx'] == 32768 and captured[1][2]['num_predict'] == 6144
    assert len(list(tmp_path.glob('*.json'))) == 2


def diagnostic_analysis(duration=19.014):
    from test_v43_handoff import analysis_fixture
    analysis = analysis_fixture()
    segments, _ = short_discourse()
    analysis['metadata']['duration'] = duration
    analysis['transcript_segments'] = [{**row, 'speaker': 'SP1'} for row in segments if row['end'] <= duration]
    analysis['main_moments'] = []; analysis['editorial_shortlist'] = []
    analysis['topics'] = []
    analysis['words'] = [{'word_id': 'W1', 'segment_id': 'S2', 'word': 'trunks.', 'raw': ' trunks.',
                          'start': 11.9, 'end': 12.32, 'speaker': 'SP1', 'hypothesis_id': 'H1'}] if duration >= 12.32 else []
    analysis['transcription_provenance'] = {'task': 'transcribe', 'text_kind': 'original_asr_hypothesis',
                                          'raw_hypotheses_ref': [{'path': 'cache/source/raw.json', 'sha256': 'a' * 64}]}
    analysis['transcription_language_hypotheses'] = [{'hypothesis_id': 'H1', 'task': 'transcribe', 'language_hint': 'en'}]
    analysis['source_audio_review'] = {'schema_version': '1.0', 'requires_editorial_shortlist': False,
                                     'windows': [{'word_ids': ['W1'], 'ORIGINAL': deepcopy(analysis['words'])}] if analysis['words'] else [],
                                     'audio_verification_performed': False, 'publication_ready': False}
    analysis['transcription_hypothesis_comparison'] = {'schema_version': '1.0', 'affected_word_ids': ['W1'] if analysis['words'] else [],
                                                      'replacement_applied': False}
    return analysis


@pytest.mark.parametrize('duration', [5., 19.014])
def test_full_source_review_is_diagnostic_even_below_hard_minimum(duration):
    analysis = diagnostic_analysis(duration); original = deepcopy(analysis)
    result = classify_editorial_outcome(analysis)
    review = result['full_source_review']
    assert result['state'] == 'video_too_short'
    assert review['source_interval'] == {'start': 0., 'end': duration}
    assert not review['eligible_for_shortlist'] and not review['publication_ready'] and review['editorial_score'] is None
    assert result['duration_contract']['hard_min_seconds'] == 8 and result['quality_floor'] == .5
    assert analysis == original


def test_full_source_diagnostic_does_not_create_candidate_or_block_source_dossier(tmp_path):
    package = build_core_package(diagnostic_analysis(), output_dir=tmp_path)
    assert package['candidate_count'] == 0 and package['shortlist_count'] == 0
    assert validate_core_package(package['path'])['status'] == 'valid'
    with zipfile.ZipFile(package['path']) as archive:
        manifest = json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
        assert manifest['transcript_contract']['schema_version'] == '1.1'
        review = json.loads(archive.read('editorial/full_source_review.json'))
        assert review['word_ids'] == ['W1'] and not review['eligible_for_shortlist']
        words = [json.loads(line) for line in archive.read('transcript/relevant_words.jsonl').decode().splitlines()]
        assert words[0]['word_id'] == 'W1'
        dossier = json.loads(archive.read('transcript/raw_hypothesis_dossier.json'))
        assert dossier['producer_raw_artifacts'][0]['availability_in_package'] == 'unavailable'
        assert dossier['hypotheses'][0]['canonical_word_ids'] == ['W1']
        assert 'cache/source/raw.json' not in archive.namelist()


def rewrite_member(source, destination, member, mutate):
    with zipfile.ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    document = json.loads(files[member]); mutate(document)
    files[member] = json.dumps(document, ensure_ascii=False).encode()
    manifest = json.loads(files['SECOND_CURATION_MANIFEST.json'])
    entry = next(row for row in manifest['files'] if row['path'] == member)
    entry.update(bytes=len(files[member]), sha256=hashlib.sha256(files[member]).hexdigest())
    files['SECOND_CURATION_MANIFEST.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(destination, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)


@pytest.mark.parametrize('member,mutate,reason', [
    ('transcript/raw_hypothesis_dossier.json', lambda d: d['producer_raw_artifacts'][0].update(included_in_package=True), 'raw_external_availability'),
    ('transcript/source_audio_review.json', lambda d: d['windows'][0]['ORIGINAL'][0].update(word='invented'), 'original_word_disagreement'),
    ('transcript/hypothesis_comparison.json', lambda d: d.update(affected_word_ids=['MISSING']), 'review_word_reference'),
    ('editorial/full_source_review.json', lambda d: d.update(eligible_for_shortlist=True), 'diagnostic_only_gate'),
])
def test_rehashed_review_dossier_corruption_fails_closed(tmp_path, member, mutate, reason):
    package = build_core_package(diagnostic_analysis(), output_dir=tmp_path)
    altered = tmp_path / 'altered.zip'; rewrite_member(package['path'], altered, member, mutate)
    validation = validate_core_package(altered)
    assert validation['status'] == 'failed' and any(reason in error for error in validation['errors'])


def test_additive_causal_diagnostics_preserve_legacy_root_and_cross_document_parity(tmp_path):
    analysis = diagnostic_analysis()
    roots = [{'stage': '10_active_speaker', 'category': 'insufficient_evidence', 'code': 'synthetic_unresolved_fixture'}]
    analysis['quality_gate'] = {'status': 'P1_DEGRADED', 'issues': [], 'root_causes': roots,
                              'causal_diagnostics': {'schema_version': '1.0', 'legacy_root_cause_stage': '04_transcription', 'root_causes': roots}}
    package = build_core_package(analysis, output_dir=tmp_path)
    with zipfile.ZipFile(package['path']) as archive:
        gate = json.loads(archive.read('summary/final_quality_gate.json'))
        quality = json.loads(archive.read('summary/quality_summary.json'))
    assert gate['causal_diagnostics']['legacy_root_cause_stage'] == '04_transcription'
    assert gate['root_causes'] == quality['quality_gate']['root_causes'] == roots
    altered = tmp_path / 'causal_altered.zip'
    rewrite_member(package['path'], altered, 'summary/quality_summary.json', lambda d: d['quality_gate'].update(root_causes=[]))
    assert any('quality_causal_diagnostics_disagreement' in error for error in validate_core_package(altered)['errors'])
