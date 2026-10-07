from copy import deepcopy

import pytest

from ldporto.config import DEFAULTS
from ldporto.editorial import classify_content, rank_candidate, COMMERCIAL_TYPES


@pytest.mark.parametrize("text", [
    "Para voce que esta nos acompanhando agora, use o magnesio: desinflama o corpo e alivia diretamente a dor.",
    "Vendas abertas, adquira o seu ingresso em MegaBilheteria.com. Quer patrocinar?",
    "Sofa couro 100%, preco em torno de 15 mil na Openbox, 10 de 799,99, pronta entrega.",
    "Oportunidade imperdivel, taxa zero em 36 vezes e super valorizacao do seu carro.",
    "Oferecimento: Marca de exemplo, o patrocinador deste programa.",
])
def test_known_commercial_false_negatives_have_grounded_exclusion(text):
    result = classify_content(text, ["SEG_1"])
    assert result["content_type"] in COMMERCIAL_TYPES
    assert result["eligibility"] == "excluded"
    assert result["commercial_score"] >= .6
    assert result["evidence_spans"]
    assert result["evidence_segment_ids"] == ["SEG_1"]
    assert all(text[span["start_char"]:span["end_char"]] == span["text"] for span in result["evidence_spans"])


def test_editorial_product_discussion_is_not_sales_content():
    result = classify_content("Discutimos estudos sobre magnesio, riscos e efeitos colaterais, sem recomendar compra.", ["SEG_1"])
    assert result["content_type"] == "editorial_product_discussion"
    assert result["eligibility"] == "eligible"


def test_editorial_sponsorship_question_is_not_forced_sponsor_read():
    result = classify_content("Como o patrocinio afeta a independencia editorial?", ["SEG_1"])
    assert result["content_type"] not in COMMERCIAL_TYPES


def test_commercial_gate_reassesses_literal_evidence_before_ranking():
    candidate = {"moment_id": "AD", "ideal_start": 0, "ideal_end": 60,
                 "core_moment": {"text": "Adquira seu ingresso, vendas abertas em MegaBilheteria.com."},
                 "content_type": "editorial_content", "commercial_score": 0,
                 "hook_score": 1, "standalone_score": 1, "information_score": 1,
                 "clean_opening": True, "clean_ending": True,
                 "duration_suitability_score": 1, "context_requirement": "none"}
    ranked = rank_candidate(candidate, deepcopy(DEFAULTS["understanding"]))
    assert not ranked["default_shortlist_eligible"]
    assert ranked["commercial_classification"]["content_type"] in COMMERCIAL_TYPES


@pytest.mark.parametrize("duration,eligible", [(5, False), (20, False), (30, True), (90, True), (91, False), (181, False)])
def test_default_candidate_duration_contract_uses_timestamps(duration, eligible):
    row = {"moment_id": "M", "ideal_start": 0, "ideal_end": duration,
           "core_moment": {"text": "Uma explicacao completa sobre a carreira."},
           "clean_opening": True, "clean_ending": True, "context_requirement": "none",
           "duration_suitability_score": 1, "hook_score": .8, "standalone_score": .8}
    result = rank_candidate(row, deepcopy(DEFAULTS["understanding"]))
    assert result["default_shortlist_eligible"] is eligible
    assert result["duration_contract"]["target_max_seconds"] == 90


def test_long_story_exception_requires_grounded_setup_development_and_payoff():
    from ldporto.editorial import optimize_boundaries
    segments = [{"segment_id": f"S{index}", "start": index * 10, "end": (index + 1) * 10,
                 "speaker": "SPEAKER", "text": "Uma frase completa da historia."} for index in range(12)]
    story = {"start": 0, "end": 120, "kind": "complete_story", "completeness": "supported_setup_development_payoff",
             "setup": {"segment_ids": ["S0"]}, "development": {"segment_ids": ["S1", "S2"]},
             "payoff": {"segment_ids": ["S11"]}}
    row = {"start": 0, "end": 120, "evidence_segment_ids": [segment["segment_id"] for segment in segments], "context_requirement": "none"}
    result = optimize_boundaries(row, segments, deepcopy(DEFAULTS["understanding"]), story)
    assert result["duration_exception"]
    assert result["duration_exception_reason"]
    assert result["duration_suitability_score"] < 1
    story["payoff"] = None
    assert not optimize_boundaries(row, segments, deepcopy(DEFAULTS["understanding"]), story)["duration_exception"]


def test_discussion_section_does_not_expand_a_useful_clip_to_120_seconds():
    from ldporto.editorial import optimize_boundaries
    segments = [{"segment_id": f"S{index}", "start": index * 10, "end": (index + 1) * 10,
                 "speaker": "A", "text": "Uma explicacao completa sobre instrumentos."} for index in range(12)]
    row = {"start": 20, "end": 70, "evidence_segment_ids": [f"S{index}" for index in range(2, 7)], "context_requirement": "none"}
    discussion = {"start": 0, "end": 120, "completeness": "unresolved_payoff", "payoff": None}
    result = optimize_boundaries(row, segments, DEFAULTS["understanding"], discussion)
    assert result["ideal_end"] - result["ideal_start"] <= 90


def test_mid_sentence_opening_is_not_marked_clean_by_segment_start_alone():
    from ldporto.editorial import optimize_boundaries
    segments = [{"segment_id": "S0", "start": 0, "end": 45, "speaker": "A", "text": "Eu estava contando sobre"},
                {"segment_id": "S1", "start": 45, "end": 75, "speaker": "A", "text": "um problema que resolvemos."}]
    result = optimize_boundaries({"start": 45, "end": 75, "evidence_segment_ids": ["S1"], "context_requirement": "none"}, segments)
    assert result["clean_opening"] is False


def test_incomplete_ending_is_not_shortlist_eligible_despite_high_hook():
    row = {"moment_id": "M", "ideal_start": 0, "ideal_end": 60,
           "core_moment": {"text": "Uma revelacao importante e entao"},
           "clean_opening": True, "clean_ending": False, "context_requirement": "none",
           "hook_score": 1, "standalone_score": 1, "duration_suitability_score": 1}
    assert not rank_candidate(row)["default_shortlist_eligible"]


@pytest.mark.parametrize("text,kind", [("Tudo bem com voces?", "greeting_question"),
                                      ("A vida muda, ne?", "tag_question"),
                                      ("Quem nunca errou na vida?", "rhetorical_question")])
def test_non_editorial_questions_are_not_strong_hooks_or_answer_candidates(text, kind):
    from ldporto.semantic import classify_question, classify_hook, questions_answers, qa_contract
    assert classify_question(text)["question_type"] == kind
    assert classify_hook(text)["hook_strength"] <= .25
    records = questions_answers([{"segment_id": "S", "start": 0, "end": 2, "speaker": "A", "text": text}])
    assert qa_contract(records)["qa_metrics"]["question_candidate_count"] == 0


def test_grounded_reveal_is_a_true_editorial_hook():
    from ldporto.semantic import classify_hook
    result = classify_hook("Nunca contei o segredo que mudou a minha carreira.")
    assert result["hook_type"] == "reveal"
    assert result["hook_strength"] >= .7


def test_qa_answer_can_continue_after_a_short_interruption():
    from ldporto.semantic import questions_answers
    rows = [{"segment_id": "Q", "start": 0, "end": 3, "speaker": "HOST", "text": "Como gravou o album?"},
            {"segment_id": "X", "start": 3, "end": 4, "speaker": "HOST", "text": "Conta para nos."},
            {"segment_id": "A1", "start": 4, "end": 9, "speaker": "GUEST", "text": "Gravei o album num pequeno estudio."},
            {"segment_id": "Y", "start": 9, "end": 10, "speaker": "HOST", "text": "Muito bom!"},
            {"segment_id": "A2", "start": 10, "end": 15, "speaker": "GUEST", "text": "Depois finalizei a gravacao com a banda."}]
    result = questions_answers(rows)[0]
    assert result["answer_segment_ids"] == ["A1", "A2"]
    assert result["interruption_count"] == 2
    assert result["question_answer_complete"]
    assert result["answer_span"] == {"start": 4, "end": 15}


def test_discussion_blocks_are_not_reported_as_complete_stories():
    from ldporto.understanding import build_story_arcs
    segments = [{"segment_id": f"S{index}", "start": index * 10, "end": (index + 1) * 10,
                 "text": "Discutimos conceitos importantes de gravacao musical."} for index in range(4)]
    topics = [{"topic_id": "T", "start": 0, "end": 40, "evidence_segment_ids": [segment["segment_id"] for segment in segments]}]
    arc = build_story_arcs({"segments": segments}, topics)[0]
    assert arc["kind"] == "discussion_segment"
    assert arc["setup"] is None and arc["payoff"] is None
    assert not arc["narrative_supported"]


def test_complete_story_has_ordered_grounded_setup_and_payoff():
    from ldporto.understanding import build_story_arcs
    from test_v2_perception import transcript_fixture
    transcript = transcript_fixture()
    topic = {"topic_id": "T", "start": 0, "end": 10, "evidence_segment_ids": [segment["segment_id"] for segment in transcript["segments"]]}
    arc = build_story_arcs(transcript, [topic])[0]
    assert arc["kind"] == "complete_story"
    assert arc["setup"]["segment_ids"] == ["SEG_00000"]
    assert arc["payoff"]["segment_ids"] == ["SEG_00002"]


def test_topic_hierarchy_has_real_section_parents_and_merge_reasons():
    from ldporto.editorial import topic_hierarchy
    topics = [{"topic_id": "T1", "start": 0, "end": 10, "topic": "Carreira musical gravacao", "method": "ollama", "evidence_segment_ids": ["S1"]},
              {"topic_id": "T2", "start": 10, "end": 20, "topic": "Carreira musical instrumentos", "method": "ollama", "evidence_segment_ids": ["S2"]}]
    merged, sections, _, _, quality = topic_hierarchy(topics, [{"segment_id": "S1", "text": "Carreira musical."}, {"segment_id": "S2", "text": "Instrumentos musicais."}])
    assert len(merged) == 2 and len(sections) == 1
    assert all(topic["parent_section_id"] == sections[0]["section_id"] for topic in merged)
    assert quality["topic_merge_decisions"][0]["decision"] == "keep_separate"


def test_entities_keep_literal_spans_connectors_and_explainable_aliases():
    from ldporto.understanding import extract_entities
    text = "O professor Clovis de Barros veio ao programa Panico. O professor Clovis falou em Sao Paulo sobre a marca Openbox."
    rows = extract_entities({"segments": [{"segment_id": "S", "start": 0, "end": 20, "text": text}]})
    by_name = {row["name"]: row for row in rows}
    assert {"Clovis de Barros", "Clovis", "Panico", "Sao Paulo", "Openbox"} <= set(by_name)
    assert by_name["Clovis"]["canonical_entity_id"] == by_name["Clovis de Barros"]["entity_id"]
    assert by_name["Openbox"]["type"] == "brand"
    for row in rows:
        for mention in row["mentions_evidence"]:
            assert text[mention["start_char"]:mention["end_char"]] == mention["literal"]


def test_incomplete_generic_tail_is_not_part_of_program_entity():
    from ldporto.understanding import extract_entities
    rows = extract_entities({"segments": [{"segment_id": "S", "start": 0, "end": 5, "text": "O programa Panico Pelas conversas."}]})
    assert rows[0]["name"] == "Panico"


def test_ranking_separates_high_quality_from_missing_evidence_uncertainty():
    candidate = {'moment_id': 'M', 'ideal_start': 0, 'ideal_end': 60,
                 'core_moment': {'text': 'Uma explicacao completa sobre a carreira.'},
                 'hook_score': .9, 'standalone_score': .9, 'information_score': .9,
                 'clean_opening': True, 'clean_ending': True, 'context_requirement': 'none'}
    result = rank_candidate(candidate)
    assert result['editorial_quality_score'] > .8
    assert result['evidence_coverage'] < 1
    assert result['ranking_confidence'] != 'high'
    assert not result['ranking_uncertainty']['score_is_probability']
    assert 'audio_quality' in result['ranking_uncertainty']['missing_optional_components']


def test_candidate_metrics_do_not_call_every_duration_exclusion_commercial(tmp_path):
    import logging
    from ldporto.core import Context
    from ldporto.understanding import run_understanding
    from ldporto.config import load_config
    cfg = load_config()
    cfg['understanding']['extract_frames'] = False
    ctx = Context(tmp_path / 'none.mp4', tmp_path, cfg, 'fixture', logging.getLogger('candidate-metrics'))
    transcript = {'words':[], 'segments':[{'segment_id':'S', 'start':0, 'end':5, 'speaker':'SP', 'text':'Nunca contei o segredo desta pesquisa.'}]}
    semantic = {'topics':[{'topic_id':'T', 'start':0, 'end':5, 'topic':'Pesquisa', 'evidence_segment_ids':['S']}],
                'moments':[{'moment_id':'M', 'start':0, 'end':5, 'text':transcript['segments'][0]['text'],
                            'categories':['hook'], 'editorial':{'hook_strength':.9, 'clarity':.9}, 'standalone_class':'good',
                            'context_requirement':'none', 'evidence_segment_ids':['S']}], 'questions_answers':[]}
    result = run_understanding(ctx, {'duration':5}, transcript, {'speakers':[]}, {'people':[]}, {}, semantic, [], cfg['understanding'])['data']
    assert result['candidate_metrics']['excluded_commercial_count'] == 0
    assert result['candidate_metrics']['excluded_eligibility_count'] == 1
    assert result['candidate_metrics']['final_shortlist_count'] == len(result['editorial_shortlist'])

def test_understanding_normalizes_semantic_contract_list_shapes(tmp_path):
    import logging
    from ldporto.core import Context
    from ldporto.understanding import run_understanding
    from ldporto.config import load_config
    cfg = load_config()
    cfg['understanding']['extract_frames'] = False
    ctx = Context(tmp_path / 'none.mp4', tmp_path, cfg, 'fixture-contract', logging.getLogger('understanding-contract'))
    transcript = {'words': [], 'segments': [
        {'segment_id': 'S0', 'start': 0.0, 'end': 4.0, 'speaker': 'SP', 'text': 'Um dia eu comecei este trabalho.'},
        {'segment_id': 'S1', 'start': 4.0, 'end': 8.0, 'speaker': 'SP', 'text': 'Mas apareceu um problema.'},
        {'segment_id': 'S2', 'start': 8.0, 'end': 12.0, 'speaker': 'SP', 'text': 'No final deu certo.'},
    ]}
    moment = {'moment_id': 'M0', 'start': 0.0, 'end': 12.0, 'text': 'historia completa',
              'categories': ['storytelling'], 'editorial': {'hook_strength': .8, 'clarity': .9},
              'standalone_class': 'good', 'context_requirement': 'none',
              'evidence_segment_ids': ['S0', 'S1', 'S2']}
    semantic = {
        'topics': [
            {'topic_id': 'T0', 'start': 0.0, 'end': 12.0, 'topic': 'Historia', 'summary': 'Resumo',
             'method': 'ollama', 'evidence_segment_ids': ['S0', 'S1', 'S2']},
            ['provider-nested-row-that-must-not-crash'],
        ],
        'moments': [moment],
        'questions_answers': [],
        'program_sections': [{'section_id': 'SEC0', 'topic_ids': ['T0']}],
        'editorial_review': [{'moment_id': 'M0', 'editorial_score': .91}],
    }
    result = run_understanding(ctx, {'duration': 12.0}, transcript, {'speakers': []}, {'people': []},
                               {}, semantic, [], cfg['understanding'])
    assert result['status'] == 'ok'
    assert result['data']['main_moments']
    assert result['data']['main_moments'][0]['editorial_score'] is not None
    assert any('semantic_contract_normalized' in note for note in result['notes'])


def test_understanding_deep_contract_normalizes_nested_lists_and_writes_diagnostics(tmp_path):
    import logging
    from ldporto.config import load_config
    from ldporto.core import Context, read_json
    from ldporto.understanding import run_understanding
    cfg = load_config(); cfg['understanding']['extract_frames'] = False
    ctx = Context(tmp_path / 'none.mp4', tmp_path, cfg, 'deep-contract', logging.getLogger('deep-contract'))
    transcript = {'words': [], 'segments': [
        {'segment_id': 'S0', 'start': 0.0, 'end': 5.0, 'speaker': 'SP', 'text': 'Um dia eu comecei e no final deu certo.'}]}
    semantic = {
        'topics': [{'topic_id': 'T0', 'start': 0.0, 'end': 5.0, 'topic': 'Historia', 'summary': 'Resumo',
                    'method': 'ollama', 'evidence_segment_ids': ['S0'], 'speakers': ['SP']}],
        'moments': [{'moment_id': 'M0', 'start': 0.0, 'end': 5.0, 'text': 'momento completo',
                     'categories': ['storytelling'], 'editorial': [['bad nested provider row']],
                     'standalone_class': 'good', 'context_requirement': 'none', 'evidence_segment_ids': ['S0']}],
        'questions_answers': [], 'program_sections': [{'section_id': 'SEC', 'topic_ids': ['T0']}],
        'editorial_review': {'top_moments': [['bad'], {'moment_id': 'M0', 'editorial_score': .8}],
                             'content_angles': 'bad-string'}}
    result = run_understanding(ctx, {'duration': 5.0}, transcript, {'speakers': []}, {'people': []}, {}, semantic, [], cfg['understanding'])
    assert result['status'] == 'ok'
    diagnostics = read_json(tmp_path / 'understanding_contract_diagnostics.json')
    paths = {row['path'] for row in diagnostics['events']}
    assert 'semantic.moments[0].editorial' in paths
    assert 'semantic.editorial_review.top_moments' in paths
    assert 'semantic.editorial_review.content_angles' in paths
