"""Offline regressions for a review-only legacy evidence path (never a verified replay)."""
import json
import hashlib
from pathlib import Path

import pytest

from ldporto.core import write_json, file_hash
from ldporto.legacy_review import (SUMMARY_INLINE_FIELDS, CAMERA_OUTPUTS,
                                   plan_legacy_review, create_legacy_review_input)
from ldporto.compact_artifacts import load_analysis_artifacts


def _fixture(tmp_path):
    root = tmp_path / 'analysis'
    root.mkdir(parents=True)
    original = {name: {'field': name} if name not in ('editorial_shortlist', 'issues') else []
                for name in SUMMARY_INLINE_FIELDS}
    original['metadata'] = {'duration': 120, 'source': {'id': 'synthetic'}}
    original['analysis_status'] = 'partial'
    original['editorial_shortlist'] = []
    original['issues'] = []
    original.update(collection_storage='references', collection_refs={},
                    run_manifest={'stage_status': {'18b_global_camera_planner': {'status': 'ok'},
                                                   '19_camera_director': {'status': 'partial'}}})
    summary = {source: original[key] for key, source in SUMMARY_INLINE_FIELDS.items()}
    summary['stage_status'] = original['run_manifest']['stage_status']
    signed = {}
    for name, value in (
        ('analysis_summary.json', summary),
        ('second_curation_package.json', {'schema_version': '3.1', 'candidates': []}),
        ('CHATGPT_ANALYSIS_HANDOFF.compact.json', {'schema_version': '4.2', 'second_curation_package_ref': {'path': 'second_curation_package.json'}}),
        ('camera_plan.json', {'camera': 'synthetic'}),
        ('camera_director_timeline.json', {'camera': []}),
        ('transcript_segments.json', [{'segment_id': 's1', 'text': 'test', 'start': 0, 'end': 3},
                                      {'segment_id': 's2', 'text': 'contact synthetic@example.test', 'start': 4, 'end': 8}]),
        ('second_curation_package_unused.json', {})
    ):
        write_json(root / name, value)
        if name != 'second_curation_package_unused.json':
            signed[name] = file_hash(root / name)
    original['collection_refs']['transcript_segments'] = {
        'path': 'transcript_segments.json', 'sha256': signed['transcript_segments.json']}
    write_json(root / 'analysis.json', original)
    write_json(root / 'manifest.json', {'artifact_checksums': signed})
    return root


def test_legacy_review_accepts_self_consistency_without_pretending_authentication(tmp_path):
    root = _fixture(tmp_path)
    plan = plan_legacy_review(root)
    assert plan['status'] == 'review_input_possible'
    assert plan['review_input_possible'] is True
    assert not plan['can_replay_verified_stage21']
    assert not plan['publication_ready']
    assert plan['historical_authentication'] == 'not_established'
    assert plan['collection_count'] == 1
    assert len(plan['inline_fields']) == 9
    assert plan['cache_receipts']['19_camera_director'] == 'not_attested'
    assert not list(tmp_path.rglob('DERIVED_FROM.json'))


def test_isolated_sanitized_review_hydrates_and_preserves_original(tmp_path):
    root = _fixture(tmp_path)
    before = {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    plan = plan_legacy_review(root)
    output = tmp_path / 'review'
    result = create_legacy_review_input(root, output, expected_hashes=plan['source_reference_hashes'])
    assert result['status'] == 'review_only_created'
    assert result['historical_authentication'] == 'not_established'
    assert not result['publication_ready']
    derived = load_analysis_artifacts(output)
    assert derived['derived_review_only'] is True
    assert derived['editorial_shortlist'] == []
    assert '[REDACTED_PRIVATE]' in derived['transcript_segments'][1]['text']
    assert 'synthetic@example.test' not in (output/'transcript_segments.json').read_text()
    evidence = json.loads((output/'DERIVED_FROM.json').read_text())
    assert evidence['publication_ready'] is False
    assert evidence['historical_authentication'] == 'not_established'
    assert before == {p.name: file_hash(p) for p in root.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match='unsafe_or_existing_review_output'):
        create_legacy_review_input(root, output, expected_hashes=plan['source_reference_hashes'])


@pytest.mark.parametrize('target', ['analysis_summary.json', 'camera_plan.json', 'transcript_segments.json'])
def test_signed_artifact_change_is_blocked(tmp_path, target):
    root = _fixture(tmp_path)
    (root / target).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        plan_legacy_review(root)


def test_inline_difference_blocks_review(tmp_path):
    root = _fixture(tmp_path)
    analysis = json.loads((root / 'analysis.json').read_text())
    analysis['quality_gate'] = {'status': 'READY'}
    write_json(root / 'analysis.json', analysis)
    plan = plan_legacy_review(root)
    assert not plan['review_input_possible']
    assert plan['inline_fields']['quality_gate'] == 'not_verifiable_from_local_export'
    assert not plan['can_replay_verified_stage21']


def test_unverifiable_run_manifest_blocks_review(tmp_path):
    root = _fixture(tmp_path)
    analysis = json.loads((root / 'analysis.json').read_text())
    analysis['run_manifest']['stage_status']['19_camera_director']['status'] = 'ok'
    write_json(root / 'analysis.json', analysis)
    plan = plan_legacy_review(root)
    assert not plan['review_input_possible']
    assert plan['run_manifest_stage_status'] == 'unverified'


def test_unknown_collection_or_missing_signature_rejected(tmp_path):
    root = _fixture(tmp_path)
    analysis = json.loads((root / 'analysis.json').read_text())
    analysis['collection_refs']['private_custom'] = {'path': 'analysis.json', 'sha256': '0' * 64}
    write_json(root / 'analysis.json', analysis)
    with pytest.raises(ValueError, match='unknown_collection_reference'):
        plan_legacy_review(root)
    root = _fixture(tmp_path / 'new')
    manifest = json.loads((root / 'manifest.json').read_text())
    del manifest['artifact_checksums']['transcript_segments.json']
    write_json(root / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='missing_local_artifact_checksum'):
        plan_legacy_review(root)


def test_plan_hash_conflict_cannot_be_applied(tmp_path):
    root = _fixture(tmp_path)
    plan = plan_legacy_review(root)
    bad = {**plan['source_reference_hashes'], 'analysis.json': '0' * 64}
    with pytest.raises(ValueError, match='unapproved_or_changed_review_source'):
        create_legacy_review_input(root, tmp_path/'review', expected_hashes=bad)
    assert not (tmp_path/'review').exists()


def test_untrusted_manifest_cannot_insert_absolute_or_traversal(tmp_path):
    root = _fixture(tmp_path)
    manifest = json.loads((root/'manifest.json').read_text())
    manifest['artifact_checksums']['../other.json'] = '0' * 64
    write_json(root/'manifest.json', manifest)
    with pytest.raises(ValueError, match='invalid_artifact_checksum_inventory'):
        plan_legacy_review(root)


def test_source_mutation_during_generation_blocks_confirmation(tmp_path, monkeypatch):
    import ldporto.legacy_review as review
    root = _fixture(tmp_path)
    plan = review.plan_legacy_review(root)
    previous = review._read_verified
    calls = [0]
    def changed(folder, filename, signed, **kwargs):
        result = previous(folder, filename, signed, **kwargs)
        calls[0] += 1
        if filename == 'transcript_segments.json' and calls[0] > 4:
            (root / 'analysis.json').write_text('{}', encoding='utf-8')
        return result
    monkeypatch.setattr(review, '_read_verified', changed)
    with pytest.raises((ValueError, KeyError)):
        review.create_legacy_review_input(root, tmp_path / 'review', expected_hashes=plan['source_reference_hashes'])
    assert not (tmp_path / 'review').exists()


def test_legacy_review_integrates_with_recovery_but_never_promotes_verified_status(tmp_path):
    from ldporto.curation_recovery import recover
    root = _fixture(tmp_path)
    preview = recover(root, root/'not_needed_cache', review_only=True)
    assert preview['review_input_possible'] and not preview['can_replay_verified_stage21']
    with pytest.raises(ValueError, match='explicit_review_output_required'):
        recover(root, root/'not_needed_cache', review_only=True, apply=True,
                expected_hashes=preview['source_reference_hashes'])
    finished = recover(root, root/'not_needed_cache', tmp_path/'review', review_only=True, apply=True,
                       expected_hashes=preview['source_reference_hashes'])
    assert finished['status'] == 'review_only_created'
    assert not finished['publication_ready']
