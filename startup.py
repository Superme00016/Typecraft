"""Offline startup checks. No installation, network requests, or simulated keys."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import webbrowser

APP = Path(__file__).resolve().parent
PYTHON_URL = 'https://www.python.org/downloads/'
TK_URL = 'https://docs.python.org/3/library/tkinter.html'
TOOLS_URL = 'https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/'
PYNPUT_URL = 'https://pypi.org/project/pynput/'
PLATFORM_URL = 'https://pynput.readthedocs.io/en/latest/limitations.html'


def language():
    try:
        path = APP / 'user_data/settings.json'
        if path.stat().st_size < 600000:
            return json.loads(path.read_text(encoding='utf-8')).get('language', 'zh')
    except (OSError, ValueError, AttributeError, RecursionError):
        pass
    return 'zh'


def tr(zh, en):
    return en if language() == 'en' else zh


def probe(code):
    """Use the selected interpreter afresh, with a bounded check and no shell."""
    try:
        result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=8,
                                creationflags=0x08000000 if sys.platform == 'win32' else 0)
        return result.returncode == 0, (result.stderr or result.stdout).strip()[-1600:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def pip_command():
    if sys.platform == 'win32':
        def quoted(value):
            return "'" + str(value).replace("'", "''") + "'"
        python = quoted(sys.executable)
        if sys.prefix != sys.base_prefix:
            return "& {} -m pip install 'pynput>=1.7.7,<2'".format(python)
        venv = quoted(APP / '.venv')
        executable = quoted(APP / '.venv' / 'Scripts' / 'python.exe')
        return "& {} -m venv {}\n& {} -m pip install 'pynput>=1.7.7,<2'".format(python, venv, executable)
    if sys.prefix != sys.base_prefix:
        return shlex.quote(sys.executable) + " -m pip install 'pynput>=1.7.7,<2'"
    python = shlex.quote(sys.executable)
    venv = shlex.quote(str(APP / '.venv'))
    executable = shlex.quote(str(APP / '.venv/bin/python'))
    return '{} -m venv {}\n{} -m pip install \'pynput>=1.7.7,<2\''.format(python, venv, executable)


def tk_help():
    if sys.platform.startswith('linux'):
        return tr('Ubuntu / Debian / Linux Mint：sudo apt install python3-tk\n其他发行版：通过系统软件管理器安装与当前 Python 对应的 Tkinter 包。自编译 Python 需要重新构建 Tk 支持。',
                  'Ubuntu / Debian / Linux Mint: sudo apt install python3-tk\nOther distributions: install the Tkinter package matching this Python through your package manager. Custom Python builds need Tk support rebuilt.')
    return tr('从 Python 官网安装包含 Tcl/Tk 的 Python；Windows 安装器中启用 Tcl/Tk and IDLE。安装后重新启动应用。',
              'Install Python with Tcl/Tk from python.org; enable Tcl/Tk and IDLE in the Windows installer. Restart the app afterwards.')


def issue(name, required, help_text, url, detail=''):
    return dict(name=name, required=required, help=help_text, url=url, detail=detail)


def inspect_dependencies():
    issues = []
    if sys.version_info < (3, 10):
        return [issue('Python 3.10+', True, tr('请安装受支持的新版 Python，然后重新打开启动脚本。', 'Install a supported recent Python and reopen the launcher.'), PYTHON_URL)]
    ok, detail = probe('import tkinter; r=tkinter.Tk(); r.withdraw(); r.update_idletasks(); r.destroy()')
    if not ok:
        issues.append(issue('Tkinter / Tcl/Tk / desktop', True, tk_help() + '\n' + tr('若已安装：请在图形桌面运行，并检查 DISPLAY 或 Tcl/Tk 配置。', 'If installed: run on a graphical desktop and check DISPLAY or Tcl/Tk configuration.'), TK_URL, detail))
    ok, detail = probe('import ssl; ssl.create_default_context()')
    if not ok:
        issues.append(issue('Python SSL', True, tr('当前 Python 的 SSL 支持不可用。请修复或重新安装带 OpenSSL 支持的 Python。', 'SSL support is unavailable. Repair or reinstall Python with OpenSSL support.'), PYTHON_URL, detail))
    ok, detail = probe("from importlib.metadata import version; installed=version('pynput'); v=tuple(int(n) for n in installed.split('.')[:3]); assert (1,7,7)<=v<(2,0), 'Installed: '+installed+'; requires pynput>=1.7.7,<2'")
    if not ok:
        issues.append(issue('pynput ≥ 1.7.7, < 2', False,
                            tr('外部输入需要此组件。在终端执行以下命令（Windows 使用 PowerShell）。若提示缺少 venv/pip，请先按链接安装这些工具；Ubuntu 可安装 python3-venv。\n', 'External typing needs this package. Run these commands in a terminal (PowerShell on Windows). If venv/pip is missing, install those tools first; Ubuntu provides python3-venv.\n') + pip_command() + '\n' + TOOLS_URL + '\n' + tr('安装完成后重新打开启动脚本，让它使用 .venv。', 'Reopen the launcher after installation so it selects .venv.'), PYNPUT_URL, detail))
    wayland = sys.platform.startswith('linux') and (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('XDG_SESSION_TYPE') == 'wayland')
    if wayland:
        issues.append(issue('Wayland → X11', False, tr('当前桌面是 Wayland。外部输入需要注销后，在登录界面选择 X11/Xorg 会话；无需为预览安装组件。', 'This desktop uses Wayland. For external typing, log out and select an X11/Xorg session at login. Preview needs no additional package.'), PLATFORM_URL))
    elif ok:
        ok, detail = probe('from pynput.keyboard import Controller, Listener; from keyboard_output import check_macos_permissions; check_macos_permissions()')
        if not ok:
            issues.append(issue('pynput / desktop permissions', False, tr('外部输入后端无法加载。Linux 请检查 X11 显示连接；macOS 请在系统设置 → 隐私与安全性中授予运行 Python 的程序辅助功能/输入监控权限，再重新启动。依赖包损坏时可重新安装 pynput。', 'External input backend could not load. Check the X11 display on Linux. On macOS, enable Accessibility/Input Monitoring for the program running Python under System Settings → Privacy & Security, then restart. Reinstall pynput if its dependencies are broken.'), PLATFORM_URL, detail))
    return issues


def report(issues):
    blocks = [tr('启动前检查', 'Startup check'), 'Python: ' + sys.executable]
    for item in issues:
        level = tr('必需', 'Required') if item['required'] else tr('仅影响外部输入', 'External typing only')
        blocks.append('{} [{}]\n{}\n{}\n{}'.format(item['name'], level, item['help'], item['url'], item['detail']))
    return '\n\n'.join(blocks)


def native_notice(message):
    """Fallback when Tk itself is missing; console output always remains available."""
    print(message, file=sys.stderr)
    try:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, 'Typecraft', 0x10)
        elif sys.platform == 'darwin':
            script = 'on run argv\ndisplay dialog (item 1 of argv) with title "Typecraft" buttons {"OK"} default button "OK"\nend run'
            subprocess.run(['osascript', '-e', script, message], check=False)
        elif shutil.which('zenity'):
            subprocess.run(['zenity', '--error', '--no-markup', '--width=640', '--title=Typecraft', '--text=' + message], check=False)
        elif shutil.which('xmessage'):
            subprocess.run(['xmessage', '-center', message], check=False)
    except (OSError, RuntimeError):
        pass


class CheckWindow:
    def __init__(self, root, issues):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.issues, self.accepted = root, issues, False
        root.title(tr('Typecraft · 启动前检查', 'Typecraft · Startup check'))
        root.geometry('790x660')
        root.minsize(620, 460)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=tr('还需要准备这些', 'A few things to set up'), font=('', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=tr('只检查本机环境，不自动下载或安装。可选组件缺失时仍可进入预览。', 'Local checks only. Optional components do not prevent preview.'), wraplength=690).pack(anchor='w', pady=(10, 16))
        area = ttk.Frame(frame)
        area.pack(fill='both', expand=True)
        self.body = tk.Text(area, wrap='word', padx=16, pady=14, font=('', 11), relief='flat')
        scroll = ttk.Scrollbar(area, command=self.body.yview)
        self.body.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.body.pack(side='left', fill='both', expand=True)
        self.body.insert('end', report(issues))
        for index, url in enumerate(dict.fromkeys([item['url'] for item in issues] + [TOOLS_URL])):
            start = self.body.search(url, '1.0', stopindex='end')
            if start:
                tag = 'link' + str(index)
                self.body.tag_add(tag, start, '{}+{}c'.format(start, len(url)))
                self.body.tag_config(tag, foreground='#225caa', underline=True)
                self.body.tag_bind(tag, '<Button-1>', lambda event, url=url: webbrowser.open(url))
        self.body.configure(state='disabled')
        buttons = ttk.Frame(frame)
        buttons.pack(side='bottom', before=area, fill='x', pady=(18, 0))
        ttk.Button(buttons, text=tr('复制说明', 'Copy instructions'), command=self.copy).pack(side='left')
        ttk.Button(buttons, text=tr('退出', 'Exit'), command=root.destroy).pack(side='right')
        self.next = ttk.Button(buttons, text=tr('继续进入', 'Continue'), command=self.accept)
        self.next.pack(side='right', padx=8)
        if any(item['required'] for item in issues):
            self.next.configure(state='disabled')
        ttk.Label(frame, text=tr('安装或授权完成后，请关闭此窗口并重新启动应用，以重新检查。', 'After installation or permission changes, close this window and relaunch to check again.'), wraplength=690).pack(side='bottom', before=buttons, anchor='w', pady=(12, 0))

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(report(self.issues))

    def accept(self):
        if not any(item['required'] for item in self.issues):
            self.accepted = True
            self.root.destroy()


def launch():
    issues = inspect_dependencies()
    if issues:
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception:
            native_notice(report(issues))
            return 1
        window = CheckWindow(root, issues)
        root.mainloop()
        if not window.accepted:
            return 0
    from typecraft import main
    main()
    return 0


if __name__ == '__main__':
    sys.exit(launch())
