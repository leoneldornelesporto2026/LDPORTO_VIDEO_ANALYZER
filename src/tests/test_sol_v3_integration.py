"""Observable causal accounting and signed source-review handoff integration."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from ldporto.analysis_quality import quality_gate
from ldporto.compact_artifacts import load_analysis_artifacts
from ldporto.core import read_json, write_json
from ldporto.execution_receipts import verify_report_receipt
from ldporto.director_integration import attach_director
from ldporto.reports import ReportEngine
from ldporto.transcript_dossier import raw_hypothesis_dossier, validate_review_dossier
from test_stage06_report_coherence import fixture


def test_causal_diagnostics_distinguishes_measured_unqualified_asd_from_missing_and_preview():
    analysis = {'run_manifest': {'root_cause_stage': '07_people_tracking'},
        'analysis_quality': {'diarization_available': True, 'resolved_focus_coverage': 0.,
                             'source_preservation_fraction': 1.},
        'people_observations': [{'time': 1}],
        'stage_status': {'10_active_speaker': {'status': 'partial'}},
        'speaker_person_summary': [{'speaker_id': 'S0', 'person_id': None,
            'raw_audio_windows': 10, 'candidate_evidence_windows': 4,
            'independent_affinity_windows': 2, 'qualified_positive_windows': 0}],
        'metadata': {'duration': 19.014},
        'video_analysis': {'quality': {'body_detection': {'fallback_reason': 'yolo_local_model_missing',
                            'actually_executed_backend': 'hog'}}}}
    attach_director(analysis, {'timeline': [], 'metrics': {'zoom_gate_diagnostics': {'source_windows': 251}}})
    before = deepcopy(analysis)
    gate = quality_gate(analysis)
    causes = {row['reason_code']: row for row in gate['root_causes']}
    assert gate['status'] == 'P1_DEGRADED'
    assert gate['publication_ready'] is False and gate['preview_approved'] is False
    assert causes['active_speaker_unavailable']['category'] == 'insufficient_evidence'
    accounting = causes['active_speaker_unavailable']['evidence']['speaker_windows'][0]
    assert [accounting[key] for key in ('raw_audio_windows', 'candidate_evidence_windows',
            'independent_affinity_windows', 'qualified_positive_windows')] == [10, 4, 2, 0]
    assert causes['unresolved_camera_focus']['stage'] == '19_camera_director'
    assert causes['unresolved_camera_focus']['evidence']['camera_gate_diagnostics'] == {'source_windows': 251}
    assert causes['preview_skipped']['category'] == 'not_validated'
    assert gate['causal_diagnostics']['legacy_root_cause_stage'] == '07_people_tracking'
    assert gate['causal_diagnostics']['capability_limitations'] == [{'stage': '07_people_tracking',
        'reason_code': 'yolo_local_model_missing', 'category': 'dependency_unavailable',
        'executed_backend': 'hog', 'effect_on_speaker_person': 'not_independently_established'}]
    assert analysis == before


def test_legacy_unknown_measurements_remain_unknown_and_required_dependencies_still_fail():
    analysis = {'speaker_person_summary': [{'speaker_id': 'S0', 'evidence_windows': 0}],
                'stage_status': {'05_diarization': {'status': 'unavailable'}}}
    gate = quality_gate(analysis)
    causes = {row['reason_code']: row for row in gate['root_causes']}
    evidence = causes['active_speaker_unavailable']['evidence']
    assert evidence['measurement_accounting_available'] is False
    assert evidence['speaker_windows'][0]['candidate_evidence_windows'] is None
    assert gate['status'] == 'P0_FAIL'
    assert causes['diarization_unavailable']['category'] == 'availability_cause_unknown'
    assert gate['publication_ready'] is False


@pytest.mark.parametrize('status,category', [('unavailable','availability_cause_unknown'),
    ('cancelled','interrupted'), ('blocked','blocked_reason_unknown'), ('failed','technical_error')])
def test_stage_state_does_not_invent_missing_dependency_or_technical_error(status, category):
    gate = quality_gate({'stage_status': {'10_active_speaker': {'status': status}}})
    cause = next(row for row in gate['root_causes'] if row['reason_code'] == 'active_speaker_unavailable')
    assert cause['category'] == category
    assert cause['evidence']['recorded_stage_status'] == status
    assert gate['publication_ready'] is False


@pytest.mark.parametrize('target', ['source_audio_review.json', 'transcription_hypothesis_comparison.json'])
@pytest.mark.parametrize('auto_export', [False, True])
@pytest.mark.parametrize('legacy_full', [False, True])
def test_source_review_signed_sidecars_hydrate_and_tampering_blocks_reuse(
        tmp_path, monkeypatch, target, auto_export, legacy_full):
    monkeypatch.setattr('ldporto.runtime_metrics.record_runtime_history', lambda *a, **kw: None)
    analysis = fixture()
    analysis['words'] = [{'word_id': 'W_DIAGNOSTIC', 'start': 1., 'end': 2.,
                          'word': 'Synthetic', 'probability': .5, 'speaker': None}]
    analysis['source_audio_review'] = {'schema_version': '1.0', 'human_review_status': 'PENDING',
        'regions': [{'start': 1., 'end': 2., 'word_ids': [analysis['words'][0]['word_id']]}]}
    analysis['transcription_hypothesis_comparison'] = {'schema_version': '1.0',
        'regions': [], 'status': 'UNRESOLVED'}
    original = deepcopy(analysis['words'])
    ctx = SimpleNamespace(output=tmp_path / 'reports', signature=analysis['metadata']['sha256'],
        config={'strict': False, 'export': {'second_curation_auto': auto_export,
                'legacy_full_analysis': legacy_full, 'second_curation_output_dir': str(tmp_path/'packages')}})
    ReportEngine().run(ctx, analysis, [])
    receipt, _ = verify_report_receipt(ctx.output)
    assert target in receipt['artifact_checksums']
    compact = read_json(ctx.output / 'analysis.json')
    if not legacy_full:
        assert compact['source_audio_review_ref']['path'] == 'source_audio_review.json'
    hydrated = load_analysis_artifacts(ctx.output)
    assert hydrated['source_audio_review'] == analysis['source_audio_review']
    assert hydrated['transcription_hypothesis_comparison'] == analysis['transcription_hypothesis_comparison']
    assert hydrated['words'] == original
    write_json(ctx.output / target, {'tampered': True})
    with pytest.raises(ValueError, match='checksum_mismatch'):
        load_analysis_artifacts(ctx.output)


@pytest.mark.parametrize('corruption', ['human_review', 'word_hypothesis', 'segment_hypothesis'])
def test_raw_dossier_rejects_false_verification_and_cross_hypothesis_bindings(corruption):
    words = [{'word_id': 'W0', 'hypothesis_id': 'H0'}]
    segments = [{'segment_id': 'S0', 'hypothesis_ids': ['H0']}]
    dossier = raw_hypothesis_dossier({'transcript_segments': segments}, words)
    contract = {'schema_version': '1.1', 'source_audio_review_ref': 'review',
                'hypothesis_comparison_ref': 'comparison', 'raw_hypothesis_dossier_ref': 'raw'}
    documents = {'review': {'publication_ready': False}, 'comparison': {}, 'raw': dossier}
    read = lambda key: json.dumps(documents[key]).encode()
    assert validate_review_dossier(contract, read, segments, words, {}) == []
    if corruption == 'human_review':
        dossier['human_audio_review_performed'] = True
        expected = 'transcript_contract:raw_dossier_must_not_claim_verification'
    elif corruption == 'word_hypothesis':
        words[0]['hypothesis_id'] = 'OTHER'
        expected = 'transcript_contract:hypothesis_word_binding_disagreement'
    else:
        segments[0]['hypothesis_ids'] = ['OTHER']
        expected = 'transcript_contract:hypothesis_segment_binding_disagreement'
    assert expected in validate_review_dossier(contract, read, segments, words, {})
    assert validate_review_dossier({'schema_version':'1.0'}, read, segments, words, {}) == []


@pytest.mark.parametrize('backend,category', [
    ({'fallback_reason':'yolo_import_failed','diagnostic_reason':'dependency_missing'}, 'dependency_unavailable'),
    ({'fallback_reason':'yolo_inference_failed','exception_type':'OutOfMemoryError'}, 'resource_unavailable'),
    ({'fallback_reason':'yolo_inference_failed','diagnostic_reason':'inference_error'}, 'runtime_failure')])
def test_body_failure_reason_is_not_mislabeled_configuration(backend, category):
    gate = quality_gate({'video_analysis':{'quality':{'body_detection':backend}}})
    limitation = gate['causal_diagnostics']['capability_limitations'][0]
    assert limitation['category'] == category
    assert limitation['effect_on_speaker_person'] == 'not_independently_established'
