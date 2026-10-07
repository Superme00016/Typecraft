"""Optional OS keyboard adapter; imported only for external typing."""
import os
import sys
import threading


STARTUP_TIMEOUT = 5.0
PERMISSION_ERROR = ('Allow your Python launcher or Terminal in macOS System Settings → '
                    'Privacy & Security → Accessibility and Input Monitoring, then restart the app.')


def check_macos_permissions():
    """Query the OS without starting a listener or prompting for permissions."""
    if sys.platform == 'darwin':
        from HIServices import AXIsProcessTrusted
        if not AXIsProcessTrusted():
            raise RuntimeError(PERMISSION_ERROR)


class _StartupCancelled(Exception):
    pass


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
        check_macos_permissions()
        self.keys = Key
        self.controller = Controller()
        ready = threading.Event()
        cancelled = self.stop_requested
        startup_errors = []

        class ManagedListener(Listener):
            # pynput 1.x exposes no timed wait. Keep its readiness hook, but
            # notify our own event on both readiness and early thread failure.
            def _mark_ready(listener):
                if cancelled.is_set():
                    raise _StartupCancelled()
                super()._mark_ready()
                ready.set()

            def _stop_platform(listener):
                if sys.platform.startswith('linux') and hasattr(listener, '_display_stop') and hasattr(listener, '_context'):
                    # The recording connection is blocked waiting for events.
                    # Send and flush cancellation on pynput's stop connection.
                    listener._display_stop.record_disable_context(listener._context)
                    listener._display_stop.flush()
                else:
                    super()._stop_platform()

            def run(listener):
                try:
                    super().run()
                except _StartupCancelled:
                    pass
                except Exception as exc:
                    startup_errors.append(exc)
                finally:
                    ready.set()

        def on_press(key):
            if not cancelled.is_set() and key == Key.esc:
                cancelled.set()
        self.listener = ManagedListener(on_press=on_press)
        try:
            self.listener.start()
            if not ready.wait(STARTUP_TIMEOUT):
                raise RuntimeError('The emergency-stop keyboard listener timed out. Check desktop permissions and try again.')
            if startup_errors or not self.listener.is_alive():
                raise RuntimeError('The emergency-stop keyboard listener could not start.')
            if sys.platform == 'darwin' and not self.listener.IS_TRUSTED:
                raise RuntimeError(PERMISSION_ERROR)
        except Exception:
            self.close()
            raise

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
            listener, self.listener = self.listener, None
            # Some backends block in stop() while initialization is incomplete.
            # Cancellation takes effect immediately; cleanup must not block Tk.
            def stop_listener():
                try:
                    listener.stop()
                except Exception:
                    pass
            threading.Thread(target=stop_listener, daemon=True,
                             name='Typecraft-keyboard-cleanup').start()
