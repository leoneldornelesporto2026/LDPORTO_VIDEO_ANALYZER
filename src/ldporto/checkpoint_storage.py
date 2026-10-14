"""Lossless physical storage for new ASD checkpoints; consumers receive legacy lists.

Checksums and producer receipts cover the hydrated logical data. File checksums
cover the stored bytes. This codec never edits a checkpoint or follows references.
"""
from copy import deepcopy
import json


CODEC = 'asd_mapping_projection_v1'
STAGE = '10_active_speaker'
MARKER = 'checkpoint_storage'
EXCLUDED = frozenset(('speaker', 'visible_person', 'association_confidence'))
VIEW = 'mappings_without_legacy_aliases_v1'


def _projection(row):
    return {key: value for key, value in row.items() if key not in EXCLUDED}


def _canonical(row):
    # Dict equality would equate bool/int, int/float and positive/negative zero.
    return json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':'), default=str)


def encode_checkpoint(record, stage=STAGE):
    """Return a physical view only when every interval is the exact projection.

    The source object remains untouched. Any incompatible producer payload keeps
    its complete legacy representation, including all interval evidence.
    """
    if stage != STAGE or not isinstance(record, dict) or MARKER in record:
        return record
    data = record.get('data')
    if not isinstance(data, dict):
        return record
    mappings, intervals = data.get('mappings'), data.get('intervals')
    if (not isinstance(mappings, list) or not mappings or
            not isinstance(intervals, list) or len(mappings) != len(intervals)):
        return record
    try:
        for mapping, interval in zip(mappings, intervals):
            if (not isinstance(mapping, dict) or not isinstance(interval, dict) or
                    _canonical(_projection(mapping)) != _canonical(interval)):
                return record
    except (TypeError, ValueError, OverflowError):
        return record
    count = len(mappings)
    return {**record, MARKER: {'schema_version': '1.0', 'codec': CODEC, 'stage_id': STAGE},
            'data': {**data, 'intervals': {'$derived': VIEW, 'record_count': count}}}


def decode_checkpoint(value):
    """Hydrate known physical views; reject ambiguous or unsupported markers.

    Legacy documents return unchanged. Nested interval containers are independent
    of mappings, matching the behavior of parsing the old full JSON checkpoint.
    """
    if not isinstance(value, dict) or MARKER not in value:
        return value
    marker = value[MARKER]
    if marker != {'schema_version': '1.0', 'codec': CODEC, 'stage_id': STAGE}:
        raise ValueError('unsupported_checkpoint_storage')
    data = value.get('data')
    if not isinstance(data, dict):
        raise ValueError('invalid_checkpoint_storage_data')
    mappings, view = data.get('mappings'), data.get('intervals')
    if (not isinstance(mappings, list) or not isinstance(view, dict) or
            set(view) != {'$derived', 'record_count'} or view.get('$derived') != VIEW or
            type(view.get('record_count')) is not int or view['record_count'] < 1 or
            view['record_count'] != len(mappings) or
            any(not isinstance(row, dict) for row in mappings)):
        raise ValueError('invalid_checkpoint_storage_reference')
    intervals = [deepcopy(_projection(row)) for row in mappings]
    return {**{key: item for key, item in value.items() if key != MARKER},
            'data': {**data, 'intervals': intervals}}
