from ldporto.reports import _editorial_review_mapping


def test_report_normalizes_legacy_review_list_without_crash():
    value = _editorial_review_mapping([{'moment_id': 'M1', 'editorial_score': .8}, 'bad'])
    assert value['status'] == 'partial'
    assert value['top_moments'] == [{'moment_id': 'M1', 'editorial_score': .8}]


def test_report_omits_non_mapping_review_payload():
    assert _editorial_review_mapping('provider-error') == {}
