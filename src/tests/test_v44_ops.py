import json
import pytest
from ldporto.progress import WeightedProgress


def test_slower_current_units_are_not_discarded_and_future_stages_not_scaled():
    model = WeightedProgress({'semantic': 100, 'export': 20}, clock=lambda: 0)
    model.update({'stage':'semantic','status':'running','current':0,'total':20,'elapsed_seconds':0})
    elapsed = 0
    for i, cost in enumerate([1, 1, 1, 10, 10, 10], 1):
        elapsed += cost
        model.update({'stage':'semantic','status':'running','current':i,'total':20,'elapsed_seconds':elapsed})
    s = model.snapshot()
    assert s['stage_eta_seconds'] >= 77
    assert s['total_eta_seconds'] == s['stage_eta_seconds'] + 20
    assert s['total_eta_range_seconds'][1] >= s['total_eta_seconds']


def test_cleanup_preserves_editorial_and_live_media_and_requires_confirmation(tmp_path):
    from ldporto.storage import cleanup_preview, execute_cleanup, media_lease
    audio = tmp_path/'audio'; audio.mkdir()
    (audio/'original.wav').write_bytes(b'a'*100)
    (audio/'words.json').write_text('{}')
    (tmp_path/'FINAL.mp4').write_bytes(b'final')
    source=tmp_path/'source.mp4'; source.write_bytes(b'source')
    with media_lease(source):
        preview=cleanup_preview(tmp_path, source, include_source=True)
        assert str(source) not in [r['path'] for r in preview['removable']]
        assert preview['reclaimable_bytes'] == 100
        with pytest.raises(ValueError):
            execute_cleanup(preview)
        execute_cleanup(preview, confirmed=True)
    assert source.exists() and (tmp_path/'FINAL.mp4').exists() and (audio/'words.json').exists()


def test_cleanup_rejects_files_changed_after_preview(tmp_path):
    from ldporto.storage import cleanup_preview, execute_cleanup
    audio=tmp_path/'audio'; audio.mkdir()
    path=audio/'original.wav'; path.write_bytes(b'old')
    preview=cleanup_preview(tmp_path)
    path.write_bytes(b'new contents')
    result=execute_cleanup(preview, confirmed=True)
    assert result['removed_bytes'] == 0 and path.exists()


def test_eta_history_requires_matching_hardware_models_config_and_non_cached_work(tmp_path):
    from ldporto.runtime_metrics import record_runtime_history, historical_stage_estimates
    path=tmp_path/'history.json'; meta={'duration':60,'width':1920,'height':1080}
    for cost in (10, 12, 14):
        record_runtime_history(meta, {}, {'semantic':{'elapsed_seconds':cost,'cache_hit':False}}, path)
    assert historical_stage_estimates(meta, {}, path)['semantic']['median_seconds'] == 12
    assert not historical_stage_estimates(meta, {'semantic_analysis':{'model':'changed'}}, path)


def test_optional_source_selection_cannot_remove_a_final_render(tmp_path):
    from ldporto.storage import cleanup_preview
    final = tmp_path / 'clip_FINAL.mp4'
    final.write_bytes(b'final-render')
    preview = cleanup_preview(tmp_path, final, include_source=True)
    assert preview['removable'] == []


def test_eta_history_separates_cpu_and_gpu_profiles():
    from ldporto.runtime_metrics import history_fingerprint
    assert history_fingerprint({}, {'device': 'cpu'}) != history_fingerprint({}, {'device': 'cuda'})
