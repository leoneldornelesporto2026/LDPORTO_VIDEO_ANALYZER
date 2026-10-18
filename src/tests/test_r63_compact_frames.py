"""Sparse CPU/video and cache/reprofile contracts with synthetic pixels only."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

from ldporto import compact_frames
from ldporto.core import file_hash


def fixture_source(tmp_path, *, count=20, constant=False):
    source=tmp_path/'synthetic.avi'
    writer=cv2.VideoWriter(str(source),cv2.VideoWriter_fourcc(*'MJPG'),10.,(80,60))
    assert writer.isOpened()
    for index in range(count):
        image=np.full((60,80,3),80 if constant else (index*7)%200,dtype=np.uint8)
        writer.write(image)
    writer.release()
    metadata={'sha256':file_hash(source),'width':80,'height':60,'duration':count/10.,'fps':10.,'rotation':0}
    analysis=tmp_path/'analysis';analysis.mkdir()
    (analysis/'manifest.json').write_text(json.dumps({'video_sha256':metadata['sha256']}),encoding='utf-8')
    return source,metadata,analysis


def cache_scene(analysis,index,start,end,*,time=None,aspect=(80,60),tone=80):
    sid='SCENE_%05d'%index;time=start if time is None else time
    name='thumbnails/%s_%.3f.jpg'%(sid,time)
    path=analysis/name;path.parent.mkdir(exist_ok=True)
    Image.new('RGB',aspect,(tone,tone,tone)).save(path,'JPEG',quality=85)
    return {'scene_id':sid,'start':start,'end':end,'keyframe':name}


def test_real_synthetic_decoder_preserves_assembled_piece_bounds(tmp_path):
    source,metadata,analysis=fixture_source(tmp_path)
    scenes=[{'scene_id':'SCENE_A','start':0.,'end':1.},{'scene_id':'SCENE_B','start':1.,'end':2.}]
    pieces=[{'piece_id':'PIECE_GAP','source_intervals':[{'start':.2,'end':.8},{'start':1.2,'end':1.8}]}]
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,pieces,tmp_path/'atlas',media_path=source)
    assert result['statistics']['new_decoder_reads']>0
    assert result['sampling_policy']['navigation_width']==320
    assert result['sampling_policy']['analysis_width']==640
    assert result['sampling_policy']['jpeg_quality']==62
    assert result['sampling_policy']['contact_width']==640
    assert result['statistics']['scene_ids_without_frames']==[]
    for row in result['frames']:
        if 'PIECE_GAP' in row['piece_ids']:
            assert any(interval['start']<=row['source_time_s']<interval['end'] for interval in pieces[0]['source_intervals'])
    assert any('piece_end' in row['sampling_reasons'] and row['source_time_s']<1.8 for row in result['frames'])


def test_cached_filename_time_is_retained_and_decoder_never_opens_for_complete_cache(tmp_path,monkeypatch):
    _,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,2.,time=.2)]
    class MustNotOpen:
        def __init__(self,*args,**kwargs):raise AssertionError('cache-only export opened media')
    monkeypatch.setattr(compact_frames,'SparseFrameProvider',MustNotOpen)
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],tmp_path/'atlas',media_path=tmp_path/'never_opened.mp4')
    assert result['frames'][0]['source_time_s']==.2
    assert result['frames'][0]['source_time_s']!=scenes[0]['start']
    assert result['frames'][0]['timestamp_independently_verified'] is False
    assert result['statistics']['new_decoder_reads']==0


def test_bad_aspect_cache_falls_back_to_hash_bound_synthetic_decoder(tmp_path):
    source,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,2.,time=.2,aspect=(80,80))]
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],tmp_path/'atlas',media_path=source)
    assert result['statistics']['new_decoder_reads']>0
    assert result['cache_rejections'][0]['reason']=='persisted_frame_aspect_mismatch'
    assert len(result['frames'])==1 and result['frames'][0]['capture_method']=='opencv_cpu_sparse_seek'


def test_foreign_analysis_manifest_is_rejected(tmp_path):
    source,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,2.)]
    (analysis/'manifest.json').write_text(json.dumps({'video_sha256':'b'*64}),encoding='utf-8')
    with pytest.raises(ValueError,match='manifest_source_mismatch'):
        compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],tmp_path/'atlas',media_path=source)


class SameDecodedFixture:
    actual=.5
    def __init__(self,*args,**kwargs):self.decoded_frames=0
    def __enter__(self):return self
    def close(self):pass
    def __call__(self,timestamp,output):
        self.decoded_frames+=1
        Image.new('RGB',(80,60),(80,80,80)).save(output,'JPEG')
        return {'captured':True,'source_time_s':self.actual,'source_frame_index':None,
            'capture_method':'SYNTHETIC_FIXTURE','width':80,'height':60}


def test_duplicate_decoded_frames_merge_piece_ids_and_reasons(tmp_path,monkeypatch):
    source,metadata,analysis=fixture_source(tmp_path)
    monkeypatch.setattr(compact_frames,'SparseFrameProvider',SameDecodedFixture)
    pieces=[{'piece_id':ident,'source_intervals':[{'start':0.,'end':1.}]} for ident in ('P1','P2')]
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,[{'scene_id':'S','start':0.,'end':2.}],pieces,tmp_path/'atlas',media_path=source)
    # Navigation JPEG quality differs; all analysis requests share one frame.
    analysis_rows=[row for row in result['frames'] if row['piece_ids']]
    assert len(analysis_rows)==1
    assert analysis_rows[0]['piece_ids']==['P1','P2']
    assert {'piece_start','piece_middle','piece_end'}<=set(analysis_rows[0]['sampling_reasons'])
    assert result['statistics']['duplicate_frame_requests_merged']>=2


def test_invalid_decoded_timestamp_creates_no_orphan_jpeg(tmp_path,monkeypatch):
    source,metadata,analysis=fixture_source(tmp_path)
    class Outside(SameDecodedFixture):actual=20.
    monkeypatch.setattr(compact_frames,'SparseFrameProvider',Outside)
    root=tmp_path/'atlas'
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,[{'scene_id':'S','start':0.,'end':2.}],[],root,media_path=source)
    assert result['frames']==[]
    assert not list((root/'06_VISUAL_ATLAS/frames').glob('*.jpg'))
    assert result['missing_requests'][0]['reason']=='decoded_timestamp_outside_source'
    assert result['statistics']['scene_ids_without_frames']==['S']


def test_379_cached_requests_preserve_every_scene_and_physically_deduplicate(tmp_path):
    source,metadata,analysis=fixture_source(tmp_path,count=379,constant=True)
    scenes=[cache_scene(analysis,index,round(index/10.,3),round((index+1)/10.,3)) for index in range(379)]
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,list(reversed(scenes)),[],tmp_path/'atlas',media_path=source,max_frames=400)
    assert result['statistics']['planned_requests']==379
    assert result['statistics']['indexed_scene_count']==379
    assert result['statistics']['captured_frame_records']==379
    assert result['statistics']['unique_image_files']==1
    assert result['statistics']['identical_content_deduplicated']==378
    assert result['statistics']['new_decoder_reads']==0
    assert result['statistics']['scene_ids_without_frames']==[]
    assert {row['scene_id'] for row in result['frames']}=={row['scene_id'] for row in scenes}


def test_byte_budget_rejection_is_explicit_and_has_no_files(tmp_path):
    _,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,2.)]
    root=tmp_path/'atlas'
    result=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],root,max_bytes=1)
    assert result['frames']==[] and result['statistics']['stored_image_bytes']==0
    assert result['missing_requests'][0]['reason']=='shared_image_byte_budget_exhausted'
    assert not list((root/'06_VISUAL_ATLAS/frames').iterdir())


def test_reprofile_preserves_cache_and_corrects_legacy_cached_timestamp_without_decoder(tmp_path,monkeypatch):
    _,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,1.,time=.2),cache_scene(analysis,1,1.,2.,time=1.2)]
    cache=tmp_path/'cache'
    atlas=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],cache)
    # Simulate the old R6.3 harvest bug: assigned scene.start to cached frames.
    for row in atlas['frames']:row['source_time_s']=0. if row['scene_id']==scenes[0]['scene_id'] else 1.
    path=cache/'06_VISUAL_ATLAS/atlas_index.json';path.write_text(json.dumps(atlas),encoding='utf-8')
    before={str(p.relative_to(cache)):file_hash(p) for p in cache.rglob('*') if p.is_file()}
    class NoVideo:
        def __init__(self,*args,**kwargs):raise AssertionError('reprofile opened a video decoder')
    monkeypatch.setattr(compact_frames,'SparseFrameProvider',NoVideo)
    root=tmp_path/'reprofile'
    result=compact_frames.reprofile_shared_atlas(cache,root,metadata,scenes,analysis_folder=analysis)
    assert [row['source_time_s'] for row in result['frames']]==[.2,1.2]
    assert result['statistics']['new_decoder_reads']==0
    assert result['statistics']['timestamp_reconciliations']==2
    assert result['sampling_policy']['navigation_width']==320
    assert result['sampling_policy']['analysis_width']==640
    assert result['statistics']['unresolved_cached_timestamps']==0
    assert result['statistics']['unique_image_files']==1
    assert len(result['source_frame_id_map'])==2
    assert {str(p.relative_to(cache)):file_hash(p) for p in cache.rglob('*') if p.is_file()}==before
    assert all(file_hash(root/row['path'])==row['sha256'] for row in result['frames']+result['contact_sheets'])
    with pytest.raises(ValueError,match='immutable_cache'):
        compact_frames.reprofile_shared_atlas(cache,cache/'nested',metadata,scenes)
    with pytest.raises(FileExistsError):
        compact_frames.reprofile_shared_atlas(cache,root,metadata,scenes)


def test_reprofile_does_not_hide_unverifiable_cache_time_or_foreign_frame(tmp_path):
    _,metadata,analysis=fixture_source(tmp_path)
    scenes=[cache_scene(analysis,0,0.,2.,time=.2)]
    cache=tmp_path/'cache';atlas=compact_frames.build_shared_visual_atlas(analysis,metadata,scenes,[],cache)
    result=compact_frames.reprofile_shared_atlas(cache,tmp_path/'reprofile',metadata,scenes)
    assert result['statistics']['unresolved_cached_timestamps']==1
    atlas['frames'][0]['source_sha256']='b'*64
    (cache/'06_VISUAL_ATLAS/atlas_index.json').write_text(json.dumps(atlas),encoding='utf-8')
    with pytest.raises(ValueError,match='frame_identity'):
        compact_frames.reprofile_shared_atlas(cache,tmp_path/'foreign',metadata,scenes)
