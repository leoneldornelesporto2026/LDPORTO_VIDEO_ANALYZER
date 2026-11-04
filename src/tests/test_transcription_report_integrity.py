"""Original-language sidecars remain separate and signed through report export."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ldporto.compact_artifacts import load_analysis_artifacts
from ldporto.core import read_json, write_json
from ldporto.execution_receipts import verify_report_receipt
from ldporto.reports import ReportEngine
from test_stage06_report_coherence import fixture


@pytest.mark.parametrize('auto_export', [False, True])
@pytest.mark.parametrize('target', ['transcription_provenance.json', 'translations.json',
                                  'original_import_segments.json', 'transcription_language_hypotheses.json'])
def test_original_language_report_sidecars_are_signed_and_tampering_blocks_replay(
        tmp_path, monkeypatch, auto_export, target):
    monkeypatch.setattr('ldporto.runtime_metrics.record_runtime_history', lambda *args, **kwargs: None)
    analysis = fixture()
    original = deepcopy(analysis['transcript_segments'])
    analysis['transcript_original_import_segments'] = deepcopy(original)
    analysis['transcription_provenance'] = {'task': 'transcribe', 'text_kind': 'original_transcript',
                                           'engine': 'synthetic_test_fixture'}
    analysis['transcription_language_hypotheses'] = []
    analysis['transcript_translations'] = [{'segment_id': original[0]['segment_id'],
                                          'text': 'Synthetic translated annotation.', 'target_language': 'en'}]
    ctx = SimpleNamespace(output=tmp_path / 'reports', signature=analysis['metadata']['sha256'],
                          config={'strict': False, 'export': {'second_curation_auto': auto_export,
                                  'second_curation_output_dir': str(tmp_path / 'packages')}})
    ReportEngine().run(ctx, analysis, [])
    receipt, _ = verify_report_receipt(ctx.output)
    assert target in receipt['artifact_checksums']
    assert read_json(ctx.output / 'transcript_segments.json') == original
    assert read_json(ctx.output / 'translations.json') == analysis['transcript_translations']
    hydrated = load_analysis_artifacts(ctx.output)
    assert hydrated['transcript_translations'] == analysis['transcript_translations']
    assert hydrated['transcript_original_import_segments'] == original
    write_json(ctx.output / target, {'tampered': True})
    with pytest.raises(ValueError, match='checksum_mismatch'):
        load_analysis_artifacts(ctx.output)
