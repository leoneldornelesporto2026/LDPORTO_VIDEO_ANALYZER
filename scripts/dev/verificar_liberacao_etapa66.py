#!/usr/bin/env python3
r"""PROMPT 01: valida a etapa 65 sem aprovar, reiniciar ou alterar o estado.

Uso no Windows, a partir da raiz do projeto:
    .\.venv\Scripts\python.exe scripts\dev\verificar_liberacao_etapa66.py --focused
    .\.venv\Scripts\python.exe scripts\dev\verificar_liberacao_etapa66.py --full

--focused roda apenas testes da 65/proveniencia; --full executa a mesma
regressao do orquestrador. Ambos informam separadamente testes e aprovacao.
NUNCA transforma sucesso dos testes em aprovacao artificial.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[2]
STATE = PROJECT / 'automacao' / 'execucao' / 'estado.json'
LOCK = PROJECT / 'automacao' / 'execucao' / 'orquestrador.lock'
LOG_DIR = PROJECT / 'automacao' / 'execucao' / 'validacao66'
FOCUSED = [
    'src/tests/test_stage65_execution_receipts.py',
    'src/tests/test_build_manifest_truth.py',
    'src/tests/test_stage64_curation_recovery.py',
    'src/tests/test_stage64_legacy_review.py',
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_state():
    if not STATE.is_file():
        raise RuntimeError('estado.json ausente; export ZIP nao contem execucao real')
    with STATE.open('r', encoding='utf-8-sig') as f:
        return json.load(f)


def last_pytest_failure():
    path = PROJECT / 'automacao' / 'execucao' / 'logs' / 'ETAPA_65_pytest.log'
    if not path.is_file():
        return {'present': False}
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    signals = [line for line in lines if ('FAILED ' in line or 'ERROR ' in line or
                                           'failed in ' in line or 'passed' in line or 'TIMEOUT:' in line)]
    return {'present': True, 'sha256': sha256(path), 'last_signals': signals[-25:]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--focused', action='store_true')
    group.add_argument('--full', action='store_true')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args(argv)
    if args.timeout_seconds <= 0:
        parser.error('timeout-seconds deve ser positivo')
    report = {'report_version': 1, 'checked_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'project': str(PROJECT), 'mutated_project_source': False}
    try:
        state = read_state()
        deferred = state.get('deferred_stages', [])
        approved = [r for r in state.get('stages', []) if isinstance(r, dict) and r.get('n') == 65]
        completed = state.get('completed')
        cursor = state.get('stage_cursor', completed)
        status = state.get('status')
        lock = LOCK.exists()
        report['orchestrator'] = {'status': status, 'completed': completed,
                                  'stage_cursor': cursor, 'active': state.get('active'),
                                  'next_stage': (cursor + 1 if isinstance(cursor, int) else None),
                                  'stage65_records': len(approved), 'lock_present': lock,
                                  'stage64_deferred': any(isinstance(d, dict) and d.get('n') == 64 for d in deferred)}
        report['last_stage65_pytest'] = last_pytest_failure()
        if args.focused or args.full:
            if lock or status == 'RUNNING':
                report['tests'] = {'status': 'BLOCKED_ACTIVE_ORCHESTRATOR'}
            else:
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                label = 'FULL' if args.full else 'FOCUSED'
                log = LOG_DIR / f'VALIDACAO_{label}_65.log'
                command = [sys.executable, '-m', 'pytest', '-q'] + ([] if args.full else FOCUSED)
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
                with log.open('w', encoding='utf-8', errors='replace') as sink:
                    try:
                        completed_test = subprocess.run(command, cwd=PROJECT, stdout=sink,
                                                        stderr=subprocess.STDOUT, timeout=args.timeout_seconds,
                                                        env=env, check=False)
                        code = completed_test.returncode
                    except subprocess.TimeoutExpired:
                        sink.write('\nTIMEOUT: suite nao terminou no prazo configurado.\n')
                        code = 124
                tail = log.read_text(encoding='utf-8', errors='replace').splitlines()[-35:]
                report['tests'] = {'suite': label, 'exit_code': code,
                                   'status': 'PASS' if code == 0 else 'FAIL',
                                   'log': str(log), 'log_sha256': sha256(log),
                                   'last_lines': tail}
        gate = (status in {'READY', 'FINISHED', 'FINISHED_WITH_DEFERRED'}
                and completed == 64 and cursor == 65 and not lock
                and len(approved) == 1
                and report['orchestrator']['stage64_deferred'])
        tests = report.get('tests')
        if tests and tests['status'] != 'PASS':
            report['decision'] = 'BLOCKED_TESTS'
        elif gate and args.full and tests and tests['status'] == 'PASS':
            report['decision'] = 'READY_FOR_STAGE66'
        elif gate:
            report['decision'] = 'GATE_OK_FULL_REGRESSION_NOT_RUN_THIS_CHECK'
        else:
            report['decision'] = 'BLOCKED_STAGE65_NOT_OFFICIALLY_APPROVED'
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['decision'] == 'READY_FOR_STAGE66' else 2
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
        report['decision'] = 'ERROR'
        report['error'] = type(exc).__name__ + ': ' + str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
