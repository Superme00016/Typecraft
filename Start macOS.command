#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then
    typecraft_python=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    typecraft_python=python3
else
    osascript -e 'display dialog "缺少 Python / Python is missing.\n请从官网安装包含 Tcl/Tk 的新版 Python（最低 3.10），然后重新打开此启动器。\nInstall Python with Tcl/Tk, then relaunch.\nhttps://www.python.org/downloads/macos/" with title "Typecraft" buttons {"退出 / Exit", "下载 / Download"} default button 2' -e 'if button returned of result is "下载 / Download" then open location "https://www.python.org/downloads/macos/"'
    exit 1
fi
"$typecraft_python" typecraft.py
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nTypecraft could not start. See the instructions above or README.md.\nPress Return to close.\n'
    read -r ignored
fi
exit "$result"
