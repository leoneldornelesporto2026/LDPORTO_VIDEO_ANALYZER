from ldporto.semantic import semantic_failure_category


def test_real_v43_portuguese_topic_error_is_coverage_not_reference():
    assert semantic_failure_category('Tópicos do LLM não cobrem todos os segmentos em ordem.') == 'TOPIC_COVERAGE'
