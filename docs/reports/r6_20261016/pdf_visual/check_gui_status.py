"""Native hidden Tk status check. No media, model, network or export operation."""
from pathlib import Path
import importlib.util
import json
import tkinter as tk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location('r6_gui_visual_check', ROOT / 'app.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)

window = tk.Tk()
window.withdraw()
def forbidden(*args, **kwargs):
    raise AssertionError('status_check_started_external_operation')

try:
    with patch.object(gui.App, 'refresh_ollama', lambda self: None), \
         patch.object(gui.subprocess, 'Popen', forbidden), \
         patch.object(gui.threading, 'Thread', forbidden):
        app = gui.App(window)
        initial_status = app.project_status.get()
        assert app.auto_project_export.get() is False
        app.show_completion(0)
        app.project_path = Path(__file__).resolve().parent
        app.open_results_center()
        dialogs = [child for child in window.winfo_children() if isinstance(child, tk.Toplevel)]
        for dialog in dialogs:
            dialog.withdraw()
        window.update_idletasks()
        def widgets(parent):
            for widget in parent.winfo_children():
                yield widget
                yield from widgets(widget)
        buttons = [widget.cget('text') for dialog in dialogs for widget in widgets(dialog)
                   if isinstance(widget, gui.ttk.Button)]
        report = {'scope': 'native_hidden_tk_status_only_no_inference_or_external_operations',
            'initial_dossier_status': initial_status,
            'automatic_export_default': app.auto_project_export.get(),
            'completion_heading': app.final_heading.get(),
            'completion_readiness': app.final_readiness.get(),
            'results_center_count': len(dialogs), 'results_center_buttons': buttons,
            'worker_started': False, 'process_started': False,
            'inference_executed': False, 'network_accessed': False}
        assert dialogs and 'Verificar integridade' in buttons
        assert app.proc is None and not app.project_busy
        target = Path(__file__).resolve().parent / 'gui_status_result.json'
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True, indent=2))
finally:
    window.destroy()
