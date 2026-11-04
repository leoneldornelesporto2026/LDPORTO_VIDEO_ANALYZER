"""Local-only OCR checks. READY here means configuration, never media evidence."""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata

from .core import scrub
from .ocr_runtime import resolve_executable, languages as effective_languages


def _windows_job(process, memory_bytes, cpu_seconds):
    """Apply hard limits before resuming a suspended Windows child; fail closed."""
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [('process_time', c.c_int64), ('job_time', c.c_int64),
                    ('flags', w.DWORD), ('min_ws', c.c_size_t), ('max_ws', c.c_size_t),
                    ('active', w.DWORD), ('affinity', c.c_size_t),
                    ('priority', w.DWORD), ('scheduling', w.DWORD)]

    class IO(c.Structure):
        _fields_ = [(name, c.c_uint64) for name in
                    ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

    class Extended(c.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                    ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]

    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError('job_create_failed')
    try:
        info = Extended()
        info.basic.flags = 0x100 | 0x2000 | 0x2  # process memory, kill on close, CPU time
        info.basic.process_time = int(cpu_seconds * 10_000_000)
        info.process_memory = memory_bytes
        if not kernel.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info)):
            raise OSError('job_limits_failed')
        if not kernel.AssignProcessToJobObject(job, w.HANDLE(int(process._handle))):
            raise OSError('job_assign_failed')
        nt = c.WinDLL('ntdll')
        nt.NtResumeProcess.argtypes = [w.HANDLE]
        nt.NtResumeProcess.restype = c.c_long
        if nt.NtResumeProcess(w.HANDLE(int(process._handle))) != 0:
            raise OSError('process_resume_failed')
        return lambda: kernel.CloseHandle(job)
    except Exception:
        kernel.CloseHandle(job)
        raise


def _run(args, *, timeout=5, cwd=None):
    """No shell, one OpenMP thread, 256 MiB, 5 CPU seconds, bounded wall time."""
    env = os.environ.copy()
    env['OMP_THREAD_LIMIT'] = '1'
    kwargs = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                  env=env, cwd=cwd)
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | 0x4  # suspended
    else:
        def limits():
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        kwargs['preexec_fn'] = limits
    process = subprocess.Popen(args, **kwargs)
    close_job = None
    try:
        if os.name == 'nt':
            close_job = _windows_job(process, 256 * 1024**2, 5)
        out, err = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, process.returncode,
            out.decode('utf-8', errors='replace'), err.decode('utf-8', errors='replace'))
    finally:
        if process.poll() is None:
            process.kill()
        if close_job:
            # Closing first terminates descendants which could hold pipe handles.
            close_job()
        process.communicate(timeout=1)


def _normalize(text):
    plain = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', plain.casefold()))


def _fixture(path):
    from PIL import Image, ImageDraw, ImageFont
    limitation = None
    try:
        font = ImageFont.truetype('arial.ttf' if os.name == 'nt' else 'DejaVuSans.ttf', 38)
        # A font with matching replacement glyphs cannot prove accent support.
        if bytes(font.getmask('ã')) == bytes(font.getmask('\ufffd')):
            raise ValueError('accent_glyph_unavailable')
        text = 'PORTUGUÊS: ação e informação\nENGLISH: clear text sample'
    except (OSError, ValueError):
        font = ImageFont.load_default(size=38)
        text = 'PORTUGUES: acao e informacao\nENGLISH: clear text sample'
        limitation = 'accent_font_unavailable_ascii_fixture'
    image = Image.new('RGB', (1000, 180), 'white')
    ImageDraw.Draw(image).multiline_text((25, 20), text, font=font, fill='black', spacing=12)
    image.save(path)
    return text, limitation


def diagnose_ocr(cfg, *, smoke=False):
    """Check executable and each requested traineddata; smoke is opt-in only.

    Raw command output/exceptions/paths are never exported. No silent fallback,
    no installation, no config or pytesseract global mutation.
    """
    result = {'enabled': bool(cfg.get('enabled')), 'ok': False, 'status': 'DISABLED',
              'reason': 'disabled_by_user', 'checks': {}, 'version': None,
              'requested_languages': [], 'available_languages': None,
              'missing_languages': [], 'inference_executed': False,
              'smoke': {'requested': bool(smoke), 'success': None, 'observed_text': None,
                        'normalized_text': None, 'elapsed_seconds': None},
              'readiness_scope': 'configuration_only'}
    if not result['enabled']:
        return result

    def fail(reason, exc=None):
        result.update(status=reason, reason=reason)
        if exc is not None:
            # Class only: even scrubbed messages can contain private paths/env.
            result['error'] = {'type': type(exc).__name__}
        return result

    try:
        importlib.import_module('pytesseract')
        result['checks']['import'] = {'ok': True}
    except Exception as exc:
        result['checks']['import'] = {'ok': False}
        return fail('dependency_missing', exc)
    try:
        languages = effective_languages(cfg).split('+')
    except ValueError as exc:
        return fail('missing_languages', exc)
    result['requested_languages'] = [scrub(lang) for lang in languages]
    try:
        try:
            executable = resolve_executable(cfg)
        except OSError as exc:
            result['checks']['binary'] = {'ok': False}
            return fail('binary_missing', exc)
        result['checks']['binary'] = {'ok': True}
        result['failed_check'] = 'version'
        version = _run([str(executable), '--version'])
        match = re.search(r'^tesseract\s+v?(\d[\w.+-]*)', version.stdout, re.MULTILINE)
        if version.returncode or not match:
            result['returncode'] = version.returncode
            return fail('binary_execution_failed')
        result['version'] = scrub(match.group(1))
        result['checks']['version'] = {'ok': True}
        result['failed_check'] = 'languages'
        listing = _run([str(executable), '--list-langs'])
        # Verified listing gives the directory actually selected by Tesseract.
        listing_text = listing.stdout + '\n' + listing.stderr
        header = re.search(r'List of available languages in "(.+)" \(\d+\):', listing_text)
        if listing.returncode or not header:
            result['returncode'] = listing.returncode
            return fail('tessdata_unavailable')
        available = [line.strip() for line in listing_text.splitlines()
                     if re.fullmatch(r'[A-Za-z0-9_]+', line.strip())]
        result['available_languages'] = sorted(scrub(lang) for lang in available)
        missing = sorted(set(languages) - set(available))
        result['missing_languages'] = [scrub(lang) for lang in missing]
        result['checks']['languages'] = {'ok': not missing, 'missing': result['missing_languages']}
        if missing:
            return fail('missing_languages')
        result['failed_check'] = 'tessdata'
        folder = Path(header.group(1))
        for language in languages:
            with (folder / (language + '.traineddata')).open('rb') as handle:
                if not handle.read(1):
                    raise ValueError('empty_traineddata')
        result['checks']['tessdata'] = {'ok': True}
        result['failed_check'] = 'model_load'
        loaded = _run([str(executable), '-l', '+'.join(languages), '--print-parameters'])
        if loaded.returncode or 'Failed loading language' in loaded.stderr:
            result['returncode'] = loaded.returncode
            return fail('tessdata_unavailable')
        result['checks']['model_load'] = {'ok': True, 'inference_executed': False}
    except subprocess.TimeoutExpired as exc:
        return fail('timeout', exc)
    except Exception as exc:
        return fail('tessdata_unavailable' if result.get('failed_check') == 'tessdata'
                    else 'binary_execution_failed', exc)
    if smoke:
        result['readiness_scope'] = 'synthetic_smoke_only'
        result['smoke']['limits'] = {'wall_seconds': 5, 'cpu_seconds': 5,
                                    'memory_mib': 256, 'threads': 1}
        started = time.monotonic()
        result['failed_check'] = 'smoke'
        try:
            with tempfile.TemporaryDirectory(prefix='ldporto_ocr_') as temporary:
                image = Path(temporary) / 'fixture.png'
                expected, limitation = _fixture(image)
                result['smoke'].update(expected_text=expected, limitation=limitation)
                result['smoke']['inference_attempted'] = True
                # A timeout or launch failure cannot prove the engine reached inference.
                result['inference_executed'] = None
                observed = _run([str(executable), str(image), 'stdout', '-l',
                                 '+'.join(languages), '--psm', '6'])
                # Only text from this synthetic fixture; discard raw failure output.
                if observed.returncode:
                    raise RuntimeError('ocr_failed')
                result['inference_executed'] = True
                literal = observed.stdout.strip()
                # Unexpected paths/diagnostics are not safe observed fixture text.
                if not re.fullmatch(r'[\w\s:.,!?;\-]*', literal) or len(literal) > 512:
                    raise ValueError('unexpected_output')
                literal = scrub(literal)
                normalized = _normalize(literal)
                success = normalized == _normalize(expected)
                result['smoke'].update(observed_text=scrub(literal), normalized_text=scrub(normalized), success=success)
                if not success:
                    return fail('smoke_failed')
        except subprocess.TimeoutExpired as exc:
            result['smoke']['success'] = False
            return fail('timeout', exc)
        except Exception as exc:
            result['smoke']['success'] = False
            return fail('smoke_failed', exc)
        finally:
            result['smoke']['elapsed_seconds'] = round(time.monotonic() - started, 4)
    result.update(ok=True, status='READY', reason=None)
    result.pop('failed_check', None)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='OCR local: sem instalar nem alterar configuração.')
    parser.add_argument('--tesseract-cmd', default=None)
    parser.add_argument('--languages', default='por+eng')
    parser.add_argument('--smoke', action='store_true', help='Inferência curta em imagem sintética, explícita.')
    args = parser.parse_args(argv)
    report = diagnose_ocr({'enabled': True, 'tesseract_cmd': args.tesseract_cmd,
                           'languages': args.languages}, smoke=args.smoke)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
