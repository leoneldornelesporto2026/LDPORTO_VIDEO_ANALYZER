"""Small native local launcher; runs the same CLI in a child process."""
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import json
import time
import uuid
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import webbrowser

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/"src"))

from ldporto.config import load_config
from ldporto.progress import WeightedProgress, STAGE_WEIGHTS, STAGE_LABELS, EVENT_PREFIX, human_duration
from ldporto.core import scrub


def inspect_media_selection(source, *, root, local_path='', expected_sha256='', download_config=None):
    """Read-only local resolution; this GUI helper never invokes a downloader."""
    from ldporto.media import youtube_id
    from ldporto.media_library import resolve_existing_media
    cfg = download_config or {}
    remote = source.startswith(('http://', 'https://'))
    if remote:
        video_id = youtube_id(source)
        return resolve_existing_media(video_id, expected_sha256=expected_sha256 or cfg.get('expected_sha256'),
            explicit_path=local_path or None, project_reference=cfg.get('media_reference'),
            library_root=cfg.get('media_library_root'), legacy_root=Path(root)/'input/youtube')
    selected = Path(source).expanduser()
    if not selected.is_file():
        raise ValueError('Arquivo local ausente; selecione o original.')
    return resolve_existing_media('LOCAL_SELECTION', expected_sha256=expected_sha256 or None,
                                  explicit_path=selected)


def media_selection_text(result):
    if result.get('status') == 'FOUND_VERIFIED':
        origins = {'explicit_selection': 'arquivo escolhido', 'project_reference': 'referência do projeto',
                   'media_library': 'biblioteca', 'legacy_input': 'arquivo existente do YouTube'}
        return ('Mídia encontrada: ' + origins.get(result.get('origin'), 'arquivo registrado') +
                ' · download desnecessário · SHA256 ' + str(result.get('source_sha256') or '') +
                ' · conteúdo será verificado antes do processamento.')
    if result.get('status') == 'BLOCKED':
        return 'Mídia bloqueada: ' + str(result.get('error') or 'falha na verificação local')
    return ('Mídia não encontrada ou incompatível. Selecione o original local ou autorize o download para este link.')


def media_cli_options(source, *, allow_download=False, local_path='', expected_sha256=''):
    """Explicit session choices; a local original preserves the source YouTube ID."""
    options = []
    if source.startswith(('http://', 'https://')):
        if local_path:
            options += ['--media-path', local_path]
        if allow_download:
            options.append('--allow-download')
    if expected_sha256:
        options += ['--media-sha256', expected_sha256]
    return options


def body_diagnostic_text(report):
    """Passive checks never replace proof of a real four-frame inference."""
    reason = report.get('model_validation_reason')
    return ('Diagnostico passivo (nao executa frames):\nSolicitado: ' + str(report.get('configured_model')) +
            '\nResolvido: ' + str(report.get('resolved_model_path')) +
            '\nUltralytics: ' + str(report.get('ultralytics_version') or 'nao instalado') +
            '\nArquivo: ' + str(reason or 'presente; carregamento ainda nao testado') +
            '\nNOT_READY | modelo nao carregado | inferencia nao executada')


def body_execution_text(report):
    measured = lambda value: 'sim' if value is True else 'nao' if value is False else 'nao medido'
    return ('Corpos: backend real=' + str(report.get('actually_executed_backend') or 'nao medido') +
            ' | qualidade=' + str(report.get('quality') or 'nao medida') +
            ' | chamadas=' + str(report.get('inference_calls') or 'nao medidas') +
            ' | YOLO carregado=' + measured(report.get('model_loaded')) +
            ', inferencia=' + measured(report.get('inference_executed')) +
            ' | ' + str(report.get('readiness') or 'NOT_READY') +
            (' | motivo=' + str(report.get('fallback_reason') or report.get('body_limit_reason'))
             if report.get('fallback_reason') or report.get('body_limit_reason') else ''))


def editorial_triage_text(editorial):
    """Human triage and automatic selection have separate, recorded denominators."""
    summary = editorial.get('human_review_summary') if isinstance(editorial, dict) else None
    if not isinstance(summary, dict):
        return None
    def count(value):
        return str(value) if type(value) is int and value >= 0 else 'nao medido'
    text = ('Triagem humana: ' + count(summary.get('human_review_queue_count')) +
            ' candidatos | revisao editorial provisoria: ' + count(summary.get('provisional_human_review_count')) +
            '\nShortlist automatica: ' + count(editorial.get('shortlist_count')) +
            ' | triagem nao aprova cortes, previa ou publicacao.')
    reasons = summary.get('recorded_local_gate_counts')
    if isinstance(reasons, dict):
        labels = {'duration_outside_target_without_exception': 'duracao fora do alvo sem excecao comprovada',
                  'below_editorial_quality_floor': 'score abaixo do piso editorial',
                  'missing_required_score:hook': 'hook nao medido',
                  'missing_required_score:standalone_clarity': 'clareza independente nao medida',
                  'answer_or_payoff_unresolved': 'resposta ou conclusao pendente',
                  'topic_boundary_crossed': 'fronteira de topico cruzada'}
        measured = sorted(((key, value) for key, value in reasons.items()
                           if isinstance(key, str) and type(value) is int and value > 0),
                          key=lambda item: (-item[1], item[0]))[:3]
        if measured:
            text += '\nGates locais (contagens se sobrepoem): ' + '; '.join(
                labels.get(key, key) + ': ' + str(value) for key, value in measured)
    text += '\nFila com texto, contexto, audio e tarefas: editorial/human_review_queue.json'
    return text


class App:
    def __init__(self, window):
        self.window, self.proc, self.messages, self.output_folder = window, None, queue.Queue(), None
        window.title("L.D.PORTO VIDEO ANALYZER")
        window.geometry("1100x900")
        window.configure(bg="#17171b")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#17171b")
        style.configure("TLabel", background="#17171b", foreground="#eeeeee")
        style.configure("TCheckbutton", background="#17171b", foreground="#eeeeee")
        # Generated by GitHub Copilot - Oct-05-2026
        style.map('TButton',background=[('focus','#4c4c59')],foreground=[('focus','#ffffff')])
        style.map('TCheckbutton',background=[('focus','#3c3c49')])
        outer = ttk.Frame(window, padding=24)
        self.configuration_frame = outer
        self.in_execution = False
        self.closing_requested = False
        self.progress_model = WeightedProgress()
        self.package_path = None
        self.project_path = None
        self.project_busy = False
        self.project_cancel = threading.Event()
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="L.D.PORTO · VIDEO ANALYZER", font=("Segoe UI", 24, "bold"),
                  foreground="#fb505a").pack(anchor="w")
        ttk.Label(outer, text="Vídeo inteiro → transcrição → pessoas → timeline → insights",
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(3, 22))
        ttk.Label(outer, text="Arquivo local ou link do YouTube").pack(anchor="w")
        line = ttk.Frame(outer)
        line.pack(fill="x", pady=6)
        self.source = tk.StringVar()
        ttk.Entry(line, textvariable=self.source).pack(side="left", fill="x", expand=True)
        ttk.Button(line, text="Selecionar vídeo", command=self.select).pack(side="left", padx=(8, 0))
        self.media_busy, self.media_generation, self.media_check_result = False, 0, None
        self.allow_download = tk.BooleanVar(value=False)
        self.local_original, self.media_sha256 = tk.StringVar(), tk.StringVar()
        self.media_status = tk.StringVar(value='Mídia: selecione o arquivo ou verifique o link para reutilizar um original existente.')
        media_row = ttk.Frame(outer)
        media_row.pack(fill='x', pady=3)
        ttk.Button(media_row, text='Verificar mídia local', command=self.verify_media).pack(side='left')
        ttk.Button(media_row, text='Original local para este link', command=self.select_media_original).pack(side='left', padx=8)
        ttk.Checkbutton(media_row, text='Autorizar download se o original estiver ausente',
                        variable=self.allow_download).pack(side='left', padx=8)
        ttk.Entry(outer, textvariable=self.local_original, state='readonly').pack(fill='x')
        hash_row = ttk.Frame(outer)
        hash_row.pack(fill='x', pady=3)
        ttk.Label(hash_row, text='SHA256 esperado (opcional)').pack(side='left')
        ttk.Entry(hash_row, textvariable=self.media_sha256).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Label(outer, textvariable=self.media_status, wraplength=980).pack(anchor='w')
        self.source.trace_add('write', lambda *_: self.change_media_selection(clear_original=True))
        self.local_original.trace_add('write', lambda *_: self.change_media_selection())
        self.media_sha256.trace_add('write', lambda *_: self.change_media_selection())
        line2 = ttk.Frame(outer)
        line2.pack(fill="x", pady=8)
        ttk.Label(line2, text="Modelo ASR").pack(side="left")
        self.model = tk.StringVar(value="large-v3")
        ttk.Combobox(line2, textvariable=self.model, values=["large-v3", "medium", "small", "turbo", "tiny"],
                     width=15, state="readonly").pack(side="left", padx=8)
        ttk.Label(line2, text="Dispositivo").pack(side="left", padx=(16, 0))
        self.device = tk.StringVar(value="cuda" if shutil.which("nvidia-smi") else "auto")
        ttk.Combobox(line2, textvariable=self.device, values=["auto", "cpu", "cuda"],
                     width=10, state="readonly").pack(side="left", padx=8)
        try:
            sem_cfg = load_config(ROOT/"config"/"config.yaml")["semantic_analysis"]
        except Exception:
            sem_cfg = {"backend": "ollama", "model": "qwen3:8b", "profile": "max"}
        self.ollama = tk.BooleanVar(value=sem_cfg.get("backend") == "ollama")
        ttk.Checkbutton(outer, text="Usar Ollama local para análise semântica + revisão editorial global",
                        variable=self.ollama).pack(anchor="w", pady=4)
        ollama_row = ttk.Frame(outer)
        ollama_row.pack(fill="x", pady=4)
        ttk.Label(ollama_row, text="Modelo Ollama").pack(side="left")
        self.ollama_model = tk.StringVar(value=sem_cfg.get("model") or "qwen3:8b")
        self.ollama_combo = ttk.Combobox(ollama_row, textvariable=self.ollama_model,
                                         values=["qwen3:8b", "qwen3:14b", "qwen3:30b"], width=24)
        self.ollama_combo.pack(side="left", padx=8)
        ttk.Label(ollama_row, text="Perfil").pack(side="left", padx=(12, 0))
        self.ollama_profile = tk.StringVar(value=sem_cfg.get("profile") or "max")
        ttk.Combobox(ollama_row, textvariable=self.ollama_profile,
                     values=["max", "balanced", "fast"], width=12, state="readonly").pack(side="left", padx=8)
        ttk.Button(ollama_row, text="Atualizar modelos", command=self.refresh_ollama).pack(side="left", padx=4)
        ttk.Button(ollama_row, text="Configurar Ollama", command=self.configure_ollama).pack(side="left", padx=4)
        self.ollama_status = tk.StringVar(value="Ollama: verificando…")
        ttk.Label(outer, textvariable=self.ollama_status, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))
        try:
            camera_cfg = load_config(ROOT/"config"/"config.yaml")["camera_director"]
        except Exception:
            camera_cfg = {"enabled": True, "profile": "natural"}
        camera_row = ttk.Frame(outer)
        camera_row.pack(fill="x", pady=4)
        self.camera_enabled = tk.BooleanVar(value=camera_cfg.get("enabled", True))
        ttk.Checkbutton(camera_row, text="Camera Director", variable=self.camera_enabled).pack(side="left")
        self.camera_profile = tk.StringVar(value=camera_cfg.get("profile", "natural"))
        ttk.Combobox(camera_row, textvariable=self.camera_profile, state="readonly", width=18,
                     values=["natural", "podcast", "dynamic_short", "documentary", "conservative"]).pack(side="left", padx=8)
        self.camera_advanced = ttk.Frame(outer)
        self.camera_hold = tk.StringVar()
        self.camera_zoom = tk.StringVar()
        ttk.Label(self.camera_advanced, text="Hold mínimo (s; vazio = perfil)").pack(side="left")
        ttk.Entry(self.camera_advanced, textvariable=self.camera_hold, width=7).pack(side="left", padx=6)
        ttk.Label(self.camera_advanced, text="Zoom máximo (vazio = perfil)").pack(side="left")
        ttk.Entry(self.camera_advanced, textvariable=self.camera_zoom, width=7).pack(side="left", padx=6)
        ttk.Button(camera_row, text="Configuração avançada", command=self.toggle_camera_settings).pack(side="left")
        ttk.Button(camera_row, text="Reprocessar só câmera", command=self.resume_camera).pack(side="left", padx=8)
        smart_row = ttk.Frame(outer)
        smart_row.pack(fill='x', pady=4)
        self.smart_zoom = tk.BooleanVar(value=(camera_cfg.get('smart_zoom') or {}).get('enabled', True))
        self.smart_profile = tk.StringVar(value=(camera_cfg.get('smart_zoom') or {}).get('profile', 'natural'))
        ttk.Checkbutton(smart_row, text='Smart Zoom', variable=self.smart_zoom).pack(side='left')
        ttk.Combobox(smart_row, textvariable=self.smart_profile, values=['conservative', 'natural', 'dynamic'], width=18, state='readonly').pack(side='left', padx=8)
        self.include_previews = tk.BooleanVar(value=False)
        ttk.Checkbutton(smart_row, text='Previews no pacote de midia separado', variable=self.include_previews).pack(side='left', padx=10)
        try:
            social_cfg = load_config(ROOT/"config"/"config.yaml")["social_output"]
        except Exception:
            social_cfg = {"aspect_ratio":"9:16","caption_preset":"auto","content_mode":"auto","caption_font":"Arial","caption_size_scale":1.0,
                          "caption_primary_color":"#FFFFFF","caption_highlight_color":"#F4FF26","stories":{"max_stories":12}}
        social_row = ttk.Frame(outer)
        social_row.pack(fill='x', pady=4)
        ttk.Label(social_row, text='Saída social').pack(side='left')
        self.social_aspect = tk.StringVar(value=social_cfg.get('aspect_ratio','9:16'))
        ttk.Combobox(social_row, textvariable=self.social_aspect, values=['9:16','4:5','1:1','16:9'], width=8, state='readonly').pack(side='left', padx=6)
        self.caption_preset = tk.StringVar(value=social_cfg.get('caption_preset','auto'))
        ttk.Combobox(social_row, textvariable=self.caption_preset,
                     values=['auto','no_caption','simple','karaoke','popline','deep_diver','think_media','pod_p','news','show_highlight','clean_bold','high_contrast','soft_subtitle','creator_style'],
                     width=18, state='readonly').pack(side='left', padx=6)
        self.content_mode = tk.StringVar(value=social_cfg.get('content_mode','auto'))
        ttk.Combobox(social_row, textvariable=self.content_mode,
                     values=['auto','show','entrevista','podcast','programa_tv','reacao','educativo','humor','noticias'],
                     width=14, state='readonly').pack(side='left', padx=6)
        ttk.Label(social_row, text='Stories').pack(side='left', padx=(10,2))
        self.story_count = tk.IntVar(value=int((social_cfg.get('stories') or {}).get('max_stories',12)))
        ttk.Spinbox(social_row, from_=1, to=30, textvariable=self.story_count, width=4).pack(side='left')
        social_row2 = ttk.Frame(outer)
        social_row2.pack(fill='x', pady=4)
        ttk.Label(social_row2, text='Fonte legenda').pack(side='left')
        self.caption_font = tk.StringVar(value=social_cfg.get('caption_font','Arial'))
        ttk.Combobox(social_row2, textvariable=self.caption_font, values=['Arial','Segoe UI','Montserrat','Inter','Roboto','Poppins','Impact'], width=18).pack(side='left', padx=6)
        ttk.Label(social_row2, text='Tamanho').pack(side='left', padx=(10,2))
        self.caption_size = tk.DoubleVar(value=float(social_cfg.get('caption_size_scale',1.0)))
        ttk.Spinbox(social_row2, from_=0.6, to=2.0, increment=0.1, textvariable=self.caption_size, width=5).pack(side='left')
        self.caption_color = tk.StringVar(value=social_cfg.get('caption_primary_color','#FFFFFF'))
        self.highlight_color = tk.StringVar(value=social_cfg.get('caption_highlight_color','#F4FF26'))
        ttk.Button(social_row2, text='Cor texto', command=lambda: self.pick_social_color(self.caption_color)).pack(side='left', padx=(10,3))
        ttk.Button(social_row2, text='Destaque', command=lambda: self.pick_social_color(self.highlight_color)).pack(side='left', padx=3)
        ttk.Button(social_row2, text='Configurar saída social', command=self.social_settings).pack(side='left', padx=8)
        ttk.Label(social_row2, text='Stories = vários momentos independentes.', font=('Segoe UI',9)).pack(side='left', padx=6)
        self.camera_summary = tk.StringVar(value="Camera Director: aguardando análise")
        ttk.Label(outer, textvariable=self.camera_summary, font=("Segoe UI", 9), wraplength=980).pack(anchor="w")
        self.force = tk.BooleanVar(value=False)
        ttk.Checkbutton(outer, text="Reprocessar (ignorar cache)", variable=self.force).pack(anchor="w", pady=4)
        # Generated by GitHub Copilot - Oct-05-2026
        capability_cfg = load_config(ROOT/"config"/"config.yaml")
        self.ocr_busy = False
        self.ocr_generation = 0
        self.ocr_enabled = tk.BooleanVar(value=capability_cfg['ocr']['enabled'])
        self.ocr_languages = tk.StringVar(value=capability_cfg['ocr']['languages'])
        self.ocr_command = tk.StringVar(value=capability_cfg['ocr']['tesseract_cmd'] or '')
        self.ocr_status = tk.StringVar(value='Não testado' if self.ocr_enabled.get() else 'Desligado: visual comercial not_measured / requires_review')
        ocr_row = ttk.Frame(outer)
        ocr_row.pack(fill='x', pady=4)
        ttk.Checkbutton(ocr_row, text='OCR comercial / texto na tela (Tesseract)', variable=self.ocr_enabled,
                        command=lambda: self.change_ocr('enabled')).pack(side='left')
        ttk.Label(ocr_row, text='Idiomas').pack(side='left', padx=6)
        languages = ttk.Combobox(ocr_row, textvariable=self.ocr_languages, values=['por+eng', 'por', 'eng'], state='readonly', width=9)
        languages.pack(side='left')
        languages.bind('<<ComboboxSelected>>', lambda event: self.change_ocr('languages'))
        ttk.Button(ocr_row, text='Verificar OCR', command=self.verify_ocr).pack(side='left', padx=6)
        ttk.Button(ocr_row, text='Smoke sintético', command=lambda: self.verify_ocr(smoke=True)).pack(side='left')
        ocr_path_row = ttk.Frame(outer)
        ocr_path_row.pack(fill='x')
        ttk.Entry(ocr_path_row, textvariable=self.ocr_command, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(ocr_path_row, text='Selecionar Tesseract.exe', command=self.select_ocr_command).pack(side='left', padx=6)
        ttk.Button(ocr_path_row, text='Usar PATH', command=self.clear_ocr_command).pack(side='left')
        ttk.Label(outer, textvariable=self.ocr_status, wraplength=980).pack(anchor='w')
        ttk.Label(outer, text='Windows: selecione tesseract.exe; tessdata precisa de por.traineddata/eng.traineddata conforme idiomas, legíveis e com permissão de execução. O app não instala. Pronto = configuração; smoke = fixture, não vídeo.',
                  wraplength=980, font=('Segoe UI', 9)).pack(anchor='w')
        capability_row = ttk.Frame(outer)
        capability_row.pack(fill="x", pady=4)
        self.diarization = tk.BooleanVar(value=capability_cfg["diarization"]["enabled"])
        self.vision = tk.BooleanVar(value=capability_cfg["vision"]["enabled"])
        ttk.Checkbutton(capability_row, text="Diarizacao", variable=self.diarization).pack(side="left")
        ttk.Checkbutton(capability_row, text="Visao / active speaker", variable=self.vision).pack(side="left", padx=12)
        ttk.Button(capability_row, text="Detector corporal local", command=self.body_settings).pack(side="left")
        self.body_status = tk.StringVar(value='Corpos: ' + capability_cfg['vision']['body_backend'] +
            ' / ' + capability_cfg['vision']['yolo_device'] + ' | NOT_READY: execução não comprovada')
        ttk.Label(outer, textvariable=self.body_status, wraplength=980).pack(anchor='w')
        self.preflight_status = tk.StringVar(value="Preflight: nao executado")
        ttk.Label(outer, textvariable=self.preflight_status, wraplength=980).pack(anchor="w")
        self.inference_smoke_gate = tk.BooleanVar(value=False)
        ttk.Checkbutton(outer, text='Canario de inferencia antes de analisar (opt-in; falha bloqueia)',
                        variable=self.inference_smoke_gate).pack(anchor='w')
        self.inference_smoke_status = tk.StringVar(value='Model load verified: nao medido | Actual inference executed: nao medido')
        ttk.Label(outer, textvariable=self.inference_smoke_status, wraplength=980).pack(anchor='w')
        ttk.Button(outer, text='Executar canario sintetico local (30s/teste, 120s total)',
                   command=self.diagnose_inference).pack(anchor='w')
        token_row = ttk.Frame(outer)
        token_row.pack(fill="x", pady=6)
        ttk.Label(token_row, text="HF_TOKEN (somente nesta sessao)").pack(side="left")
        self.hf_token = tk.StringVar(value=os.environ.get("HF_TOKEN", ""))
        ttk.Entry(token_row, textvariable=self.hf_token, show="*", width=42).pack(side="left", padx=8)
        ttk.Label(outer, text="Large-v3 prioriza fidelidade. Em NVIDIA, use CUDA; falha de GPU nao cai silenciosamente para CPU."
                  "\nDiarização exige extras + HF_TOKEN. Veja README.md.",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=10)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=10)
        self.start_button = ttk.Button(buttons, text="ANALISAR", command=self.start)
        self.start_button.pack(side="left")
        ttk.Button(buttons, text="Diagnóstico", command=self.diagnose).pack(side="left", padx=8)
        ttk.Button(buttons, text="Recursos S10", command=self.diagnose_s10).pack(side='left', padx=5)
        if os.name == "nt":
            ttk.Button(buttons, text="Reparar GPU", command=self.repair_gpu).pack(side="left", padx=4)
        ttk.Button(buttons, text="Abrir resultados", command=self.open_results).pack(side="left")
        ttk.Button(buttons, text="Modelos visuais", command=self.visual_models).pack(side="left", padx=4)
        ttk.Button(buttons, text="Gerenciar espaço", command=self.clean_heavy).pack(side="left", padx=4)
        ttk.Button(buttons, text="Interromper", command=self.stop).pack(side="right")
        self.status = tk.StringVar(value="Prontidao ainda nao verificada. Diagnostico verifica recursos habilitados.")
        self.auto_project_export = tk.BooleanVar(value=False)
        ttk.Checkbutton(outer, text='Exportar projeto completo para Vídeos ao finalizar (PDFs e evidências)',
                        variable=self.auto_project_export).pack(anchor='w')
        ttk.Button(outer, text='Central de resultados / reabrir projeto', command=self.open_results_center).pack(anchor='w')
        ttk.Label(outer, textvariable=self.status).pack(anchor="w", pady=(8, 3))
        self.warning_count=0
        self.run_state=tk.StringVar(value='Etapa: aguardando | Avisos: 0 | Qualidade: nao medida | Cache: nao verificado')
        ttk.Label(outer,textvariable=self.run_state,wraplength=980).pack(anchor='w')
        self.log = tk.Text(outer, bg="#222229", fg="#eeeeee", insertbackground="white",
                           wrap="word", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self.build_execution_screens()
        window.after(150, self.poll)
        window.after(500, self.refresh_ollama)
        window.protocol("WM_DELETE_WINDOW", self.close)

    def body_settings(self):
        from ldporto.config import load_config, save_body_options
        from ldporto.body_model_paths import body_model_diagnostics
        cfg = load_config(ROOT/'config'/'config.yaml')['vision']
        dialog = tk.Toplevel(self.window)
        dialog.title('Detector corporal opcional — arquivo local')
        backend = tk.StringVar(value=cfg['body_backend'])
        model = tk.StringVar(value=cfg['yolo_model'])
        device = tk.StringVar(value=cfg['yolo_device'])
        diagnostic = ttk.Label(dialog, text=body_diagnostic_text(body_model_diagnostics(cfg, root=ROOT)), wraplength=650)
        diagnostic.pack(anchor='w', pady=8)
        last_smoke = self.body_status.get().strip()
        if 'INFERENCE_EXECUTED' in last_smoke:
            ttk.Label(dialog, text='Ultimo teste explicito nesta sessao: ' + last_smoke +
                      '\nNao altera diagnostico passivo nem homologa qualidade.', wraplength=650).pack(anchor='w')
        def refresh_diagnostic():
            options = {**cfg, 'body_backend': backend.get(), 'yolo_model': model.get(), 'yolo_device': device.get()}
            diagnostic.configure(text=body_diagnostic_text(body_model_diagnostics(options, root=ROOT)))
        ttk.Label(dialog, text='Backend').pack(anchor='w')
        ttk.Combobox(dialog, textvariable=backend, values=['auto', 'hog', 'yolo'], state='readonly').pack(fill='x')
        ttk.Entry(dialog, textvariable=model, state='readonly', width=70).pack(fill='x')
        def select_model():
            path = filedialog.askopenfilename(parent=dialog, filetypes=[('Pesos locais confiáveis', '*.pt')])
            if path:
                model.set(path)
                refresh_diagnostic()
        ttk.Button(dialog, text='Selecionar arquivo .pt local', command=select_model).pack()
        ttk.Label(dialog, text='Device: CPU padrão; CUDA exige VRAM livre e não reserva GPU.').pack()
        ttk.Combobox(dialog, textvariable=device, values=['cpu', 'cuda'], state='readonly').pack()
        ttk.Button(dialog, text='Atualizar diagnostico passivo', command=refresh_diagnostic).pack()
        ttk.Button(dialog, text='Testar 4 quadros de video local',
                   command=lambda: self.run_body_smoke(model.get(), device.get(), parent=dialog)).pack()
        ttk.Label(dialog, text='Sem instalação/download. Leia docs/YOLO_LOCAL_57.md e requirements/yolo.txt.\n'
            'YOLO não comprova identidade/active speaker; produção exige revisão de licença.', wraplength=560).pack()
        def save():
            if self.runtime_busy():
                messagebox.showinfo('Em execucao', 'Aguarde o processamento atual para salvar escolhas.', parent=dialog)
                return
            try:
                result = save_body_options(ROOT/'config'/'config.yaml', {
                    'body_backend': backend.get(), 'yolo_model': model.get(), 'yolo_device': device.get()})
                choice = result['vision']
                self.body_status.set('Corpos: ' + choice['body_backend'] + ' / ' + choice['yolo_device'] +
                    ' | NOT_READY: consulte body_backend no preflight e body_backend_execution após execução')
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror('Configuração corporal', str(exc), parent=dialog)
        ttk.Button(dialog, text='Salvar escolhas', command=save).pack()
        ttk.Button(dialog, text='Cancelar', command=dialog.destroy).pack()

    def runtime_busy(self):
        proc = getattr(self, 'proc', None)
        return bool(getattr(self, 'project_busy', False) or getattr(self, 'smoke_busy', False) or
                    getattr(self, 'ocr_busy', False) or getattr(self, 'media_busy', False) or proc and proc.poll() is None)

    def run_body_smoke(self, model=None, device=None, parent=None):
        """Explicit four-frame subprocess; no pipeline, download or GUI model import."""
        if self.runtime_busy():
            messagebox.showinfo('Em execucao', 'Aguarde o processamento atual antes do teste corporal.', parent=parent)
            return
        from ldporto.config import load_config
        from ldporto.body_model_paths import body_model_diagnostics
        cfg = load_config(ROOT/'config'/'config.yaml')['vision']
        cfg.update(yolo_model=model or cfg['yolo_model'], yolo_device=device or cfg['yolo_device'])
        diagnostic = body_model_diagnostics(cfg, root=ROOT)
        if diagnostic.get('model_validation_reason') or not diagnostic.get('ultralytics_available'):
            self.body_status.set(body_diagnostic_text(diagnostic))
            messagebox.showinfo('Detector corporal NOT_READY', body_diagnostic_text(diagnostic), parent=parent)
            return
        selected = filedialog.askopenfilename(parent=parent, title='Video local para teste corporal curto (4 quadros)',
                                              filetypes=[('Videos locais', '*.mp4 *.mkv *.webm *.mov *.avi')])
        if not selected:
            return
        video = Path(selected).resolve()
        if not video.is_file():
            messagebox.showerror('Teste corporal', 'Selecione um arquivo de video local existente.', parent=parent)
            return
        if self.runtime_busy():
            return
        output = ROOT/'.cache'/'body_smoke'/uuid.uuid4().hex
        command = [sys.executable, '-u', str(ROOT/'scripts/dev/smoke_body_detector.py'),
                   '--video', str(video), '--output', str(output), '--config', str(ROOT/'config/config.yaml'),
                   '--model', cfg['yolo_model'], '--device', cfg['yolo_device']]
        self.body_smoke_busy = self.smoke_busy = True
        self.body_smoke_cancel = threading.Event()
        self.body_smoke_proc = None
        self.start_button.configure(state='disabled')
        self.body_status.set('Teste corporal explicito em andamento: 4 quadros; qualidade ainda nao homologada.')
        self.status.set('Testando detector corporal em video local...')
        def worker():
            result = {'output': str(output), 'report': {}, 'exit_code': None}
            process = None
            try:
                if self.body_smoke_cancel.is_set():
                    raise InterruptedError('body_smoke_cancelled')
                process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace',
                    env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', YOLO_AUTOINSTALL='false', YOLO_OFFLINE='true'),
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.body_smoke_proc = process
                if self.body_smoke_cancel.is_set():
                    process.terminate()
                stdout, _ = process.communicate(timeout=180)
                result.update(exit_code=process.returncode, log=scrub(stdout or ''))
                report_path = output/'result.json'
                if report_path.is_file():
                    report = json.loads(report_path.read_text(encoding='utf-8'))
                    if not isinstance(report, dict):
                        raise ValueError('Relatorio corporal deve ser objeto JSON.')
                    result.update(report=report, report_file_available=True)
            except Exception as exc:
                try:
                    if process is not None and process.poll() is None:
                        process.kill()
                        process.communicate()
                except OSError:
                    pass
                result['error'] = scrub(str(exc))
            result['cancelled'] = self.body_smoke_cancel.is_set()
            self.messages.put(('body_smoke_result', result))
        threading.Thread(target=worker, daemon=True).start()

    def handle_body_smoke_result(self, result):
        self.body_smoke_busy = self.smoke_busy = False
        self.body_smoke_proc = None
        self.start_button.configure(state='normal')
        report = result.get('report') if isinstance(result.get('report'), dict) else {}
        backend = report.get('backend') if isinstance(report.get('backend'), dict) else {}
        frames = report.get('frames') if isinstance(report.get('frames'), list) else []
        verified = (result.get('exit_code') == 0 and not result.get('cancelled') and backend.get('model_loaded') is True and
                    backend.get('inference_executed') is True and backend.get('inference_successful') is True and
                    backend.get('local_smoke_validated') is True and len(frames) == 4)
        status = 'INFERENCE_EXECUTED' if verified else 'NOT_READY'
        message = (status + ' | teste curto: ' + str(len(frames)) + ' quadros; qualidade nao homologada' +
                   (' | evidencia: ' + str(Path(result['output'])/'result.json') if result.get('report_file_available') else
                    ' | relatorio nao gerado; saida solicitada: ' + str(result.get('output'))))
        if not verified:
            message += ' | motivo: ' + str('interrompido' if result.get('cancelled') else result.get('error') or
                                          backend.get('fallback_reason') or report.get('error') or 'inferência nao comprovada')
        self.body_status.set(message)
        self.status.set('Teste corporal concluido: ' + status)

    def select(self):
        path = filedialog.askopenfilename(filetypes=[("Vídeos", "*.mp4 *.mkv *.webm *.mov *.avi"), ("Todos", "*.*")])
        if path:
            self.source.set(path)

    def change_media_selection(self, clear_original=False):
        self.media_generation += 1
        self.media_check_result = None
        if clear_original:
            self.allow_download.set(False)
            if self.local_original.get():
                self.local_original.set('')
        self.media_status.set('Mídia: seleção alterada; verificação local pendente.')

    def select_media_original(self):
        path = filedialog.askopenfilename(title='Original local correspondente ao link e ao SHA256',
            filetypes=[('Vídeos', '*.mp4 *.mkv *.webm *.mov *.avi'), ('Todos', '*.*')])
        if path:
            self.local_original.set(path)

    def media_options(self):
        return {'source': self.source.get().strip(), 'local_path': self.local_original.get().strip(),
                'expected_sha256': self.media_sha256.get().strip().lower()}

    def verify_media(self, start_after=False):
        if self.runtime_busy():
            return
        options, generation = self.media_options(), self.media_generation
        if not options['source']:
            self.media_status.set('Mídia: selecione um arquivo ou informe o link.')
            return
        self.media_busy = True
        self.start_button.configure(state='disabled')
        self.media_status.set('Mídia: verificando arquivos e SHA256; nenhum download em execução…')
        def worker():
            try:
                cfg = load_config(ROOT/'config'/'config.yaml').get('download') or {}
                result = inspect_media_selection(root=ROOT, download_config=cfg, **options)
            except (OSError, ValueError, TypeError) as exc:
                result = {'status': 'BLOCKED', 'error': scrub(exc), 'download_authorized': False}
            self.messages.put(('media_result', (generation, options, result, start_after)))
        threading.Thread(target=worker, daemon=True).start()

    def handle_media_result(self, value):
        generation, options, result, start_after = value
        self.media_busy = False
        self.start_button.configure(state='normal')
        if generation != self.media_generation or options != self.media_options():
            self.media_status.set('Mídia: seleção alterada; resultado anterior ignorado.')
            return
        self.media_check_result = (options, result)
        self.media_status.set(media_selection_text(result))
        permitted = (result.get('status') == 'FOUND_VERIFIED' or
            result.get('status') == 'OPERATOR_SELECTION_REQUIRED' and self.allow_download.get()
            and options['source'].startswith(('http://', 'https://')))
        if start_after and permitted and not getattr(self, 'closing_requested', False):
            self._start_checked()

    def build_execution_screens(self):
        self.execution_frame = ttk.Frame(self.window, padding=24)
        ttk.Label(self.execution_frame, text='L.D.PORTO VIDEO ANALYZER', font=('Segoe UI', 19, 'bold'), foreground='#fb505a').pack(anchor='w')
        self.execution_title = tk.StringVar(value='Processando')
        self.execution_metadata = tk.StringVar(value='')
        ttk.Label(self.execution_frame, textvariable=self.execution_title, font=('Segoe UI', 15, 'bold'), wraplength=920).pack(anchor='w', pady=(12, 3))
        ttk.Label(self.execution_frame, textvariable=self.execution_metadata).pack(anchor='w', pady=(0, 14))
        self.overall_text = tk.StringVar(value='Progresso geral: 0%')
        ttk.Label(self.execution_frame, textvariable=self.overall_text).pack(anchor='w')
        self.overall_bar = ttk.Progressbar(self.execution_frame, maximum=100)
        self.overall_bar.pack(fill='x', pady=(5, 14))
        self.stage_text = tk.StringVar(value='Preflight')
        ttk.Label(self.execution_frame, textvariable=self.stage_text, font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.stage_bar = ttk.Progressbar(self.execution_frame, maximum=100)
        self.stage_bar.pack(fill='x', pady=6)
        self.elapsed_text = tk.StringVar(value='Decorrido: <1m | ETA etapa: calculando... | ETA total: calculando...')
        self.next_stage_text = tk.StringVar(value='')
        ttk.Label(self.execution_frame, textvariable=self.elapsed_text, wraplength=920).pack(anchor='w', pady=4)
        ttk.Label(self.execution_frame, textvariable=self.next_stage_text).pack(anchor='w', pady=(0, 10))
        self.ocr_execution_status = tk.StringVar(value='OCR geral 13 / comercial 17c: não medidos')
        ttk.Label(self.execution_frame, textvariable=self.ocr_execution_status, wraplength=920).pack(anchor='w')
        stage_area = ttk.Frame(self.execution_frame)
        stage_area.pack(fill='both', expand=True)
        self.stage_tree = ttk.Treeview(stage_area, columns=('status', 'elapsed'), show='tree headings', height=12)
        self.stage_tree.heading('#0', text='Etapa')
        self.stage_tree.heading('status', text='Estado')
        self.stage_tree.heading('elapsed', text='Tempo')
        self.stage_tree.column('#0', width=430, stretch=True)
        self.stage_tree.column('status', width=150, stretch=False)
        self.stage_tree.column('elapsed', width=90, stretch=False)
        scrollbar = ttk.Scrollbar(stage_area, command=self.stage_tree.yview)
        self.stage_tree.configure(yscrollcommand=scrollbar.set)
        self.stage_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        for stage, label in STAGE_LABELS.items():
            self.stage_tree.insert('', 'end', iid=stage, text=label, values=('Pendente', ''))
        self.execution_log = tk.Text(self.execution_frame, height=5, bg='#222229', fg='#eeeeee', wrap='word', font=('Consolas', 9))
        self.execution_log.pack(fill='x', pady=10)
        self.execution_diagnostic = tk.StringVar(value='')
        ttk.Label(self.execution_frame, textvariable=self.execution_diagnostic, wraplength=920, foreground='#ffc857').pack(anchor='w')
        ttk.Button(self.execution_frame, text='Solicitar parada segura', command=self.stop).pack(anchor='e', pady=8)
        self.final_frame = ttk.Frame(self.window, padding=24)
        self.final_heading = tk.StringVar(value='Analise finalizada')
        ttk.Label(self.final_frame, textvariable=self.final_heading, font=('Segoe UI', 20, 'bold'), foreground='#fb505a').pack(anchor='w', pady=(0, 18))
        self.final_summary = tk.StringVar(value='')
        ttk.Label(self.final_frame, textvariable=self.final_summary, wraplength=920, font=('Segoe UI', 12), justify='left').pack(anchor='w', pady=12)
        ttk.Label(self.final_frame, textvariable=self.ocr_execution_status, wraplength=920).pack(anchor='w')
        self.final_readiness = tk.StringVar(value='')
        ttk.Label(self.final_frame, textvariable=self.final_readiness, justify='left', wraplength=920).pack(anchor='w', pady=12)
        self.final_package = tk.StringVar(value='Pacote indisponivel')
        ttk.Label(self.final_frame, textvariable=self.final_package, wraplength=920, font=('Consolas', 10), foreground='#70d6c8').pack(anchor='w', pady=16)
        final_buttons = ttk.Frame(self.final_frame)
        final_buttons.pack(fill='x', pady=12)
        ttk.Button(final_buttons, text='Abrir pasta', command=self.open_package_folder).pack(side='left')
        ttk.Button(final_buttons, text='Copiar caminho', command=self.copy_package_path).pack(side='left', padx=8)
        ttk.Button(final_buttons, text='Ver resumo', command=self.open_results).pack(side='left', padx=8)
        ttk.Button(final_buttons, text='Gerar plano Curator S9', command=self.prepare_curator_s9).pack(side='left', padx=8)
        ttk.Button(final_buttons, text='Ouvir/ver fila', command=self.open_review_queue).pack(side='left', padx=8)
        ttk.Button(final_buttons, text='Nova analise', command=self.new_analysis).pack(side='right')
        project_buttons = ttk.Frame(self.final_frame)
        project_buttons.pack(fill='x', pady=8)
        ttk.Button(project_buttons, text='Central de resultados', command=self.open_results_center).pack(side='left')
        ttk.Button(project_buttons, text='Exportar projeto completo para Vídeos', command=self.export_project_dossier).pack(side='left',padx=8)
        self.project_status = tk.StringVar(value='Dossiê: ainda não gerado; PDFs e vídeos finais têm estados separados.')
        ttk.Label(self.final_frame, textvariable=self.project_status, wraplength=970).pack(anchor='w')

    def show_execution(self):
        self.ocr_execution_status.set('OCR geral 13 / comercial 17c: solicitado' if self.ocr_enabled.get() else 'OCR geral 13 / comercial 17c: ignorados; not_measured / requires_review')
        self.configuration_frame.pack_forget()
        self.final_frame.pack_forget()
        self.execution_frame.pack(fill='both', expand=True)
        self.in_execution = True
        weights = dict(STAGE_WEIGHTS)
        if not self.ollama.get():
            weights['15_semantic'] = 2.
        if not self.vision.get():
            for stage in ('07_people_tracking', '08_person_reid', '09_person_motion', '10_active_speaker'):
                weights[stage] = 0.
        if not self.diarization.get():
            weights['05_diarization'] = 0.
        self.progress_model = WeightedProgress(weights)
        self.execution_title.set(self.source.get() or 'Processando evidencias salvas')
        self.execution_log.delete('1.0', 'end')
        self.execution_diagnostic.set('')

    def save_failure_diagnostic(self, code):
        """Persist a bounded, redacted GUI failure trace outside analysis checkpoints."""
        if code == 0:
            return None
        from datetime import datetime, timezone
        folder = ROOT / 'diagnostics' / 'gui_failures'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            path = folder / ('gui_error_' + timestamp + '_' + uuid.uuid4().hex[:8] + '.txt')
            lines = list(getattr(self, '_recent_process_lines', []))[-400:]
            reason = getattr(self, 'last_failure', None)
            content = ('L.D.PORTO VIDEO ANALYZER - processo retornou ' + str(code) + '\n'
                       + 'Motivo reportado: ' + scrub(reason or 'nao registrado') + '\n'
                       + 'Esta evidencia NAO identifica por si so a causa raiz.\n\n'
                       + 'ULTIMAS LINHAS DO PROCESSO (max. 400):\n' + ''.join(lines))
            with path.open('x', encoding='utf-8') as handle:
                handle.write(scrub(content))
            return path
        except OSError:
            return None

    def handle_stage_event(self, event):
        if event.get('event') == 'run_failed':
            self.last_failure = scrub(str(event.get('cause') or event.get('summary') or 'falha nao detalhada'))
        self.progress_model.update(event)
        metadata = event.get('metadata')
        if metadata:
            self.execution_title.set((metadata.get('source') or {}).get('title') or metadata.get('filename') or self.source.get())
            self.execution_metadata.set(human_duration(metadata.get('duration')) + ' | ' + str(metadata.get('width')) + 'x' + str(metadata.get('height')) + ' | ' + str(metadata.get('fps')) + ' fps')
        status = event.get('status')
        if status in ('partial', 'unavailable', 'failed', 'blocked', 'degraded'):
            stage = event.get('stage')
            label = STAGE_LABELS.get(stage) if stage else None
            if not label:
                label = {
                    'run_failed': 'Execucao',
                    'run_cancelled': 'Execucao',
                    'run_completed': 'Execucao',
                }.get(event.get('event')) or stage or 'Execucao'
            cause = event.get('cause') or event.get('summary') or 'Consulte o diagnostico de qualidade; fallback permanece explicito.'
            self.execution_diagnostic.set(f'{label}: {status}. {cause}')
            if event.get('event') == 'run_failed' and 'Preflight reprovado' in cause and 'vision' in cause:
                from ldporto.paths import MODELS_DIR
                visual_names = ['face_detection_yunet_2023mar.onnx', 'face_recognition_sface_2021dec.onnx', 'face_landmarker.task']
                if any(not (MODELS_DIR / name).is_file() for name in visual_names):
                    self.window.after_idle(self.visual_models)
        self.refresh_execution()

    def refresh_execution(self):
        if not self.in_execution:
            return
        snapshot = self.progress_model.snapshot()
        self.overall_bar['value'] = snapshot['overall_fraction'] * 100
        detail = (' | finalizando artefatos e verificacoes' if snapshot['finalization_pending'] else
                  ' | etapas pendentes: ' + str(snapshot['remaining_stage_count']) if not snapshot['finished'] else '')
        self.overall_text.set('Progresso geral: ' + f"{snapshot['overall_fraction'] * 100:.1f}%" + detail)
        if snapshot['stage_fraction'] is None and snapshot['status'] == 'running':
            if str(self.stage_bar.cget('mode')) != 'indeterminate':
                self.stage_bar.configure(mode='indeterminate')
                self.stage_bar.start(30)
        else:
            self.stage_bar.stop()
            self.stage_bar.configure(mode='determinate')
            self.stage_bar['value'] = (snapshot['stage_fraction'] or 0) * 100
        units = '' if snapshot['total'] is None else f" | {snapshot['current']} / {snapshot['total']}"
        substage = {'local_grounded_extraction': 'Analisando fala original', 'global_review': 'Revisao editorial global',
                    'semantic_validation': 'Validando evidencias semanticas'}.get(snapshot['substage'], snapshot['substage'])
        self.stage_text.set(str(snapshot['stage_label'] or 'Preparando') + units + (' | ' + substage if substage else ''))
        eta_range = snapshot['stage_eta_range_seconds']
        stage_eta = human_duration(snapshot['stage_eta_seconds'], True) if not eta_range else human_duration(eta_range[0], True) + ' - ' + human_duration(eta_range[1], True)
        total_range = snapshot.get('total_eta_range_seconds')
        total_eta = human_duration(snapshot['total_eta_seconds'], True) if not total_range else human_duration(total_range[0], True) + ' - ' + human_duration(total_range[1], True)
        eta_evidence = (' | amostras: ' + str(snapshot['eta_sample_count']) +
                        (' | total usa baseline; hardware atual pendente' if snapshot['future_eta_basis'] == 'baseline_weights_unvalidated_on_current_hardware' else ' | historico compativel')) if snapshot['stage_eta_seconds'] is not None else ''
        self.elapsed_text.set('Decorrido: ' + human_duration(snapshot['elapsed_seconds']) + ' | ETA etapa: ' + stage_eta + ' | ETA total: ' + total_eta + eta_evidence)
        if snapshot.get('blocking_reason'):
            self.execution_diagnostic.set(str(snapshot['stage_label']) + ': ' + snapshot['status'] + '. ' + snapshot['blocking_reason'])
        elif snapshot.get('performance'):
            perf = snapshot['performance']
            body = perf.get('body_backend') or {}
            def measured(value):
                return f'{value:.2f}' if isinstance(value, (int, float)) else 'n/d'
            self.execution_diagnostic.set(
                'Visao: ' + str(perf.get('frames_succeeded')) + '/' + str(perf.get('frames_attempted')) +
                ' frames | fps=' + measured(perf.get('fps')) +
                ' | p95=' + measured(perf.get('latency_p95_seconds')) + 's | backend=' +
                str(body.get('actually_executed_backend') or 'sem execucao comprovada') +
                ' | devices=' + str(body.get('devices_used') or {}) +
                ' | VRAM livre=' + measured((body.get('device_preflight') or {}).get('free_vram_mb')) +
                ' MiB (snapshot) | motivo=' + str(body.get('fallback_reason') or 'nenhum'))
        self.next_stage_text.set('Proxima etapa: ' + str(snapshot['next_stage_label'] or 'aguardando'))
        status_labels = {'running':'Em execucao', 'ok':'Concluido', 'partial':'Parcial', 'degraded':'Degradado',
                         'skipped':'Desativado', 'unavailable':'Indisponivel', 'failed':'Falhou', 'blocked':'Bloqueado', 'cancelled':'Interrompido'}
        for stage, state in snapshot['stage_states'].items():
            if self.stage_tree.exists(stage):
                self.stage_tree.item(stage, values=(status_labels.get(state.get('status'), state.get('status')), human_duration(state.get('elapsed_seconds'))))
                if stage == snapshot['stage']:
                    self.stage_tree.see(stage)

    def show_completion(self, code=0):
        self.in_execution = False
        self.stage_bar.stop()
        self.execution_frame.pack_forget()
        self.configuration_frame.pack_forget()
        self.final_frame.pack(fill='both', expand=True)
        package, quality, manifest, gate, video, review, provenance = {}, {}, {}, {}, {}, {}, {}
        translations = None
        if self.output_folder:
            folder = Path(self.output_folder)
            for name, target in (('second_curation_export.json', package), ('analysis_quality.json', quality), ('run_manifest.json', manifest),
                                 ('quality_gate.json', gate), ('video_analysis.json', video), ('source_audio_review.json', review),
                                 ('transcription_provenance.json', provenance)):
                try:
                    if name != 'second_curation_export.json' or code == 0:
                        document = json.loads((folder / name).read_text(encoding='utf-8'))
                        if isinstance(document, dict):
                            target.update(document)
                except (OSError, ValueError):
                    pass
            try:
                document = json.loads((folder/'translations.json').read_text(encoding='utf-8'))
                translations = document if isinstance(document, list) else None
            except (OSError, ValueError):
                pass
        self.package_path = Path(package['path']) if package.get('path') else None
        self.final_heading.set('Execucao interrompida' if code == 130 else 'Analise finalizada' if code == 0 else 'Analise terminou com erro')
        self.final_summary.set('Tempo: ' + human_duration(self.progress_model.snapshot()['elapsed_seconds']) + '\nStatus: ' + str(manifest.get('analysis_status', 'unavailable')) +
            '\nCandidatos: ' + str(package.get('candidate_count', 'n/d')) + ' | Shortlist: ' + str(package.get('shortlist_count', 'n/d')) +
            '\nSmart Camera: ' + str(quality.get('smart_camera_decision_count', 'n/d')) + ' decisões' +
            '\nZoom: propostos=' + str(quality.get('proposed_zoom_event_count', 'n/d')) +
            ' | timeline=' + str(quality.get('zoom_event_count', 'n/d')) +
            ' | renderizados=' + str(quality.get('rendered_zoom_event_count', 'não medido')) +
            ' | confirmados em frames finais=' + str(quality.get('zoom_delivered_event_count', 'não medido')))
        editorial = package.get('editorial_result') or {}
        if editorial.get('message'):
            self.final_summary.set(self.final_summary.get() + '\nResultado editorial: ' + editorial['message'])
        triage = editorial_triage_text(editorial)
        if triage:
            self.final_summary.set(self.final_summary.get() + '\n' + triage)
        detail = '\nQualidade: ' + str(gate.get('status') or quality.get('quality_status') or 'nao medida')
        detail += '\nTranscricao: ' + ('fala original (transcribe)' if provenance.get('task') == 'transcribe' else 'origem nao registrada')
        detail += ' | traducoes separadas: ' + (str(len(translations)) if translations is not None else 'nao registradas')
        if review:
            detail += '\nRevisao por fonte: ' + str(review.get('status') or 'nao registrada')
            if review.get('audio_verification_performed') is False or review.get('status') == 'pending_human_audio_review':
                detail += ' | revisao humana do audio: pendente'
            else:
                detail += ' | verificacao de audio: ' + ('registrada' if review.get('audio_verification_performed') is True else 'nao medida')
            acoustic = review.get('acoustic_multipass') if isinstance(review.get('acoustic_multipass'), dict) else {}
            if acoustic.get('asr_calls') is not None:
                detail += ' | multipass ASR: ' + str(acoustic['asr_calls']) + ' chamadas'
        causal_document = gate.get('causal_diagnostics') if isinstance(gate.get('causal_diagnostics'), dict) else {}
        causal = gate.get('root_causes') or causal_document.get('root_causes') or []
        causal = causal if isinstance(causal, list) else []
        categories = {'source_limitation': 'limitacao da fonte', 'dependency_unavailable': 'dependencia indisponivel',
                      'insufficient_evidence': 'evidencia insuficiente', 'logic': 'logica',
                      'configuration': 'configuracao', 'not_validated': 'nao homologado',
                      'availability_cause_unknown': 'causa da indisponibilidade nao medida', 'interrupted': 'interrompido',
                      'blocked_reason_unknown': 'bloqueio sem causa confirmada', 'technical_error': 'erro tecnico'}
        for cause in causal:
            if isinstance(cause, dict):
                category = str(cause.get('category') or 'nao classificada')
                detail += '\nCausa: ' + str(cause.get('stage') or 'nao registrada') + ' | ' + categories.get(category, str(category)) + ' | ' + str(cause.get('reason_code') or cause.get('code') or 'consulte qualidade')
        visual_quality = video.get('quality') if isinstance(video.get('quality'), dict) else {}
        backend = visual_quality.get('body_detection') if isinstance(visual_quality.get('body_detection'), dict) else {}
        if not backend and isinstance(video.get('body_backend_execution'), dict):
            backend = video['body_backend_execution']
        if not backend and self.output_folder:
            try:
                analysis_path = Path(self.output_folder)/'analysis.json'
                if analysis_path.stat().st_size <= 4 * 1024 ** 2:
                    analysis = json.loads(analysis_path.read_text(encoding='utf-8'))
                    performance = analysis.get('vision_performance') or {}
                    if isinstance(performance.get('body_backend_execution'), dict):
                        backend = performance['body_backend_execution']
            except (OSError, ValueError, AttributeError):
                pass
        if backend:
            detail += '\n' + body_execution_text(backend)
            self.body_status.set(body_execution_text(backend))
        self.final_summary.set(self.final_summary.get() + detail)
        if code != 0:
            reason = getattr(self, 'last_failure', None)
            logfile = getattr(self, 'failure_log_path', None)
            if reason:
                self.final_summary.set(self.final_summary.get() + '\nErro reportado: ' + scrub(reason)[:700])
            if logfile:
                self.final_summary.set(self.final_summary.get() + '\nLog da falha: ' + str(logfile))
        labels = {'editorial_ready':'Editorial', 'transcript_ready':'Transcricao', 'visual_ready':'Visual',
                  'speaker_person_ready':'Speaker/person', 'camera_ready':'Camera', 'preview_ready':'Preview'}
        self.final_readiness.set('\n'.join(label + ': ' + ('pronta para revisao' if package.get('readiness', {}).get(key) is True else
            'nao medida' if package.get('readiness', {}).get(key) is None else 'indisponivel/degradada') for key, label in labels.items()) +
            '\nPreview aprovado: ' + ('sim' if gate.get('preview_approved') is True else 'nao' if gate.get('preview_approved') is False else 'nao registrado') +
            '\nPublicacao pronta: ' + ('sim' if gate.get('publication_ready') is True else 'nao' if gate.get('publication_ready') is False else 'nao registrada') +
            ('\nCamera preservando source: speaker/person ou crop ainda insuficiente.' if not package.get('readiness', {}).get('camera_ready') else ''))
        self.final_package.set(str(self.package_path) + '\n' + f"{package.get('bytes', 0) / 1024 ** 2:.2f} MB | {package.get('state', 'FAILED')}" if self.package_path else 'Pacote indisponivel; artifacts locais foram preservados para diagnostico/resume.')
        self.restore_project_pointer()
        auto_export=getattr(self,'auto_project_export',None)
        if code == 0 and auto_export and auto_export.get() and self.package_path and not self.project_path:
            self.export_project_dossier(choose_directory=False)

    def restore_project_pointer(self):
        self.project_path = None
        if self.output_folder:
            try:
                pointer = json.loads((Path(self.output_folder)/'project_export.json').read_text(encoding='utf-8'))
                target = Path(pointer['path'])
                if (target/'PROJECT_MANIFEST.json').is_file():
                    self.project_path = target
                    self.project_status.set('Dossiê: '+str(target)+' | '+str(pointer.get('state','não verificado')))
            except (OSError,ValueError,KeyError):
                pass

    def _project_worker(self, operation):
        if self.project_busy:
            return
        self.project_busy = True
        self.project_cancel.clear()
        self.project_status.set('Preparando evidências do projeto…')
        def worker():
            try:
                result = operation()
                self.messages.put(('project_result',result))
            except Exception as exc:
                self.messages.put(('project_result',{'state':'FAILED','error':scrub(str(exc))}))
        threading.Thread(target=worker,daemon=True).start()

    def export_project_dossier(self, choose_directory=True):
        if getattr(self,'project_busy',False) or (self.proc and self.proc.poll() is None):
            messagebox.showinfo('Dossiê','Aguarde a operação em curso terminar.')
            return
        package = self.package_path
        analysis_folder = None
        if not package or not Path(package).is_file():
            value = filedialog.askopenfilename(title='ZIP existente da segunda curadoria',filetypes=[('Pacote ZIP','*.zip')])
            if not value:
                return
            package = Path(value)
            self.package_path = package
        # Bind every export, including repeated manual selections, to its producer.
        if self.output_folder:
            try:
                from ldporto.core import file_hash
                pointer=json.loads((Path(self.output_folder)/'second_curation_export.json').read_text(encoding='utf-8'))
                linked=Path(pointer['path'])
                if linked.resolve()==Path(package).resolve() and file_hash(linked)==pointer.get('zip_sha256'):
                    analysis_folder=self.output_folder
            except (OSError,ValueError,KeyError):
                pass
        from ldporto.paths import videos_directory
        destination = videos_directory()/'LDPORTO_VIDEO_ANALYZER'
        if choose_directory:
            value = filedialog.askdirectory(title='Destino do projeto completo',initialdir=str(videos_directory()))
            if not value:
                return
            destination = Path(value)
        def operation():
            from ldporto.project_export import export_project
            analysis = None
            if analysis_folder and (Path(analysis_folder)/'analysis.json').is_file():
                from ldporto.compact_artifacts import load_analysis_artifacts
                analysis = load_analysis_artifacts(analysis_folder, collections=['transcript_segments','words','scenes','camera_director_timeline'])
            result = export_project(package,destination,analysis=analysis,
                progress=lambda name,current,total:self.messages.put(('project_progress',name+' · '+str(current)+'/'+str(total))),
                cancelled=self.project_cancel.is_set)
            if analysis_folder:
                from ldporto.core import write_json
                write_json(Path(analysis_folder)/'project_export.json',result)
            return result
        self._project_worker(operation)

    def open_project_artifact(self, relative=''):
        if not self.project_path:
            messagebox.showinfo('Central de resultados','Gere ou reabra um dossiê organizado para acessar este material.')
            return
        target = (self.project_path/relative).resolve()
        if not target.is_relative_to(self.project_path.resolve()) or not target.exists():
            messagebox.showinfo('Central de resultados','Material indisponível neste projeto; consulte as limitações.')
            return
        if os.name == 'nt':
            os.startfile(str(target))
        else:
            webbrowser.open(target.as_uri())

    def open_results_center(self):
        if not self.output_folder and not self.project_path:
            chosen = filedialog.askdirectory(title='Reabrir pasta de análise ou projeto exportado')
            if not chosen:
                return
            folder = Path(chosen)
            if (folder/'PROJECT_MANIFEST.json').is_file():
                self.project_path = folder
            else:
                self.output_folder = folder
                self.restore_project_pointer()
                try:
                    result = json.loads((folder/'second_curation_export.json').read_text(encoding='utf-8'))
                    self.package_path = Path(result['path'])
                except (OSError,ValueError,KeyError):
                    pass
        dialog = tk.Toplevel(self.window)
        dialog.title('Análise finalizada — Central de resultados')
        dialog.geometry('940x650')
        ttk.Label(dialog,textvariable=self.project_status,wraplength=880,padding=12).pack(anchor='w')
        metrics = tk.Text(dialog,height=13,wrap='word')
        metrics.pack(fill='x',padx=12,pady=8)
        metrics.insert('end','Candidatos, legendas, foco, zoom, séries e pendências: consultar manifest/relatórios; valores ausentes são não medidos.\n')
        if self.project_path:
            try:
                data = json.loads((self.project_path/'PROJECT_MANIFEST.json').read_text(encoding='utf-8'))
                for key,label in (('state','Estado do dossiê'),('candidate_count','Candidatos'),('story_series_count','Séries propostas'),
                    ('story_parts_proposed_count','Partes propostas (IDs únicos)'),('complete_phrase_story_count','Stories com frase completa comprovada'),
                    ('candidates_with_geometrically_valid_interval','Candidatos com algum intervalo de crop geometricamente válido'),
                    ('zoom_confirmed_in_final_frames_count','Zooms confirmados em frames finais'),
                    ('transcript_coverage_ratio','Cobertura temporal transcrita'),('caption_preflight_summary','Preflight de legendas'),('pdf_status','PDF')):
                    metrics.insert('end',label+': '+str(data.get(key) if data.get(key) is not None else 'não medido')+'\n')
                metrics.insert('end','Preview aprovado: '+str(data.get('preview_approved'))+' | Publicação pronta: '+str(data.get('publication_ready'))+'\n')
            except (OSError,ValueError):
                metrics.insert('end','Manifest indisponível ou inválido.\n')
        metrics.configure(state='disabled')
        actions = ttk.Frame(dialog,padding=12)
        actions.pack(fill='both',expand=True)
        for i,(label,path) in enumerate((('Abrir projeto',''),('Guia editorial PDF','00_RESUMO/GUIA_EDITORIAL_COMPLETO.pdf'),
            ('Transcrição disponível','01_TRANSCRICAO/TRANSCRICAO_COMPLETA.pdf'),('Reels propostos','03_REELS'),
            ('Stories sequenciais','04_STORIES'),('Pessoas e cenas','02_PESSOAS_E_CENAS'),('Camera Director','05_CAMERAS'),
            ('Pendências de revisão','07_RELATORIOS_TECNICOS/limitations.json'),('ZIP da segunda curadoria','06_SEGUNDA_CURADORIA'))):
            ttk.Button(actions,text=label,command=lambda p=path:self.open_project_artifact(p)).grid(row=i//3,column=i%3,sticky='ew',padx=4,pady=4)
        ttk.Button(actions,text='Exportar / gerar PDFs novamente',command=self.export_project_dossier).grid(row=3,column=0,sticky='ew',padx=4,pady=4)
        def verify():
            if self.project_path:
                target = self.project_path
                def operation():
                    from ldporto.project_export import verify_project_export
                    report=verify_project_export(target)
                    return {'state':report['status'],'verification':report}
                self._project_worker(operation)
        ttk.Button(actions,text='Verificar integridade',command=verify).grid(row=3,column=1,sticky='ew',padx=4,pady=4)
        ttk.Button(actions,text='Gerenciar espaço',command=self.clean_heavy).grid(row=3,column=2,sticky='ew',padx=4,pady=4)
        ttk.Button(actions,text='Cancelar geração com segurança',command=self.project_cancel.set).grid(row=4,column=0,sticky='ew',padx=4,pady=4)
        ttk.Label(dialog,text='Retomar análise parcial: use a mesma fonte e pasta na análise; checkpoints compatíveis são preservados. Câmera: analyze.py --director-only PASTA.',wraplength=880,padding=12).pack(anchor='w')

    def diagnose_s10(self):
        """Read-only diagnostics in worker; never turn on parallelism automatically."""
        self.status.set('Recursos S10: coletando CPU, RAM, VRAM e ferramentas locais…')
        def task():
            try:
                from ldporto.performance_acceptance import resource_diagnostic
                from ldporto.curator_delivery import save_json
                report = resource_diagnostic()
                output = ROOT / '.cache' / 's10_resource_diagnostic.json'
                save_json(output, report)
                message = ('CPU lógico: ' + str(report.get('logical_cpus')) +
                           '\nNVIDIA: ' + ('detectada' if report.get('gpu', {}).get('available') else 'indisponível') +
                           '\nRAM disponível (bytes): ' + str(report.get('ram_available_bytes')) +
                           '\nRAM processo (bytes): ' + str(report.get('working_set_bytes')) +
                           '\nVRAM livre por GPU (MiB): ' + str([gpu.get('vram_free_mib') for gpu in report.get('gpu', {}).get('gpus', [])] or None) +
                           '\nFFmpeg: ' + ('disponível' if report.get('ffmpeg') else 'ausente') +
                           '\nParalelismo adaptativo: desativado até benchmark A/B' +
                           '\nRelatório: ' + str(output))
                self.window.after(0, lambda: (self.status.set('Diagnóstico S10 concluído — A/B real ainda pendente'),
                                               messagebox.showinfo('Recursos S10', message)))
            except Exception as exc:
                self.window.after(0, lambda error=str(exc): messagebox.showerror('Recursos S10', error))
        threading.Thread(target=task, daemon=True).start()

    def open_review_queue(self):
        """Inspect original media or a verified preview without changing approvals."""
        package = self.package_path
        if not package or not Path(package).is_file():
            package = filedialog.askopenfilename(title='Pacote de segunda curadoria', filetypes=[('ZIP', '*.zip')])
        if not package:
            return
        def load():
            try:
                import zipfile
                from ldporto.second_curation_export import validate_core_package
                from ldporto.review_media import build_source_media_references
                validation = validate_core_package(Path(package))
                if validation['status'] != 'valid':
                    raise ValueError('Pacote inválido: ' + '; '.join(validation.get('errors', [])[:3]))
                with zipfile.ZipFile(package) as archive:
                    queue = json.loads(archive.read('editorial/human_review_queue.json'))
                    metadata = json.loads(archive.read('source/metadata.json'))
                entries = queue['entries']
                for row in entries:
                    row.setdefault('source_media_references', build_source_media_references(metadata, row))
                self.window.after(0, lambda: show(entries))
            except Exception as exc:
                self.window.after(0, lambda error=str(exc): messagebox.showerror('Fila de revisão', error))
        def show(entries):
            if not entries:
                messagebox.showinfo('Fila de revisão', 'Não há candidatos elegíveis para revisão neste pacote.')
                return
            dialog = tk.Toplevel(self.window)
            dialog.title('Revisão editorial — nenhuma aprovação automática')
            labels = [f'{row["candidate_id"]} | {row["start"]:.2f}–{row["end"]:.2f}s' for row in entries]
            selected = ttk.Combobox(dialog, values=labels, state='readonly', width=80)
            selected.pack(padx=12, pady=12)
            selected.current(0)
            ttk.Label(dialog, text='Selecione a mídia local. O SHA-256 será conferido antes de abrir.\n'
                      'Assistir não conclui revisão nem aprova prévia ou publicação.').pack(padx=12, pady=8)
            local_paths = {}
            def play(kind):
                refs = entries[selected.current()].get('source_media_references')
                if not refs:
                    messagebox.showerror('Mídia', 'Referência verificável indisponível.')
                    return
                if kind == 'preview':
                    if not refs.get('existing_previews'):
                        messagebox.showinfo('Mídia', 'Não existe prévia vinculada por hash a este intervalo.')
                        return
                    key = 'preview_root'
                    path = local_paths.get(key) or filedialog.askdirectory(parent=dialog,
                        title='Pasta que contém source_previews')
                else:
                    key = 'original_path'
                    path = local_paths.get(key) or filedialog.askopenfilename(parent=dialog,
                        title='Vídeo ORIGINAL (o áudio será o da própria fonte)',
                        filetypes=[('Vídeo', '*.mp4 *.mkv *.webm *.mov *.avi'), ('Todos', '*.*')])
                if not path:
                    return
                local_paths[key] = path
                def verify_and_open():
                    try:
                        import tempfile
                        from ldporto.review_media import resolve_review_media, review_player_html
                        resolved = resolve_review_media(refs, kind=kind, **{key: path})
                        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.html',
                                                         prefix='ldporto_review_', delete=False) as handle:
                            handle.write(review_player_html(resolved))
                            target = Path(handle.name)
                        webbrowser.open(target.as_uri())
                    except Exception as exc:
                        local_paths.pop(key, None)
                        self.window.after(0, lambda error=str(exc): messagebox.showerror('Mídia', error))
                threading.Thread(target=verify_and_open, daemon=True).start()
            buttons = ttk.Frame(dialog)
            buttons.pack(pady=12)
            for label, kind in [('Vídeo original', 'video'), ('Áudio original', 'audio'), ('Prévia existente', 'preview')]:
                ttk.Button(buttons, text=label, command=lambda k=kind: play(k)).pack(side='left', padx=5)
        threading.Thread(target=load, daemon=True).start()

    def prepare_curator_s9(self):
        """Create a reviewed render plan; no render, publication or automatic approval."""
        if not self.package_path or not self.package_path.is_file():
            messagebox.showerror('Curator S9', 'Pacote de segunda curadoria indisponível. Gere o SECOND_CURATION_READY primeiro.')
            return
        video = filedialog.askopenfilename(title='Selecione o vídeo ORIGINAL da análise',
                                           filetypes=[('Vídeo', '*.mp4 *.mkv *.webm *.mov *.avi'), ('Todos', '*.*')])
        if not video:
            return
        output = filedialog.askdirectory(title='Onde salvar o plano para o Curator S9?')
        if not output:
            return
        self.final_heading.set('Curator S9: conferindo hashes e elegibilidade…')
        package_path = self.package_path
        def task():
            try:
                from ldporto.curator_delivery import prepare_plan, save_json
                plan = prepare_plan(package_path, video, output_dir=output)
                target = Path(output) / 'CURATOR_S9_PLAN.json'
                if target.exists():
                    raise FileExistsError('CURATOR_S9_PLAN.json já existe; escolha outra pasta para não sobrescrever.')
                save_json(target, plan)
                message = (f'Plano salvo em {target}\nCortes: {len(plan["clips"])}\n'
                           'Ainda requer renderizar canário, revisar e aprovar por hash.\n'
                           'Veja docs/S9_S11_REAL_TEST.md para os próximos comandos.')
                self.window.after(0, lambda: (self.final_heading.set('Plano Curator S9 pronto para canário'),
                                               messagebox.showinfo('Curator S9', message)))
            except Exception as exc:
                self.window.after(0, lambda error=str(exc): (self.final_heading.set('Curator S9 bloqueado'),
                                                               messagebox.showerror('Curator S9', error)))
        threading.Thread(target=task, daemon=True).start()

    def new_analysis(self):
        if getattr(self,'project_busy',False):
            return
        self.final_frame.pack_forget()
        self.execution_frame.pack_forget()
        self.configuration_frame.pack(fill='both', expand=True)
        self.start_button.configure(state='normal')

    def open_package_folder(self):
        folder = self.package_path.parent if self.package_path else self.output_folder
        if folder and folder.exists():
            os.startfile(str(folder)) if os.name == 'nt' else webbrowser.open(folder.as_uri())

    def copy_package_path(self):
        if self.package_path:
            self.window.clipboard_clear()
            self.window.clipboard_append(str(self.package_path))
    def launch(self, args):
        if getattr(self, 'media_busy', False):
            messagebox.showinfo('Mídia', 'Aguarde a verificação local do original.')
            return
        if getattr(self, 'smoke_busy', False):
            messagebox.showinfo('Canario em execucao', 'Aguarde o canario sequencial terminar.')
            return
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("Em execução", "Aguarde o processamento atual.")
            return
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        if self.hf_token.get().strip():
            env["HF_TOKEN"] = self.hf_token.get().strip()
        self._recent_process_lines = []
        self.last_failure = None
        self.failure_log_path = None
        try:
            self.proc = subprocess.Popen([sys.executable, "-u", str(ROOT/"analyze.py")]+args,
                        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                        start_new_session=os.name != "nt")
        except OSError as exc:
            self.status.set('Nao foi possivel iniciar analyze.py: ' + scrub(exc))
            messagebox.showerror('Falha ao iniciar', self.status.get())
            return
        self.start_button.configure(state="disabled")
        if '--doctor' not in args:
            self.show_execution()
        self.warning_count=0
        self.status.set("Processando… acompanhe as etapas abaixo.")
        proc = self.proc
        def read():
            try:
                # PIPE is requested above, but keep the optional stream explicit.
                stream = proc.stdout
                if stream is not None:
                    for line in stream:
                        if line.startswith(EVENT_PREFIX):
                            try:
                                self.messages.put(('event', json.loads(line[len(EVENT_PREFIX):])))
                                continue
                            except ValueError:
                                pass
                        self.messages.put(("line", scrub(line)))
            except (OSError, UnicodeError) as exc:
                self.messages.put(('line', 'Falha na leitura do processo: ' + scrub(exc) + '\n'))
            finally:
                self.messages.put(("done", proc.wait()))
        threading.Thread(target=read, daemon=True).start()

    def ocr_options(self):
        return {'enabled': self.ocr_enabled.get(), 'languages': self.ocr_languages.get(),
                'tesseract_cmd': self.ocr_command.get() or None}

    def change_ocr(self, key):
        from ldporto.config import save_ocr_options, load_config
        self.ocr_generation += 1
        try:
            save_ocr_options(ROOT/'config'/'config.yaml', {key: self.ocr_options()[key]})
        except (OSError, ValueError) as exc:
            cfg = load_config(ROOT/'config'/'config.yaml')['ocr']
            self.ocr_enabled.set(cfg['enabled'])
            self.ocr_languages.set(cfg['languages'])
            self.ocr_command.set(cfg['tesseract_cmd'] or '')
            self.ocr_status.set('Bloqueado: configuração não salva (' + type(exc).__name__ + ')')
            return
        if self.ocr_enabled.get():
            self.ocr_status.set('Não testado: configuração alterada')
            self.verify_ocr()
        else:
            self.ocr_status.set('Desligado: visual comercial not_measured / requires_review; publicação exige revisão humana')

    def select_ocr_command(self):
        selected = filedialog.askopenfilename(title='Selecionar executável Tesseract', filetypes=[('Tesseract executável', '*.exe')])
        if selected:
            self.ocr_command.set(selected)
            self.change_ocr('tesseract_cmd')

    def clear_ocr_command(self):
        self.ocr_command.set('')
        self.change_ocr('tesseract_cmd')

    def verify_ocr(self, smoke=False, start_after=False):
        if self.runtime_busy():
            return
        options = self.ocr_options()
        generation = self.ocr_generation
        self.ocr_busy = True
        self.start_button.configure(state='disabled')
        self.ocr_status.set('Não testado: verificando OCR…')
        def worker():
            from ldporto.ocr_diagnostics import diagnose_ocr
            try:
                report = diagnose_ocr(options, smoke=smoke)
            except Exception as exc:
                report = {'ok': False, 'status': 'ERROR', 'reason': 'diagnostic_failed', 'error': {'type': type(exc).__name__}}
            self.messages.put(('ocr_result', (generation, options, report, start_after)))
        threading.Thread(target=worker, daemon=True).start()

    def handle_ocr_result(self, value):
        generation, options, report, start_after = value
        self.ocr_busy = False
        self.start_button.configure(state='normal')
        if generation != self.ocr_generation or options != self.ocr_options():
            self.ocr_status.set('Não testado: resultado anterior ignorado')
            if self.ocr_enabled.get():
                self.verify_ocr()
            return
        self.ocr_last_diagnostic = report
        if not options['enabled']:
            self.ocr_status.set('Desligado: visual comercial not_measured / requires_review')
        elif report['ok']:
            self.ocr_status.set('Pronto: ' + options['languages'] + ' | ' + report.get('readiness_scope', 'configuration_only'))
        else:
            reasons = {'dependency_missing': 'pytesseract indisponível neste Python',
                       'binary_missing': 'executável Tesseract ausente ou sem permissão',
                       'language_missing': 'idiomas/traineddata ausentes: ' + ', '.join(report.get('missing_languages', [])),
                       'model_load_failed': 'Tesseract não carregou versão/idiomas; confira tessdata e permissões',
                       'missing_languages': 'idiomas/traineddata ausentes: ' + ', '.join(report.get('missing_languages', [])),
                       'binary_execution_failed': 'Tesseract falhou ao executar ou retornou resposta inválida',
                       'tessdata_unavailable': 'Tesseract não conseguiu listar/ler/carregar tessdata',
                       'timeout': 'Tesseract excedeu o timeout de 5 segundos',
                       'smoke_failed': 'smoke sintético falhou; OCR não comprovado'}
            detail = ' | check=' + report['failed_check'] if report.get('failed_check') else ''
            if report.get('error'):
                detail += ' | ' + report['error']['type']
            if 'returncode' in report:
                detail += ' | exit=' + str(report['returncode'])
            self.ocr_status.set('Bloqueado: ' + reasons.get(report.get('reason'), 'diagnóstico OCR falhou') + detail)
        if start_after and (not options['enabled'] or report['ok']):
            self._start_checked()

    def start(self):
        if self.runtime_busy():
            return
        if not self.source.get().strip():
            messagebox.showinfo('Entrada', 'Selecione um vídeo ou cole um link.')
            return
        self.verify_ocr(start_after=True)

    def _start_checked(self):
        if self.runtime_busy():
            return
        source = self.source.get().strip()
        if not source:
            messagebox.showinfo("Entrada", "Selecione um vídeo ou cole um link.")
            return
        if hasattr(self, 'media_status'):
            options = self.media_options()
            checked = self.media_check_result
            if checked is None or checked[0] != options:
                self.verify_media(start_after=True)
                return
            result = checked[1]
            permitted_download = (source.startswith(('http://', 'https://')) and self.allow_download.get()
                                  and result.get('status') == 'OPERATOR_SELECTION_REQUIRED')
            if result.get('status') != 'FOUND_VERIFIED' and not permitted_download:
                messagebox.showinfo('Original local', media_selection_text(result))
                return
        self.output_folder = ROOT/"analysis"/__import__("datetime").datetime.now().strftime("execucao_%Y%m%d_%H%M%S")
        args = [source, "--output", str(self.output_folder), "--model", self.model.get(),
                "--device", self.device.get(), "--semantic", "ollama" if self.ollama.get() else "heuristic"]
        if hasattr(self, 'media_status'):
            options, result = self.media_check_result
            args += media_cli_options(source, allow_download=self.allow_download.get(),
                local_path=options['local_path'] or result.get('path', ''),
                expected_sha256=options['expected_sha256'] or result.get('source_sha256', ''))
        if self.ollama.get():
            args += ["--ollama-model", self.ollama_model.get().strip() or "qwen3:8b",
                     "--ollama-profile", self.ollama_profile.get()]
        if self.force.get():
            args.append("--force")
        # Generated by GitHub Copilot - Oct-05-2026
        if not self.diarization.get():
            args.append("--no-diarization")
        if not self.vision.get():
            args.append("--no-vision")
        self.preflight_status.set("Preflight: verificando capacidades habilitadas")
        # Stable output per source allows automatic resume from previous GUI executions.
        if self.inference_smoke_gate.get():
            args.append('--inference-smoke')
        import hashlib
        tag = hashlib.sha256(source.encode()).hexdigest()[:12]
        self.output_folder = ROOT/"analysis"/f"video_{tag}"
        args[2] = str(self.output_folder)
        if (self.output_folder / 'run_manifest.json').is_file() and not self.force.get():
            try:
                previous = json.loads((self.output_folder / 'run_manifest.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                previous = {}
            if previous.get('analysis_status') == 'partial':
                valid = previous.get('modules_still_valid', [])
                last = valid[-1] if valid else 'nenhuma etapa valida'
                choice = messagebox.askyesnocancel('Analise incompleta encontrada', 'Ultima etapa valida: ' + last + '\nContinuar a analise? Nao = reprocessar; cancelar = voltar.')
                if choice is None:
                    return
                if choice is False:
                    args.append('--force')
        (self.output_folder / 'CANCEL_REQUESTED').unlink(missing_ok=True)
        if self.include_previews.get():
            args.append('--include-candidate-previews')
        args += ['--social-aspect', self.social_aspect.get(), '--caption-preset', self.caption_preset.get(),
                 '--content-mode', self.content_mode.get(), '--story-count', str(self.story_count.get()),
                 '--caption-font', self.caption_font.get().strip() or 'Arial', '--caption-size', str(self.caption_size.get()),
                 '--caption-color', self.caption_color.get(), '--highlight-color', self.highlight_color.get()]
        try:
            args += self.camera_args()
        except ValueError:
            messagebox.showerror("Câmera", "Hold e zoom devem ser números válidos.")
            return
        self.launch(args)

    def camera_args(self):
        args = ["--camera-profile", self.camera_profile.get(), '--smart-zoom-profile', self.smart_profile.get()]
        if not self.smart_zoom.get():
            args.append('--no-smart-zoom')
        if not self.camera_enabled.get():
            args.append("--no-camera-director")
        for flag, var in (("--camera-min-hold", self.camera_hold), ("--camera-max-zoom", self.camera_zoom)):
            if var.get().strip():
                args += [flag, str(float(var.get().replace(",", ".")))]
        return args

    def toggle_camera_settings(self):
        if self.camera_advanced.winfo_manager():
            self.camera_advanced.pack_forget()
        else:
            self.camera_advanced.pack(fill="x", pady=4, before=self.log)

    def resume_camera(self):
        if self.proc and self.proc.poll() is None:
            return
        folder = filedialog.askdirectory(title="Pasta contendo analysis.json")
        if folder:
            try:
                args = ["--director-only", folder]+self.camera_args()
            except ValueError:
                messagebox.showerror("Câmera", "Hold e zoom devem ser números válidos.")
                return
            self.output_folder = Path(folder)
            self.launch(args)

    def update_ocr_execution(self):
        folder = self.output_folder
        if folder is None:
            return
        try:
            data = json.loads((folder/'ocr_execution.json').read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        rows = []
        for key, label in [('general_13', 'geral 13'), ('commercial_17c', 'comercial 17c')]:
            row = data.get(key, {})
            rows.append(f"OCR {label}: {row.get('state', 'not_measured')} | frames={row.get('measured_frames')} | falhas={row.get('failed_frames_or_ocr')} | idiomas={row.get('languages')} | segundos={row.get('elapsed_seconds')}")
        self.ocr_execution_status.set('\n'.join(rows))

    def update_camera_summary(self):
        folder = self.output_folder
        if folder is None:
            return
        self.update_ocr_execution()
        try:
            q = json.loads((folder/"analysis_quality.json").read_text(encoding="utf-8"))
            manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
            status = manifest.get("stage_status", {}).get("19_camera_director", {}).get("status", "unavailable")
            def pct(key):
                v = q.get(key)
                return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "n/d"
            def num(key):
                v = q.get(key)
                return f"{v:.2f}" if isinstance(v, (int, float)) else "n/d"
            self.camera_summary.set(f"Camera Director: {status} | Active speaker: {pct('active_speaker_coverage')} | "
                f"Cobertura temporal: {pct('timeline_temporal_coverage')} | Foco resolvido: {pct('resolved_focus_coverage')} | Plano médio: {num('average_director_shot_seconds')}s | "
                f"Trocas/min: {num('director_switches_per_minute')} | Split: {pct('split_fraction')} | "
                f"Foco incerto: {pct('unresolved_focus_fraction')} | Pan/zoom com limites físicos; revisar keyframes.")
            self.run_state.set('Etapa: finalizada | Avisos: '+str(self.warning_count)+' | Qualidade: '+str(q.get('quality_status','nao medida')))
        except (OSError, ValueError):
            self.camera_summary.set("Camera Director: resultado ainda indisponível")

    def pick_social_color(self, variable):
        chosen = colorchooser.askcolor(color=variable.get(), parent=self.window)[1]
        if chosen:
            variable.set(chosen.upper())

    def social_settings(self):
        dialog = tk.Toplevel(self.window)
        dialog.title('Saída social · Stories / Reels / Shorts')
        dialog.geometry('720x520')
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Formato de saída', font=('Segoe UI', 12, 'bold')).grid(row=0, column=0, sticky='w', pady=(0,6))
        ttk.Combobox(frame, textvariable=self.social_aspect, values=['9:16','4:5','1:1','16:9'], state='readonly', width=14).grid(row=1,column=0,sticky='w')
        ttk.Label(frame, text='Preset de legenda', font=('Segoe UI', 12, 'bold')).grid(row=0,column=1,sticky='w',padx=(20,0),pady=(0,6))
        ttk.Combobox(frame, textvariable=self.caption_preset, values=['auto','no_caption','simple','karaoke','popline','deep_diver','think_media','pod_p','news','show_highlight','clean_bold','high_contrast','soft_subtitle','creator_style'], state='readonly', width=22).grid(row=1,column=1,sticky='w',padx=(20,0))
        ttk.Label(frame, text='Modo de conteúdo').grid(row=2,column=0,sticky='w',pady=(18,4))
        ttk.Combobox(frame, textvariable=self.content_mode, values=['auto','show','entrevista','podcast','programa_tv','reacao','educativo','humor','noticias'], state='readonly', width=18).grid(row=3,column=0,sticky='w')
        ttk.Label(frame, text='Quantidade máxima de Stories').grid(row=2,column=1,sticky='w',padx=(20,0),pady=(18,4))
        ttk.Spinbox(frame, from_=1, to=30, textvariable=self.story_count, width=8).grid(row=3,column=1,sticky='w',padx=(20,0))
        ttk.Label(frame, text='Fonte').grid(row=4,column=0,sticky='w',pady=(18,4))
        ttk.Combobox(frame, textvariable=self.caption_font, values=['Arial','Segoe UI','Montserrat','Inter','Roboto','Poppins','Impact'], width=20).grid(row=5,column=0,sticky='w')
        ttk.Label(frame, text='Escala da legenda').grid(row=4,column=1,sticky='w',padx=(20,0),pady=(18,4))
        ttk.Spinbox(frame, from_=0.6, to=2.0, increment=0.1, textvariable=self.caption_size, width=8).grid(row=5,column=1,sticky='w',padx=(20,0))
        ttk.Label(frame, text='Cor principal').grid(row=6,column=0,sticky='w',pady=(18,4))
        color_row = ttk.Frame(frame); color_row.grid(row=7,column=0,sticky='w')
        ttk.Entry(color_row, textvariable=self.caption_color, width=12).pack(side='left')
        ttk.Button(color_row, text='Escolher', command=lambda: self.pick_social_color(self.caption_color)).pack(side='left', padx=5)
        ttk.Label(frame, text='Cor de destaque').grid(row=6,column=1,sticky='w',padx=(20,0),pady=(18,4))
        high_row = ttk.Frame(frame); high_row.grid(row=7,column=1,sticky='w',padx=(20,0))
        ttk.Entry(high_row, textvariable=self.highlight_color, width=12).pack(side='left')
        ttk.Button(high_row, text='Escolher', command=lambda: self.pick_social_color(self.highlight_color)).pack(side='left', padx=5)
        preview = tk.Label(frame, text='TÍTULO FORTE\nLegenda inteligente com DESTAQUE', bg='#242429', fg=self.caption_color.get(), font=(self.caption_font.get() or 'Arial', 18, 'bold'), padx=18, pady=18, justify='center')
        preview.grid(row=8,column=0,columnspan=2,sticky='ew',pady=(26,8))
        note = ('Stories 60s = vários momentos independentes escolhidos ao longo do vídeo.\n'
                'O Analyzer só planeja estilo/layout; o Curator faz o render final e recalcula safe-area após crop/câmera.')
        ttk.Label(frame, text=note, wraplength=650, justify='left').grid(row=9,column=0,columnspan=2,sticky='w',pady=8)
        def refresh_preview(*_):
            try:
                preview.configure(fg=self.caption_color.get(), font=(self.caption_font.get() or 'Arial', max(10, int(18*float(self.caption_size.get()))), 'bold'))
            except Exception:
                pass
        for var in (self.caption_color, self.caption_font, self.caption_size):
            var.trace_add('write', refresh_preview)
        ttk.Button(frame, text='Fechar', command=dialog.destroy).grid(row=10,column=1,sticky='e',pady=(18,0))

    def refresh_ollama(self):
        self.ollama_status.set("Ollama: verificando serviço local…")
        def work():
            try:
                from ldporto.ollama_local import service_info
                info = service_info("http://127.0.0.1:11434", timeout=2)
                names = [m.get("name") for m in info.get("models", []) if m.get("name")]
                def apply():
                    if info.get("reachable"):
                        self.ollama_status.set(f"Ollama {info.get('version') or ''}: {len(names)} modelo(s) instalado(s)" +
                                               (" · " + ", ".join(names[:4]) if names else " · nenhum modelo"))
                        if names:
                            self.ollama_combo.configure(values=names)
                            if self.ollama_model.get() not in names:
                                self.ollama_status.set(self.ollama_status.get()+' | modelo configurado ausente; escolha nao foi alterada')
                    else:
                        self.ollama_status.set("Ollama não respondeu em 127.0.0.1:11434. Use Configurar Ollama.")
                self.window.after(0, apply)
            except Exception as exc:
                from ldporto.core import scrub
                message=scrub(exc)
                self.window.after(0, lambda text=message: self.ollama_status.set('Ollama: '+text))
        threading.Thread(target=work, daemon=True).start()

    def configure_ollama(self):
        bat = ROOT/"CONFIGURAR_OLLAMA_MAXIMO_WINDOWS.bat"
        if os.name == "nt" and bat.is_file():
            os.startfile(str(bat))
        else:
            messagebox.showinfo("Ollama", "Veja docs/setup/LEIA_PRIMEIRO.md para instalar o Ollama e baixar um modelo.")


    def repair_gpu(self):
        bat = ROOT/"CORRIGIR_GPU_WINDOWS.bat"
        if os.name == "nt" and bat.is_file():
            os.startfile(str(bat))
        else:
            messagebox.showinfo("GPU", "Use o instalador CUDA/cuDNN correspondente ao seu sistema.")

    # Generated by GitHub Copilot - Oct-05-2026
    def diagnose_inference(self):
        if self.proc and self.proc.poll() is None or getattr(self, 'smoke_busy', False):
            return
        self.smoke_busy = True
        self.start_button.configure(state='disabled')
        try:
            cfg = load_config(ROOT / 'config' / 'config.yaml')
            cfg['device'] = self.device.get()
            cfg['diarization']['enabled'] = self.diarization.get()
            cfg['vision']['enabled'] = self.vision.get()
            cfg['ocr'].update(self.ocr_options())
            cfg['semantic_analysis'].update(backend='ollama' if self.ollama.get() else 'heuristic',
                                            model=self.ollama_model.get().strip())
        except Exception as exc:
            self.smoke_busy = False
            self.start_button.configure(state='normal')
            self.inference_smoke_status.set('Canario bloqueado na configuracao: ' + type(exc).__name__)
            return
        self.inference_smoke_status.set('Canario em execucao sequencial; qualidade nao medida')
        def work():
            from ldporto.inference_smoke import run_inference_smoke, save_smoke
            from datetime import datetime, timezone
            try:
                report = run_inference_smoke(cfg)
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                save_smoke(report, ROOT / 'diagnostics' / ('inference_smoke_' + stamp + '.json'))
                summary = '\n'.join(name + ': Model load verified=' + str(row['model_load_verified']) +
                    ' | Actual inference executed=' + str(row['inference_executed']) +
                    ' | ' + row['status'] + ' (' + row['reason'] + ')'
                    for name, row in report['capabilities'].items())
            except Exception as exc:
                summary = 'Canario falhou: ' + type(exc).__name__
            def apply():
                self.smoke_busy = False
                self.start_button.configure(state='normal')
                self.inference_smoke_status.set(summary)
            self.window.after(0, apply)
        threading.Thread(target=work, daemon=True).start()

    def diagnose(self):
        """Diagnose the selected GUI capabilities instead of unrelated defaults."""
        args = ["--doctor", "--device", self.device.get(),
                "--semantic", "ollama" if self.ollama.get() else "heuristic",
                "--ollama-model", self.ollama_model.get().strip(),
                "--ollama-profile", self.ollama_profile.get()]
        if not self.diarization.get():
            args.append("--no-diarization")
        if not self.vision.get():
            args.append("--no-vision")
        self.preflight_status.set("Preflight: verificando capacidades habilitadas")
        self.launch(args)

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == 'event':
                    self.handle_stage_event(value)
                elif kind == 'ocr_result':
                    self.handle_ocr_result(value)
                elif kind == 'media_result':
                    self.handle_media_result(value)
                    if self.closing_requested:
                        self.window.destroy()
                        return
                elif kind == 'body_smoke_result':
                    self.handle_body_smoke_result(value)
                    if self.closing_requested:
                        self.window.destroy()
                        return
                elif kind == 'project_progress':
                    self.project_status.set(value)
                elif kind == 'project_result':
                    self.project_busy = False
                    if value.get('path'):
                        self.project_path = Path(value['path'])
                    self.project_status.set('Dossiê: '+str(value.get('state'))+' | '+str(value.get('path') or value.get('error') or value.get('verification')))
                    if self.closing_requested:
                        self.window.destroy()
                        return
                elif kind == "line":
                    recent = getattr(self, '_recent_process_lines', None)
                    if isinstance(recent, list):
                        recent.append(scrub(value)[:6000])
                        if len(recent) > 400:
                            del recent[:-400]
                    if 'execução de backend de corpos:' in value and hasattr(self, 'body_status'):
                        self.body_status.set(value.strip())
                    if 'WARNING' in value or 'fallback' in value.casefold():
                        self.warning_count+=1
                    # Generated by GitHub Copilot - Oct-05-2026
                    if "00_preflight: READY" in value:
                        self.preflight_status.set(value.strip())
                    if "Preflight reprovado" in value or '"status": "ERROR"' in value:
                        self.preflight_status.set("Preflight: ERROR. Consulte o diagnostico abaixo.")
                    if "19_camera_director:" in value:
                        self.camera_summary.set(value.strip())
                    self.log.insert("end", value)
                    self.log.see("end")
                    if self.in_execution and not any(fragment in value.lower() for fragment in ('clearcut', 'created tensorflow lite xnnpack delegate', 'portable_clearcut_uploader.cc')):
                        self.execution_log.insert('end', value)
                        self.execution_log.see('end')
                        if int(self.execution_log.index('end-1c').split('.')[0]) > 80:
                            self.execution_log.delete('1.0', '20.0')
                elif kind == 'done':
                    self.start_button.configure(state="normal")
                    if value == 0:
                        self.update_camera_summary()
                    else:
                        self.failure_log_path = self.save_failure_diagnostic(value)
                    self.status.set("Finalizado. Consulte os avisos no relatório." if value == 0
                                    else "Processamento terminou com erro/interrupção. Veja o log.")
                    if self.in_execution:
                        self.show_completion(value)
                    if self.closing_requested:
                        self.window.destroy()
                        return
        except queue.Empty:
            pass
        self.refresh_execution()
        self.window.after(150, self.poll)

    def stop(self):
        if getattr(self, 'body_smoke_busy', False):
            self.body_smoke_cancel.set()
            process = getattr(self, 'body_smoke_proc', None)
            if process is not None and process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
            self.status.set('Interrompendo teste corporal curto; evidencia parcial permanece na pasta nova.')
            return
        if self.proc and self.proc.poll() is None:
            if self.output_folder:
                self.output_folder.mkdir(parents=True, exist_ok=True)
                (self.output_folder / 'CANCEL_REQUESTED').write_text('safe_stop_requested', encoding='ascii')
            self.status.set('Solicitando parada segura; finalizando unidade atual e salvando checkpoint.')
            self.execution_diagnostic.set(self.status.get())

    def open_results(self):
        folder = self.output_folder or ROOT/"analysis"
        report = folder/"report.html"
        if report.is_file():
            webbrowser.open(report.as_uri())
        elif folder.exists():
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                webbrowser.open(folder.as_uri())

    def visual_models(self):
        dialog = tk.Toplevel(self.window)
        dialog.title('Modelos visuais')
        from ldporto.paths import MODELS_DIR
        names = ['face_detection_yunet_2023mar.onnx', 'face_recognition_sface_2021dec.onnx', 'face_landmarker.task']
        missing = [name for name in names if not (MODELS_DIR/name).is_file()]
        ttk.Label(dialog, text=f'{len(missing)} modelos ausentes.\n' + '\n'.join(missing or ['Modelos presentes; o diagnóstico valida os checksums.']), padding=12).pack()
        command = f'"{sys.executable}" "{ROOT / "scripts/download_models.py"}"'
        def copy_command():
            self.window.clipboard_clear()
            self.window.clipboard_append(command)
        def download():
            def worker():
                proc = subprocess.run([sys.executable, str(ROOT/'scripts/download_models.py')], cwd=ROOT,
                                      capture_output=True, text=True, encoding='utf-8', errors='replace',
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.messages.put(('line', scrub(proc.stdout + proc.stderr)))
            threading.Thread(target=worker, daemon=True).start()
            dialog.destroy()
        ttk.Button(dialog, text='Baixar modelos', command=download).pack(pady=4)
        ttk.Button(dialog, text='Abrir pasta', command=lambda: os.startfile(str(MODELS_DIR))).pack(pady=4)
        ttk.Button(dialog, text='Copiar comando', command=copy_command).pack(pady=4)

    def clean_heavy(self):
        if self.project_busy or (self.proc and self.proc.poll() is None):
            messagebox.showinfo('Limpeza', 'Aguarde o processamento terminar.')
            return
        folder = self.output_folder or filedialog.askdirectory(title='Escolha a análise para visualizar a limpeza')
        if not folder:
            return
        from ldporto.storage_dialog import show_cleanup
        from ldporto.project_export import verify_project_export
        def export_selected(root):
            if self.project_busy or (self.proc and self.proc.poll() is None):
                return
            self.output_folder = Path(root)
            self.package_path = None
            try:
                pointer = json.loads((Path(root)/'second_curation_export.json').read_text(encoding='utf-8'))
                if pointer.get('path'):
                    self.package_path = Path(pointer['path'])
            except (OSError,ValueError):
                pass
            self.export_project_dossier()
        show_cleanup(self.window, folder, export_project=export_selected, export_verifier=verify_project_export,
                     application_busy=lambda:getattr(self,'project_busy',False) or (self.proc and self.proc.poll() is None))

    def close(self):
        if getattr(self, 'media_busy', False):
            self.closing_requested = True
            self.media_status.set('Concluindo a leitura do SHA256 antes de fechar…')
            return
        if self.project_busy:
            self.project_cancel.set()
            self.closing_requested = True
            self.project_status.set('Cancelando geração; aguardando fechamento seguro do manifest…')
            return
        if getattr(self, 'body_smoke_busy', False):
            if messagebox.askyesno('Fechar', 'Teste corporal em curso. Interromper e fechar?'):
                self.closing_requested = True
                self.stop()
            return
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Fechar", "Há processamento em curso. Interromper e fechar?"):
                return
            self.stop()
            self.closing_requested = True
            return
        self.window.destroy()


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 11):
        raise SystemExit('Use a .venv Python 3.11.x deste projeto. Veja README.md.')
    App(tk.Tk())
    tk.mainloop()
