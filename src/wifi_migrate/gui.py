"""Small desktop workbench: phone actions happen only after an explicit click."""
from __future__ import annotations
import os
import json
import hashlib
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import webbrowser
from collections import Counter
from .adb import Adb, import_records, import_report_path
from .adb_runtime import OFFICIAL_PAGE, discover, install_platform_tools, remember
from .migration import ROUTE_LABELS, helper_results, recommend, record_event
from .archive import encrypted
from .workflow import new_run, convert_run, log_failure, windows_run
from .catalog_ui import build_catalog
from .formats import load
from .core import normalize
from .outputs import export_run
from .vault import archive_file, archive_history, file_digest, verify_archive
from .errors import MigrationError

SHIZUKU_DOWNLOAD = 'https://github.com/RikkaApps/Shizuku/releases'
WPM_DOWNLOAD = 'https://github.com/Khh-vu/wifi-password-manager/releases'


class Workbench:
    def __init__(self, root):
        self.root, self.events, self.busy = root, queue.Queue(), False
        self.run_path = None
        self.source_path = None
        self.ready_to_save = False
        self.trial_visible = False
        self.full_result = None
        self.controls = []
        self.result_controls = []
        self.phone_controls = {}
        self.capabilities = {}
        self.run_summary = {}
        self.route_pages = {}
        self.download_cancel = None
        self.labels = []
        self.records = None
        root.title('WiFi Migrate')
        root.geometry('1000x740')
        root.minsize(760, 640)
        root.report_callback_exception = self.callback_error
        self.adb_path = tk.StringVar(value=str(discover() or ""))
        self.device_ids = {role: tk.StringVar() for role in ("source", "target")}
        self.device_info = {role: tk.StringVar(value="尚未选择设备。") for role in self.device_ids}
        self.device_boxes = {}
        self.device_labels = {}
        self.recommendation = tk.StringVar(value="已有二维码可直接扫码；连接新机后可检测批量导入方式。")
        self.legacy = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='先选择已有资料，或连接旧手机备份。')
        self.summary = tk.StringVar(value='尚未读取资料。')
        self.save_plan = tk.StringVar(value='请先检测所选新手机。')
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='WiFi Migrate · 跨品牌 Wi-Fi 迁移', font=('', 20, 'bold')).pack(anchor='w')
        self.note(outer, variable=self.summary)
        self.build_devices(outer)
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True, pady=10)
        self.tabs.enable_traversal()
        self.home_page, self.source_page, self.catalog_page, self.target_page = (
            ttk.Frame(self.tabs, padding=12) for _ in range(4))
        for page, title in zip((self.home_page, self.source_page, self.catalog_page, self.target_page),
                               ('首页', '1  获取备份', '2  检查与导出', '3  迁移与结果')):
            self.tabs.add(page, text=title)
        self.build_home(self.home_page)
        self.build_source(self.source_page)
        self.build_exports(self.catalog_page)
        self.build_target(self.target_page)
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 6))
        self.cancel_download_button = ttk.Button(outer, text='取消下载', command=self.cancel_download)
        self.note(outer, variable=self.status)
        self.adb_path.trace_add('write', self.invalidate_devices)
        for role, variable in self.device_ids.items():
            variable.trace_add('write', lambda *_args, role=role: self.device_changed(role))
        outer.bind('<Configure>', self.resize_notes)
        self.update_controls()
        self.poll_id = root.after(100, self.poll)
        root.protocol('WM_DELETE_WINDOW', self.close)

    def note(self, parent, text='', *, variable=None):
        label = ttk.Label(parent, text=text, textvariable=variable, wraplength=650, justify='left')
        label.pack(fill='x', pady=(0, 6))
        self.labels.append(label)

    def action(self, parent, text, command, *, result=False, phone=False):
        button = ttk.Button(parent, text=text, command=command, padding=(8, 4))
        button.pack(side='left', padx=(0, 6), pady=3)
        self.controls.append(button)
        if result:
            self.result_controls.append(button)
        if phone:
            self.phone_controls[button] = 'target' if phone is True else phone
        return button

    def group(self, parent, text):
        frame = ttk.LabelFrame(parent, text=text, padding=(8, 4))
        frame.pack(fill='x', pady=(0, 7))
        return frame

    def build_devices(self, parent):
        panel = self.group(parent, '手机工具 · 打开本地备份不需要 ADB')
        panel.columnconfigure(0, weight=1)
        self.runtime_label = ttk.Label(panel, text=self.runtime_message())
        self.runtime_label.grid(row=0, column=0, sticky='w')
        choose = ttk.Button(panel, text='选择本地 ADB…', command=self.choose_adb)
        choose.grid(row=0, column=1, padx=4)
        download = ttk.Button(panel, text='从 Google 下载…', command=self.download_adb)
        download.grid(row=0, column=2)
        self.controls.extend((choose, download))

    def runtime_message(self):
        path = self.adb_path.get()
        if not path:
            return '未找到 ADB。操作手机时可选择本地工具或下载。'
        return 'ADB 已找到：' + Path(path).parent.name + ' / ' + Path(path).name

    def device_picker(self, page, role, title):
        panel = self.group(page, title)
        row = ttk.Frame(panel)
        row.pack(fill='x')
        box = ttk.Combobox(row, state='readonly')
        box.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.device_boxes[role] = box
        self.device_labels[role] = {}
        self.action(row, '查找设备', lambda: self.refresh(role))
        self.action(row, '清除选择', lambda: self.device_ids[role].set(''))
        def selected(_event):
            self.device_ids[role].set(self.device_labels[role][box.get()])
            self.check_role(role)
        box.bind('<<ComboboxSelected>>', selected)
        self.note(panel, variable=self.device_info[role])

    def build_home(self, page):
        self.note(page, '你要做什么？')
        for title, text, label, callback in [
            ('把 WiFi 带到新手机', '有备份可以直接打开。旧手机还在手边时，先检查它能怎样导出。', '开始迁移 →', lambda: self.tabs.select(self.source_page)),
            ('查看或整理已有备份', '离线查看网络、处理冲突，并导出 CSV、JSON、二维码或 PDF。', '打开备份…', self.choose_input),
            ('处理电脑保存的 WiFi', '读取当前 Windows 保存的网络，或导入已有的 WLAN XML。', 'Windows WiFi…', self.open_windows),
        ]:
            group = self.group(page, title)
            self.note(group, text)
            row = ttk.Frame(group)
            row.pack(fill='x')
            self.action(row, label, callback)

    def open_windows(self):
        window = tk.Toplevel(self.root)
        window.title('Windows WiFi')
        row = ttk.Frame(window, padding=16)
        row.pack()
        def start(callback):
            window.destroy()
            callback()
        if os.name == 'nt':
            ttk.Button(row, text='读取本机 WiFi', command=lambda: start(self.windows)).pack(side='left', padx=5)
        ttk.Button(row, text='打开 WLAN XML 目录…',
                   command=lambda: start(self.choose_directory)).pack(side='left', padx=5)

    def build_source(self, page):
        files = self.group(page, '我已经有备份文件')
        self.action(files, '打开备份或配置…', self.choose_input)
        self.action(files, '归档原文件…', self.archive_source)
        self.action(files, '归档历史', self.show_archives)
        self.device_picker(page, 'source', '旧手机还在手边')
        self.note(page, '没有现成文件时，按旧手机支持的能力选择下面任一方式。')
        routes = self.source_routes = ttk.Notebook(page)
        routes.pack(fill='both', expand=True)
        phone = ttk.Frame(routes, padding=8)
        backup = ttk.Frame(routes, padding=8)
        routes.add(phone, text='手机 App 导出')
        routes.add(backup, text='传统 ADB 备份')
        self.note(phone, '适用：旧机能运行 Shizuku，并能授权 WiFi Password Manager 读取已保存网络。安装两个 App 后启动 Shizuku，在手机导出到 Download，再在这里取回。')
        downloads = ttk.Frame(phone)
        downloads.pack(fill='x')
        self.app_links(downloads)
        self.action(downloads, '启动并打开旧机 Shizuku', lambda: self.start_shizuku('source'), phone='source')
        row = ttk.Frame(phone)
        row.pack(fill='x')
        self.action(row, '从旧机取回导出文件…', self.pull_source, phone='source')
        self.action(row, '使用说明', self.open_guide)
        self.note(backup, '适用：旧机无法使用手机 App 导出，且系统仍允许 ADB Backup 导出 WiFi 设置。无需安装两个 App。先连接旧机并授权调试，再在手机确认备份。')
        self.note(backup, '先用定向备份。即使命令成功，也要检查备份里是否真的有 WiFi 配置。已有旧备份可以直接在上方打开。')
        row = ttk.Frame(backup)
        row.pack(fill='x')
        self.action(row, '尝试传统 ADB 备份', self.backup, phone='source')
        legacy = ttk.Checkbutton(backup, text='高级：全量备份（含其他应用与共享存储）', variable=self.legacy)
        legacy.pack(anchor='w', pady=4)
        self.controls.append(legacy)

    def build_exports(self, page):
        self.catalog_body = ttk.Frame(page)
        self.catalog_body.pack(fill='both', expand=True)
        ttk.Label(self.catalog_body, text='读取备份后，这里会显示网络、认证类型和冲突。').pack(anchor='w')
        footer = ttk.Frame(page)
        footer.pack(fill='x', pady=(8, 0))
        self.action(footer, '打开完整输出', self.open_result, result=True)
        self.action(footer, '二维码清单', self.open_review, result=True)
        self.action(footer, '归档原文件…', self.archive_source, result=True)
        self.action(footer, '合并其他文件…', self.merge_file, result=True)
        self.action(footer, '进入迁移 →', lambda: self.tabs.select(self.target_page), result=True)

    def build_target(self, page):
        self.device_picker(page, 'target', '选择新手机 · 扫码可跳过连接')
        self.note(page, variable=self.recommendation)
        toolbar = ttk.Frame(page)
        toolbar.pack(fill='x', pady=(0, 4))
        self.restore_button = self.action(toolbar, '返回完整结果', self.restore_full, result=True)
        self.action(toolbar, '查看迁移结果', self.show_results, result=True)
        self.action(toolbar, '记录手机核对结果…', self.confirm_result, result=True)
        routes = self.routes = ttk.Notebook(page)
        routes.pack(fill='both', expand=True)
        for route, label in ROUTE_LABELS.items():
            frame = ttk.Frame(routes, padding=8)
            self.route_pages[route] = frame
            routes.add(frame, text=label)
        manager = self.route_pages['wpm']
        self.note(manager, '新机安装两个 App 并完成 Shizuku 授权。已有 WPM 原生明文 JSON 可直接在手机 App 导入。按当前范围生成的兼容 JSON 仍待真机验证，请先小批试用并核对 On-device。')
        downloads = ttk.Frame(manager)
        downloads.pack(fill='x')
        self.app_links(downloads)
        row = ttk.Frame(manager)
        row.pack(fill='x')
        self.action(row, 'USB 启动新机 Shizuku', lambda: self.start_shizuku('target'), phone=True)
        self.action(row, '复制生成的兼容 JSON', self.push_json, result=True, phone=True)
        helper = self.route_pages['helper']
        self.note(helper, '① 在所选手机安装 APK。② 复制 JSON。③ 点「在手机打开助手」后，在手机选择 Download 中的文件。助手图标只出现在安装它的手机应用列表。')
        row = ttk.Frame(helper)
        row.pack(fill='x')
        self.action(row, '安装助手 APK…', self.install_helper, phone=True)
        self.action(row, '复制 JSON', self.push_json, result=True, phone=True)
        self.action(row, '在手机打开助手', self.launch_helper, phone=True)
        self.action(row, '读入结果…', self.read_helper_result, result=True)
        direct = self.route_pages['adb']
        self.note(direct, '实验性。仅提交名称、密钥、认证、隐藏和可支持的自动加入设置。IP、DNS、代理、企业证书和 MAC 策略请另行核对。')
        row = ttk.Frame(direct)
        row.pack(fill='x')
        self.action(row, '检测并预览', self.dry_run, result=True, phone=True)
        self.write_controls = [
            self.action(row, '试存 1 条…', lambda: self.apply_import(1), result=True, phone=True),
            self.action(row, '批量保存 / 继续…', lambda: self.apply_import(None), result=True, phone=True),
        ]
        self.note(direct, variable=self.save_plan)
        scan = self.route_pages['qr']
        self.note(scan, '用新手机扫电脑屏幕，或复制二维码到相册。扫完请核对已保存列表及自动重连。')
        row = ttk.Frame(scan)
        row.pack(fill='x')
        self.action(row, '打开扫码清单', self.open_review, result=True)
        self.action(row, '复制二维码到手机', self.push, result=True, phone=True)
        self.routes.select(scan)

    def app_links(self, row):
        self.action(row, '下载 Shizuku', lambda: webbrowser.open(SHIZUKU_DOWNLOAD))
        self.action(row, '下载 WiFi Password Manager', lambda: webbrowser.open(WPM_DOWNLOAD))

    def start_shizuku(self, role):
        serial = self.device_ids[role].get()
        adb = self.adb()
        def work():
            message = adb.start_shizuku(serial)
            try:
                adb.open_shizuku(serial)
            except MigrationError as error:
                return message + ' ' + str(error)
            return '已在所选手机启动服务并打开 Shizuku。接下来打开 WiFi Password Manager 并授权。'
        def done(message):
            self.device_info[role].set(message)
            self.status.set(message)
        self.task(f'正在启动并打开 Shizuku（{serial}）…', work, done)

    def current_route(self):
        return next(route for route, page in self.route_pages.items() if str(page) == self.routes.select())

    def select_route(self, route, reason):
        self.routes.select(self.route_pages[route])
        self.recommendation.set(f'{ROUTE_LABELS[route]} · {reason}')

    def suggest_route(self):
        if not self.run_summary:
            self.select_route('qr', '读取来源备份后将按目标能力推荐。')
            return
        route, reason = recommend(self.capabilities.get('target', {}), self.run_summary.get('app_records', 0),
                                  self.run_summary.get('qr_written', 0))
        self.select_route(route, reason)

    def open_guide(self):
        self.open_path(Path(__file__).resolve().parents[2] / 'docs/toolkit.md')

    def reset_plan(self, *_):
        self.ready_to_save = False
        self.trial_visible = False
        self.save_plan.set('请先检测所选新手机。')
        self.update_controls()

    def resize_notes(self, event):
        for label in self.labels:
            label.configure(wraplength=max(250, event.width - 76))

    def update_controls(self, *_):
        for control in self.controls:
            blocked = (self.busy or
                       (control in self.result_controls and self.run_path is None) or
                       (control in self.phone_controls and not self.device_ids[self.phone_controls[control]].get())
                       or (self.phone_controls.get(control) == 'target' and self.same_device()) or
                       (control in self.write_controls and not self.ready_to_save) or
                       (control is self.write_controls[-1] and not self.trial_visible) or
                       (control is self.restore_button and self.full_result is None))
            control.state(['disabled' if blocked else '!disabled'])
        for box in self.device_boxes.values():
            box.state(['disabled' if self.busy else '!disabled'])

    def same_device(self):
        source = self.device_ids['source'].get()
        return bool(source and source == self.device_ids['target'].get())

    def device_changed(self, role):
        serial = self.device_ids[role].get()
        self.device_boxes[role].set(next((label for label, value in self.device_labels[role].items()
                                          if value == serial), serial))
        self.capabilities.pop(role, None)
        self.device_info[role].set('待检查。' if self.device_ids[role].get() else '尚未选择设备。')
        if role == 'target':
            self.reset_plan()
            self.suggest_route()
        if self.same_device():
            self.device_info['target'].set('目标与旧机相同，请另选新手机。')
        self.update_controls()

    def invalidate_devices(self, *_):
        for role, box in self.device_boxes.items():
            box['values'] = ()
            self.device_labels[role].clear()
            self.device_ids[role].set('')
        self.runtime_label.configure(text=self.runtime_message())
        self.status.set('ADB 已更改，请在旧机或新机页面查找设备。')

    def callback_error(self, kind, value, trace):
        text = str(value) if isinstance(value, MigrationError) else '操作未完成，请检查当前选择和运行环境。'
        self.status.set(text)
        messagebox.showerror('未完成', text, parent=self.root)

    def close(self):
        if self.busy:
            messagebox.showinfo('当前步骤仍在进行', '请先在手机确认或等待当前操作完成，再关闭窗口。', parent=self.root)
        else:
            self.root.after_cancel(self.poll_id)
            self.root.destroy()

    def choose_adb(self):
        path = filedialog.askopenfilename(title='选择完整 Platform Tools 目录中的 adb')
        if path:
            self.task('正在检查 ADB…', lambda: remember(path), self.runtime_ready)

    def download_adb(self):
        choice = messagebox.askyesnocancel('从 Google 下载 Platform Tools',
            '是：从 Google 下载至本机工具目录，使用即须遵守 Android SDK 条款。\n'
            '否：先打开 Google 下载页和条款。\n取消：返回。', parent=self.root)
        if choice is False:
            webbrowser.open(OFFICIAL_PAGE)
        elif choice is True:
            cancel = self.download_cancel = threading.Event()
            self.cancel_download_button.pack(anchor='e')
            def progress(size, total):
                if cancel.is_set():
                    raise MigrationError('已取消下载。')
                self.events.put(('progress', (size, total), None))
            self.task('正在下载官方 Platform Tools…', lambda: install_platform_tools(progress), self.runtime_ready)

    def cancel_download(self):
        if self.download_cancel is not None:
            self.download_cancel.set()
            self.cancel_download_button.pack_forget()

    def runtime_ready(self, result):
        path, version = result
        self.adb_path.set(str(path))
        self.status.set(version + '。现在可以查找设备。')

    def adb(self):
        return Adb(self.adb_path.get().strip() or None)

    def task(self, message, work, done=None):
        if self.busy:
            return
        self.busy = True
        self.update_controls()
        self.status.set(message)
        self.progress.start(12)
        def worker():
            try:
                result = work()
                self.events.put(('done', result, done))
            except Exception as error:
                log_failure('desktop', error)
                text = str(error) if isinstance(error, MigrationError) else '操作未完成，请检查输入格式、连接与运行环境。'
                self.events.put(('error', text, None))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, result, callback = self.events.get_nowait()
            if kind == 'progress':
                size, total = result
                tail = f' / {total / 1048576:.1f} MB' if total else ''
                self.status.set(f'下载 Platform Tools：{size / 1048576:.1f} MB{tail}')
                return
            self.busy = False
            self.progress.stop()
            self.download_cancel = None
            self.cancel_download_button.pack_forget()
            self.update_controls()
            if kind == 'error':
                self.status.set(result)
                messagebox.showerror('未完成', result, parent=self.root)
            elif callback:
                self.status.set('步骤完成。')
                callback(result)
            else:
                if result.get('mode') == 'dry-run':
                    self.ready_to_save = result['ready'] > 0
                    text = f"预览：{result['ready']} 条可尝试，{result['skipped']} 条需要其他方式。没有写入手机。"
                    if result.get('capabilities', {}).get('add_network_advertised') is False:
                        text += ' 未从该手机的帮助中识别到 ADB 保存命令。'
                    reasons = result.get('skip_reasons', {})
                    names = {'unsupported_security': '认证类型不支持', 'hidden_flag_unverified': '隐藏网络选项未识别',
                             'autojoin_flag_unverified': '自动加入选项未识别', 'missing_or_masked_key': '密钥缺失',
                             'command_or_security_not_advertised': '命令或该认证类型未声明',
                             'conflicting_same_ssid_requires_selection': '同名配置冲突'}
                    if reasons:
                        text += '\n跳过原因：' + '，'.join(f'{names.get(reason, reason)} {count} 条' for reason, count in reasons.items())
                    if result.get('wpa2_compatibility_only'):
                        text += f"\n其中 {result['wpa2_compatibility_only']} 条过渡网络只会提交 WPA2 兼容项。"
                    self.save_plan.set(text if self.ready_to_save else text + ' 可切换系统扫码或 Shizuku。')
                    self.status.set(text)
                    self.update_controls()
                elif result.get('mode') == 'apply':
                    report = import_report_path(self.run_path, self.device_ids['target'].get())
                    data = json.loads(report.read_text(encoding='utf-8'))['results'] if report.is_file() else {}
                    details = {'counts': {key: value for key, value in result.items() if type(value) is int},
                               'rows': [{'id': key, 'state': item['status']} for key, item in data.items()]}
                    self.log_migration('adb', 'SUBMITTED', 'adb_command_and_list_check', details=details)
                    self.status.set(f"已处理 {result['processed']} 条：列表可见 {result['saved_list_visible']}，尚未确认 {result['save_acknowledged_unverified']}，失败 {result['failed']}，跳过 {result['skipped']}。仍需在手机核对密码和联网。")
                elif 'copied' in result:
                    self.status.set(f"已复制 {result['copied']} 张二维码到手机的 WiFiMigrate 图片目录，请在相册或扫码入口检查。")
                else:
                    self.status.set('操作已完成，请检查结果。')
        except queue.Empty:
            pass
        finally:
            self.poll_id = self.root.after(100, self.poll)

    def refresh(self, role='target'):
        variable = self.device_ids[role]
        previous = variable.get()
        if not self.adb_path.get():
            self.status.set('ADB 未配置。请先选择本地 ADB 或从 Google 下载。')
            return
        adb = self.adb()
        def done(rows):
            ready = [row['serial'] for row in rows if row['state'] == 'device']
            self.device_labels[role] = {
                f"{row.get('model') or '型号未知'} · {row.get('transport') or '连接方式未知'} · {row['serial']}": row['serial']
                for row in rows if row['state'] == 'device'
            }
            self.device_boxes[role]['values'] = tuple(self.device_labels[role])
            other = self.device_ids['source' if role == 'target' else 'target'].get()
            candidates = [serial for serial in ready if serial != other]
            variable.set(previous if previous in candidates else candidates[0] if len(candidates) == 1 else '')
            if variable.get():
                self.check_role(role, rows)
            elif role == 'target' and len(ready) == 1 and ready[0] == other:
                self.status.set('唯一在线设备仍标为旧机。换接新机，或在旧机页清除选择后重新查找。')
            elif ready:
                self.status.set('请从列表明确选择设备，旧机和新机需分开。')
            else:
                unapproved = sum(row['state'] == 'unauthorized' for row in rows)
                offline = sum(row['state'] == 'offline' for row in rows)
                self.status.set(f'没有已授权设备（待授权 {unapproved}，离线 {offline}）。请检查 USB 调试和手机授权。')
        self.task('正在查找已授权设备…', adb.devices, done)

    def check_role(self, role, rows=()):
        serial = self.device_ids[role].get()
        if not serial or self.same_device():
            return
        adb = self.adb()
        def work():
            devices = rows or adb.devices()
            device = next((item for item in devices if item['serial'] == serial), {})
            return {**device, **adb.migration_status(serial)}
        def done(info):
            self.capabilities[role] = info
            model = info.get('model') or '型号未知'
            release = info.get('android_release') or '未知'
            transport = info.get('transport') or '未识别'
            text = f'{model} · Android {release} · {transport} · ADB 已授权'
            if info.get('wpm_installed') and info.get('shizuku_server_visible'):
                text += ' · 已检测到 App 和 Shizuku，权限在手机确认'
            elif role == 'source':
                if info.get('shizuku_package_visible'):
                    text += ' · 请在旧机检查 Shizuku，USB 也可启动'
                else:
                    text += ' · 可安装手机端工具，或尝试旧式备份'
            other = self.capabilities.get('source' if role == 'target' else 'target', {})
            if info.get('model') and info.get('model') == other.get('model'):
                text += ' · 两个角色型号相同，请核对是否为同一手机的 USB 与无线连接。'
            self.device_info[role].set(text)
            if role == 'target':
                self.suggest_route()
        self.task('正在只读检查所选设备…', work, done)

    def choose_input(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title='选择已有备份或配置')
        if path:
            self.read(Path(path))

    def choose_directory(self):
        if self.busy:
            return
        path = filedialog.askdirectory(title='选择 Windows 明文 WLAN XML 目录')
        if path:
            self.read(Path(path))

    def clear_result(self):
        self.run_path = self.records = None
        self.run_summary = {}
        self.source_path = None
        self.full_result = None
        self.summary.set('等待生成新结果。此前生成的文件仍可在 runs 目录找到。')
        for child in self.catalog_body.winfo_children():
            child.destroy()
        ttk.Label(self.catalog_body, text='读取备份后在此检查网络。').pack(anchor='w')
        self.reset_plan()

    def read(self, path):
        password = None
        try:
            needs_password = path.is_file() and encrypted(path)
        except Exception:
            needs_password = False
        if needs_password:
            password = simpledialog.askstring('备份密码', '输入备份时设置的密码（不会保存）：', show='*', parent=self.root)
            if password is None:
                return
        self.clear_result()
        self.source_path = path
        output = new_run()
        self.task('正在读取、校验并生成本地结果…',
                  lambda: convert_run(path, output, password), self.read_done)

    def read_done(self, result):
        self.records, self.run_path, summary = result
        self.run_summary = summary
        self.summary.set(f"本次结果：{summary['records']} 条网络，{summary['qr_written']} 张二维码。手机保存状态尚未验证。")
        elapsed = f"解析用时 {summary['parse_seconds']:.3f} 秒。 " if 'parse_seconds' in summary else ''
        self.status.set(elapsed + '结果：' + str(self.run_path.resolve()))
        if summary.get('qr_warning'):
            self.status.set(summary['qr_warning'])
        for child in self.catalog_body.winfo_children():
            child.destroy()
        build_catalog(self, self.catalog_body)
        self.reset_plan()
        self.suggest_route()
        self.tabs.select(self.catalog_page)

    def use_subset(self, rows, output, summary):
        if self.full_result is None:
            original_summary = json.loads((self.run_path / 'summary.json').read_text(encoding='utf-8'))
            self.full_result = self.records, self.run_path, original_summary
        self.read_done((rows, output, summary))
        self.summary.set(f'迁移范围：所选 {len(rows)} 条。可返回完整结果。')
        self.tabs.select(self.target_page)

    def restore_full(self):
        if self.full_result is not None:
            result, self.full_result = self.full_result, None
            self.read_done(result)

    def merge_file(self):
        name = filedialog.askopenfilename(title='选择要追加的未加密备份或配置')
        if not name:
            return
        original = self.full_result or (self.records, self.run_path, self.run_summary)
        records, run, summary = original
        output = new_run()
        def work():
            extra, digest, kind = load(name)
            combined = normalize([*records, *[{'source': kind, **row} for row in extra]])
            source = hashlib.sha256((summary['source_content_sha256'] + digest).encode()).hexdigest()
            return combined, output, export_run(combined, output, source, 'merged')
        def done(result):
            self.source_path = None
            self.full_result = None
            self.read_done(result)
        self.task('正在合并记录，原始文件和冲突条目会保留…', work, done)

    def backup(self):
        if self.busy:
            return
        serial, legacy, adb = self.device_ids['source'].get(), self.legacy.get(), self.adb()
        self.clear_result()
        output = new_run() / 'phone.adb'
        self.task('请在旧手机确认备份；完成后将检查并转换 WiFi 数据…',
                  lambda: adb.backup(serial, output, legacy), self.read)

    def windows(self):
        if self.busy or not messagebox.askyesno('读取本机 WiFi', '将在本地导出当前电脑的已保存网络及可读取的明文密钥，继续？', parent=self.root):
            return
        self.clear_result()
        output = new_run()
        self.task('正在读取 Windows 配置…', lambda: windows_run(output), self.read_done)

    def require_result(self):
        if not self.run_path or self.records is None:
            messagebox.showinfo('先读取资料', '请先在第一个页面读取备份或配置。', parent=self.root)
            return False
        return not self.busy

    def open_result(self):
        if self.require_result():
            self.open_path(self.run_path)

    def open_path(self, path):
        if os.name == 'nt':
            os.startfile(path.resolve())
        else:
            webbrowser.open(path.resolve().as_uri())

    def result_digest(self, run):
        summary = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
        return summary['source_content_sha256']

    def archive_source(self):
        source = self.source_path
        result = self.full_result[1] if self.full_result else self.run_path
        if source is None or not source.is_file():
            selected = filedialog.askopenfilename(title='选择要原样保存的原始文件')
            if not selected:
                return
            source, result = Path(selected), None
        root = Path('runs/archives')
        self.task('正在复制原件并核对 SHA-256…', lambda: archive_file(source, root, result),
                  lambda entry: self.open_path(Path(entry['archive'])))

    def show_archives(self):
        entries = archive_history(Path('runs/archives'))
        window = tk.Toplevel(self.root)
        window.title('原始备份归档')
        window.geometry('660x340')
        items = tk.Listbox(window)
        items.pack(fill='both', expand=True, padx=10, pady=10)
        for entry in entries:
            items.insert('end', f"{entry['created_utc']}   {entry['source_name']}   {entry['bytes']} 字节")
        def open_selected():
            selected = items.curselection()
            if selected:
                folder = Path(entries[selected[0]]['archive'])
                self.task('正在核对归档 SHA-256…', lambda: verify_archive(folder),
                          lambda _: self.open_path(folder))
        ttk.Button(window, text='校验并打开归档', command=open_selected).pack(anchor='e', padx=10, pady=(0, 10))

    def push_json(self):
        if self.same_device() or not self.require_result():
            return
        serial, adb, run = self.device_ids['target'].get(), self.adb(), self.run_path
        if not self.run_summary.get('app_records', 0):
            raise MigrationError('本次没有可供手机 App 导入的记录。请检查认证方式或改用扫码。')
        if messagebox.askyesno('复制明文备份', f'目标：{serial}。JSON 含密码，将复制到手机 Download 目录。继续？', parent=self.root):
            route = self.current_route()
            def done(remote):
                self.log_migration(route, 'TRANSFERRED', 'adb_file_copy', count=self.run_summary.get('app_records'))
                self.status.set('已复制，等待手机端确认。请在手机导入工具中打开：' + remote)
            self.task('正在复制导入 JSON…', lambda: adb.push_manager_json(
                serial, run / 'wifi-password-manager.json', new_run().name), done)

    def pull_source(self):
        name = simpledialog.askstring('取回导出文件', '输入旧机 Download 中的 JSON 或 GZip 文件名：', parent=self.root)
        if name:
            adb, serial, output = self.adb(), self.device_ids['source'].get(), new_run()
            self.task('正在从旧机复制备份…', lambda: adb.pull_download(serial, name, output), self.read)

    def install_helper(self):
        info = self.capabilities.get('target', {})
        sdk = str(info.get('sdk') or '')
        if sdk.isdecimal() and int(sdk) < 30:
            raise MigrationError('请先选择并检测 Android 11 或更新版本的新机。')
        project = Path(__file__).resolve().parents[2]
        bundled = sorted(project.parent.glob('wifi-migrate-importer-v*-debug.apk'), reverse=True)
        apk = str(bundled[0]) if len(bundled) == 1 else filedialog.askopenfilename(title='选择项目发布的 WiFi 导入助手 APK',
                                        initialdir=str(project.parent),
                                        initialfile=bundled[0].name if bundled else '',
                                        filetypes=[('Android APK', '*.apk')])
        serial = self.device_ids['target'].get()
        if apk and messagebox.askyesno('安装或更新助手', f'目标手机：{serial}\nAPK：{Path(apk).name}\n继续安装？', parent=self.root):
            adb = self.adb()
            self.task('正在安装助手…', lambda: adb.install_helper(serial, apk),
                      lambda _: self.status.set('已在新机核对助手安装。请复制 JSON 后打开助手。'))

    def launch_helper(self):
        adb, serial = self.adb(), self.device_ids['target'].get()
        self.task('正在打开手机助手…', lambda: adb.launch_helper(serial),
                  lambda _: self.status.set('请在手机上选择 JSON 并按系统提示确认。'))

    def read_helper_result(self):
        path = filedialog.askopenfilename(title='选择手机导入助手保存的结果 JSON')
        if path:
            digest = file_digest(self.run_path / 'wifi-password-manager.json')
            source_count = len(json.loads((self.run_path / 'wifi-password-manager.json').read_text(encoding='utf-8')))
            details = helper_results(path, digest, source_count)
            legacy = details['report_version'] == 1
            if not legacy:
                details['counts'] = dict(Counter(row['state'] for row in details['rows']))
            else:
                for row in details['rows']:
                    row['reported_state'] = row.pop('state')
            evidence = 'legacy_helper_report_unverified' if legacy else 'imported_helper_report'
            self.log_migration('helper', 'UNKNOWN' if legacy else 'SUBMITTED', evidence, details=details)
            self.show_results()

    def log_migration(self, route, state, evidence, **fields):
        return record_event(self.run_path, route, self.device_ids['target'].get(), state,
                            evidence=evidence, **fields)

    def confirm_result(self):
        choice = messagebox.askyesnocancel('记录人工核对',
            '是：已验证关开 WiFi 后自动重连。\n否：只在系统已保存列表核对。\n取消：返回。', parent=self.root)
        if choice is None:
            return
        count = simpledialog.askinteger('核对条数', '你实际核对了多少条？', minvalue=1,
                                        maxvalue=len(self.records), parent=self.root)
        if count:
            self.log_migration(self.current_route(), 'AUTO_RECONNECT_VERIFIED' if choice else 'SYSTEM_VISIBLE',
                               'user_confirmed', count=count)
            self.show_results()

    def show_results(self):
        path = self.run_path / 'migration-results.json'
        events = json.loads(path.read_text(encoding='utf-8'))['events'] if path.exists() else []
        window = tk.Toplevel(self.root)
        window.title('迁移结果与证据')
        window.geometry('730x430')
        summary = self.run_summary
        ttk.Label(window, padding=10, text=f"总数 / 已解析：{summary.get('records', 0)}   App JSON：{summary.get('app_records', 0)}   二维码：{summary.get('qr_written', 0)}").pack(anchor='w')
        body = tk.Text(window, wrap='word', padx=10, pady=8)
        body.pack(fill='both', expand=True)
        names = {'TRANSFERRED': '已复制文件，等待手机操作', 'SUBMITTED': '收到提交结果',
                 'SYSTEM_VISIBLE': '用户已核对系统列表', 'AUTO_RECONNECT_VERIFIED': '用户已验证自动重连'}
        for event in events:
            route, state, evidence = event['route'], event['state'], event['evidence']
            count = f"（{event['count']} 条）" if 'count' in event else ''
            body.insert('end', f"{event['time']}  {ROUTE_LABELS[route]}  {names.get(state, state)}{count}\n"
                               f"证据：{evidence}  目标：{event['target'] or '未记录'}\n")
            details = event.get('details', {})
            if details:
                if evidence == 'legacy_helper_report_unverified':
                    body.insert('end', '旧版助手报告，仅展示自报状态，缺少逐条 ID 和批次证据。\n')
                body.insert('end', json.dumps(details, ensure_ascii=False, indent=2) + '\n')
        if not events:
            body.insert('end', '尚无手机迁移结果。导出文件本身不代表手机已保存。')
        body.configure(state='disabled')
        if events:
            ttk.Button(window, text='打开报告文件夹', command=lambda: self.open_path(path.parent)).pack(anchor='e', padx=10, pady=8)

    def open_review(self):
        if self.require_result():
            webbrowser.open((self.run_path / 'review.html').resolve().as_uri())

    def push(self):
        serial = self.device_ids['target'].get()
        if self.same_device() or not self.require_result() or not messagebox.askyesno('复制二维码到所选设备', f'目标设备：{serial}\n只复制二维码到 WiFiMigrate 图片目录。继续？', parent=self.root):
            return
        adb, serial, run = self.adb(), self.device_ids['target'].get(), self.run_path
        def done(result):
            self.log_migration('qr', 'TRANSFERRED', 'adb_file_copy', count=result['copied'])
            self.status.set(f"已复制 {result['copied']} 张二维码。请在手机扫码后核对。")
        self.task('正在复制二维码…', lambda: adb.push_qr(serial, run), done)

    def dry_run(self):
        self.reset_plan()
        self.import_job(False, None)

    def apply_import(self, limit):
        if (self.same_device() or not self.ready_to_save or not self.require_result()
                or (limit is None and not self.trial_visible)):
            return
        serial = self.device_ids['target'].get()
        prompt = ('我已在目标手机的系统 WiFi 列表中核对试存条目。确认继续批量添加或更新网络？'
                  if limit is None else '仅试存一条，可能更新同名配置。继续？')
        if messagebox.askyesno('向所选新手机保存网络', f'目标设备：{serial}\n{prompt}', parent=self.root):
            if limit is None:
                self.log_migration('adb', 'SYSTEM_VISIBLE', 'user_confirmed_trial', count=1)
            else:
                self.trial_visible = False
            self.import_job(True, limit)

    def import_job(self, apply, limit):
        if not self.require_result():
            return
        adb, serial, records, run = self.adb(), self.device_ids['target'].get(), self.records, self.run_path
        confirmed = apply and limit is None and self.trial_visible
        report = import_report_path(run, serial)
        def trial_done(result):
            self.trial_visible = result['saved_list_visible'] == 1 and result['failed'] == 0
            self.log_migration('adb', 'SUBMITTED', 'adb_trial_command',
                               details={'acknowledged': result['saved_list_visible'] + result['save_acknowledged_unverified']})
            if self.trial_visible:
                self.log_migration('adb', 'SYSTEM_VISIBLE', 'adb_trial_list_readback', count=1)
            message = ('已在系统列表回读试存条目，请在手机核对后再批量保存。' if self.trial_visible else
                       '试存未通过系统列表回读。请检查手机或改用其他方式，批量保存保持禁用。')
            self.save_plan.set(message)
            self.status.set(message)
            self.update_controls()
        self.task('正在检测和处理新手机；只有明确保存操作才会写入…',
                  lambda: import_records(adb, serial, records, report, apply=apply,
                                         first_ready=limit == 1, resume=True, confirm_trial=confirmed,
                                         source_id=str(run.resolve())),
                  trial_done if apply and limit == 1 else None)


def launch():
    root = tk.Tk()
    Workbench(root)
    root.mainloop()
