"""Historical evidence remains intact without importing an automation executor."""
import hashlib
import json
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / 'fixtures'


def test_historical_prompt_blobs_retain_recorded_git_provenance():
    folder = FIXTURES / 'autopilot_historico'
    origin = json.loads((folder / 'ORIGEM.json').read_text(encoding='utf-8'))
    assert origin['source_commit'] == '34797e164377f05e64ae628daf499cda2fb8bf55'
    files = {'MAPA_ETAPAS.json'} | {p.relative_to(folder).as_posix()
                                  for p in (folder / 'prompts').glob('ETAPA_*.txt')}
    assert len(files) == origin['prompt_count'] + 1 == 53
    assert files == set(origin['files'])
    for name, item in origin['files'].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == item['sha256']
    assert (folder / 'prompts/ETAPA_02.txt').is_file()


def test_relocated_historical_zip_bytes_match_original_provenance():
    folder = FIXTURES / 'historical_evidence'
    origin = json.loads((folder / 'ORIGEM.json').read_text(encoding='utf-8'))
    assert origin['evidence_scope'] == 'historical_Joao_Gordo_R4.9-S4_not_current_inference'
    for name, item in origin['files'].items():
        data = (folder / name).read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
