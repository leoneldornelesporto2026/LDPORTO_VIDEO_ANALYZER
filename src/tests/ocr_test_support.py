"""Explicit synthetic runtime boundary for legacy frame/fusion tests."""
import sys
from ldporto import commercial_gate, ocr
from ldporto.ocr_runtime import languages


def mock_ocr_runtime(monkeypatch):
    def check(cfg):
        return {'ok': True, 'status': 'READY', 'reason': None}

    def call(cfg, method, *args, **kwargs):
        kwargs['lang'] = languages(cfg)
        return getattr(sys.modules['pytesseract'], method)(*args, **kwargs)

    for module in (ocr, commercial_gate):
        monkeypatch.setattr(module, 'diagnose_ocr', check)
        monkeypatch.setattr(module, 'ocr_call', call)
