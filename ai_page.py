"""AI workbench. Network work stays off Tk's event thread."""
from copy import deepcopy
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ai_client import complete, public_config, endpoint_for
from ai_features import AIError, TASKS, build_messages, validate_plan
from engine import duration_for, format_time, make_plan

BG, CARD, INK, MUTED, GREEN = '#F4F3EE', '#FFFFFF', '#25362E', '#626C63', '#315E46'
TASK_LABELS = {'rhythm': 'Design typing rhythm', 'rewrite': 'Natural rewrite',
               'translate': 'Translate', 'custom': 'Custom task'}


class AIPage(tk.Frame):
    def __init__(self, app):
        super().__init__(app.root, bg=BG)
        self.app = app
        self.t = app.tr
        self.busy = False
        self.closed = False
        self.generation = 0
        self.events = queue.Queue()
        self.poll_id = None
        self.result = None
        self.network_widgets = []
        self.pack(fill='both', expand=True)
        header = tk.Frame(self, bg=BG)
        header.pack(fill='x', padx=24, pady=(18, 10))
        self.button(header, 'Back', self.back, lock=False).pack(side='left', padx=(0, 14))
        tk.Label(header, text=self.t('AI assistant'), bg=BG, fg=INK,
                 font=(app.face, 21, 'bold')).pack(side='left')
        self.undo_button = self.button(header, 'Undo last AI application', self.undo, lock=False)
        self.undo_button.pack(side='right')
        self.undo_button.configure(state='normal' if app.ai_undo else 'disabled')
        self.label(self, 'Generate a draft or a typing plan. You choose what reaches the main page.',
                   color=MUTED).pack(fill='x', padx=24, pady=(0, 12))

        config_frame = tk.LabelFrame(self, text=self.t('API connection'), bg=BG, fg=INK, padx=12, pady=8)
        config_frame.pack(fill='x', padx=24)
        config_frame.grid_columnconfigure(1, weight=3)
        config_frame.grid_columnconfigure(3, weight=2)
        connection = app.ai_draft.get('connection', app.ai_config)
        self.base_url = tk.StringVar(value=connection['base_url'])
        self.model = tk.StringVar(value=connection['model'])
        self.key = tk.StringVar(value=app.ai_key)
        self.limit = tk.StringVar(value=str(connection['max_tokens']))
        self.timeout = tk.StringVar(value=str(connection['timeout']))
        self.show_key = tk.BooleanVar(value=False)
        for row, col, caption, variable in [(0, 0, 'API base URL', self.base_url),
                                           (0, 2, 'Model name', self.model),
                                           (1, 0, 'API key (session only)', self.key)]:
            self.label(config_frame, caption).grid(row=row, column=col, sticky='w', padx=(0, 8), pady=5)
            entry = ttk.Entry(config_frame, textvariable=variable, width=25, show='•' if variable is self.key else '')
            entry.grid(row=row, column=col + 1, sticky='ew', padx=(0, 14), pady=5)
            self.network_widgets.append(entry)
            if variable is self.key:
                self.key_entry = entry
        key_tools = tk.Frame(config_frame, bg=BG)
        key_tools.grid(row=1, column=2, columnspan=2, sticky='w')
        ttk.Checkbutton(key_tools, text=self.t('Show key'), variable=self.show_key,
                        command=lambda: self.key_entry.configure(show='' if self.show_key.get() else '•')).pack(side='left')
        self.button(key_tools, 'Read environment', self.read_env).pack(side='left', padx=5)
        self.button(key_tools, 'Clear key', self.clear_key).pack(side='left')
        options = tk.Frame(config_frame, bg=BG)
        options.grid(row=2, column=0, columnspan=4, sticky='ew', pady=(5, 0))
        for caption, variable in [('Output token limit', self.limit), ('Timeout (s)', self.timeout)]:
            self.label(options, caption).pack(side='left', padx=(0, 6))
            entry = ttk.Entry(options, textvariable=variable, width=6)
            entry.pack(side='left', padx=(0, 16))
            self.network_widgets.append(entry)
        self.button(options, 'Save connection settings', self.save_connection).pack(side='left', padx=(0, 7))
        self.button(options, 'Test connection', lambda: self.generate(test=True)).pack(side='left')
        self.label(config_frame, 'Chat Completions compatible. Use your provider’s API address and model ID.',
                   color=MUTED).grid(row=3, column=0, columnspan=4, sticky='w', pady=(6, 0))

        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill='x', padx=24, pady=10)
        self.label(toolbar, 'Task').pack(side='left', padx=(0, 8))
        self.task = tk.StringVar(value=self.t(TASK_LABELS[app.ai_draft.get('task', 'rhythm')]))
        self.task_selector = ttk.Combobox(toolbar, state='readonly', textvariable=self.task,
                                          values=[self.t(TASK_LABELS[k]) for k in TASKS], width=24)
        self.task_selector.pack(side='left', padx=(0, 8))
        self.task_selector.bind('<<ComboboxSelected>>', self.task_changed)
        self.network_widgets.append(self.task_selector)
        self.button(toolbar, 'Reload main text', self.reload_source).pack(side='left')
        self.generate_button = self.button(toolbar, 'Generate', self.generate, primary=True)
        self.generate_button.pack(side='right')
        self.cancel_button = self.button(toolbar, 'Cancel request', self.cancel, lock=False)
        self.cancel_button.pack(side='right', padx=(0, 8))
        self.cancel_button.configure(state='disabled')

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True, padx=24)
        body.grid_columnconfigure(0, weight=1, uniform='panes')
        body.grid_columnconfigure(1, weight=1, uniform='panes')
        body.grid_rowconfigure(1, weight=1)
        self.label(body, 'Text sent to AI').grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.label(body, 'Result preview').grid(row=0, column=1, sticky='w', padx=(14, 0), pady=(0, 6))
        self.source = self.text_box(body, 3)
        self.source.master.grid(row=1, column=0, sticky='nsew')
        self.output = self.text_box(body, 3)
        self.output.master.grid(row=1, column=1, sticky='nsew', padx=(14, 0))
        self.output.configure(state='disabled')
        self.source.insert('1.0', app.ai_draft.get('source', app.source_text()))
        self.source.edit_modified(False)
        self.source.bind('<<Modified>>', self.input_changed)

        instructions = tk.Frame(self, bg=BG)
        instructions.pack(fill='x', padx=24, pady=(9, 0))
        self.label(instructions, 'Instructions / target language / tone').pack(anchor='w')
        self.instructions = tk.Text(instructions, height=2, wrap='word', bg=CARD, fg=INK,
                                     relief='solid', bd=1, font=(app.face, 10), padx=7, pady=5)
        self.instructions.pack(fill='x', pady=(5, 0))
        self.instructions.insert('1.0', app.ai_draft.get('instructions', ''))
        self.notice = self.label(self, 'Generate sends the text above to your chosen API and may incur provider charges. Nothing is applied automatically.',
                                 color=MUTED, wraplength=1040, justify='left')
        self.notice.pack(fill='x', padx=24, pady=(7, 5))
        self.status = self.label(self, 'Ready. Add the API address, model and key.', color=GREEN,
                                 wraplength=1040, justify='left')
        self.status.pack(fill='x', padx=24, pady=(0, 6))
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill='x', padx=24, pady=(0, 16))
        self.button(actions, 'Copy result', self.copy_result, lock=False).pack(side='left')
        self.apply_text_button = self.button(actions, 'Use result as main text', self.apply_text, lock=False)
        self.apply_text_button.pack(side='right')
        self.apply_plan_button = self.button(actions, 'Apply typing plan', self.apply_plan, primary=True, lock=False)
        self.apply_plan_button.pack(side='right', padx=(0, 8))
        self.apply_text_button.configure(state='disabled')
        self.apply_plan_button.configure(state='disabled')
        # Reserve the action and instruction area before giving spare height to text panes.
        for widget in (actions, self.status, self.notice, instructions):
            widget.pack_configure(side='bottom', before=body)
        self.bind('<Configure>', self.resize)
        if app.ai_draft.get('result') is not None:
            self.show_result(deepcopy(app.ai_draft['result']))
        self.poll_id = app.root.after(60, self.poll)

    def resize(self, event):
        width = max(200, event.width - 48)
        self.notice.configure(wraplength=width)
        self.status.configure(wraplength=width)

    def label(self, parent, text, color=INK, **kwargs):
        return tk.Label(parent, text=self.t(text), bg=parent.cget('bg'), fg=color, anchor='w', **kwargs)

    def button(self, parent, text, command, primary=False, lock=True):
        button = tk.Button(parent, text=self.t(text), command=command, relief='flat', padx=10, pady=8,
                            bg=GREEN if primary else '#E8EEE5', fg='white' if primary else INK, cursor='hand2')
        if lock:
            self.network_widgets.append(button)
        return button

    def text_box(self, parent, height):
        frame = tk.Frame(parent, bg=CARD)
        scroll = ttk.Scrollbar(frame)
        box = tk.Text(frame, height=height, width=10, wrap='word', bg=CARD, fg=INK,
                       font=(self.app.face, 11), padx=10, pady=8, undo=True, relief='solid', bd=1,
                       yscrollcommand=scroll.set)
        scroll.configure(command=box.yview)
        scroll.pack(side='right', fill='y')
        box.pack(fill='both', expand=True)
        return box

    def task_id(self):
        return next(k for k in TASKS if self.t(TASK_LABELS[k]) == self.task.get())

    def notify(self, message, **values):
        self.status.configure(text=self.t(message, **values))

    def error(self, exc):
        messagebox.showerror(self.t('AI request failed'), self.app.error_text(exc), parent=self.app.root)

    def config(self):
        try:
            return public_config({'base_url': self.base_url.get(), 'model': self.model.get(),
                                  'max_tokens': int(self.limit.get()), 'timeout': int(self.timeout.get())})
        except ValueError as exc:
            if isinstance(exc, AIError):
                raise
            raise AIError('Invalid output limit or timeout.') from exc

    def save_connection(self):
        try:
            config = self.config()
            self.app.save_ai_connection(config)
            self.app.ai_key = self.key.get()
            self.notify('Connection settings saved. The key was not written to disk.')
        except (OSError, ValueError) as exc:
            self.error(exc)

    def read_env(self):
        value = os.environ.get('TYPECRAFT_API_KEY') or os.environ.get('OPENAI_API_KEY')
        if value:
            self.key.set(value)
            self.app.ai_key = value
            self.notify('Key loaded from the environment for this session.')
        else:
            self.notify('Neither TYPECRAFT_API_KEY nor OPENAI_API_KEY is set.')

    def clear_key(self):
        self.key.set('')
        self.app.ai_key = ''
        self.notify('Session key cleared.')

    def reload_source(self):
        self.source.delete('1.0', 'end')
        self.source.insert('1.0', self.app.source_text())
        self.input_changed()

    def input_changed(self, event=None):
        if self.source.edit_modified():
            self.source.edit_modified(False)
        if self.result and self.result['kind'] == 'rhythm':
            unchanged = self.source.get('1.0', 'end-1c') == self.result['source']
            self.apply_plan_button.configure(state='normal' if unchanged and not self.busy else 'disabled')
            if not unchanged:
                self.notify('Input changed. Generate a new typing plan before applying it.')

    def task_changed(self, event=None):
        self.result = None
        self._output('')
        self.apply_text_button.configure(state='disabled')
        self.apply_plan_button.configure(state='disabled')

    def _output(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')

    def _lock(self, busy):
        self.busy = busy
        for widget in self.network_widgets:
            widget.configure(state='disabled' if busy else 'normal')
        if not busy:
            self.task_selector.configure(state='readonly')
        self.source.configure(state='disabled' if busy else 'normal')
        self.instructions.configure(state='disabled' if busy else 'normal')
        self.cancel_button.configure(state='normal' if busy else 'disabled')
        self.undo_button.configure(state='normal' if self.app.ai_undo and not busy else 'disabled')
        self.apply_plan_button.configure(state='disabled')
        self.apply_text_button.configure(state='disabled')
        if not busy and self.result:
            if self.result['kind'] == 'rhythm':
                self.input_changed()
            else:
                self.apply_text_button.configure(state='normal')

    def _remember(self):
        self.app.ai_key = self.key.get()
        self.app.ai_draft = {'source': self.source.get('1.0', 'end-1c'),
                             'instructions': self.instructions.get('1.0', 'end-1c'), 'task': self.task_id(),
                             'result': deepcopy(self.result),
                             'connection': {'base_url': self.base_url.get(), 'model': self.model.get(),
                                            'max_tokens': self.limit.get(), 'timeout': self.timeout.get()}}

    def generate(self, test=False):
        if self.busy:
            return
        try:
            config = self.config()
            key = self.key.get()
            kind = 'test' if test else self.task_id()
            source = '' if test else self.source.get('1.0', 'end-1c')
            if test:
                messages = [{'role': 'user', 'content': 'Reply with only OK.'}]
            else:
                messages = build_messages(kind, source, self.instructions.get('1.0', 'end-1c'), self.app.language)
        except (ValueError, TypeError) as exc:
            self.error(exc)
            return
        self._remember()
        self.result = None
        self._output('')
        self.generation += 1
        generation = self.generation
        seed = self.app.plan_seed
        self._lock(True)
        self.notify('Requesting {model}… Destination: {endpoint}', model=config['model'], endpoint=endpoint_for(config['base_url']))
        events = self.events
        def work():
            try:
                response = complete(config, key, messages)
                plan = validate_plan(response['text'], source) if kind == 'rhythm' else None
                proposed = None
                if plan is not None:
                    proposed = make_plan(source, duration_for(source, 'wps', plan['speed_wps']),
                                         plan['error_rate'] / 100, plan['variation'] / 100,
                                         seed=seed, profile=plan['profile'])
                events.put((generation, 'ok', {'kind': kind, 'source': source, 'response': response,
                                               'plan': plan, 'proposed': proposed, 'seed': seed}))
            except ValueError as exc:
                message = str(exc)
                if key:
                    message = message.replace(key, '[redacted]')
                events.put((generation, 'error', message))
            except Exception:
                events.put((generation, 'error', 'The AI request could not be completed. Check the connection settings.'))
        threading.Thread(target=work, daemon=True, name='Typecraft-AI').start()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                generation, state, data = self.events.get_nowait()
                if generation != self.generation:
                    continue
                self._lock(False)
                if state == 'error':
                    self.notify('AI request failed')
                    self.error(AIError(data))
                elif data['kind'] == 'test':
                    self.notify('Connection succeeded. No main-page text was sent.')
                    self._output(data['response']['text'])
                else:
                    self.show_result(data)
        except queue.Empty:
            pass
        self.poll_id = self.app.root.after(60, self.poll)

    def show_result(self, data):
        self.result = data
        if data['kind'] == 'rhythm':
            plan = data['plan']
            # Estimate using the same seed that Apply will install on the main page.
            proposed = data['proposed']
            summary = self.t('Suggested pace: {speed:g} words/s · Variation: {variation:g}% · Nearby-key errors: {errors:g}%\nAdded waits: {extra:.1f}s · Expected total: {total}\n\n{explanation}\n\nProfile JSON:\n',
                             speed=plan['speed_wps'], variation=plan['variation'], errors=plan['error_rate'],
                             extra=proposed.extra_wait, total=format_time(proposed.duration), explanation=plan['explanation'])
            self._output(summary + json.dumps(plan['profile'], ensure_ascii=False, indent=2))
            self.apply_plan_button.configure(state='normal')
            self.notify('Review the plan. Apply brings this input text and the proposed settings to the main page; typing will not start.')
        else:
            self._output(data['response']['text'])
            self.apply_text_button.configure(state='normal')
            self.notify('Review the result, then choose whether to use it. The main text is unchanged.')
        tokens = data['response'].get('total_tokens')
        if tokens is not None:
            self.status.configure(text=self.status.cget('text') + self.t('  Reported usage: {tokens} tokens.', tokens=tokens))

    def cancel(self):
        if self.busy:
            self.generation += 1
            self.result = None
            self._lock(False)
            self.notify('Cancelled locally. The provider may still finish or charge for the sent request.')

    def copy_result(self):
        text = self.output.get('1.0', 'end-1c')
        if text:
            self.app.root.clipboard_clear()
            self.app.root.clipboard_append(text)
            self.notify('AI result copied.')

    def apply_text(self):
        if self.busy or not self.result or self.result['kind'] == 'rhythm':
            return
        try:
            self.app.apply_ai_text(self.result['response']['text'])
            self._return()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def apply_plan(self):
        if self.busy or not self.result or self.result['kind'] != 'rhythm':
            return
        if self.source.get('1.0', 'end-1c') != self.result['source']:
            self.notify('Input changed. Generate a new typing plan before applying it.')
            return
        try:
            self.app.apply_ai_plan(self.result['plan'], self.result['source'], self.result['seed'])
            self._return()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def undo(self):
        try:
            self.app.undo_ai_application()
            self._return()
        except (ValueError, OSError) as exc:
            self.error(exc)

    def _return(self):
        self._remember()
        self.app.ai_page = None
        self.destroy()
        self.app.main_page.pack(fill='both', expand=True)

    def back(self):
        self.cancel()
        self._return()

    def destroy(self):
        self.closed = True
        self.generation += 1
        if self.poll_id is not None:
            self.app.root.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
