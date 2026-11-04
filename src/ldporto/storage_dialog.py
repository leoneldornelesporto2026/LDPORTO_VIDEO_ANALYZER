"""Project inventory and recoverable cleanup, using the existing storage API."""
from pathlib import Path
import os
import queue
import threading
import webbrowser

from .storage import (cleanup_preview, execute_cleanup, list_projects,
                      list_quarantines, restore_preview, restore_quarantine)


def show_cleanup(parent, folder, source=None, export_project=None, export_verifier=None,
                 application_busy=None):
    """Open read only. Every quarantine/restore requires its own confirmation."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    window = tk.Toplevel(parent)
    window.title('GERENCIAR ESPAÇO / PROJETOS ANTERIORES')
    window.geometry('1120x720')
    window.transient(parent)
    summary = tk.StringVar(value='Lendo projetos; nenhum arquivo será alterado.')
    ttk.Label(window, textvariable=summary, padding=12, wraplength=1080).pack(anchor='w')
    ttk.Label(window, text='Vídeo original sempre protegido. Quarentena é recuperável e não libera espaço físico.',
              padding=(12, 0)).pack(anchor='w')
    columns = ('name', 'video_id', 'status', 'disk', 'regenerable', 'protected', 'export', 'integrity', 'last_used')
    tree = ttk.Treeview(window, columns=columns, show='headings', height=7)
    labels = ('Projeto', 'Vídeo ID', 'Estado', 'Disco', 'Regenerável', 'Protegido', 'Exportação', 'Integridade', 'Última alteração')
    for column, label in zip(columns, labels):
        tree.heading(column, text=label)
        tree.column(column, width=115 if column != 'name' else 230, minwidth=75)
    tree.pack(fill='x', padx=12, pady=8)
    scrollbar = ttk.Scrollbar(window, orient='horizontal', command=tree.xview)
    tree.configure(xscrollcommand=scrollbar.set)
    scrollbar.pack(fill='x', padx=12)
    text = tk.Text(window, height=14, wrap='word', state='disabled')
    text.pack(fill='both', expand=True, padx=12, pady=8)
    controls = ttk.Frame(window)
    controls.pack(fill='x', padx=12, pady=6)
    restore_controls = ttk.Frame(window)
    restore_controls.pack(fill='x', padx=12, pady=(0, 12))
    ttk.Label(restore_controls, text='Quarentena:').pack(side='left')
    quarantine_choice = ttk.Combobox(restore_controls, state='readonly', width=48)
    quarantine_choice.pack(side='left', padx=8)

    projects, plan, quarantines = [], None, []
    busy, closing = False, False
    cancel = threading.Event()
    messages = queue.Queue()
    buttons = []
    result = None
    last_application_busy = False

    def app_busy():
        try:
            return bool(application_busy and application_busy())
        except Exception:
            return True

    def mutation_allowed():
        if app_busy():
            messagebox.showinfo('Projeto em uso', 'Aguarde a operação da aplicação terminar.', parent=window)
            return False
        return True

    def cancel_requested():
        return cancel.is_set() or app_busy()

    def mb(value):
        return f'{value / 1024 ** 2:.2f} MB'

    def show_text(value):
        text.configure(state='normal')
        text.delete('1.0', 'end')
        text.insert('end', value)
        text.configure(state='disabled')

    def set_controls():
        for button in buttons:
            button.configure(state='disabled' if busy else 'normal')
        quarantine_button.configure(state='normal' if not busy and not app_busy() and plan and plan['removable'] else 'disabled')
        restore_button.configure(state='normal' if not busy and not app_busy() and quarantines else 'disabled')
        if export_project is None or app_busy():
            export_button.configure(state='disabled')

    def run(operation, done):
        nonlocal busy
        if busy:
            return
        busy = True
        cancel.clear()
        set_controls()
        def worker():
            try:
                messages.put((done, operation(), None))
            except Exception as exc:
                messages.put((done, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        nonlocal busy, last_application_busy
        current_application_busy = app_busy()
        if last_application_busy != current_application_busy:
            last_application_busy = current_application_busy
            set_controls()
        try:
            done, value, error = messages.get_nowait()
            busy = False
            set_controls()
            if closing:
                window.destroy()
                return
            if error:
                summary.set('Operação interrompida; consulte o erro. Arquivos preservados quando o movimento falhou.')
                messagebox.showerror('Gerenciar espaço', error, parent=window)
            else:
                done(value)
        except queue.Empty:
            pass
        if window.winfo_exists():
            window.after(100, poll)

    def selected():
        selection = tree.selection()
        return projects[int(selection[0][1:])] if selection else None

    def select_project(event=None):
        nonlocal plan
        if busy:
            return
        project = selected()
        if not project:
            return
        plan = None
        summary.set('Lendo arquivos regeneráveis e recibos; modo somente leitura.')
        def inspect():
            return cleanup_preview(project['root'], source), list_quarantines(project['root'])
        def display(value):
            nonlocal plan, quarantines
            plan, quarantines = value
            state = 'Projeto em uso: movimentação bloqueada. ' if plan['project_in_use'] else ''
            summary.set(state + f"Disco: {mb(plan['current_bytes'])} | Regeneráveis: {mb(plan['regenerable_bytes'])} | "
                        f"Protegidos: {mb(plan['preserved_bytes'])} | Em quarentena: {mb(plan['quarantine_bytes'])}")
            show_text(project['root'] + '\n\nPrévia — arquivos regeneráveis elegíveis para quarentena:\n' +
                      ''.join(f"{mb(row['bytes'])}  {row['relative_path']}\nSHA-256: {row['sha256']}\n"
                              for row in plan['removable']) +
                      '\nProtegidos: vídeo original, transcrições, JSONs, SRT, candidatos, câmera, pacotes, '
                      'contact sheets, relatórios, aprovações, revisões e renders finais.\n'
                      'Última utilização é aproximada pela alteração mais recente de artefato; não mede abertura.\n'
                      'Esta ferramenta não remove projetos inteiros nem apaga definitivamente a quarentena.')
            quarantine_choice.configure(values=[f"{row['quarantine_id']} | {mb(row['restorable_bytes'])}"
                                                 for row in quarantines])
            if quarantines:
                quarantine_choice.current(0)
            else:
                quarantine_choice.set('')
            set_controls()
        run(inspect, display)

    def refresh(verify=False):
        summary.set('Verificando exportações e inventário…' if verify else 'Lendo inventário; modo somente leitura…')
        def inspect():
            validator = export_verifier
            if verify and validator is None:
                from .project_export import verify_project_export
                validator = verify_project_export
            rows = list_projects(folder, export_verifier=validator if verify else None)
            if not rows:
                preview = cleanup_preview(folder, source)
                rows = [{'root': preview['root'], 'name': Path(folder).name, 'video_id': None,
                         'status': 'unavailable', 'disk_bytes': preview['current_bytes'],
                         'regenerable_bytes': preview['regenerable_bytes'], 'protected_bytes': preview['preserved_bytes'],
                         'export_exists': False, 'export_integrity': 'unavailable', 'last_used': None}]
            return rows
        def display(rows):
            nonlocal projects
            previous = selected()
            projects = rows
            tree.delete(*tree.get_children())
            for index, row in enumerate(rows):
                tree.insert('', 'end', iid=f'p{index}', values=(
                    row['name'], row.get('video_id') or 'não registrado', row['status'],
                    mb(row['disk_bytes']), mb(row['regenerable_bytes']), mb(row['protected_bytes']),
                    'existente' if row['export_exists'] else 'não localizada', row['export_integrity'],
                    row.get('last_used') or 'não registrado'))
            index = next((index for index, row in enumerate(rows)
                          if previous and row['root'] == previous['root']), 0)
            tree.selection_set(f'p{index}')
            select_project()
        run(inspect, display)

    def quarantine():
        if not mutation_allowed() or not plan or not plan['removable']:
            return
        if not messagebox.askyesno('Confirmar quarentena',
                f"Mover somente os {len(plan['removable'])} arquivos listados para quarentena recuperável?\n"
                'Nenhum espaço físico será liberado. O vídeo original permanece protegido.', parent=window):
            return
        def display(value):
            nonlocal result
            result = value
            messagebox.showinfo('Quarentena',
                f"Movidos: {mb(value['quarantined_bytes'])}. Espaço físico liberado: 0 MB.\n"
                f"Preservados/ignorados: {len(value['skipped'])}. Erros: {len(value['errors'])}.\n"
                'A restauração está disponível neste gerenciador.', parent=window)
            refresh()
        if mutation_allowed():
            run(lambda: execute_cleanup(plan, confirmed=True, cancel=cancel_requested), display)

    def restore():
        if not mutation_allowed():
            return
        project = selected()
        index = quarantine_choice.current()
        if not project or index < 0:
            return
        identifier = quarantines[index]['quarantine_id']
        def confirm(value):
            eligible = sum(row['restorable'] for row in value['files'])
            if not eligible:
                messagebox.showinfo('Restauração', 'Nenhum arquivo pode ser restaurado. Verifique colisões, hashes e uso do projeto.',
                                    parent=window)
                return
            if mutation_allowed() and messagebox.askyesno('Confirmar restauração',
                    f"Restaurar {eligible} arquivos ({mb(value['restorable_bytes'])})?\n"
                    'Destinos existentes, arquivos alterados ou em uso serão preservados.', parent=window):
                def display(restored):
                    messagebox.showinfo('Restauração',
                        f"Restaurados: {mb(restored['restored_bytes'])}. Ignorados: {len(restored['skipped'])}. "
                        f"Erros: {len(restored['errors'])}.", parent=window)
                    refresh()
                if mutation_allowed():
                    run(lambda: restore_quarantine(project['root'], identifier, confirmed=True, cancel=cancel_requested), display)
        run(lambda: restore_preview(project['root'], identifier), confirm)

    def open_folder():
        project = selected()
        if project:
            path = Path(project['root'])
            if os.name == 'nt':
                os.startfile(str(path))
            else:
                webbrowser.open(path.as_uri())

    def export_selected():
        project = selected()
        if project and export_project and mutation_allowed():
            export_project(project['root'])

    def close():
        nonlocal closing
        if busy:
            closing = True
            cancel.set()
            summary.set('Cancelamento solicitado; aguardando concluir a unidade atual com segurança.')
        else:
            window.destroy()

    def button(label, callback, container=controls):
        widget = ttk.Button(container, text=label, command=callback)
        widget.pack(side='left', padx=(0, 6))
        buttons.append(widget)
        return widget

    button('Atualizar inventário', refresh)
    button('Abrir pasta', open_folder)
    button('Verificar exportação', lambda: refresh(verify=True))
    export_button = button('Exportar antes da limpeza', export_selected)
    quarantine_button = button('Mover lista para quarentena', quarantine)
    restore_button = button('Restaurar selecionada', restore, restore_controls)
    ttk.Button(restore_controls, text='Cancelar / Fechar', command=close).pack(side='right')
    tree.bind('<<TreeviewSelect>>', select_project)
    window.protocol('WM_DELETE_WINDOW', close)
    set_controls()
    refresh()
    window.after(100, poll)
    window.wait_window()
    return result
