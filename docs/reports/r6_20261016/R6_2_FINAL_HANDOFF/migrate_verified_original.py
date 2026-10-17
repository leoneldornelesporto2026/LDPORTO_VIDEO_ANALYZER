"""Additive copy of the confirmed show original; no removal/download/inference."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'src'))
from ldporto.core import file_hash
from ldporto.media import resolve_input
from ldporto.media_library import register_media_copy,resolve_existing_media,library_directory
from ldporto.media_runtime import find_media_tool


def main():
    folder=Path(__file__).parent
    baseline=json.loads((folder/'BASELINE.json').read_text(encoding='utf-8'))
    source=Path(baseline['source']);before=source.stat()
    expected=baseline['source_sha256'];vid='9UCGZia2p1k'
    command=[str(find_media_tool('ffprobe')),'-v','error','-show_streams','-show_format','-of','json',str(source)]
    probe=json.loads(subprocess.check_output(command))
    streams=[{'type':s['codec_type'],'codec':s.get('codec_name'),'width':s.get('width'),'height':s.get('height')}
        for s in probe['streams']]
    assert abs(float(probe['format']['duration'])-baseline['duration'])<.1
    assert any(s['type']=='video' and s['width']==1920 and s['height']==1080 for s in streams)
    copied=register_media_copy(source,vid,expected,metadata={'duration':float(probe['format']['duration']),'streams':streams})
    resolved=resolve_existing_media(vid,expected_sha256=expected)
    assert resolved['origin']=='media_library' and resolved['download_needed'] is False
    cfg={'offline':True,'download':{'allow_download':False,'expected_sha256':expected}}
    analyzer_path,analyzer_metadata=resolve_input('https://www.youtube.com/watch?v='+vid,cfg,ROOT)
    assert analyzer_path==Path(copied['path']) and analyzer_metadata['media_resolution']['origin']=='media_library'
    # Reopen/inspect the copied container and confirm the unchanged original again.
    copy_command=[*command[:-1],str(analyzer_path)]
    copied_probe=json.loads(subprocess.check_output(copy_command))
    assert copied_probe['format']['size']==probe['format']['size']
    assert file_hash(source)==expected==file_hash(analyzer_path)
    assert source.stat().st_size==before.st_size and source.stat().st_mtime_ns==before.st_mtime_ns
    receipt={'source':str(source),'library':str(library_directory()),'copy':copied,'resolution':resolved,
        'analyzer_resolved_path':str(analyzer_path),'container_probe':{'command':copy_command,'duration':copied_probe['format']['duration'],'streams':streams},
        'original_bytes':before.st_size,'original_mtime_ns_preserved':True,'original_sha256_preserved':True,
        'source_removed':False,'download_called':False,'models_executed':False,'publication_ready':False,
        'rollback':'Keep legacy source selected; no automatic removal of either original.'}
    (folder/'MEDIA_LIBRARY_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
