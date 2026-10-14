"""Offline privacy/schema regressions; every credential/path is synthetic."""
from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest

from ldporto.core import scrub
from ldporto.export_privacy import (PRIVATE_PATH, document_findings,
                                    privacy_findings, sanitize_export)


@pytest.mark.parametrize('uri', [
    'https://json-schema.org/draft/2020-12/schema',
    'http://json-schema.org/draft-07/schema#',
    'https://example.invalid/schemas/story.schema.json#/$defs/unit',
    'http://example.invalid/video?id=synthetic',
])
def test_public_schema_and_source_urls_are_preserved(uri):
    original = {'$schema': uri, '$id': uri, '$ref': uri,
                'source': {'url': uri}, 'scalar': None, 'flag': False}
    snapshot = deepcopy(original)
    assert scrub(uri) == uri
    assert not PRIVATE_PATH.search(uri)
    assert sanitize_export(original) == original
    assert not privacy_findings(original)
    assert not document_findings('schemas/example.json', json.dumps(original).encode())
    assert original == snapshot


@pytest.mark.parametrize('prefix', ['', '(', '[', '=', ':', '"', 'texto: '])
@pytest.mark.parametrize('path', [
    'C:\\Users\\Synthetic\\private.txt',
    'z:/Users/Synthetic/private.txt',
    '\\\\synthetic-server\\share\\private.txt',
    '/home/synthetic/private.txt',
])
def test_private_paths_after_punctuation_are_still_redacted(prefix, path):
    original = {'text': prefix + path, 'timestamp': 12.5, 'value': None}
    assert PRIVATE_PATH.search(original['text'])
    assert privacy_findings(original)
    clean = sanitize_export(original)
    assert path not in clean['text'] and '[PRIVATE_PATH]' in clean['text']
    assert clean['timestamp'] == 12.5 and clean['value'] is None
    assert not privacy_findings(clean)
    assert sanitize_export(clean) == clean


@pytest.mark.parametrize('value,secret', [
    ('https://synthetic-user:synthetic-password@example.invalid/path', 'synthetic-password'),
    ('http://example.invalid/?token=synthetic-token', 'synthetic-token'),
    ('https://example.invalid/?access_token=synthetic-access', 'synthetic-access'),
    ('https://example.invalid/?api_key=synthetic-key', 'synthetic-key'),
    ('https://example.invalid/?password=synthetic-password', 'synthetic-password'),
])
def test_url_credentials_remain_detected_and_redacted(value, secret):
    rules = {finding['rule'] for finding in privacy_findings(value)}
    assert rules & {'credential_url', 'credential_query'}
    clean = sanitize_export({'url': value})
    assert secret not in clean['url']
    assert not privacy_findings(clean)
    assert sanitize_export(clean) == clean


def test_public_urls_and_private_paths_can_coexist_in_one_decoded_string():
    uri = 'https://json-schema.org/draft/2020-12/schema'
    path = 'C:\\Users\\Synthetic\\private.json'
    clean = sanitize_export(uri + ' arquivo=' + path)
    assert clean == uri + ' arquivo=[PRIVATE_PATH]'
    assert not privacy_findings(clean)


def test_recursive_sanitization_keeps_schema_uri_but_removes_sensitive_keys():
    uri = 'https://json-schema.org/draft/2020-12/schema'
    original = {'schema': {'$schema': uri}, 'nested': [
        {'token': 'synthetic', 'api_key': 'synthetic', 'private_prompt': 'synthetic',
         'source': 'https://example.invalid/source'}]}
    before = deepcopy(original)
    clean = sanitize_export(original)
    assert clean == {'schema': {'$schema': uri},
                     'nested': [{'source': 'https://example.invalid/source'}]}
    assert original == before and not privacy_findings(clean)


def test_narrative_schema_remains_exact_and_valid_after_public_sanitization():
    schema_path = Path(__file__).parents[2] / 'schemas/narrative_handoff.schema.json'
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    clean = sanitize_export(schema)
    assert clean == schema
    assert clean['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
    jsonschema.Draft202012Validator.check_schema(clean)


def test_new_core_export_embeds_exact_usable_schemas_without_media_or_models(tmp_path):
    from ldporto.second_curation_export import build_core_package
    from test_v43_handoff import analysis_fixture

    analysis = analysis_fixture()
    analysis['metadata']['sha256'] = 'a' * 64
    analysis['story_arcs'] = []
    analysis['questions_answers'] = []
    before = deepcopy(analysis)
    result = build_core_package(analysis, output_dir=tmp_path / 'core', directory_only=True,
        cfg={'narrative_handoff_enabled': True, 'second_curation_visual_candidate_limit': 0})
    assert result['validation']['status'] == 'valid'
    assert result['expensive_inference_executed'] is False
    assert analysis == before
    root = Path(result['path'])
    schemas = sorted((root / 'schemas').glob('*.json'))
    assert {p.name for p in schemas} >= {
        'narrative_handoff.schema.json', 'second_curation_decisions.schema.json'}
    source_root = Path(__file__).parents[2] / 'schemas'
    for path in schemas:
        embedded = json.loads(path.read_text(encoding='utf-8'))
        source = json.loads((source_root / path.name).read_text(encoding='utf-8'))
        assert embedded == source
        assert embedded['$schema'] == 'https://json-schema.org/draft/2020-12/schema'
        assert not privacy_findings(embedded)
        jsonschema.Draft202012Validator.check_schema(embedded)
    handoff = json.loads((root / 'SECOND_CURATION_NARRATIVE_HANDOFF.json').read_text(encoding='utf-8'))
    embedded = json.loads((root / 'schemas/narrative_handoff.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(embedded).validate(handoff)
