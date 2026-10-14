from copy import deepcopy

import pytest

from ldporto.semantic_package import SCHEMA_DIALECT, validate_embedded_schemas


def test_whole_embedded_schema_is_validated():
    schema = {'$schema': SCHEMA_DIALECT, 'type': 'object'}
    result = validate_embedded_schemas({'schemas/example.schema.json': schema})
    assert result['status'] == 'valid' and result['metadata_removed'] is False


@pytest.mark.parametrize('patch', [{'$schema': 'http[PRIVATE_PATH]'}, {'type': 'invented'},
                                  {'$schema': None}, {'required': [7]}])
def test_corrupt_metadata_or_schema_cannot_be_stripped_to_pass(patch):
    schema = {'$schema': SCHEMA_DIALECT, 'type': 'object'}
    schema.update(deepcopy(patch))
    assert validate_embedded_schemas({'schemas/example.schema.json': schema})['status'] == 'invalid'
