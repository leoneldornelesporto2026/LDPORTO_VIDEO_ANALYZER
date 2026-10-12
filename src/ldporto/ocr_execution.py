"""Additive execution receipts. Readiness never substitutes for frame evidence."""
from functools import wraps
import time


def receipt(scope):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            started = time.monotonic()
            result = function(*args, **kwargs)
            cfg = (args[1] if len(args) > 1 else kwargs['ctx']).config['ocr'] if scope == 'general' else (args[2] if len(args) > 2 else kwargs['cfg'])
            data = result['data'] if scope == 'general' else result
            status = result['status']
            measured = data.get('measured_frames', 0)
            failures = data.get('failed_frames_or_ocr', 0)
            data['execution'] = {
                'scope': scope, 'requested': bool(cfg.get('enabled')),
                'state': 'ignored' if status == 'skipped' else 'unavailable' if status == 'unavailable' or not measured else 'sampled',
                'measured_frames': measured, 'failed_frames_or_ocr': failures,
                'languages': cfg.get('languages', 'por+eng'),
                'elapsed_seconds': round(time.monotonic() - started, 4),
                'measurement_state': data.get('measurement_state', 'not_measured'),
                'requires_review': True, 'commercial_present': None,
            }
            return result
        return run
    return decorate


def execution_summary(general, commercial):
    # Old caches carry no receipt; missing measurements stay null.
    def read(data):
        return data.get('execution') or {
            'state': 'not_measured', 'measured_frames': data.get('measured_frames'),
            'failed_frames_or_ocr': data.get('failed_frames_or_ocr'),
            'languages': None, 'elapsed_seconds': None, 'requires_review': True,
        }
    return {'general_13': read(general), 'commercial_17c': read(commercial)}
