"""Offline replay must preserve evidence and never approve publication."""
import copy
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.dev.replay_editorial_stage17 import compare, encoded, main
from scripts.dev.review_editorial_s3 import evaluate


EVIDENCE = Path(__file__).resolve().parents[2] / 'automacao/evidencias'


def test_real_same_52_ids_reproducible_and_unapproved(tmp_path):
    review = EVIDENCE / 'CHATGPT_REVIEW.zip'
    curation = EVIDENCE / 'SECOND_CURATION_READY.zip'
    first, shortlist = compare(review, curation)
    assert encoded(first) == encoded(compare(review, curation)[0])
    assert first['source_build'] == 'R4.9-S4-TRACKING-FACIAL'
    assert len(first['diff']) == first['candidate_count'] == 52
    assert len({r['candidate_id'] for r in first['diff']}) == 52
    assert first['old_shortlist_ids'] == ['MOMENT_00006_0005']
    assert first['inputs'][0]['members'] and first['inputs'][1]['members']
    assert not shortlist['homologated'] and not shortlist['publish_ready']
    assert all(r['payoff_confirmed'] is None and not r['publish_ready'] for r in first['diff'])
    # Byte-identical output across independent CLI invocations, including CSV.
    for name in ('a', 'b'):
        main(['--review-package', str(review), '--curation-package', str(curation),
              '--output-dir', str(tmp_path / name)])
    for name in ('comparison.json', 'candidates.csv', 'shortlist_candidate.json', 'output_hashes.json'):
        assert (tmp_path / 'a' / name).read_bytes() == (tmp_path / 'b' / name).read_bytes()


@pytest.mark.parametrize('interval', [(None, 10), (10, 5), (True, 10), (-1, 10)])
def test_invalid_intervals_remain_in_audit(interval):
    rows = [{'moment_id': 'invalid', 'ideal_start': interval[0], 'ideal_end': interval[1],
             'default_shortlist_eligible': True, 'editorial_score_final': .9}]
    original = copy.deepcopy(rows)
    result = evaluate(rows, [], [], [], True)
    assert rows == original
    assert result['evaluated_candidate_count'] == 1
    assert result['shortlist_ids'] == []
    assert 'invalid_source_interval' in result['candidate_diagnostics'][0]['editorial_blockers']


def test_mismatched_run_rejected(tmp_path):
    target = tmp_path / 'mismatch.zip'
    with ZipFile(EVIDENCE / 'SECOND_CURATION_READY.zip') as source, ZipFile(target, 'w') as out:
        for name in ('SECOND_CURATION_MANIFEST.json', 'editorial/candidate_catalog.json',
                     'editorial/default_shortlist.json', 'editorial/selection_report_s3.json'):
            data = source.read(name)
            if name == 'SECOND_CURATION_MANIFEST.json':
                doc = json.loads(data)
                doc['run_id'] = 'different'
                data = encoded(doc).encode()
            out.writestr(name, data)
    with pytest.raises(ValueError, match='same run'):
        compare(EVIDENCE / 'CHATGPT_REVIEW.zip', target)


def test_missing_upstream_does_not_promote(tmp_path):
    target = tmp_path / 'limited.zip'
    with ZipFile(EVIDENCE / 'CHATGPT_REVIEW.zip') as source, ZipFile(target, 'w') as out:
        for name in source.namelist():
            if name.endswith(('/main_moments.json', '/run_manifest.json')):
                out.writestr(name, source.read(name))
    report, shortlist = compare(target, EVIDENCE / 'SECOND_CURATION_READY.zip')
    assert report['candidate_count'] == 52
    assert 'story_arcs.json' in report['limitations']
    assert shortlist['candidate_ids'] == []
    assert shortlist['status'] == 'PROVISIONAL_UPSTREAM_INCOMPLETE'
