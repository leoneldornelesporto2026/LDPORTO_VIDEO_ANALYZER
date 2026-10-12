"""Privacy checks on decoded values, never JSON escape syntax.

Export redactions keep scalar types and expose only hashes and JSON pointers.
Original evidence is never edited. Public brands, prices and timestamps are
not private by themselves; contact details are conservatively redacted.
"""
import hashlib
import json
import re
import stat
from pathlib import Path

from .core import scrub

SENSITIVE_KEYS = {'hf_token', 'token', 'password', 'passphrase', 'authorization',
                  'api_key', 'credentials', 'cookies_file', 'private_prompt',
                  'secret', 'client_secret', 'access_token', 'refresh_token'}
PRIVATE_PATH = re.compile(r'(?i)(?:[a-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\s]+|(?<!\w)/(?:Users|home|tmp|mnt)/)[^\s"\r\n]*')
PATTERNS = {
    'private_path': PRIVATE_PATH,
    'email': re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'),
    'phone': re.compile(r'(?<!\d)(?:\+55\s*)?\(?\d{2}\)?[ .-]+\d{4,5}[ -]\d{4}(?!\d)'),
    'personal_identifier': re.compile(r'(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)'),
    'credential_url': re.compile(r'(?i)https?://[^\s/@]+:[^\s/@]+@[^\s]+'),
    'credential_query': re.compile(r'(?i)([?&](?:token|api_key|password|access_token)=)[^\s&#]+'),
}


def safe_path(path):
    """Reject symlinks and Windows junction/reparse points, including parents."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        info = item.lstat()
        if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
            raise ValueError('unsafe_link')
    return path


def string_rules(value):
    rules = [name for name, pattern in PATTERNS.items() if pattern.search(value)]
    if scrub(value) != value:
        rules.append('secret')
    return rules


def privacy_findings(value, pointer=''):
    """Only diagnostic metadata; neither matched values nor keys are logged."""
    result = []
    if isinstance(value, dict):
        for key, item in value.items():
            diagnostic_key = str(key)
            if string_rules(diagnostic_key):
                diagnostic_key = 'key_sha256_' + hashlib.sha256(diagnostic_key.encode('utf-8')).hexdigest()
            child = pointer + '/' + diagnostic_key.replace('~', '~0').replace('/', '~1')
            if str(key).casefold() in SENSITIVE_KEYS:
                result.append({'pointer': child, 'type': type(item).__name__, 'rule': 'sensitive_key',
                               'sha256': hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
            result.extend(privacy_findings(str(key), pointer))
            result.extend(privacy_findings(item, child))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            result.extend(privacy_findings(item, pointer + '/' + str(i)))
    elif isinstance(value, str):
        for rule in string_rules(value):
            result.append({'pointer': pointer, 'type': 'str', 'rule': rule, 'length': len(value),
                           'sha256': hashlib.sha256(value.encode('utf-8')).hexdigest()})
    return result


def sanitize_export(value):
    if isinstance(value, dict):
        return {sanitize_export(str(key)): sanitize_export(item) for key, item in value.items()
                if str(key).casefold() not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [sanitize_export(item) for item in value]
    if isinstance(value, str):
        value = scrub(value)
        for name, pattern in PATTERNS.items():
            value = pattern.sub('[PRIVATE_PATH]' if name == 'private_path' else '[REDACTED_PRIVATE]', value)
    return value


def document_findings(name, data):
    text = data.decode('utf-8-sig')
    if name.endswith('.json'):
        return privacy_findings(json.loads(text))
    if name.endswith('.jsonl'):
        return [finding for i, line in enumerate(text.splitlines()) if line
                for finding in privacy_findings(json.loads(line), '/' + str(i))]
    return privacy_findings(text)
