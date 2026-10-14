"""Verify an actual completed replay reuses the same package; no new export."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))

from ldporto.narrative_replay import replay_narrative_analysis
from ldporto.core import file_hash

if __name__ == '__main__':
    previous = json.loads((REPORT/'release_replay/replay_result.json').read_text(encoding='utf8'))
    evidence = json.loads((REPORT/'test_evidence_summary.json').read_text(encoding='utf8'))
    started = time.perf_counter()
    result = replay_narrative_analysis(ROOT/'analysis/video_5198fcdaef38', REPORT/'release_replay',
        reference_package=ROOT/'pacotes_para_enviar/SECOND_CURATION_PARTIAL_zd_wjssZ7mc_20261014_001849_795742_c0795c.zip',
        test_evidence=evidence)
    record = {'cache_hit': result['cache_hit'], 'actual_lookup_wall_seconds': time.perf_counter()-started,
        'same_package': result['result']['path'] == previous['result']['path'],
        'same_package_sha256': file_hash(result['result']['path']) == previous['package_sha256'],
        'new_model_calls': result['new_model_calls'], 'publication_ready': False}
    assert record['cache_hit'] and record['same_package'] and record['same_package_sha256']
    (REPORT/'cache_repeat_validation.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record))
