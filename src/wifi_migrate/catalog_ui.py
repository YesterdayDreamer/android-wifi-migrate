"""Local network browser and selection for derived exports."""
from pathlib import Path
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .catalog import classify
from .pdf import export_pdf
from .outputs import export_run
from .workflow import new_run


def build_catalog(workbench, window):
    records, run = workbench.records, workbench.run_path
    controls = ttk.Frame(window, padding=10)
    controls.pack(fill='x')
    query = tk.StringVar()
    ttk.Label(controls, text='搜索名称').pack(side='left')
    ttk.Entry(controls, textvariable=query).pack(side='left', padx=8, fill='x', expand=True)
    only_conflicts = tk.BooleanVar()
    ttk.Checkbutton(controls, text='只看同名记录', variable=only_conflicts).pack(side='left')
    table = ttk.Frame(window, padding=(10, 0))
    table.pack(fill='both', expand=True)
    tree = ttk.Treeview(table, columns=('ssid', 'security', 'status'), height=7,
                        show='headings', selectmode='extended')
    scroll = ttk.Scrollbar(table, orient='vertical', command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    by_id = {row['id']: row for row in records}
    labels = classify(records)
    sort_key = 'ssid'
    reverse = False

    def refresh(*_):
        tree.delete(*tree.get_children())
        rows = [(row['ssid'], ', '.join(row['security']), labels.get(row['id'], ''), row['id']) for row in records
                if query.get().casefold() in row['ssid'].casefold()
                and (not only_conflicts.get() or row['id'] in labels)]
        column = ('ssid', 'security', 'status').index(sort_key)
        for ssid, security, status, record_id in sorted(rows, key=lambda row: row[column].casefold(), reverse=reverse):
            tree.insert('', 'end', iid=record_id, values=(ssid, security, status))

    def sort(key):
        nonlocal sort_key, reverse
        reverse = not reverse if key == sort_key else False
        sort_key = key
        refresh()

    for key, title, width in [('ssid', '名称', 270), ('security', '认证', 220), ('status', '检查结果', 120)]:
        tree.heading(key, text=title, command=lambda column=key: sort(column))
        tree.column(key, width=width)
    query.trace_add('write', refresh)
    only_conflicts.trace_add('write', refresh)
    refresh()

    def show_key():
        if workbench.busy:
            return
        selected = tree.selection()
        if len(selected) == 1:
            messagebox.showinfo('所选网络的密钥', by_id[selected[0]]['password'] or '此条没有密钥。',
                                parent=workbench.root)

    def selection():
        return set(tree.selection()) or set(tree.get_children())

    def make_pdf():
        if workbench.busy or not selection():
            return
        selected = selection()
        target = filedialog.asksaveasfilename(parent=workbench.root, defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
        if target:
            workbench.task('正在排版 PDF…', lambda: export_pdf(run, target, selected),
                           lambda _: workbench.open_path(Path(target)))

    def export_selected(migrate=False):
        selected = selection()
        if workbench.busy or not selected:
            return
        rows = [row for row in records if row['id'] in selected]
        output = new_run()
        source = workbench.result_digest(run)
        digest = hashlib.sha256((source + ':' + ','.join(sorted(selected))).encode()).hexdigest()
        def done(summary):
            if migrate:
                workbench.use_subset(rows, output, summary)
            else:
                workbench.open_path(output)
        workbench.task('正在导出所选网络…', lambda: export_run(rows, output, digest, 'selected'), done)

    actions = ttk.Frame(window, padding=10)
    actions.pack(fill='x')
    for text, callback in [('查看密码', show_key), ('导出所选', export_selected),
                           ('生成 PDF', make_pdf), ('迁移所选 →', lambda: export_selected(True))]:
        ttk.Button(actions, text=text, command=callback).pack(side='left', padx=(0, 8))
    ttk.Label(actions, text='未选中时使用当前筛选').pack(side='right')
