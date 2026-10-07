from ldporto.config import load_config
from ldporto.core import read_json, write_json, file_hash
from ldporto.replay import replay_analysis
from test_v43_runtime import replay_fixture


def test_commercial_replay_uses_canonical_context_without_asr_or_llm(tmp_path):
    folder=replay_fixture(tmp_path)
    segments=read_json(folder/'transcript_segments.json')
    segments[0]['text']='Venha para a Havan, compre hoje por 69,99 reais no Pix e aproveite a promoção com desconto!'
    write_json(folder/'transcript_segments.json',segments)
    manifest=read_json(folder/'manifest.json')
    manifest['artifact_checksums']['transcript_segments.json']=file_hash(folder/'transcript_segments.json')
    write_json(folder/'manifest.json',manifest)
    cfg=load_config()
    cfg['camera_director']['enabled']=False
    cfg['preview']['enabled']=False
    cfg['vision']['enabled']=False
    cfg['diarization']['enabled']=False
    cfg['export']['second_curation_output_dir']=str(tmp_path/'packages')
    _,analysis=replay_analysis(folder,cfg,'commercial',tmp_path/'output')
    assert analysis['main_moments'][0]['commercial_classification']['eligibility']=='excluded'
    assert analysis['editorial_shortlist']==[]
    assert analysis['candidate_metrics']['final_shortlist_count']==0
    assert not analysis['replay_provenance']['llm_rerun']
