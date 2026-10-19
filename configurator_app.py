"""Miles Language Lab — offline native-subtitle configurator."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from configuration import LANGUAGES, Profile
from configurator_backend import (ROOT, app_data, apply_profile, inspect_game, restore_game,
                                  work_directory, java_command)
from patch import atomic_write, game_running

TITLE = '迈尔斯 · 多语言字幕工具'
NONE = '关闭这一层'
LABELS = {code: lang.label for code, lang in LANGUAGES.items()}
CODES = {label: code for code, label in LABELS.items()}


def read_game_resolution():
    """Read graphics settings only. No registry writes and no desktop/DPI guess."""
    if os.name != 'nt':
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           "Software\\Insomniac Games\\Marvel's Spider-Man Miles Morales\\Graphics") as key:
            values = {winreg.EnumValue(key, i)[0]: winreg.EnumValue(key, i)[1]
                      for i in range(winreg.QueryInfoKey(key)[1])}
        full = values.get('Fullscreen', values.get('FullScreen', 1))
        prefix = 'Fullscreen' if full else 'Window'
        width, height = values[prefix + 'Width'], values[prefix + 'Height']
        if type(width) is int and type(height) is int and 480 <= width <= 16384 and 480 <= height <= 16384:
            return width, height
    except (OSError, KeyError):
        pass
    return None


class Configurator:
    def __init__(self, root, game=None):
        self.root = root
        self.root.title(TITLE)
        width = min(1120, root.winfo_screenwidth() - 80)
        height = min(850, root.winfo_screenheight() - 110)
        self.root.geometry(f'{width}x{height}')
        self.root.minsize(min(960, width), min(640, height))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.busy = False
        self.events = queue.Queue()
        self.widgets = []
        self.profile = Profile()
        self.inspected_game = None
        self.applied_profile = None
        self.vars = {}
        resolution = read_game_resolution()
        if resolution:
            self.profile = replace(self.profile, output_width=resolution[0], output_height=resolution[1])
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', font=('Microsoft YaHei UI', 10))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 22, 'bold'))
        style.configure('Sub.TLabel', foreground='#637181')
        style.configure('Apply.TButton', font=('Microsoft YaHei UI', 11, 'bold'), padding=(16, 11))
        style.configure('TButton', padding=(10, 7))
        self.root.configure(bg='#f0f2f5')
        outer = ttk.Frame(root, padding=22)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='MILES / LANGUAGE LAB', style='Sub.TLabel').pack(anchor='w')
        ttk.Label(outer, text='把游戏变成你的语言课堂', style='Title.TLabel').pack(anchor='w', pady=(3, 6))
        ttk.Label(outer, text='原生双层字幕 · 英语配音 · 本地生成与安装', style='Sub.TLabel').pack(anchor='w')

        directory = ttk.Frame(outer)
        directory.pack(fill='x', pady=(18, 6))
        self.game_var = tk.StringVar(value=str(game or self.initial_game()))
        self.entry = ttk.Entry(directory, textvariable=self.game_var)
        self.entry.pack(side='left', fill='x', expand=True)
        self.widgets.append(self.entry)
        self.button(directory, '选择游戏目录', self.choose_game).pack(side='left', padx=(8, 0))
        self.button(directory, '检查', self.check).pack(side='left', padx=(8, 0))
        self.game_status = tk.StringVar(value='选择包含 MilesMorales.exe 的目录；支持资源版本 4.0630.0.0。')
        ttk.Label(outer, textvariable=self.game_status, style='Sub.TLabel', wraplength=1050).pack(anchor='w', pady=(0, 12))

        body_shell = ttk.Frame(outer)
        body_shell.pack(fill='both', expand=True)
        body_canvas = tk.Canvas(body_shell, highlightthickness=0, height=380)
        scrollbar = ttk.Scrollbar(body_shell, orient='vertical', command=body_canvas.yview)
        scrollbar.pack(side='right', fill='y')
        body_canvas.pack(side='left', fill='both', expand=True)
        body_canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(body_canvas)
        body_item = body_canvas.create_window(0, 0, anchor='nw', window=body)
        body.bind('<Configure>', lambda event: body_canvas.configure(scrollregion=body_canvas.bbox('all')))
        body_canvas.bind('<Configure>', lambda event: body_canvas.itemconfigure(body_item, width=event.width))
        body_canvas.bind('<MouseWheel>', lambda event: body_canvas.yview_scroll(-int(event.delta / 120), 'units'))
        left = ttk.Frame(body, width=350)
        left.pack(side='left', fill='y', padx=(0, 20))
        self.layer_controls(left, 'top', '顶部辅助字幕')
        self.button(left, '⇅  交换上下语言', self.swap).pack(fill='x', pady=8)
        self.layer_controls(left, 'bottom', '底部主字幕')
        screen = ttk.LabelFrame(left, text='游戏输出画面', padding=12)
        screen.pack(fill='x', pady=(12, 0))
        row = ttk.Frame(screen)
        row.pack(fill='x')
        self.number(row, 'output_width', self.profile.output_width, 480, 16384, width=7).pack(side='left')
        ttk.Label(row, text=' × ').pack(side='left')
        self.number(row, 'output_height', self.profile.output_height, 480, 16384, width=7).pack(side='left')
        self.button(screen, '读取游戏分辨率', self.detect_resolution).pack(fill='x', pady=(8, 0))
        ttk.Label(screen, text='更改游戏分辨率后需重新应用。\n字号按 1080 高界面单位缩放。', style='Sub.TLabel').pack(anchor='w', pady=(7, 0))

        right = ttk.Frame(body)
        right.pack(side='left', fill='both', expand=True)
        ttk.Label(right, text='字幕布局预览', font=('Microsoft YaHei UI', 12, 'bold')).pack(anchor='w')
        self.canvas = tk.Canvas(right, bg='#111c2e', highlightthickness=0, height=320)
        self.canvas.pack(fill='both', expand=True, pady=(9, 8))
        self.canvas.bind('<Configure>', lambda event: self.preview())
        ttk.Label(right, text='示意预览：字体与换行以游戏内显示为准。', style='Sub.TLabel').pack(anchor='w')
        self.validation = tk.StringVar(value='22 种语言文本已审计，字形样例已实测；各语言完整剧情同步仍待验证。')
        ttk.Label(right, textvariable=self.validation, wraplength=580, foreground='#8a5b21').pack(anchor='w', pady=(12, 7))
        ttk.Label(right, text='开始前：在游戏中开启字幕，文本语言设为简体中文，配音设为英语。\n工具只修改对话字幕，菜单继续使用原有中文。', wraplength=580, style='Sub.TLabel').pack(anchor='w')
        profiles = ttk.Frame(right)
        profiles.pack(fill='x', pady=(15, 0))
        self.button(profiles, '导入配置', self.import_profile).pack(side='left')
        self.button(profiles, '导出配置', self.export_profile).pack(side='left', padx=8)
        self.button(profiles, '恢复默认设置', self.defaults).pack(side='left')

        footer = ttk.Frame(outer)
        footer.pack(fill='x', pady=(18, 0))
        self.button(footer, '生成并应用字幕', self.apply, style='Apply.TButton').pack(side='left')
        self.button(footer, '还原原版字幕', self.restore).pack(side='left', padx=9)
        self.button(footer, '启动游戏', self.launch).pack(side='right')
        self.button(footer, '打开报告目录', self.open_report).pack(side='right', padx=9)
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(12, 5))
        self.status = tk.StringVar(value='就绪。配置保存在本机，游戏运行时不能安装或还原。')
        ttk.Label(outer, textvariable=self.status, wraplength=1050).pack(anchor='w')
        self.root.after(100, self.poll)
        self.root.after(250, self.check)

    def initial_game(self):
        try:
            saved = json.loads((app_data() / 'preferences.json').read_text(encoding='utf-8'))
            if Path(saved['game']).is_dir():
                return saved['game']
        except (OSError, ValueError, KeyError):
            pass
        return ROOT.parent if (ROOT.parent / 'MilesMorales.exe').is_file() else ''

    def button(self, parent, label, command, **kwargs):
        widget = ttk.Button(parent, text=label, command=command, **kwargs)
        self.widgets.append(widget)
        return widget

    def number(self, parent, name, value, low, high, width=8):
        var = tk.StringVar(value=str(value))
        self.vars[name] = var
        var.trace_add('write', lambda *args: self.preview())
        widget = ttk.Spinbox(parent, from_=low, to=high, textvariable=var, width=width)
        self.widgets.append(widget)
        return widget

    def layer_controls(self, parent, layer, title):
        box = ttk.LabelFrame(parent, text=title, padding=12)
        box.pack(fill='x')
        language = getattr(self.profile, layer + '_language')
        var = tk.StringVar(value=LABELS.get(language, NONE))
        self.vars[layer + '_language'] = var
        combo = ttk.Combobox(box, textvariable=var, values=[NONE, *LABELS.values()], state='readonly', width=29)
        combo.pack(fill='x', pady=(0, 9))
        combo.bind('<<ComboboxSelected>>', lambda event: self.preview())
        self.widgets.append(combo)
        row = ttk.Frame(box)
        row.pack(fill='x')
        ttk.Label(row, text='字号 ').pack(side='left')
        self.number(row, layer + '_size', getattr(self.profile, layer + '_size'), 16, 56).pack(side='left')
        if layer == 'top':
            row2 = ttk.Frame(box)
            row2.pack(fill='x', pady=(8, 0))
            ttk.Label(row2, text='距顶部（像素） ').pack(side='left')
            self.number(row2, 'top_margin_px', self.profile.top_margin_px, 0, 1000).pack(side='left')
        row3 = ttk.Frame(box)
        row3.pack(fill='x', pady=(9, 0))
        for suffix, label in (('outline', '黑色描边'), ('background', '字幕背景')):
            name = layer + '_' + suffix
            var = tk.BooleanVar(value=getattr(self.profile, name))
            self.vars[name] = var
            widget = ttk.Checkbutton(row3, text=label, variable=var, command=self.preview)
            widget.pack(side='left', padx=(0, 10))
            self.widgets.append(widget)

    def read_profile(self):
        value = self.profile.to_dict()
        for name, var in self.vars.items():
            raw = var.get()
            if name.endswith('_language'):
                value[name] = None if raw == NONE else CODES[raw]
            elif name in ('output_width', 'output_height'):
                value[name] = int(raw)
            elif name.endswith(('_outline', '_background')):
                value[name] = bool(raw)
            else:
                value[name] = float(raw)
        return Profile.from_dict(value)

    def set_profile(self, profile):
        self.profile = profile
        for name, var in self.vars.items():
            value = getattr(profile, name)
            var.set(LABELS.get(value, NONE) if name.endswith('_language') else value)
        self.preview()

    def preview(self):
        if not hasattr(self, 'canvas'):
            return
        canvas = self.canvas
        canvas.delete('all')
        width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 100)
        try:
            profile = self.read_profile()
        except (ValueError, KeyError, tk.TclError):
            canvas.create_text(width/2, height/2, text='请填写有效的字幕设置', fill='#dce5ef')
            return
        ratio = min(width / profile.output_width, height / profile.output_height)
        vw, vh = profile.output_width * ratio, profile.output_height * ratio
        x, y = (width-vw)/2, (height-vh)/2
        canvas.create_rectangle(x, y, x+vw, y+vh, fill='#14273a', outline='#456079')
        for index, (fraction, tall) in enumerate(((.08,.22),(.20,.38),(.34,.27),(.50,.48),(.66,.33),(.82,.24))):
            left = x + vw*fraction
            canvas.create_rectangle(left, y+vh*(1-tall), left+vw*.11, y+vh, fill='#1e3a4f', outline='')
        canvas.create_text(x+vw/2, y+vh/2, text='GAME VIEW', fill='#496478', font=('Segoe UI', 15, 'bold'))
        for layer in ('top', 'bottom'):
            code = getattr(profile, layer + '_language')
            if code is None:
                continue
            size = max(10, round(getattr(profile, layer + '_size') * profile.ui_scale() * ratio))
            ypos = y + profile.top_margin_px*ratio if layer == 'top' else y+vh*.86
            text = LANGUAGES[code].sample
            if getattr(profile, layer + '_background'):
                canvas.create_rectangle(x+vw*.10, ypos, x+vw*.90, ypos+size*2.1, fill='#080d14', outline='')
            if getattr(profile, layer + '_outline'):
                for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    canvas.create_text(x+vw/2+dx, ypos+dy, text=text, fill='black', font=('Microsoft YaHei UI', -size), anchor='n', width=vw*.84)
            canvas.create_text(x+vw/2, ypos, text=text, fill='#f5f7fb', font=('Microsoft YaHei UI', -size), anchor='n', width=vw*.84)
        if hasattr(self, 'validation'):
            self.validation.set('当前选择：' + ' / '.join(LABELS[c] for c in (profile.top_language, profile.bottom_language) if c)
                                + '。文本已审计，字形样例已实测；完整剧情同步待验证。')

    def swap(self):
        top, bottom = self.vars['top_language'].get(), self.vars['bottom_language'].get()
        self.vars['top_language'].set(bottom)
        self.vars['bottom_language'].set(top)
        self.preview()

    def defaults(self):
        size = read_game_resolution() or (1920, 1080)
        self.set_profile(Profile(output_width=size[0], output_height=size[1]))

    def detect_resolution(self):
        value = read_game_resolution()
        if not value:
            messagebox.showinfo(TITLE, '没有读到游戏输出尺寸，请手动填写游戏设置中的分辨率。')
            return
        self.vars['output_width'].set(value[0])
        self.vars['output_height'].set(value[1])
        self.status.set(f'已读取 {value[0]} × {value[1]}；与游戏当前显示模式核对后应用。')

    def choose_game(self):
        folder = filedialog.askdirectory(title='选择迈尔斯游戏目录')
        if folder:
            self.game_var.set(folder)
            self.check()

    def run_task(self, task, done):
        if self.busy:
            return
        self.busy = True
        for widget in self.widgets:
            widget.configure(state='disabled')
        self.progress.start(12)
        def worker():
            try:
                result = task(lambda text: self.events.put(('progress', text)))
                self.events.put(('done', (done, result)))
            except Exception as exc:
                log = app_data() / 'last-error.log'
                atomic_write(log, traceback.format_exc().encode('utf-8'))
                self.events.put(('error', str(exc) + '\n\n详细日志：' + str(log)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.status.set(value)
                    continue
                self.busy = False
                self.progress.stop()
                for widget in self.widgets:
                    widget.configure(state='readonly' if isinstance(widget, ttk.Combobox) else 'normal')
                if kind == 'error':
                    self.status.set('操作未完成，请查看提示。')
                    messagebox.showerror(TITLE, value)
                else:
                    callback, result = value
                    callback(result)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def check(self):
        folder = self.game_var.get().strip()
        if not folder:
            return
        self.status.set('正在检查游戏资源与备份……')
        self.run_task(lambda progress: inspect_game(Path(folder)), self.checked)

    def checked(self, info):
        self.inspected_game = info['game']
        names = {'not-installed':'未安装', 'installed':'已安装', 'restored':'已还原'}
        self.game_status.set(f"资源版本 {info['version']} · {names.get(info['status'], info['status'])} · 原始资源校验通过")
        path = info['state'] / 'profile.json'
        if info['status'] == 'installed' and path.is_file():
            try:
                self.applied_profile = Profile.load(path)
                self.set_profile(self.applied_profile)
            except (ValueError, OSError):
                pass
        atomic_write(app_data() / 'preferences.json', json.dumps({'game': str(info['game'])}).encode('utf-8'))
        self.status.set('目录检查通过。关闭游戏后即可生成并应用。')

    def apply(self):
        try:
            profile = self.read_profile()
            game = Path(self.game_var.get().strip()).resolve()
        except (ValueError, KeyError) as exc:
            messagebox.showerror(TITLE, str(exc))
            return
        self.status.set('正在生成；请保持游戏关闭，完成前不要移动工具或游戏目录。')
        def complete(manifest):
            self.applied_profile = profile
            self.game_status.set(f"资源版本 4.0630.0.0 · 已安装 · {manifest['dialogue_entries']:,} 条对话")
            self.status.set('安装与文件校验完成。游戏中使用简体中文文本、英语配音；可启动游戏检查效果。')
            self.inspected_game = game
        self.run_task(lambda progress: apply_profile(game, profile, progress), complete)

    def restore(self):
        game = Path(self.game_var.get().strip()).resolve()
        self.run_task(lambda progress: restore_game(game),
                      lambda result: (self.game_status.set('已还原原版字幕'), self.status.set('原始资源索引已恢复并校验。')))

    def import_profile(self):
        path = filedialog.askopenfilename(title='导入字幕配置', filetypes=[('字幕配置', '*.json')])
        if path:
            try:
                self.set_profile(Profile.load(path))
                self.status.set('配置已导入；点击生成并应用后才会改变游戏字幕。')
            except (ValueError, OSError, TypeError) as exc:
                messagebox.showerror(TITLE, str(exc))

    def export_profile(self):
        try:
            profile = self.read_profile()
            path = filedialog.asksaveasfilename(title='导出字幕配置', defaultextension='.json', initialfile='miles-subtitles.json', filetypes=[('字幕配置', '*.json')])
            if path:
                profile.save(path)
                self.status.set('配置已导出，可分享给他人；其中不含游戏文本和游戏目录。')
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showerror(TITLE, str(exc))

    def launch(self):
        try:
            game = Path(self.game_var.get().strip()).resolve()
            inspect_game(game)
            current = read_game_resolution()
            if self.applied_profile and current and current != (self.applied_profile.output_width, self.applied_profile.output_height):
                messagebox.showinfo(TITLE, '游戏分辨率与已安装配置不同，请先读取分辨率并重新应用。')
                return
            if not game_running():
                subprocess.Popen([str(game / 'MilesMorales.exe')], cwd=game)
            self.status.set('游戏已启动；如需切换字幕，请退出游戏后重新应用。')
        except (ValueError, OSError) as exc:
            messagebox.showerror(TITLE, str(exc))

    def open_report(self):
        path = work_directory(Path(self.game_var.get().strip()).resolve())
        if path.is_dir():
            os.startfile(path)
        else:
            messagebox.showinfo(TITLE, '应用字幕后会在本机生成覆盖报告。')

    def close(self):
        if self.busy:
            messagebox.showinfo(TITLE, '正在处理资源，请等待操作结束后关闭。')
        else:
            self.root.destroy()


def self_test(output, game=None):
    """Packaged-runtime smoke test, callable with PATH stripped of Python/Java."""
    result = {'python_embedded': bool(getattr(sys, 'frozen', False)), 'tk': tk.TkVersion,
              'profile_roundtrip': Profile.from_dict(Profile().to_dict()) == Profile()}
    test_root = tk.Tk()
    test_root.withdraw()
    ttk.Label(test_root, text='简体 / 日本語 / 한국어 / Русский').pack()
    test_root.update()
    test_root.destroy()
    run = subprocess.run(java_command('-help'), capture_output=True, timeout=40,
                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    result['bundled_jpexs'] = run.returncode == 0 and b'JPEXS Free Flash Decompiler' in run.stdout
    if game:
        info = inspect_game(game)
        result['game_version'] = info['version']
        result['game_status'] = info['status']
        # Exercise the shipped font helper and Java compiler path as well as Tk.
        # Uses the player's original UI locally; this probe is never installed.
        from archive import GameArchive
        from configurator_backend import OVERLAY, compile_overlay
        original = GameArchive(info['game'], info['original_toc']).extract(OVERLAY)
        font_work = Path(output).resolve().parent / 'portable-font-self-test'
        probe = compile_overlay(original, Profile(top_language='ko'), font_work,
                                lambda message: None, [('Hello', '한국어 Русский Ελληνικά')])
        result['bundled_font_pipeline'] = len(probe) > len(original)
    atomic_write(Path(output), json.dumps(result, indent=2).encode())
    return all(result.get(k) for k in ('profile_roundtrip', 'bundled_jpexs')) and (
        not game or result.get('bundled_font_pipeline', False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path)
    parser.add_argument('--self-test', type=Path)
    args = parser.parse_args()
    if args.self_test:
        return 0 if self_test(args.self_test, args.game) else 1
    root = tk.Tk()
    Configurator(root, args.game)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
