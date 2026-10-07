#!/bin/sh
cd "$(dirname "$0")" || exit 1

show_error() {
    printf '%s\n' "$1" >&2
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        if command -v zenity >/dev/null 2>&1; then
            zenity --error --no-markup --title='Typecraft could not start' \
                --width=540 --text="$1" 2>/dev/null && return
        fi
        if command -v xmessage >/dev/null 2>&1; then
            xmessage -center "$1" 2>/dev/null && return
        fi
    fi
    if [ -t 0 ]; then
        printf '\nPress Return to close.\n'
        read -r ignored
    fi
}

if [ -x .venv/bin/python ]; then
    typecraft_python=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
    typecraft_python=python3
else
    show_error 'Python 3 is missing / 缺少 Python 3。
Ubuntu / Debian / Linux Mint: sudo apt install python3 python3-tk python3-venv
Other Linux systems: install Python and Tkinter using your package manager.
下载与安装说明：https://www.python.org/downloads/
Install a supported Python version (minimum 3.10), then relaunch.'
    exit 1
fi

typecraft_log=$(mktemp "${TMPDIR:-/tmp}/typecraft-start.XXXXXX") || exit 1
trap 'rm -f "$typecraft_log"' EXIT HUP INT TERM
"$typecraft_python" typecraft.py 2>"$typecraft_log"
typecraft_result=$?
if [ "$typecraft_result" -ne 0 ]; then
    typecraft_details=$(tail -n 30 "$typecraft_log")
    show_error "Typecraft could not open. Run it from a graphical desktop.

$typecraft_details

See README.md for setup instructions."
fi
exit "$typecraft_result"
