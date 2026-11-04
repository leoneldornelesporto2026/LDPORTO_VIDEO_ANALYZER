"""Dossier integrity/cancellation and searchable Unicode: no models or source media."""
import hashlib
import json
from pathlib import Path
import re
import zlib

import pytest

from ldporto.editorial_pdf import EditorialPDF
from ldporto.paths import windows_component
from ldporto.project_export import export_project, verify_project_export
from ldporto.second_curation_export import build_core_package
from test_v43_handoff import analysis_fixture


def _package(tmp_path):
    analysis=analysis_fixture()
    analysis['metadata']['sha256']='a'*64
    analysis['metadata']['source']={'type':'local','id':'SYNTHETIC_R6','title':'Revisão: ação / música?'}
    return build_core_package(analysis,output_dir=tmp_path/'packages')['path']


def _pdf_text(data):
    """Read the PDF's public Unicode map and text operators, independent of writer."""
    mappings={int(a,16):bytes.fromhex(b.decode()).decode('utf-16-be')
              for a,b in re.findall(rb'<([0-9A-Fa-f]{4})> <([0-9A-Fa-f]{4,8})>',data)
              if a != b'0000'}
    lines=[]
    for match in re.finditer(rb'<<(.*?)>>\nstream\n',data,re.S):
        length=int(re.search(rb'/Length (\d+)',match.group(1))[1])
        raw=data[match.end():match.end()+length]
        if b'/FlateDecode' in match.group(1):
            raw=zlib.decompress(raw)
        for encoded in re.findall(rb'<([0-9A-F]+)> Tj',raw):
            chars=[mappings[int(encoded[i:i+4],16)] for i in range(0,len(encoded),4)]
            lines.append(''.join(chars))
    return '\n'.join(lines)


def test_unicode_searchable_pdf_with_index_bookmarks_links_and_pagination(tmp_path):
    pdf=EditorialPDF('Transcrição disponível – João','Teste sintético')
    pdf.section('Áudio e revisão')
    literal='Ação, coração e música: café às três.'
    pdf.text(literal,url='https://www.youtube.com/watch?v=SYNTHETIC&t=12s')
    for i in range(100):
        pdf.text('Trecho sintético %d com limite natural de frase.'%i)
    target=tmp_path/'dossier.pdf'
    result=pdf.save(target)
    data=target.read_bytes()
    assert result['pages']>2
    assert literal in _pdf_text(data)
    assert 'Índice de leitura' in _pdf_text(data)
    assert b'/Outlines' in data and b'/Subtype /Link' in data and b'/ToUnicode' in data
    startxref=int(re.search(rb'startxref\n(\d+)',data)[1])
    assert data[startxref:startxref+4]==b'xref'


def test_unicode_aliases_keep_distinct_text_cids_with_the_same_embedded_font_glyph(tmp_path):
    pdf=EditorialPDF('Unicode aliases')
    literal='Normal space: A B. NBSP: A\u00a0B. Hyphen: A-B. Soft hyphen: A\u00adB.'
    pdf.text(literal)
    target=tmp_path/'unicode_aliases.pdf'
    pdf.save(target)
    data=target.read_bytes()
    # Read public ToUnicode/text operators independently of the writer. A single
    # glyph reused for NBSP or soft-hyphen must not replace normal source text.
    assert literal in _pdf_text(data)
    aliases=[(' ', '\u00a0'), ('-', '\u00ad')]
    reference=int(re.search(rb'/CIDToGIDMap (\d+) 0 R',data)[1])
    body=re.search(rb'\b'+str(reference).encode()+rb' 0 obj\n(.*?)\nendobj',data,re.S)[1]
    start=body.index(b'\nstream\n')+len(b'\nstream\n')
    size=int(re.search(rb'/Length (\d+)',body)[1])
    glyph_map=zlib.decompress(body[start:start+size])
    unicode_to_cid={bytes.fromhex(char.decode()).decode('utf-16-be'):int(cid,16)
                    for cid,char in re.findall(rb'<([0-9A-Fa-f]{4})> <([0-9A-Fa-f]{4,8})>',data)
                    if cid!=b'0000'}
    for first,second in aliases:
        a,b=unicode_to_cid[first],unicode_to_cid[second]
        assert a!=b
        assert glyph_map[a*2:a*2+2]==glyph_map[b*2:b*2+2]


def test_project_delivery_is_exclusive_verified_and_preserves_source_package(tmp_path):
    package=Path(_package(tmp_path))
    before=hashlib.sha256(package.read_bytes()).hexdigest()
    first=export_project(package,tmp_path/'Videos')
    second=export_project(package,tmp_path/'Videos')
    assert first['path']!=second['path']
    assert hashlib.sha256(package.read_bytes()).hexdigest()==before
    root=Path(first['path'])
    manifest=json.loads((root/'PROJECT_MANIFEST.json').read_text(encoding='utf-8'))
    assert manifest['publication_ready'] is False and manifest['preview_approved'] is False
    assert manifest['source_video_included'] is False
    assert first['verification']['status']=='valid'
    assert (root/'00_RESUMO/GUIA_EDITORIAL_COMPLETO.pdf').is_file()
    assert (root/'01_TRANSCRICAO/TRANSCRICAO_COMPLETA.pdf').is_file()
    assert list((root/'03_REELS').glob('*/RELATORIO_REEL.pdf'))
    assert not list(root.rglob('*.mp4'))
    gaps=json.loads((root/'01_TRANSCRICAO/lacunas_e_revisoes.json').read_text(encoding='utf-8'))
    assert gaps['coverage_ratio']<=1 and gaps['audio_verified'] is False
    file=root/'01_TRANSCRICAO/transcricao.txt'
    file.write_text('tampered synthetic text',encoding='utf-8')
    assert verify_project_export(root)['status']=='failed'


def test_cancelled_export_keeps_partial_manifest_and_never_claims_ready(tmp_path):
    package=_package(tmp_path)
    result=export_project(package,tmp_path/'Videos',cancelled=lambda:True)
    assert result['state']=='CANCELLED'
    assert result['verification']['status']=='valid'
    assert result['summary']['pdf_status']=='PARTIAL'
    assert Path(result['path'],'PROJECT_MANIFEST.json').is_file()
    assert Path(package).is_file()


def test_dossier_verifier_rejects_traversal_and_approval(tmp_path):
    result=export_project(_package(tmp_path),tmp_path/'Videos')
    root=Path(result['path']); path=root/'PROJECT_MANIFEST.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    data['publication_ready']=True
    path.write_text(json.dumps(data),encoding='utf-8')
    assert 'dossier_cannot_grant_approval' in verify_project_export(root)['errors']
    data['files'][0]['path']='../outside.txt'
    path.write_text(json.dumps(data),encoding='utf-8')
    assert verify_project_export(root)['status']=='failed'


@pytest.mark.parametrize('title',['CON','AUX.txt','../..','áudio<>:"/\\|?* .','LPT1'])
def test_windows_directory_names_are_safe(title):
    value=windows_component(title)
    assert not re.search(r'[<>:"/\\|?*]',value)
    assert value not in {'CON','AUX.txt','LPT1'}
    assert value.strip(' .')==value and value
