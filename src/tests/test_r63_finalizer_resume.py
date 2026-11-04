"""Safety regressions for reprofile/finalization of interrupted R6.3 revisions."""
import pytest
from scripts.dev.finalize_compact_revision import _frame_reference_remap
from test_r63_compact_handoff import persisted_fixture


def test_first_pass_raw_atlas_without_source_frame_map_can_resume():
    old={'frames':[{'frame_id':'RAW_1'},{'frame_id':'RAW_2'}]}
    new={'frames':[{'frame_id':'NEW_1'},{'frame_id':'NEW_2'}],
         'source_frame_id_map':{'RAW_1':'NEW_1','RAW_2':'NEW_2'}}
    assert _frame_reference_remap(old,new)=={'RAW_1':'NEW_1','RAW_2':'NEW_2'}


def test_rereprofiled_atlas_maps_original_ids_to_old_revision_ids():
    old={'frames':[{'frame_id':'OLD_1'}], 'source_frame_id_map':{'RAW_1':'OLD_1'}}
    new={'frames':[{'frame_id':'NEW_1'}], 'source_frame_id_map':{'RAW_1':'NEW_1'}}
    assert _frame_reference_remap(old,new)=={'OLD_1':'NEW_1'}


def test_remap_never_drops_an_original_frame_or_accepts_ambiguity():
    old={'frames':[{'frame_id':'RAW_1'}]}
    with pytest.raises(ValueError,match='source_frame_id_missing'):
        _frame_reference_remap(old,{'frames':[],'source_frame_id_map':{}})
    old={'frames':[{'frame_id':'OLD_1'}], 'source_frame_id_map':{'RAW_1':'OLD_1','RAW_2':'OLD_1'}}
    new={'frames':[{'frame_id':'NEW_1'},{'frame_id':'NEW_2'}],
         'source_frame_id_map':{'RAW_1':'NEW_1','RAW_2':'NEW_2'}}
    with pytest.raises(ValueError,match='ambiguous_reprofile'):
        _frame_reference_remap(old,new)


def test_standalone_zip_auditor_requires_declared_counts(persisted_fixture):
    # All evidence is synthetic; no original video or local model is invoked.
    from test_r63_compact_handoff import export
    from scripts.dev.audit_compact_delivery import audit
    result=export(persisted_fixture)
    archive=result['archive']['path']
    valid=audit(archive,expected_source=persisted_fixture['source_sha256'],
                expected_scenes=4)
    assert valid['status'].startswith('VALID') and not valid['errors']
    assert valid['independent_zip_reader']=='PASS' and valid['models_executed'] is False
    mismatch=audit(archive,expected_scenes=99999)
    assert mismatch['status']=='FAILED'
    assert any('expected_scene_count_mismatch' in row for row in mismatch['errors'])
