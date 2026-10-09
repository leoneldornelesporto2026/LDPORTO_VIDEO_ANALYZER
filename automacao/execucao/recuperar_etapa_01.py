#!/usr/bin/env python3
"""Recupera a Etapa 01 já concluída pelo Codex sem consumir outra chamada.

Instalar em: automacao/execucao/recuperar_etapa_01.py
Executar da raiz: .venv\\Scripts\\python.exe automacao\\execucao\\recuperar_etapa_01.py

Só opera se estado PAUSED / completed=0 / active=1, Codex tiver retornado DONE,
checkpoint existir e integridade dos guardas/evidências estiver intacta.
Não altera o orquestrador nem o teste de allowlist.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import orquestrador as core

RUN = ROOT / 'automacao' / 'execucao'
STAGE = 1
DEST = ROOT / 'automacao' / 'baselines'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def recover():
    core.note('Recuperação offline da ETAPA 01 (SEM Codex).')
    require(not core.LOCK.exists(), 'Orquestrador ainda bloqueado/em execução. Não prosseguir.')
    state = core.require_state()
    require(state.get('status') == 'PAUSED' and state.get('completed') == 0 and state.get('active') == 1,
            'Estado não corresponde à Etapa 01 pausada; nada foi alterado.')
    core.verify_guard(state['guard_hashes'])
    core.validate_evidence(state)
    require(core.manifest_hash(core.manifest()) == state.get('paused_manifest_sha256'),
            'Workspace mudou depois da pausa. Confira as alterações antes de recuperar.')

    # Resposta já produzida pela execução original, sem chamada ao Codex.
    result_path = RUN / 'ETAPA_01_resultado.json'
    require(result_path.is_file(), 'Resposta JSON da execução original não encontrada.')
    result = json.loads(result_path.read_text(encoding='utf-8'))
    require(result.get('status') == 'DONE', 'Codex não declarou DONE; recuperação automática proibida.')
    require({'BASELINE.json', 'BASELINE_TECNICO.md', 'scripts/dev/baseline_etapa01.py'} <= set(result.get('files_changed', [])),
            'Os arquivos esperados não constam no resultado do Codex.')

    checkpoint = core.REPORTS / 'CHECKPOINT_ETAPA_01.md'
    require(checkpoint.is_file() and checkpoint.stat().st_size >= 120,
            'Checkpoint original da Etapa 01 ausente ou incompleto.')
    generator = ROOT / 'scripts' / 'dev' / 'baseline_etapa01.py'
    require(generator.is_file(), 'Gerador baseline_etapa01.py ausente.')
    for filename in ('BASELINE.json', 'BASELINE_TECNICO.md'):
        require((ROOT / filename).is_file(), f'Arquivo de baseline ausente: {filename}')
    require(state.get('partial_snapshot', {}).get('file'), 'Snapshot parcial não registrado.')
    partial = ROOT / state['partial_snapshot']['file']
    require(partial.is_file() and core.hash_file(partial) == state['partial_snapshot']['sha256'],
            'Snapshot parcial ausente ou com hash divergente.')

    # A intervenção é pequena, rastreável e só começa após verificar todos os pré-requisitos.
    src = generator.read_text(encoding='utf-8')
    replacements = {
        "ROOT / 'BASELINE.json'": "ROOT / 'automacao/baselines/BASELINE.json'",
        "ROOT / 'BASELINE_TECNICO.md'": "ROOT / 'automacao/baselines/BASELINE_TECNICO.md'",
    }
    require(all(src.count(old) == 1 for old in replacements),
            'A escrita do gerador não corresponde ao formato esperado; reparo manual necessário.')
    old_contents = {name: (ROOT / name).read_bytes() for name in ('BASELINE.json', 'BASELINE_TECNICO.md')}

    DEST.mkdir(parents=True, exist_ok=True)
    require(not any((DEST / name).exists() for name in old_contents),
            'Destino já contém baseline: revisar antes de sobrescrever.')
    for name in old_contents:
        (ROOT / name).replace(DEST / name)
    for old, new in replacements.items():
        src = src.replace(old, new)
    generator.write_text(src, encoding='utf-8')
    core.note('Baselines movidos para automacao/baselines; gerador atualizado.')

    # Regeneração deve ser determinística e NÃO modificar as evidências.
    run = subprocess.run([sys.executable, str(generator)], cwd=ROOT,
                         capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    require(run.returncode == 0, 'Gerador falhou: ' + (run.stderr or run.stdout)[-1200:])
    for name, original in old_contents.items():
        require((DEST / name).read_bytes() == original,
                f'Baseline mudou inesperadamente ao regenerar: {name}')
    core.verify_guard(state['guard_hashes'])
    core.validate_evidence(state)

    count, errors = core.syntax_check()
    require(not errors, 'Erros de sintaxe Python: ' + '; '.join(errors[:5]))
    previous_pytest = RUN / 'logs' / 'ETAPA_01_pytest.log'
    if previous_pytest.exists():
        shutil.copy2(previous_pytest, RUN / 'logs' / 'ETAPA_01_pytest_falha_original.log')
    core.note('Executando regressão completa do Analyzer (sem usar Codex)...')
    code, test_log = core.run_pytest(1, 1200)
    require(code == 0, f'Pytest ainda falhou; consulte {test_log}. Estado permanece PAUSED.')

    with core.exclusive_lock():
        # Prova da nova versão salva antes de tocar no estado de aprovação.
        verified = core.snapshot('LDPORTO_STAGE_01')
        files_now = core.manifest()
        changed = core.changed_paths(state['last_manifest'], files_now)
        require(changed and not set(changed).isdisjoint({'scripts/dev/baseline_etapa01.py',
                  'automacao/baselines/BASELINE.json', 'automacao/baselines/BASELINE_TECNICO.md'}),
                'Nenhuma alteração real de baseline encontrada.')
        report = ('\n\n## Recuperação offline após falha da allowlist\n\n'
                  '- Resultado original Codex: DONE (sem nova execução).\n'
                  '- A causa era a presença de BASELINE.json e BASELINE_TECNICO.md na raiz.\n'
                  '- Relatórios movidos para automacao/baselines/ sem alterar seus conteúdos.\n'
                  '- Gerador atualizado para escrever no novo caminho.\n'
                  f'- Pytest completo: exit code 0; log {test_log}.\n'
                  '- Nenhuma mídia, inferência, publicação ou cache caro foi reprocessado.\n')
        with checkpoint.open('a', encoding='utf-8') as f:
            f.write(report)
        state.setdefault('recovered_failures', []).append({
            'when': core.timestamp(), 'stage': 1, 'reason': state.get('error'),
            'method': 'offline_relocation_and_independent_pytest',
            'codex_reinvoked': False,
        })
        state.setdefault('stages', []).append({
            'n': 1, 'title': 'Reconciliação de versões e baseline',
            'result': result['status'], 'summary': result['summary'],
            'when': core.timestamp(), 'seconds': None,
            'files_changed': changed,
            'tests_reported_by_codex': result.get('tests', []),
            'pytest_log': test_log, 'python_files_checked': count,
            'checkpoint': checkpoint.relative_to(ROOT).as_posix(),
            'before_snapshot': state['partial_snapshot'],
            'snapshot': verified, 'risks': result.get('risks', []),
            'offline_recovery': True,
        })
        state['completed'] = 1
        state['active'] = None
        state['status'] = 'READY'
        state['last_snapshot'] = verified
        state['last_manifest'] = files_now
        state['last_manifest_sha256'] = core.manifest_hash(files_now)
        for field in ('paused_manifest_sha256', 'error', 'partial_snapshot', 'partial_backup_error'):
            state.pop(field, None)
        core.persist(state)
    core.note('ETAPA 01 APROVADA OFFLINE; snapshot verificado. Próxima: ETAPA 02.')
    core.note('Execute: .\\.venv\\Scripts\\python.exe .\\orquestrador.py --status')


if __name__ == '__main__':
    try:
        recover()
    except Exception as exc:
        print('RECUPERAÇÃO BLOQUEADA: ' + str(exc), file=sys.stderr)
        print('O orquestrador não foi reiniciado. Confira o diagnóstico; não rode --auto antes de READY.', file=sys.stderr)
        raise SystemExit(1)
