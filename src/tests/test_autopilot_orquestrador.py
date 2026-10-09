"""Offline smoke tests: never connect to OpenAI, do not consume Codex credits."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ldporto_autopilot', PROJECT / 'orquestrador.py')
autopilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(autopilot)


def setup_temporary_project(tmp_path, monkeypatch):
    root = tmp_path / 'Projeto com espacos'
    root.mkdir()
    (root / 'analyze.py').write_text('print("hello")\n', encoding='utf-8')
    (root / 'src').mkdir()
    (root / 'src' / 'analyzer.py').write_text('VALUE=1\n', encoding='utf-8')
    (root / '.venv' / 'Lib').mkdir(parents=True)
    (root / '.venv' / 'Lib' / 'token.txt').write_text('NEVER BACKUP')
    (root / 'models').mkdir()
    (root / 'models' / 'heavy.onnx').write_text('NO')
    (root / 'automacao' / 'evidencias').mkdir(parents=True)
    (root / 'automacao' / 'evidencias' / 'huge.zip').write_text('NO')
    (root / 'automacao' / 'prompts').mkdir()
    rows = []
    for n in range(1, 43):
        (root / 'automacao' / 'prompts' / f'ETAPA_{n:02d}.txt').write_text('Fazer tarefa ' + str(n), encoding='utf-8')
        rows.append({'n': n, 'file_path': f'prompts/ETAPA_{n:02d}.txt', 'title': f'Etapa {n}'})
    (root / 'automacao' / 'MAPA_ETAPAS.json').write_text(json.dumps(rows), encoding='utf-8')
    (root / 'AGENTS.md').write_text('Testing')
    (root / 'orquestrador.py').write_text('# fake orchestrator')
    for name, value in {'ROOT': root, 'AUTO': root / 'automacao', 'PROMPTS': root / 'automacao' / 'prompts',
                        'PLAN': root / 'automacao' / 'MAPA_ETAPAS.json', 'EVIDENCE': root / 'automacao' / 'evidencias',
                        'RUN': root / 'automacao' / 'execucao', 'LOGS': root / 'automacao' / 'execucao' / 'logs',
                        'SNAPSHOTS': root / 'automacao' / 'execucao' / 'snapshots',
                        'REPORTS': root / 'automacao' / 'execucao' / 'checkpoints',
                        'STATE': root / 'automacao' / 'execucao' / 'estado.json',
                        'LOCK': root / 'automacao' / 'execucao' / 'orquestrador.lock',
                        'SCHEMA': root / 'automacao' / 'execucao' / 'schema.json',
                        'GUARD_FILES': [root / 'orquestrador.py', root / 'AGENTS.md', root / 'automacao' / 'MAPA_ETAPAS.json']}.items():
        monkeypatch.setattr(autopilot, name, value)
    monkeypatch.setattr(autopilot, 'run_pytest', lambda n, timeout: (0, 'test_baseline.log'))
    return root


def test_plan_detects_all_prompts_and_keeps_42_legacy_map_entries():
    actual = PROJECT / 'automacao' / 'prompts'
    prompts = list(actual.glob('ETAPA_*.txt'))
    assert len(prompts) >= 42
    assert len(autopilot.load_plan()) == len(prompts)
    assert [int(row['n']) for row in autopilot.load_plan()] == list(range(1, len(prompts) + 1))
    parsed = json.loads((PROJECT / 'automacao' / 'MAPA_ETAPAS.json').read_text(encoding='utf-8'))
    assert [int(x['n']) for x in parsed] == list(range(1, 43))
    assert all((PROJECT / 'automacao' / i['file_path']).is_file() for i in parsed)


def test_init_snapshot_excludes_media_secrets_and_does_not_overwrite(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    first = autopilot.setup()
    second = autopilot.setup()
    assert first['baseline_snapshot'] == second['baseline_snapshot']
    archive = root / first['baseline_snapshot']['file']
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        assert 'src/analyzer.py' in names
        assert '.venv/Lib/token.txt' not in names
        assert 'models/heavy.onnx' not in names
        assert 'automacao/evidencias/huge.zip' not in names
        assert z.testzip() is None


def test_sequence_uses_same_workspace_and_stops_on_failure(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    autopilot.setup()
    events = []

    def fake_agent(prompt, n, timeout):
        events.append(n)
        (root / 'src' / 'analyzer.py').write_text(f'VALUE={n+1}\n')
        (autopilot.REPORTS / f'CHECKPOINT_ETAPA_{n:02d}.md').parent.mkdir(parents=True, exist_ok=True)
        (autopilot.REPORTS / f'CHECKPOINT_ETAPA_{n:02d}.md').write_text('Checklist de testes e alterações verificadas.\n' * 8)
        return ({'status': 'DONE' if n == 1 else 'FAILED',
                 'summary': 'Etapa completa' if n == 1 else 'Falha detectada',
                 'files_changed': ['src/analyzer.py'], 'tests': ['pytest'], 'risks': []}, 0.01)

    monkeypatch.setattr(autopilot, 'call_codex', fake_agent)
    monkeypatch.setattr(autopilot, 'run_pytest', lambda n, timeout: (0, 'simulated_passing_pytest.log'))
    assert autopilot.execute(3, retry=False, timeout=300, pytest_timeout=300) == 1
    assert events == [1, 2]
    state = autopilot.require_state()
    assert state['completed'] == 1 and state['status'] == 'PAUSED' and state['active'] == 2
    assert (root / state['partial_snapshot']['file']).exists()
    assert (root / state['last_snapshot']['file']).exists()
    assert (root / 'src' / 'analyzer.py').read_text() == 'VALUE=3\n'
    with pytest.raises(RuntimeError, match='--retry'):
        # Error wording may vary but advancing must fail.
        autopilot.execute(1, retry=False, timeout=300, pytest_timeout=300)

    def resume_agent(prompt, n, timeout):
        assert n == 2 and 'RETOMADA' in prompt
        (root / 'src' / 'analyzer.py').write_text('VALUE=4\n')
        return ({'status': 'DONE', 'summary': 'Retomada e aprovada',
                 'files_changed': ['src/analyzer.py'], 'tests': ['pytest'], 'risks': []}, 0.01)

    monkeypatch.setattr(autopilot, 'call_codex', resume_agent)
    assert autopilot.execute(1, retry=True, timeout=300, pytest_timeout=300) == 0
    assert autopilot.require_state()['completed'] == 2


def test_external_drift_blocks_next_step(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    autopilot.setup()
    (root / 'src' / 'analyzer.py').write_text('VALUE=99\n')
    with pytest.raises(RuntimeError, match='fora do orquestrador'):
        autopilot.execute(1, retry=False, timeout=300, pytest_timeout=300)
    assert autopilot.require_state()['completed'] == 0


def test_prompts_and_orchestrator_are_guarded(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    state = autopilot.setup()
    (root / 'automacao' / 'prompts' / 'ETAPA_01.txt').write_text('ADULTERADO')
    with pytest.raises(RuntimeError, match='orquestrador, plano ou prompts'):
        autopilot.verify_guard(state['guard_hashes'])

@pytest.mark.skipif(__import__('os').name == 'nt', reason='POSIX fake executable; Windows CLI tested on user machine')
def test_cli_process_uses_global_approval_flag_and_structured_result(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    executable = tmp_path / 'fake_codex'
    executable.write_text('''#!/usr/bin/env python3
import sys, json
args=sys.argv[1:]
assert args[:3]==['--ask-for-approval','never','exec'], args
assert '--sandbox' in args and args[args.index('--sandbox')+1]=='workspace-write'
assert '--output-schema' in args
out=args[args.index('--output-last-message')+1]
json.dump({'status':'DONE','summary':'Teste de flags','files_changed':['src/analyzer.py'],'tests':['simulado'],'risks':[]},open(out,'w'))
''', encoding='utf-8')
    executable.chmod(0o755)
    monkeypatch.setattr(autopilot, 'find_codex', lambda: str(executable))
    result, seconds = autopilot.call_codex('não consome créditos', 1, 30)
    assert result['status'] == 'DONE'
    assert seconds >= 0
    assert (root / 'automacao' / 'execucao' / 'logs' / 'ETAPA_01_codex.log').exists()


def test_unmodified_guard_and_evidence_hash_are_consistent(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    (root / 'automacao' / 'evidencias' / 'huge.zip').write_text('benchmark')
    state = autopilot.setup()
    autopilot.verify_guard(state['guard_hashes'])
    autopilot.validate_evidence(state)
    (root / 'automacao' / 'evidencias' / 'huge.zip').write_text('benchmark alterado')
    with pytest.raises(RuntimeError, match='Evidência removida ou alterada'):
        autopilot.validate_evidence(state)


def test_append_new_prompt_auto_reopens_finished_state_and_advances(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    state = autopilot.setup()
    state['completed'] = 42
    state['status'] = 'FINISHED'
    autopilot.persist(state)
    (root / 'automacao' / 'prompts' / 'ETAPA_43.txt').write_text(
        'L.D.PORTO | ETAPA 43/43 — Teste automático de expansão\n', encoding='utf-8')
    events = []
    def fake_agent(prompt, n, timeout):
        events.append((n, prompt))
        (root / 'src' / 'analyzer.py').write_text('VALUE=43\n', encoding='utf-8')
        cp = autopilot.REPORTS / 'CHECKPOINT_ETAPA_43.md'
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text('Implementado e testado.\n' * 10, encoding='utf-8')
        return ({'status':'DONE', 'summary':'Expandido', 'files_changed':['src/analyzer.py'],
                 'tests':['pytest simulado'], 'risks':[]}, 0.01)
    monkeypatch.setattr(autopilot, 'call_codex', fake_agent)
    assert autopilot.execute(99, retry=False, timeout=300, pytest_timeout=300) == 0
    assert len(events) == 1 and events[0][0] == 43
    assert 'ETAPA 43/43' in events[0][1]
    final = autopilot.require_state()
    assert final['completed'] == 43 and final['status'] == 'FINISHED'
    assert final['stages'][-1]['n'] == 43
    assert len(final['plan_expansions']) == 1


def test_old_prompt_mutation_remains_blocked_after_auto_growth(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    autopilot.setup()
    (root / 'automacao' / 'prompts' / 'ETAPA_43.txt').write_text('Etapa futura', encoding='utf-8')
    (root / 'automacao' / 'prompts' / 'ETAPA_01.txt').write_text('MODIFICADO', encoding='utf-8')
    with pytest.raises(RuntimeError, match='alterado'):
        autopilot.execute(1, retry=False, timeout=300, pytest_timeout=300)


def test_gap_in_prompt_numbers_fails_closed(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    (root / 'automacao' / 'prompts' / 'ETAPA_44.txt').write_text('Falta etapa 43', encoding='utf-8')
    with pytest.raises(RuntimeError, match='fora de sequência'):
        autopilot.load_plan()


def test_one_time_upgrade_preserves_paused_step_and_prior_checkpoint(tmp_path, monkeypatch):
    root = setup_temporary_project(tmp_path, monkeypatch)
    state = autopilot.setup()
    state['completed'], state['active'], state['status'] = 41, 42, 'PAUSED'
    (root / 'src' / 'analyzer.py').write_text('VALUE=42\n', encoding='utf-8')
    state['partial_snapshot'] = autopilot.snapshot('PARCIAL_ETAPA_42_123')
    state['paused_manifest_sha256'] = autopilot.manifest_hash(autopilot.manifest())
    autopilot.persist(state)
    (root / 'orquestrador.py').write_text('# Executor atualizado pelo usuário\n', encoding='utf-8')
    (root / 'automacao' / 'prompts' / 'ETAPA_43.txt').write_text('Nova tarefa', encoding='utf-8')
    with pytest.raises(RuntimeError, match='adopt-prompts'):
        autopilot.execute(1, retry=True, timeout=300, pytest_timeout=300)
    assert autopilot.adopt_prompts() == 0
    upgraded = autopilot.require_state()
    assert upgraded['completed'] == 41 and upgraded['active'] == 42
    assert upgraded['status'] == 'PAUSED'
    assert upgraded['paused_manifest_sha256'] == autopilot.manifest_hash(autopilot.manifest())
    assert upgraded['partial_snapshot'] == state['partial_snapshot']
    assert len(upgraded['plan_expansions']) == 1
