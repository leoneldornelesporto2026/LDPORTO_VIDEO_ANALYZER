import json
import compare_runs


def test_resumed_full_run_cache_is_not_a_measured_performance_gain(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new'
    old.mkdir();new.mkdir()
    common={'metadata':{'sha256':'same-source'},'execution_scope':'full_pipeline'}
    (old/'analysis_summary.json').write_text(json.dumps({**common,'stage_runtime':{
        '04_transcription':{'elapsed_seconds':100.,'cache_hit':False}}}),encoding='utf-8')
    (new/'analysis_summary.json').write_text(json.dumps({**common,'stage_runtime':{
        '04_transcription':{'elapsed_seconds':0.,'cache_hit':True,'original_elapsed_seconds':110.}}}),encoding='utf-8')
    report=compare_runs.compare_runs(old,new)
    result=report['changes']['total_measured_stage_runtime_seconds']
    assert result['delta'] is None
    assert result['comparison_status']=='not_comparable_cached_stages'
    markdown=compare_runs.comparison_markdown(report)
    assert 'cache' in markdown.lower()
    assert '| 04_transcription | 100.0 | 0.0 | -100.0 |' not in markdown
