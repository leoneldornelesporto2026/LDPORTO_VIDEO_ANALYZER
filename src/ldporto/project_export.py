"""Organized, additive project delivery from a validated second-curation package.

This is a dossier of plans and evidence. It never reads the original video,
renders social videos, invokes models or grants editorial/publication approval.
"""
from datetime import datetime, timezone
from html import escape
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import uuid
import zipfile
import jsonschema

from .core import file_hash, stamp
from .editorial_pdf import EditorialPDF
from .export_privacy import sanitize_export
from .paths import videos_directory, windows_component


class ExportCancelled(Exception):
    pass


def _safe_ancestors(path):
    import stat
    path = Path(path).absolute()
    for parent in [path, *path.parents]:
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024)):
            raise ValueError('export_path_link_or_reparse_point')
    if any(p.casefold() in {'.git','.venv','models'} for p in path.parts):
        raise ValueError('protected_export_destination')
    return path.resolve()


def _logical(name):
    p = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts or str(p) != name:
        raise ValueError('unsafe_project_artifact_reference')
    return p


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_export(value), ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def _rows(value, key):
    return value.get(key, []) if isinstance(value, dict) else value if isinstance(value, list) else []


def _interval(row, duration):
    start, end = row.get('start'), row.get('end')
    return (all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in (start,end,duration))
            and 0 <= start < end <= duration+1e-6)


def _gaps(segments, duration):
    cursor, gaps, covered = 0., [], 0.
    for row in sorted(segments,key=lambda s:s['start']):
        start,end = row['start'],row['end']
        if start>cursor:
            gaps.append({'start':cursor,'end':start,'status':'NO_CANONICAL_TRANSCRIPT_AVAILABLE'})
        covered += max(0.,end-max(cursor,start))
        cursor=max(cursor,end)
    if cursor<duration:
        gaps.append({'start':cursor,'end':duration,'status':'NO_CANONICAL_TRANSCRIPT_AVAILABLE'})
    return gaps,covered


def _transcript_files(folder, segments, words):
    folder.mkdir(parents=True,exist_ok=True)
    text = '\n'.join('[%s–%s] %s: %s' % (stamp(s['start']),stamp(s['end']),s.get('speaker') or 'UNKNOWN',s.get('text','')) for s in segments)
    srt = '\n\n'.join('%d\n%s --> %s\n%s' % (i,stamp(s['start'],True),stamp(s['end'],True),s.get('text','')) for i,s in enumerate(segments,1))
    (folder/'transcricao.txt').write_text(text+'\n',encoding='utf-8')
    (folder/'transcricao.srt').write_text(srt+'\n',encoding='utf-8')
    for name,rows in (('segmentos.jsonl',segments),('palavras.jsonl',words)):
        (folder/name).write_text(''.join(json.dumps(sanitize_export(s),ensure_ascii=False,allow_nan=False)+'\n' for s in rows),encoding='utf-8')


def _title(candidate):
    copy = candidate.get('generated_copy') or {}
    return str(candidate.get('title') or copy.get('hook_idea') or candidate.get('theme') or candidate['candidate_id'])


def _caption_summary(report):
    from collections import Counter
    candidates=report.get('candidates') or {}
    return {'candidate_count':len(candidates),'story_count':len(report.get('stories') or {}),
            'candidate_status_counts':dict(Counter(row.get('status') for row in candidates.values())),
            'candidates_with_reliable_captions':sum(row.get('status')=='CAPTION_READY' for row in candidates.values()),
            'candidate_review_required_count':sum(row.get('review_required') is True for row in candidates.values()),
            'new_asr_calls':report.get('new_asr_calls'),
            'status':'AVAILABLE' if report else 'UNAVAILABLE_LEGACY'}


def _describe(pdf, label, value, fallback='Não registrado; revisão necessária.'):
    if isinstance(value,list) and all(isinstance(v,(str,int,float)) for v in value):
        value='; '.join(str(v) for v in value)
    elif isinstance(value,(list,dict)):
        value = json.dumps(sanitize_export(value),ensure_ascii=False)
    pdf.text(label+': '+(str(value) if value not in (None,'',[],{}) else fallback))


def _context(rows):
    if not isinstance(rows,list):
        return rows
    return '\n'.join(('%s · %s'%(stamp(r['start']),r.get('text') or r.get('summary') or r.get('segment_id','')))
                     if isinstance(r,dict) and isinstance(r.get('start'),(int,float)) else str(r) for r in rows)


def _chapters(pdf, chapters):
    if not chapters:
        pdf.text('Capítulos não registrados; consulte os timestamps da transcrição disponível.')
    for row in chapters:
        title=row.get('title') or row.get('label') or row.get('section_type') or row.get('section_id') or 'Capítulo sem título confirmado'
        times=('%s–%s · '%(stamp(row['start']),stamp(row['end']))) if all(isinstance(row.get(k),(int,float)) for k in ('start','end')) else ''
        pdf.text(times+str(title),10,'#006A75')
        if row.get('summary'):
            pdf.text(row['summary'])


def _camera_metrics(pdf, metrics):
    labels={'smart_camera_decision_count':'Decisões editoriais propostas',
            'proposed_zoom_event_count':'Eventos de zoom propostos',
            'zoom_timeline_event_count':'Eventos de zoom na timeline',
            'rendered_zoom_event_count':'Eventos com recibo de renderização',
            'zoom_delivered_event_count':'Movimentos confirmados nos frames finais',
            'focus_resolved_fraction':'Fração temporal com foco resolvido',
            'known_speaker_focus_fraction':'Fração com falante visual confirmado'}
    for key,label in labels.items():
        _describe(pdf,label,metrics.get(key),'Não medido nesta revisão.')


def _titles(pdf, proposal):
    if not isinstance(proposal,dict):
        pdf.text('Títulos: propostas indisponíveis; revisão editorial pendente.')
        return
    options=proposal.get('suggested_titles') or []
    if proposal.get('primary_title'):
        options=[proposal['primary_title'],*(proposal.get('alternative_titles') or [])]
    for row in options[:3]:
        pdf.text('Sugestão não aprovada: '+str(row.get('title') or row.get('text')) if isinstance(row,dict) else 'Sugestão não aprovada: '+str(row))
    if not options:
        pdf.text('Títulos não gerados com sustentação suficiente; revisão editorial pendente.')


def _transcript_pdf(pdf, segments, gaps, source, cancel):
    pdf.section('Transcrição canônica disponível')
    events = [(s['start'],'segment',s) for s in segments]+[(s['start'],'gap',s) for s in gaps]
    for _,kind,row in sorted(events,key=lambda item:item[0]):
        cancel()
        label = stamp(row['start'])+'–'+stamp(row['end'])
        url = source+'&t='+str(int(row['start']))+'s' if source and 'youtube.com/watch?' in source else None
        if kind == 'gap':
            pdf.text(label+' · Lacuna de transcrição; tipo de áudio não comprovado.',9,'#815225',url)
        else:
            pdf.text(label+' · '+str(row.get('speaker') or 'UNKNOWN'),10,'#006A75',url)
            pdf.text(row.get('text',''))
            if row.get('needs_review'):
                pdf.text('Trecho incerto: '+', '.join(row.get('review_reasons') or ['revisão pendente']),9,'#815225')


def export_project(package_path, output_root=None, *, analysis=None, progress=None, cancelled=None, display_title=None):
    """Create one exclusive revision. On cancellation keep a labelled partial dossier."""
    from .second_curation_export import snapshot_core_package
    package_path = Path(package_path)
    package_bytes,validation = snapshot_core_package(package_path)
    package_hash=hashlib.sha256(package_bytes).hexdigest()
    root = _safe_ancestors(output_root or videos_directory()/'LDPORTO_VIDEO_ANALYZER')
    root.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        names=set(archive.namelist())
        def read(name,default=None):
            _logical(name)
            if name not in names:
                return default
            raw = archive.read(name)
            if name.endswith('.jsonl'):
                return [json.loads(line) for line in raw.decode('utf-8').splitlines() if line]
            return json.loads(raw)
        metadata=read('source/metadata.json',{})
        manifest=read('SECOND_CURATION_MANIFEST.json',{})
        index=read('CURATION_INDEX.json',{})
        info=metadata.get('source') or {}
        duration=metadata.get('duration')
        source_hash=metadata.get('sha256')
        title=display_title or info.get('title') or info.get('id') or 'Projeto audiovisual'
        identifier=windows_component(info.get('id') or str(source_hash or '')[:12])
        revision=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6]
        destination=root/(windows_component(title,max_length=85)+'__'+identifier+'__'+revision)
        destination.mkdir(exist_ok=False)
        state={'schema_version':'1.0','contract':'ldporto.project_dossier','revision':revision,
               'title':title,'video_id':info.get('id'),'source_sha256':source_hash,
               'display_title_provenance':'user_supplied_editorial_title' if display_title else 'source_metadata',
               'source_metadata_title':info.get('title'),
               'source_media_hash_scope':'reported_by_analyzer_not_rehashed_by_dossier',
               'source_duration':duration,'package_sha256':package_hash,
               'package_run_id':manifest.get('run_id'),'created_at':datetime.now(timezone.utc).isoformat(),
               'analysis_status':index.get('analysis_status'),'state':'PARTIAL',
               'contents_kind':'planning_and_review_evidence','source_video_included':False,
               'final_social_videos_rendered':False,'preview_approved':False,'publication_ready':False,
               'pdf_status':'PENDING','files':[]}
        def check():
            if cancelled and cancelled():
                raise ExportCancelled('export_cancelled')
        def emit(stage,current=0,total=1):
            check()
            if progress:
                progress(stage,current,total)
        def copy_entry(name,target):
            if name in names:
                _logical(name)
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(archive.read(name))
                return True
            return False
        _json(destination/'PROJECT_MANIFEST.json',state)
        try:
            emit('Evidências canônicas')
            segments=read('transcript/relevant_segments.jsonl',[])
            words=read('transcript/relevant_words.jsonl',[])
            if analysis is not None:
                from .transcription import _require_original
                if (analysis.get('metadata') or {}).get('sha256')!=source_hash:
                    raise ValueError('project_analysis_source_hash_mismatch')
                analysis_run=(analysis.get('run_manifest') or {}).get('run_id')
                if analysis_run and manifest.get('run_id') and analysis_run!=manifest['run_id']:
                    raise ValueError('project_analysis_run_mismatch')
                source_segments=analysis.get('transcript_segments') or segments
                source_words=analysis.get('words') or words
                segment_ids=[r.get('segment_id') for r in source_segments]
                word_ids=[r.get('word_id') for r in source_words]
                if (len(segment_ids)!=len(set(segment_ids)) or len(word_ids)!=len(set(word_ids)) or
                        set(segment_ids)!={r.get('segment_id') for r in segments} or
                        any(r.get('segment_id') not in set(segment_ids) for r in source_words)):
                    raise ValueError('project_analysis_canonical_id_set_mismatch')
                for row in [*source_segments,*source_words]:
                    _require_original(row)
                for exported,source_rows,id_key,keys in (
                    (segments,source_segments,'segment_id',('segment_id','start','end','text','speaker')),
                    (words,source_words,'word_id',('word_id','segment_id','start','end','word','raw','speaker'))):
                    source_by_id={r.get(id_key):sanitize_export(r) for r in source_rows}
                    for row in exported:
                        actual=source_by_id.get(row.get(id_key))
                        if actual is None or any(actual.get(k)!=row.get(k) for k in keys):
                            raise ValueError('project_analysis_package_revision_mismatch:'+str(row.get(id_key)))
                segments=sanitize_export(source_segments)
                words=sanitize_export(source_words)
            if not isinstance(segments,list) or not all(_interval(s,duration) for s in segments):
                raise ValueError('project_invalid_canonical_segment_interval')
            invalid_words=[w.get('word_id') for w in words if not _interval(w,duration)]
            gaps,covered=_gaps(segments,duration)
            coverage={'scope':'union_of_available_canonical_segment_intervals',
                      'covered_seconds':covered,'source_seconds':duration,
                      'coverage_ratio':covered/duration if duration else 0,
                      'audio_verified':False,'gaps':gaps,'invalid_word_interval_ids':invalid_words,
                      'invalid_words_preserved_for_review':True,'publication_ready':False}
            state['transcript_coverage_ratio']=coverage['coverage_ratio']
            transcript=destination/'01_TRANSCRICAO'
            _transcript_files(transcript,segments,words)
            _json(transcript/'lacunas_e_revisoes.json',coverage)
            for src,target in (('people/participants.json','participantes.json'),('people/person_appearances.json','aparicoes.json'),
                               ('people/instrument_observations.json','instrumentos.json'),('people/performer_review_queue.json','identities_review.json')):
                if not copy_entry(src,destination/'02_PESSOAS_E_CENAS'/target):
                    _json(destination/'02_PESSOAS_E_CENAS'/target,{'status':'UNAVAILABLE','observations':[], 'publication_ready':False})
            _json(destination/'02_PESSOAS_E_CENAS/cenas.json',(analysis or {}).get('scenes') or {'status':'UNAVAILABLE','reference':'06_SEGUNDA_CURADORIA/SECOND_CURATION_READY.zip#camera/candidate_camera_plans.json'})
            for src,target in (('camera/candidate_camera_plans.json','candidate_camera_plans.json'),
                               ('camera/shared_camera_handoff.json','camera_handoff.json'),('camera/camera_summary.json','zoom_validation.json')):
                copy_entry(src,destination/'05_CAMERAS'/target)
            if analysis:
                from .camera_handoff import build_camera_handoff
                _json(destination/'05_CAMERAS/camera_timeline.json',build_camera_handoff(analysis))
                _json(destination/'05_CAMERAS/focus_targets.json',{'status':'PROPOSALS_REQUIRE_REVIEW',
                    'camera_ref':'camera_timeline.json','publication_ready':False})
            else:
                _json(destination/'05_CAMERAS/camera_timeline.json',{'status':'UNAVAILABLE','reason':'source_timeline_not_in_legacy_package'})
            candidates=read('editorial/candidate_catalog.json',[])
            candidates=_rows(candidates,'candidates')
            by_candidate={r['candidate_id']:r for r in candidates}
            plans=read('camera/candidate_camera_plans.json',[])
            by_plan={r['candidate_id']:r for r in _rows(plans,'plans')}
            state['candidates_with_geometrically_valid_interval']=sum(any(
                (s.get('evidence') or {}).get('crop_geometrically_valid') is True
                for s in (p.get('camera_handoff') or {}).get('segments') or []) for p in by_plan.values())
            state['zoom_confirmed_in_final_frames_count']=read('camera/camera_summary.json',{}).get('zoom_delivered_event_count')
            state['complete_phrase_story_count']=None
            preflight=read('subtitles/caption_preflight_r6.json',{})
            caption_summary=_caption_summary(preflight)
            summary=destination/'00_RESUMO'
            _json(summary/'MELHORES_MOMENTOS.json',{'candidates':candidates,'default_shortlist':read('editorial/default_shortlist.json',[]),
                'ranking_kind':'editorial_heuristic_not_viral_probability','publication_ready':False})
            guide=EditorialPDF(title,'Guia editorial · análise '+str(index.get('analysis_status'))+' · '+revision)
            guide.section('Fonte e escopo de revisão')
            for label,value in (('URL original',info.get('url')),('Duração',stamp(duration)),('SHA256 da mídia informado',source_hash),
                ('Run do pacote',manifest.get('run_id')),('Versão da análise',metadata.get('analyzer_version')),
                ('Cobertura temporal da transcrição','%.2f%%' % (coverage['coverage_ratio']*100))):
                _describe(guide,label,value)
            guide.text('Fatos são os dados canônicos referenciados. Títulos, ranking e câmera são propostas editoriais. Identidades, direitos musicais, áudio e prévias exigem revisão humana. Nenhum vídeo social final foi renderizado por esta exportação.')
            guide.section('Resumo editorial proposto')
            episode=read('summary/analysis_summary.json',{}).get('episode_summary')
            _describe(guide,'Síntese registrada pelo Analyzer',episode.get('text') if isinstance(episode,dict) else episode)
            guide.text('Esta síntese é uma hipótese editorial produzida na análise de origem. Falas, nomes de músicas, papéis e acontecimentos citados exigem conferência com a fonte; o dossiê não realizou nova verificação de áudio.')
            guide.section('Participantes e identidades')
            for person in _rows(read('people/participants.json',[]),'participants'):
                guide.text(str(person.get('participant_id') or 'Sem ID')+' · '+str(person.get('confirmed_name') or 'Nome não confirmado'),11,'#006A75')
                _describe(guide,'Pessoa visual associada',person.get('person_id'),'UNKNOWN_PERSON')
                _describe(guide,'Locutores acústicos',person.get('speaker_ids'))
                _describe(guide,'Papel registrado (hipótese)',person.get('role'))
                guide.text('Confirmar associação rosto–participante, nome e papel com fonte verificável.')
            guide.section('Capítulos e linha do tempo')
            guide.text('Títulos e descrições dos capítulos são propostas editoriais; os intervalos remetem à fonte canônica.')
            _chapters(guide,_rows(read('editorial/program_sections.json',[]),'sections'))
            guide.section('Reels propostos e ranking editorial')
            html_rows=[]
            for number,candidate in enumerate(sorted(candidates,key=lambda c:(c.get('rank') or 100000,c['start'])),1):
                emit('Relatórios de Reels',number,len(candidates))
                cid=candidate['candidate_id']
                if not _interval(candidate,duration):
                    raise ValueError('project_invalid_candidate_interval:'+cid)
                folder=destination/'03_REELS'/('REEL_%03d'%number)
                title_text=_title(candidate)
                _json(folder/'briefing.json',candidate)
                _json(folder/'camera_plan.json',by_plan.get(cid) or {'status':'UNAVAILABLE','publication_ready':False})
                _json(folder/'title_suggestions.json',{'kind':'editorial_proposal','primary':title_text,
                    'alternatives':candidate.get('title_variants') or [],'human_approved':False})
                selected_segments=[s for s in segments if s.get('segment_id') in (candidate.get('segment_ids') or [])]
                selected_words=[w for w in words if w.get('word_id') in (candidate.get('word_ids') or [])]
                # Keep absolute source times; phrase boundaries remain source-bound.
                _transcript_files(folder,selected_segments,selected_words)
                _json(folder/'words.json',selected_words)
                clip_gaps,_=_gaps([{'start':max(candidate['start'],s['start'])-candidate['start'],
                                   'end':min(candidate['end'],s['end'])-candidate['start']}
                                  for s in selected_segments if s['start']<candidate['end'] and s['end']>candidate['start']],candidate['end']-candidate['start'])
                _json(folder/'lacunas.json',{'timebase':'clip_relative_seconds','gaps':clip_gaps})
                pdf=EditorialPDF(title_text,cid+' · proposta para revisão humana')
                pdf.section('Corte, contexto e evidência')
                for label,key in (('Início','start'),('Fim','end'),('Duração','duration'),('Categorias','categories'),('Motivo da seleção','selection_reason'),
                    ('Contexto anterior','context_before'),('Contexto posterior','context_after'),('Pessoas','person_ids'),
                    ('IDs dos segmentos','segment_ids'),('Riscos de limites','boundary_risks')):
                    value=candidate.get(key)
                    if key in {'start','end'} and isinstance(value,(int,float)):
                        value=stamp(value)
                    elif key=='duration' and isinstance(value,(int,float)):
                        value='%.2f segundos'%value
                    _describe(pdf,label,_context(value) if key in {'context_before','context_after'} else value)
                caption=candidate.get('caption_preflight') or {}
                _describe(pdf,'Estado da legenda',caption.get('status'))
                _describe(pdf,'Modalidade permitida',caption.get('allowed_caption_mode'))
                pdf.text('Sincronismo, precisão do texto e áudio continuam sujeitos a revisão humana. Evidência detalhada: briefing.json e contrato no ZIP.')
                copy=candidate.get('generated_copy') or {}
                _describe(pdf,'Gancho proposto',copy.get('hook_idea'))
                _describe(pdf,'Título alternativo proposto',copy.get('title_idea'))
                _describe(pdf,'CTA proposto',copy.get('cta'))
                pdf.section('Plano de câmera e material visual')
                plan=by_plan.get(cid) or {}
                _describe(pdf,'Viabilidade',plan.get('camera_feasibility'))
                pdf.text('Plano estruturado: camera_plan.json. Movimento planejado exige render e verificação no Curator.')
                image_name='visuals/'+cid+'/contact_sheet.jpg'
                if copy_entry(image_name,folder/'visual_evidence/contact_sheet.jpg'):
                    pdf.image(archive.read(image_name),'Frames reais incluídos pelo Analyzer; não comprovam aprovação da prévia final.')
                    thumbnail_state='CONTACT_SHEET_AVAILABLE_REQUIRES_HUMAN_FRAME_SELECTION'
                else:
                    pdf.text('Imagens de referência: indisponíveis neste pacote.')
                    thumbnail_state='UNAVAILABLE'
                _json(folder/'thumbnail_candidates/index.json',{'status':thumbnail_state,
                    'contact_sheet_ref':'../visual_evidence/contact_sheet.jpg' if image_name in names else None,
                    'final_thumbnail_created':False,'human_approved':False})
                _transcript_pdf(pdf,selected_segments,[],info.get('url'),check)
                pdf.section('Palavras com timestamp e lacunas')
                for word in selected_words:
                    safe_time=lambda v:stamp(v) if isinstance(v,(int,float)) and math.isfinite(v) else 'tempo não confiável'
                    pdf.text('%s–%s %s [%s]' % (safe_time(word.get('start')),safe_time(word.get('end')),word.get('raw') or word.get('word',''),word.get('word_id')),9)
                _describe(pdf,'Lacunas relativas ao corte',clip_gaps)
                pdf.section('Checklist editorial e de publicação')
                pdf.text('Revisar frase completa, contexto, grafia, alinhamento, direitos, título, gancho, encerramento, CTA, thumbnail, crop e áreas seguras. Aprovação humana: pendente. Preview aprovado: não. Publicação pronta: não.')
                _describe(pdf,'Palavras-chave',candidate.get('keywords'))
                pdf.save(folder/'RELATORIO_REEL.pdf')
                guide.text('%s · %s–%s · %s' % (cid,stamp(candidate['start']),stamp(candidate['end']),title_text),11,'#006A75')
                _describe(guide,'Justificativa/pendências',candidate.get('editorial_review_plan') or candidate.get('boundary_decision_reasons'))
                html_rows.append('<li><a href="../03_REELS/REEL_%03d/RELATORIO_REEL.pdf">%s</a> · %s–%s</li>' % (number,escape(title_text),stamp(candidate['start']),stamp(candidate['end'])))
            emit('Stories sequenciais')
            series=read('editorial/story_series_proposals.json',{})
            sequences=_rows(series,'series') or _rows(read('editorial/story_sequence_candidates.json',{}),'sequences')
            standalone=_rows(read('social/stories_manifest.json',{}),'stories')
            state['story_parts_proposed_count']=len({p.get('story_id') or p.get('unit_id') or uid
                for seq in sequences for uid,p in ([('',s) for s in seq.get('stories') or []] or
                    [(uid,{'unit_id':uid}) for uid in seq.get('unit_ids') or []])})
            units={r.get('unit_id'):r for r in _rows(read('editorial/story_units.json',{}),'units')}
            unit_titles={r.get('unit_id'):r for r in _rows(read('social/narrative_title_suggestions.json',{}),'titles')}
            _json(destination/'04_STORIES/series.json',{'status':'REVIEW_REQUIRED' if sequences else 'UNAVAILABLE',
                'series':sequences,'story_visual_handoff_ref':'06_SEGUNDA_CURADORIA/SECOND_CURATION_READY.zip#social/story_visual_handoff.json',
                'publication_ready':False})
            guide.section('Stories e continuidade narrativa')
            for number,sequence in enumerate(sequences,1):
                emit('Relatórios de Stories',number,len(sequences))
                folder=destination/'04_STORIES'/('SERIE_%03d'%number)
                _json(folder/'briefing.json',sequence)
                pdf=EditorialPDF('Série %03d'%number,'Sequência proposta · revisão de continuidade pendente')
                pieces=sequence.get('stories') or [units.get(uid) for uid in sequence.get('unit_ids') or []]
                for part,unit in enumerate(pieces,1):
                    if not unit:
                        raise ValueError('project_story_unit_unresolved')
                    uid=unit.get('story_id') or unit.get('unit_id')
                    intervals=unit.get('source_intervals') or []
                    if any(not _interval(s,duration) for s in intervals):
                        raise ValueError('project_story_interval_invalid')
                    piece_folder=folder/('PARTE_%02d'%part)
                    _json(piece_folder/'briefing.json',unit)
                    _json(piece_folder/'title_suggestions.json',unit_titles.get(uid) or {
                        'primary_title':unit.get('primary_title'),'alternative_titles':unit.get('alternative_titles') or [],
                        'status':'REVIEW_REQUIRED','human_approved':False})
                    _json(piece_folder/'review.json',{'status':'BLOCKED' if sum(i['end']-i['start'] for i in intervals)>60 else 'REVIEW_REQUIRED',
                        'canonical_part_id':uid,'phrase_completion_confirmed':False,'publication_ready':False})
                    ids=unit.get('source_segment_ids') or [r.get('segment_id') for r in intervals]
                    part_segments=[r for r in segments if r.get('segment_id') in ids]
                    part_words=[r for r in words if r.get('segment_id') in ids]
                    _transcript_files(piece_folder,part_segments,part_words)
                    _json(piece_folder/'words.json',part_words)
                    from .subtitle_review import build_story_interval_preflight
                    part_review=build_story_interval_preflight(words,segments,[{'story_id':uid,'source_intervals':intervals}],duration=duration)
                    _json(piece_folder/'caption_preflight.json',part_review)
                    from .camera_handoff import build_camera_handoff
                    _json(piece_folder/'camera_plan.json',build_camera_handoff({
                        'metadata':metadata,'camera_director_timeline':read('camera/camera_director_timeline.json',[])}, intervals=intervals))
                    pdf.section('Parte %d · %s'%(part,uid))
                    _describe(pdf,'Papel narrativo',unit.get('narrative_role'))
                    _describe(pdf,'Intervalos da fonte',intervals)
                    _titles(pdf,unit_titles.get(uid) or unit)
                    _transcript_pdf(pdf,part_segments,[],info.get('url'),check)
                pdf.text('Contratos de câmera/legendas e títulos canônicos permanecem no ZIP. Não há conteúdo adicional criado para preencher duração.')
                pdf.save(folder/'SERIE_COMPLETA.pdf')
                guide.text('Sequência '+str(sequence.get('series_id') or sequence.get('sequence_id'))+' · '+str(len(pieces))+' partes propostas',11,'#006A75')
                _describe(guide,'Continuidade comprovada',sequence.get('complete_supported'),'Não comprovada; revisar a fonte.')
                _describe(guide,'Pendências',sequence.get('blockers') or sequence.get('missing_components'))
            for number,story in enumerate(standalone,1):
                # An independent Story stays independent; no series or continuity is invented.
                sid=story.get('story_id') or story.get('candidate_id')
                if not sid:
                    raise ValueError('standalone_story_missing_canonical_id')
                folder=destination/'04_STORIES/AVULSOS'/windows_component(sid)
                _json(folder/'briefing.json',story)
                _json(folder/'review.json',{'series_id':None,'canonical_story_id':sid,
                    'status':'BLOCKED' if not _interval(story,duration) or story['end']-story['start']>60 else 'REVIEW_REQUIRED',
                    'publication_ready':False})
                guide.text('Story avulso '+str(sid)+' · '+str(story.get('title') or 'Título pendente'),11,'#006A75')
            if not sequences:
                guide.text('Nenhuma série narrativa comprovada disponível neste pacote. Não foram inventadas partes ou títulos.')
            guide.section('Câmera, legendas e limitações')
            _camera_metrics(guide,read('camera/camera_summary.json',{}))
            _describe(guide,'Preflight de legendas',caption_summary)
            guide.text('Arquivos de referência: 05_CAMERAS; 01_TRANSCRICAO/lacunas_e_revisoes.json; 06_SEGUNDA_CURADORIA/HANDOFF_MASTER.json. Planos não atestam crop renderizado ou zoom entregue.')
            guide.section('Revisão humana obrigatória')
            guide.text('Conferir nomes e papéis; áudio e lacunas; cortes de frases; continuidade das séries; direitos e créditos; títulos e thumbnails; legendas; geometria; renderização e frames finais. Os gates permanecem separados.')
            guide.save(summary/'GUIA_EDITORIAL_COMPLETO.pdf')
            executive=EditorialPDF(title,'Resumo executivo · materiais de planejamento')
            executive.section('Estado da entrega')
            for label,value in (('Análise',index.get('analysis_status')),('Candidatos',len(candidates)),('Shortlist automática',index.get('default_shortlist_count')),
                               ('Séries propostas',len(sequences)),('Cobertura de transcrição','%.2f%%'%(coverage['coverage_ratio']*100))):
                _describe(executive,label,value)
            executive.text('Preview aprovado: não. Publicação pronta: não. Lacunas e pendências preservadas. Consulte o guia e os JSONs canônicos.')
            executive.save(summary/'RESUMO_EXECUTIVO.pdf')
            emit('PDF da transcrição')
            pdf=EditorialPDF('Transcrição disponível · '+title,'Cobertura medida: %.2f%% · sem completar lacunas'%(coverage['coverage_ratio']*100))
            pdf.section('Fonte e cobertura')
            _describe(pdf,'SHA256 da fonte informado',source_hash)
            pdf.text('Nomes somente quando confirmados nos contratos. IDs acústicos não identificam pessoas. Fala, canto e instrumental permanecem incertos na ausência de evidência por intervalo. JSON/JSONL são a fonte canônica dos timestamps.')
            pdf.section('Capítulos e referências editoriais')
            _chapters(pdf,_rows(read('editorial/program_sections.json',[]),'sections'))
            pdf.text('Reels: 03_REELS. Stories: 04_STORIES. Cada briefing referencia IDs canônicos da fonte.')
            _transcript_pdf(pdf,segments,gaps,info.get('url'),check)
            pdf.save(transcript/'TRANSCRICAO_COMPLETA.pdf')
            emit('ZIP e índice de evidências')
            handoff=destination/'06_SEGUNDA_CURADORIA'
            handoff.mkdir(exist_ok=True)
            (handoff/'SECOND_CURATION_READY.zip').write_bytes(package_bytes)
            if file_hash(handoff/'SECOND_CURATION_READY.zip')!=state['package_sha256']:
                raise ValueError('package_copy_checksum_mismatch')
            master=read('HANDOFF_MASTER.json')
            _json(handoff/'HANDOFF_MASTER.json',{'schema_version':'1.0','package_ref':'SECOND_CURATION_READY.zip',
                'package_sha256':state['package_sha256'],'source_sha256':source_hash,'run_id':manifest.get('run_id'),
                'package_handoff_ref':'SECOND_CURATION_READY.zip#HANDOFF_MASTER.json' if master else None,
                'references':[{'archive_member':n} for n in sorted(names)],
                'publication_ready':False,'preview_approved':False})
            (handoff/'HANDOFF_MASTER.md').write_text('# Índice do projeto\n\nEvidências canônicas no ZIP; IDs e referências internos foram validados.\n\nAprovações humanas pendentes.\n',encoding='utf-8')
            copy_entry('SECOND_CURATION_DECISIONS.template.json',handoff/'decisions_template.json')
            (handoff/'IMPORT_INSTRUCTIONS.md').write_text('Importe SECOND_CURATION_READY.zip no Curator. PDFs são dossiês para leitura; JSONs são canônicos. Não há MP4 social final. Verifique pendências, direitos e aprove prévias antes da publicação.\n',encoding='utf-8')
            technical=destination/'07_RELATORIOS_TECNICOS'
            _json(technical/'quality_report.json',read('summary/quality_summary.json',{}))
            _json(technical/'limitations.json',{'analysis_status':index.get('analysis_status'),'readiness':manifest.get('readiness'),
                'transcript_coverage':coverage['coverage_ratio'],'caption_preflight':caption_summary,
                'human_review_required':True,'rights_status':'UNKNOWN_REQUIRES_REVIEW','publication_ready':False})
            _json(technical/'provenance.json',{'package_sha256':state['package_sha256'],'source_sha256':source_hash,
                'package_build_provenance':manifest.get('build_provenance'),'new_audiovisual_inference':False,'original_audio_replaced':False})
            (summary/'INDICE_GERAL.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>'+escape(title)+'</title><h1>'+escape(title)+'</h1><p>Materiais para revisão. Nenhum MP4 final; aprovações pendentes.</p><p><a href="GUIA_EDITORIAL_COMPLETO.pdf">Guia editorial</a> · <a href="../01_TRANSCRICAO/TRANSCRICAO_COMPLETA.pdf">Transcrição</a></p><ul>'+''.join(html_rows)+'</ul></html>',encoding='utf-8')
            state.update(pdf_status='GENERATED',candidate_count=len(candidates),story_series_count=len(sequences),
                         standalone_story_count=len(standalone),
                         caption_preflight_summary=caption_summary,
                         state='READY_FOR_REVIEW' if manifest.get('workflow',{}).get('review_ready') is True else 'PARTIAL')
            emit('Verificação de integridade')
        except ExportCancelled:
            state.update(state='CANCELLED',pdf_status='PARTIAL')
        except Exception as exc:
            state.update(state='FAILED',error=type(exc).__name__+':'+str(exc),pdf_status='PARTIAL')
            _finalize(destination,state)
            raise
        _finalize(destination,state)
    verification=verify_project_export(destination)
    if verification['status']!='valid':
        raise ValueError('project_export_verification_failed:'+','.join(verification['errors']))
    return {'path':str(destination),'state':state['state'],'manifest_sha256':file_hash(destination/'PROJECT_MANIFEST.json'),
            'verification':verification,'summary':{k:state.get(k) for k in ('candidate_count','story_series_count','transcript_coverage_ratio','caption_preflight_summary','pdf_status')}}


def _finalize(destination,state):
    files=[]
    for path in sorted(destination.rglob('*')):
        if path.is_file() and path.name not in {'PROJECT_MANIFEST.json','checksums.sha256'}:
            files.append({'path':path.relative_to(destination).as_posix(),'bytes':path.stat().st_size,'sha256':file_hash(path)})
    checksums=destination/'07_RELATORIOS_TECNICOS/checksums.sha256'
    checksums.parent.mkdir(parents=True,exist_ok=True)
    checksums.write_text(''.join(row['sha256']+'  '+row['path']+'\n' for row in files),encoding='utf-8')
    files.append({'path':checksums.relative_to(destination).as_posix(),'bytes':checksums.stat().st_size,'sha256':file_hash(checksums)})
    state['files']=files
    _json(destination/'PROJECT_MANIFEST.json',state)


def verify_project_export(path):
    """Read-only verification; a valid partial dossier is still a partial dossier."""
    errors=[]
    try:
        root=_safe_ancestors(path)
        manifest_path=_safe_ancestors(root/'PROJECT_MANIFEST.json')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        from .paths import SCHEMA_DIR
        if manifest.get('preview_approved') is not False or manifest.get('publication_ready') is not False:
            errors.append('dossier_cannot_grant_approval')
        jsonschema.validate(manifest,json.loads((SCHEMA_DIR/'project_manifest_r6.schema.json').read_text(encoding='utf-8')))
        expected=set()
        for row in manifest.get('files',[]):
            logical=_logical(row['path'])
            if str(logical) in expected:
                errors.append('duplicate_file_reference:'+str(logical))
            expected.add(str(logical))
            file=_safe_ancestors(root/str(logical))
            if not file.is_relative_to(root) or not file.is_file() or file.stat().st_size!=row['bytes'] or file_hash(file)!=row['sha256']:
                errors.append('checksum_or_path_mismatch:'+str(logical))
        actual=set()
        for p in root.rglob('*'):
            _safe_ancestors(p)
            if p.is_file() and p!=manifest_path:
                actual.add(p.relative_to(root).as_posix())
        if expected!=actual:
            errors.append('project_file_set_mismatch')
        if not manifest.get('files'):
            errors.append('project_file_inventory_empty')
        package=root/'06_SEGUNDA_CURADORIA/SECOND_CURATION_READY.zip'
        if manifest['state'] in {'READY_FOR_REVIEW','PARTIAL'}:
            if manifest.get('pdf_status')!='GENERATED' or not package.is_file():
                errors.append('completed_dossier_missing_package_or_pdf')
            else:
                from .second_curation_export import snapshot_core_package
                raw,_=snapshot_core_package(package)
                if hashlib.sha256(raw).hexdigest()!=manifest['package_sha256']:
                    errors.append('project_package_sha256_mismatch')
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    source=json.loads(archive.read('source/metadata.json'))
                    package_manifest=json.loads(archive.read('SECOND_CURATION_MANIFEST.json'))
                    candidates=json.loads(archive.read('editorial/candidate_catalog.json')).get('candidates') or []
                if (source.get('sha256')!=manifest['source_sha256'] or source.get('duration')!=manifest['source_duration'] or
                        (source.get('source') or {}).get('id')!=manifest.get('video_id') or package_manifest.get('run_id')!=manifest.get('package_run_id')):
                    errors.append('project_package_source_or_revision_mismatch')
                if manifest['state']=='READY_FOR_REVIEW' and package_manifest.get('workflow',{}).get('review_ready') is not True:
                    errors.append('project_review_state_exceeds_package_gate')
                required={'00_RESUMO/GUIA_EDITORIAL_COMPLETO.pdf','00_RESUMO/RESUMO_EXECUTIVO.pdf',
                    '00_RESUMO/MELHORES_MOMENTOS.json','00_RESUMO/INDICE_GERAL.html',
                    '01_TRANSCRICAO/TRANSCRICAO_COMPLETA.pdf','01_TRANSCRICAO/transcricao.txt','01_TRANSCRICAO/transcricao.srt',
                    '01_TRANSCRICAO/segmentos.jsonl','01_TRANSCRICAO/palavras.jsonl','01_TRANSCRICAO/lacunas_e_revisoes.json',
                    '06_SEGUNDA_CURADORIA/HANDOFF_MASTER.json','07_RELATORIOS_TECNICOS/limitations.json',
                    '07_RELATORIOS_TECNICOS/provenance.json','07_RELATORIOS_TECNICOS/checksums.sha256'}
                errors.extend('missing_required_project_artifact:'+name for name in sorted(required-actual))
                by_id={r['candidate_id']:r for r in candidates}
                briefings=list((root/'03_REELS').glob('*/briefing.json'))
                seen=[]
                for briefing in briefings:
                    candidate=json.loads(briefing.read_text(encoding='utf-8'))
                    cid=candidate.get('candidate_id')
                    seen.append(cid)
                    if candidate!=by_id.get(cid):
                        errors.append('project_candidate_disagrees_with_package:'+str(cid))
                    for name in ('RELATORIO_REEL.pdf','camera_plan.json','transcricao.txt','transcricao.srt','words.json','title_suggestions.json'):
                        if not (briefing.parent/name).is_file():
                            errors.append('project_reel_missing:'+str(cid)+':'+name)
                if len(seen)!=len(set(seen)) or set(seen)!=set(by_id) or manifest.get('candidate_count')!=len(candidates):
                    errors.append('project_candidate_count_or_id_set_mismatch')
                for path in root.rglob('*.pdf'):
                    with path.open('rb') as handle:
                        if handle.read(5)!=b'%PDF-':
                            errors.append('project_pdf_header_invalid:'+path.relative_to(root).as_posix())
        return {'status':'valid' if not errors else 'failed','errors':errors,'state':manifest.get('state'),
                'verified_files':len(expected),'publication_ready':False}
    except (OSError,ValueError,KeyError,TypeError, jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        return {'status':'failed','errors':errors+['project_read_failure:'+type(exc).__name__],'publication_ready':False}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description='Dossiê R6 sem executar modelos ou abrir mídia original.')
    parser.add_argument('--package',help='ZIP validado da segunda curadoria')
    parser.add_argument('--destination',help='Raiz escolhida; padrão pasta Vídeos do Windows')
    parser.add_argument('--verify-project',help='Verificar integridade somente leitura')
    parser.add_argument('--analysis',help='Análise compatível para incluir todas as palavras canônicas')
    parser.add_argument('--title',help='Título editorial fornecido pelo usuário; preserva título original nos metadados')
    parser.add_argument('--rebuild-package',help='Reconstruir somente ZIP a partir de evidências salvas')
    parser.add_argument('--reuse-visuals',help='ZIP validado da mesma fonte/intervalos para reaproveitar contact sheets')
    parser.add_argument('--rebuild-project-index',help='Raiz de análises; inventário somente leitura')
    args=parser.parse_args(argv)
    if args.verify_project:
        result=verify_project_export(args.verify_project)
    elif args.rebuild_project_index:
        from .storage import list_projects
        result={'schema_version':'1.0','projects':list_projects(args.rebuild_project_index),
                'read_only':True,'created_at':datetime.now(timezone.utc).isoformat()}
        if args.destination:
            output=_safe_ancestors(args.destination)
            output.mkdir(parents=True,exist_ok=True)
            path=output/('PROJECT_INDEX_'+uuid.uuid4().hex+'.json')
            _json(path,result)
            result={'path':str(path),'project_count':len(result['projects']),'read_only':True}
    elif args.rebuild_package:
        from .compact_artifacts import load_analysis_artifacts
        from .second_curation_export import build_core_package
        analysis=load_analysis_artifacts(args.rebuild_package)
        base=_safe_ancestors(args.destination or videos_directory()/'LDPORTO_VIDEO_ANALYZER')
        output=base/('PACKAGE_REVISION_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex[:6])
        output.mkdir(parents=True,exist_ok=False)
        result=build_core_package(analysis,source=None,output_dir=output,
            cfg={'include_candidate_previews':False,'second_curation_visual_candidate_limit':0,
                 'reuse_verified_visuals_package':args.reuse_visuals,'narrative_handoff_enabled':True},
            progress=lambda stage,**kw:print(stage+' '+str(kw.get('substage','')),flush=True))
        result['execution_scope']='package_rebuild_only_no_new_audiovisual_inference'
        _json(output/'REBUILD_RECEIPT.json',result)
        result={key:result.get(key) for key in ('path','state','bytes','candidate_count','shortlist_count','visual_count',
                    'zip_sha256','execution_scope','expensive_inference_executed')}
    elif args.package:
        analysis=None
        if args.analysis:
            from .compact_artifacts import load_analysis_artifacts
            analysis=load_analysis_artifacts(args.analysis,collections=['transcript_segments','words','scenes','camera_director_timeline'])
        result=export_project(args.package,args.destination,analysis=analysis,display_title=args.title,
            progress=lambda s,c,t:print('%s: %d/%d'%(s,c,t),flush=True))
    else:
        parser.error('Informe --package ou --verify-project.')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result.get('status')=='failed' else 0


if __name__=='__main__':
    raise SystemExit(main())
