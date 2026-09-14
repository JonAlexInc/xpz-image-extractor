"""Windows desktop front end for xpz_core."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from xpz_core import extract_file

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('XPZ Image Extractor')
        self.geometry('980x700')
        self.minsize(840, 610)
        self.configure(background='#f4f6f9')
        self.files = {}
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.busy = False
        self.last_output = None
        self.output = tk.StringVar(value=str(ROOT / 'Extracted Images'))
        self.recursive = tk.BooleanVar(value=True)
        self.layout = tk.StringVar(value='Auto')
        self.status = tk.StringVar(value='Add files or a folder to get started.')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#f4f6f9')
        style.configure('TLabel', background='#f4f6f9')
        style.configure('TCheckbutton', background='#f4f6f9')
        style.configure('TButton', padding=(12, 7))
        style.configure('Treeview', rowheight=28)
        style.configure('Go.TButton', background='#2463ba', foreground='white')
        style.map('Go.TButton', background=[('active', '#174b91'), ('disabled', '#adb8c6')])
        body = ttk.Frame(self, padding=22)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='XPZ Image Extractor', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(body, text='Choose files or a folder. Export supported Xbox textures as transparent PNGs.').pack(anchor='w', pady=(3, 16))
        toolbar = ttk.Frame(body)
        toolbar.pack(fill='x')
        self.controls = []
        for label, action in [('Add files…', self.add_files), ('Add folder…', self.add_folder), ('Remove selected', self.remove), ('Clear', self.clear)]:
            button = ttk.Button(toolbar, text=label, command=action)
            button.pack(side='left', padx=(0, 7))
            self.controls.append(button)
        recursive = ttk.Checkbutton(toolbar, text='Include subfolders', variable=self.recursive)
        recursive.pack(side='right')
        self.controls.append(recursive)
        table = ttk.Frame(body)
        table.pack(fill='both', expand=True, pady=12)
        self.tree = ttk.Treeview(table, columns=('file', 'folder', 'status'), show='headings', selectmode='extended')
        for col, label, width in [('file', 'File', 205), ('folder', 'Location', 440), ('status', 'Result', 220)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, minwidth=90)
        scrollbar = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        output_row = ttk.Frame(body)
        output_row.pack(fill='x', pady=(0, 8))
        ttk.Label(output_row, text='Save to').pack(side='left', padx=(0, 10))
        entry = ttk.Entry(output_row, textvariable=self.output)
        entry.pack(side='left', fill='x', expand=True)
        browse = ttk.Button(output_row, text='Browse…', command=self.choose_output)
        browse.pack(side='left', padx=(8, 0))
        self.controls.extend([entry, browse])
        options = ttk.Frame(body)
        options.pack(fill='x', pady=(0, 10))
        ttk.Label(options, text='Texture row layout').pack(side='left', padx=(0, 10))
        self.combo = ttk.Combobox(options, state='readonly', values=('Auto', 'Tight rows', 'GPU pitch'), textvariable=self.layout, width=13)
        self.combo.pack(side='left')
        ttk.Label(options, text='Leave on Auto unless a report asks you to choose.').pack(side='left', padx=12)
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        self.go = ttk.Button(actions, text='Extract all queued files', style='Go.TButton', command=self.start)
        self.go.pack(side='left')
        self.stop = ttk.Button(actions, text='Cancel', command=self.cancel, state='disabled')
        self.stop.pack(side='left', padx=8)
        ttk.Button(actions, text='Open output folder', command=self.open_output).pack(side='right')
        self.progress = ttk.Progressbar(body)
        self.progress.pack(fill='x', pady=(12, 6))
        ttk.Label(body, textvariable=self.status).pack(anchor='w')
        self.log = tk.Text(body, height=5, wrap='word', font=('Segoe UI', 9), background='white', relief='solid', borderwidth=1, state='disabled')
        self.log.pack(fill='x', pady=(10, 6))
        ttk.Label(body, text='Supports selected XPR0 / XPR1 formats, not every .xpz variant. Images only; menu layouts are not reconstructed.', font=('Segoe UI', 9)).pack(anchor='w')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def append_log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def add_paths(self, paths):
        known = {str(path).casefold() for path in self.files.values()}
        for path in paths:
            path = Path(path).resolve()
            if str(path).casefold() not in known:
                iid = self.tree.insert('', 'end', values=(path.name, str(path.parent), 'Ready'))
                self.files[iid] = path
                known.add(str(path).casefold())
        self.status.set(f'{len(self.files)} file(s) queued. Choose an output folder, then extract.')

    def add_files(self):
        paths = filedialog.askopenfilenames(parent=self, title='Select one or more files', filetypes=[('Xbox resources', '*.xpz *.xpr *.xbx'), ('All files', '*.*')])
        self.add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self, title='Choose a folder to search for XPZ / XPR files')
        if not folder:
            return
        recursive = self.recursive.get()
        self.set_busy(True)
        self.status.set('Finding files…')
        def scan():
            found = []
            errors = []
            for base, dirs, names in os.walk(folder, onerror=lambda exc: errors.append(str(exc)), followlinks=False):
                if self.cancelled.is_set():
                    break
                for name in names:
                    if Path(name).suffix.lower() in ('.xpz', '.xpr', '.xbx'):
                        found.append(Path(base) / name)
                if not recursive:
                    break
            self.events.put(('scan', found, errors))
        threading.Thread(target=scan, daemon=True).start()

    def remove(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.files.pop(iid, None)
        self.status.set(f'{len(self.files)} file(s) queued.')

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.files.clear()
        self.status.set('Queue cleared.')

    def choose_output(self):
        folder = filedialog.askdirectory(parent=self, title='Choose where to save extracted images')
        if folder:
            self.output.set(folder)

    def set_busy(self, value):
        self.busy = value
        if value:
            self.cancelled.clear()
        for control in self.controls + [self.go]:
            control.configure(state='disabled' if value else 'normal')
        self.combo.configure(state='disabled' if value else 'readonly')
        self.stop.configure(state='normal' if value else 'disabled')

    def start(self):
        if not self.files:
            messagebox.showinfo('No files selected', 'Use Add files or Add folder first.', parent=self)
            return
        if not self.output.get().strip():
            messagebox.showerror('Choose output', 'Choose a folder for the extracted PNGs.', parent=self)
            return
        try:
            root = Path(self.output.get()).expanduser().resolve()
            run = root / datetime.now().strftime('Extraction_%Y-%m-%d_%H-%M-%S_%f')
            run.mkdir(parents=True)
        except OSError as exc:
            messagebox.showerror('Cannot create output folder', str(exc), parent=self)
            return
        self.last_output = run
        selected = list(self.files.items())
        layout = self.layout.get()
        self.set_busy(True)
        self.progress.configure(maximum=len(selected), value=0)
        self.append_log(f'Saving to {run}')
        for iid, _ in selected:
            self.tree.set(iid, 'status', 'Waiting')
        threading.Thread(target=self.worker, args=(selected, run, layout), daemon=True).start()

    def worker(self, selected, run, layout):
        summary = []
        for index, (iid, source) in enumerate(selected):
            if self.cancelled.is_set():
                break
            self.events.put(('current', iid, source.name))
            key = hashlib.sha256(str(source).encode()).hexdigest()[:8]
            from xpz_core import safe_name
            target = run / f'{index+1:04d}_{safe_name(source.stem)}_{key}'
            try:
                report = extract_file(source, target, layout, self.cancelled.is_set)
                result = f'{report["exported"]} PNGs; {report["skipped"]} skipped'
                if report['cancelled']:
                    result += ' (cancelled)'
                for entry in report['textures']:
                    if entry['status'] == 'skipped':
                        self.events.put(('log', f'{source.name} / {entry["name"]}: {entry["reason"]}'))
                summary.append(dict(source=str(source), output=str(target), exported=report['exported'], skipped=report['skipped'], cancelled=report['cancelled']))
            except Exception as exc:
                result = 'Failed / unsupported'
                summary.append(dict(source=str(source), error=str(exc)))
                self.events.put(('log', f'{source.name}: {exc}'))
            self.events.put(('result', iid, result, index+1))
        try:
            (run / 'batch_report.json').write_text(json.dumps(dict(cancelled=self.cancelled.is_set(), files=summary), indent=2), encoding='utf-8')
        except OSError as exc:
            self.events.put(('log', f'Could not save batch report: {exc}'))
        count = sum(item.get('exported', 0) for item in summary)
        failures = sum('error' in item for item in summary)
        skipped = sum(item.get('skipped', 0) for item in summary)
        self.events.put(('done', count, failures, skipped))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == 'scan':
                    self.set_busy(False)
                    self.add_paths(event[1])
                    for error in event[2]:
                        self.append_log(error)
                    if not event[1]:
                        self.append_log('No matching files were found.')
                elif kind == 'current':
                    self.tree.set(event[1], 'status', 'Extracting…')
                    self.status.set(f'Extracting {event[2]}…')
                elif kind == 'result':
                    self.tree.set(event[1], 'status', event[2])
                    self.progress.configure(value=event[3])
                elif kind == 'log':
                    self.append_log(event[1])
                elif kind == 'done':
                    cancelled = self.cancelled.is_set()
                    self.set_busy(False)
                    for iid in self.files:
                        if self.tree.set(iid, 'status') == 'Waiting':
                            self.tree.set(iid, 'status', 'Not processed')
                    label = 'Cancelled' if cancelled else 'Finished'
                    self.status.set(f'{label}: {event[1]} PNGs, {event[2]} failed files, {event[3]} skipped resources.')
                    self.append_log(self.status.get() + ' Details are in the output reports.')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def cancel(self):
        self.cancelled.set()
        self.stop.configure(state='disabled')
        self.status.set('Cancelling after the current image finishes…')

    def open_output(self):
        target = self.last_output or Path(self.output.get())
        if target.is_dir():
            os.startfile(str(target))
        else:
            messagebox.showinfo('No output yet', 'Extract files first, or choose an existing output folder.', parent=self)

    def close(self):
        if self.busy:
            self.cancel()
            self.append_log('Wait for cancellation to finish, then close the window.')
        else:
            self.destroy()


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--verify-extraction':
        # Packaging check: exercise bundled Tcl/Tk and the real extraction engine.
        app = App()
        app.withdraw()
        app.update()
        app.destroy()
        report = extract_file(Path(sys.argv[2]), Path(sys.argv[3]))
        raise SystemExit(0 if report['exported'] and not report['skipped'] else 1)
    App().mainloop()
