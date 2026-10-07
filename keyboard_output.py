"""Optional OS keyboard adapter; imported only for external typing."""
import os
import sys
import threading


class KeyboardOutput:
    def __init__(self):
        self.stop_requested = threading.Event()
        self.listener = None
        if sys.platform.startswith('linux') and (
            os.environ.get('XDG_SESSION_TYPE') == 'wayland' or os.environ.get('WAYLAND_DISPLAY')
        ):
            raise RuntimeError('External typing requires an X11 session on Linux. '
                               'Preview works on Wayland. Sign in to an X11 session to type into other apps.')
        try:
            from pynput.keyboard import Controller, Key, Listener
        except ImportError as exc:
            raise RuntimeError('External typing needs the optional pynput package and a supported desktop. '
                               'See README.md for setup. Preview needs no extra packages.\n\n'
                               f'Details: {exc}') from exc
        self.keys = Key
        self.controller = Controller()
        if sys.platform == 'darwin' and not Listener.IS_TRUSTED:
            raise RuntimeError('Allow your Python launcher or Terminal in macOS System Settings → '
                               'Privacy & Security → Accessibility and Input Monitoring, then restart the app.')
        def on_press(key):
            if key == Key.esc:
                self.stop_requested.set()
        self.listener = Listener(on_press=on_press)
        self.listener.start()
        self.listener.wait()
        if not self.listener.is_alive():
            self.close()
            raise RuntimeError('The emergency-stop keyboard listener could not start.')

    def write(self, stroke):
        if self.stop_requested.is_set():
            return False
        if not self.listener.is_alive():
            raise RuntimeError('The emergency-stop listener stopped. Typing was cancelled.')
        if stroke.kind == 'wait':
            return True
        if stroke.kind == 'backspace':
            self.controller.tap(self.keys.backspace)
        elif stroke.text == '\n':
            self.controller.tap(self.keys.enter)
        elif stroke.text == '\t':
            self.controller.tap(self.keys.tab)
        else:
            self.controller.type(stroke.text)
        return True

    def close(self):
        self.stop_requested.set()
        if self.listener is not None:
            self.listener.stop()
