#!/usr/bin/env python3
"""Typecraft — a local, cross-platform typing simulator. Python 3.10+."""
# Bootstrap before importing Tk or application dependencies.
if __name__ == '__main__':
    import sys
    from startup import launch
    sys.exit(launch())

import math
import json
import random
from copy import deepcopy
from pathlib import Path
import sys
import time

try:
    import tkinter as tk
    from tkinter import filedialog, font, messagebox, ttk
except ImportError:
    raise SystemExit('Tkinter is missing. On Ubuntu/Debian: sudo apt install python3-tk\n'
                     'On Windows/macOS, use a Python installation that includes Tcl/Tk. See README.md.')

from engine import MAX_CHARACTERS, duration_for, format_time, make_plan, normalized_text
from i18n import translate, translate_error
from rules import builtin, validate_profile
from ai_client import DEFAULT_CONFIG, public_config

BG = '#F4F3EE'
CARD = '#FFFFFF'
INK = '#25362E'
MUTED = '#626C63'
LINE = '#DCDDD4'
GREEN = '#315E46'
PALE = '#E8EEE5'
RED = '#A64036'
SAMPLE = ('There is a rhythm to putting words on a page. A little pause, a second thought, '
          'then the next sentence.\n\n'
          'Paste your own text here, choose a pace, and watch it take shape.')


class Typecraft:
    def __init__(self, root, settings_path=None):
        self.root = root
        self.settings_path = Path(settings_path) if settings_path is not None else Path(__file__).parent / 'user_data' / 'settings.json'
        self.language = 'zh'
        self.active_profile = builtin('english')
        self.ai_config = dict(DEFAULT_CONFIG)
        self.ai_key = ''
        self.ai_draft = {}
        self.ai_undo = None
        self.ai_page = None
        self.settings_warning = False
        try:
            if self.settings_path.exists():
                if self.settings_path.stat().st_size > 600_000:
                    raise ValueError('Settings file too large')
                saved = json.loads(self.settings_path.read_text(encoding='utf-8'))
                profile = validate_profile(saved['profile'])
                language = saved['language']
                if language not in ('zh', 'en'):
                    raise ValueError('Unknown language')
                self.language, self.active_profile = language, profile
                if 'ai' in saved:
                    self.ai_config = public_config(saved['ai'], require_model=False)
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            self.settings_warning = True
        self.localized = []
        self.status_message = ('Ready when you are.', {})
        self.rule_page = None
        self.prepared_plan = None
        self.prepared_key = None
        self.plan_seed = random.SystemRandom().getrandbits(64)
        root.title(self.tr('Typecraft — typing with a little character'))
        root.geometry('1140x850')
        root.minsize(940, 680)
        root.configure(bg=BG)
        available = set(font.families(root))
        self.face = next((f for f in ('Segoe UI', 'SF Pro Text', 'Helvetica Neue', 'Noto Sans CJK SC', 'DejaVu Sans')
                          if f in available), 'TkDefaultFont')
        self.mono = next((f for f in ('Cascadia Code', 'Menlo', 'DejaVu Sans Mono', 'Consolas')
                          if f in available), 'TkFixedFont')
        root.option_add('*Font', (self.face, 10))
        self.mode = tk.StringVar(value='wps')
        self.speed = tk.StringVar(value='0.8')
        self.minutes = tk.StringVar(value='1.0')
        self.errors = tk.DoubleVar(value=2)
        self.rhythm = tk.DoubleVar(value=55)
        self.destination = tk.StringVar(value='preview')
        self.state = 'idle'
        self.controls = []
        self.plan = None
        self.keyboard = None
        self.index = 0
        self.active_elapsed = 0.0
        self.active_since = None
        self.remaining_delay = 0.0
        self.countdown_until = 0.0
        self.next_due = 0.0
        self.current_errors = 0
        self.main_page = tk.Frame(root, bg=BG)
        self.main_page.pack(fill='both', expand=True)
        self._build_style()
        self._build()
        for variable in (self.mode, self.speed, self.minutes, self.errors, self.rhythm, self.destination):
            variable.trace_add('write', self._refresh)
        self.source.bind('<<Modified>>', self._source_changed)
        root.bind('<Escape>', lambda event: self.stop())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self._refresh()
        if self.settings_warning:
            self.set_status('Saved settings could not be loaded. Defaults are shown.')
        self.timer_id = root.after(16, self._tick)

    def tr(self, message, **values):
        return translate(self.language, message, **values)

    def error_text(self, error):
        return translate_error(self.language, error)

    def set_status(self, message, **values):
        self.status_message = (message, values)
        self.status.configure(text=self.tr(message, **values))

    def _save_settings(self, language, profile):
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'language': language, 'profile': profile,
                                        'ai': public_config(self.ai_config, require_model=False)},
                                        ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temporary.replace(self.settings_path)

    def set_language(self, language):
        if self.state in ('typing', 'countdown', 'paused') or self.ai_page is not None or language == self.language:
            return
        try:
            self._save_settings(language, self.active_profile)
        except OSError as exc:
            messagebox.showerror(self.tr('Settings could not be saved'), self.error_text(exc), parent=self.root)
            return
        self.language = language
        for widget, original in self.localized:
            if widget.winfo_exists():
                widget.configure(text=self.tr(original))
        self.root.title(self.tr('Typecraft — typing with a little character'))
        self.menu_button.configure(text=self.tr('Settings ▾'))
        self.menu.entryconfigure(3, label=self.tr('Custom typing rules…'))
        self.menu.entryconfigure(4, label=self.tr('AI assistant…'))
        self.menu.entryconfigure(5, label=self.tr('Undo last AI application'))
        self.badge.configure(text=self.tr(self.state.upper()))
        self.set_status(self.status_message[0], **self.status_message[1])
        self.pause_button.configure(text=self.tr('Pause'))
        self._refresh()
        self._update_timing()

    def open_rules(self):
        if self.state in ('typing', 'countdown', 'paused') or self.rule_page is not None or self.ai_page is not None:
            return
        from rules_page import RulesPage
        self.main_page.pack_forget()
        self.rule_page = RulesPage(self)

    def open_ai(self):
        if self.state in ('typing', 'countdown', 'paused') or self.rule_page is not None or self.ai_page is not None:
            return
        from ai_page import AIPage
        self.main_page.pack_forget()
        self.ai_page = AIPage(self)

    def save_ai_connection(self, config):
        config = public_config(config)
        previous = self.ai_config
        self.ai_config = config
        try:
            self._save_settings(self.language, self.active_profile)
        except OSError:
            self.ai_config = previous
            raise

    def _main_snapshot(self):
        return {'text': self.source_text(), 'profile': deepcopy(self.active_profile),
                'mode': self.mode.get(), 'speed': self.speed.get(), 'minutes': self.minutes.get(),
                'errors': self.errors.get(), 'rhythm': self.rhythm.get(), 'seed': self.plan_seed}

    def apply_ai_text(self, text):
        if self.state in ('typing', 'countdown', 'paused'):
            raise ValueError('Stop typing before applying an AI result.')
        if not isinstance(text, str) or len(text) > MAX_CHARACTERS:
            raise ValueError('The AI result is too large.')
        self.ai_undo = self._main_snapshot()
        self._replace_source(text)
        self.menu.entryconfigure(5, state='normal')
        self.set_status('AI text applied. Review it before typing; Undo is available in Settings.')

    def apply_ai_plan(self, plan, source, seed):
        from ai_features import validate_plan
        if self.state in ('typing', 'countdown', 'paused'):
            raise ValueError('Stop typing before applying an AI result.')
        plan = validate_plan(json.dumps(plan, ensure_ascii=False), source)
        make_plan(source, duration_for(source, 'wps', plan['speed_wps']), plan['error_rate'] / 100,
                  plan['variation'] / 100, seed=seed, profile=plan['profile'])
        previous = self._main_snapshot()
        self._save_settings(self.language, plan['profile'])
        self.ai_undo = previous
        self.active_profile = deepcopy(plan['profile'])
        self.plan_seed = seed
        self.prepared_key = None
        self.mode.set('wps')
        self.speed.set(str(plan['speed_wps']))
        self.errors.set(plan['error_rate'])
        self.rhythm.set(plan['variation'])
        self._replace_source(source)
        self.menu.entryconfigure(5, state='normal')
        self.set_status('AI typing plan applied. Waits are included in the estimate; press Start when ready.')

    def undo_ai_application(self):
        if self.state in ('typing', 'countdown', 'paused') or self.ai_undo is None:
            return
        previous = self.ai_undo
        self._save_settings(self.language, previous['profile'])
        self.active_profile = deepcopy(previous['profile'])
        self.plan_seed = previous['seed']
        self.prepared_key = None
        self.mode.set(previous['mode'])
        self.speed.set(previous['speed'])
        self.minutes.set(previous['minutes'])
        self.errors.set(previous['errors'])
        self.rhythm.set(previous['rhythm'])
        self._replace_source(previous['text'])
        self.ai_undo = None
        self.menu.entryconfigure(5, state='disabled')
        self.set_status('Restored the text and typing settings from before the last AI application.')

    def apply_profile(self, profile):
        profile = validate_profile(profile)
        self._save_settings(self.language, profile)
        self.active_profile = profile
        self.prepared_key = None
        self._refresh()
        self.set_status('Rules applied. The main-page duration includes their waits.')

    def _prepare_plan(self):
        text = self.source_text()
        value = float(self.speed.get() if self.mode.get() == 'wps' else self.minutes.get())
        duration = duration_for(text, self.mode.get(), value)
        key = (text, duration, self.errors.get(), self.rhythm.get(),
               json.dumps(self.active_profile, sort_keys=True), self.plan_seed)
        if key != self.prepared_key:
            plan = make_plan(text, duration, self.errors.get() / 100, self.rhythm.get() / 100,
                             seed=self.plan_seed, profile=self.active_profile)
            self.prepared_key, self.prepared_plan = key, plan
        return self.prepared_plan

    def _update_timing(self):
        elapsed = self.elapsed()
        remaining = max(0, self.plan.duration - elapsed) if self.plan else 0
        self.timing.configure(text=self.tr('{elapsed} elapsed  /  {remaining} remaining',
                              elapsed=format_time(elapsed), remaining=format_time(remaining)))

    def _build_style(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TProgressbar', troughcolor=LINE, background=GREEN,
                        bordercolor=LINE, lightcolor=GREEN, darkcolor=GREEN, thickness=5)
        style.configure('TScrollbar', background=LINE, troughcolor=CARD,
                        bordercolor=CARD, arrowcolor=MUTED)

    def label(self, parent, text='', size=10, color=INK, weight='normal', **kwargs):
        widget = tk.Label(parent, text=self.tr(text), bg=parent.cget('bg'), fg=color,
                          font=(self.face, size, weight), **kwargs)
        if text:
            self.localized.append((widget, text))
        return widget

    def button(self, parent, text, command, primary=False, small=False, tracked=True):
        result = tk.Button(parent, text=self.tr(text), command=command, cursor='hand2',
                           bg=GREEN if primary else PALE, fg='white' if primary else INK,
                           activebackground='#244C37' if primary else '#D9E3D6',
                           activeforeground='white' if primary else INK,
                           disabledforeground='#889187', relief='flat', bd=0,
                           highlightthickness=0, padx=12, pady=7 if small else 11,
                           font=(self.face, 10, 'bold' if primary else 'normal'))
        if tracked:
            self.controls.append(result)
        self.localized.append((result, text))
        return result

    def _radio(self, parent, text, variable, value):
        item = tk.Radiobutton(parent, text=self.tr(text), variable=variable, value=value,
                              bg=parent.cget('bg'), fg=INK, activebackground=parent.cget('bg'),
                              selectcolor=CARD, anchor='w', highlightthickness=0,
                              font=(self.face, 10), cursor='hand2')
        self.controls.append(item)
        self.localized.append((item, text))
        return item

    def _entry(self, parent, variable):
        item = tk.Entry(parent, textvariable=variable, width=7, bg=CARD, fg=INK,
                        insertbackground=GREEN, relief='solid', bd=1,
                        font=(self.face, 16, 'bold'), justify='center',
                        disabledbackground=BG, disabledforeground=MUTED)
        self.controls.append(item)
        return item

    def _build(self):
        header = tk.Frame(self.main_page, bg=BG)
        header.pack(fill='x', padx=30, pady=(23, 20))
        mark = tk.Label(header, text='t.', bg=GREEN, fg='white', width=3,
                        font=(self.face, 24, 'bold'), pady=2)
        mark.pack(side='left', padx=(0, 13))
        title = tk.Frame(header, bg=BG)
        title.pack(side='left')
        self.label(title, 'Typecraft', 25, weight='bold').pack(anchor='w')
        self.label(title, 'A little rhythm. A little imperfection.', 10, MUTED).pack(anchor='w')
        self.menu_button = tk.Menubutton(header, text=self.tr('Settings ▾'), bg=GREEN, fg='white',
                                        activebackground=GREEN, activeforeground='white',
                                        relief='flat', padx=16, pady=10, cursor='hand2')
        self.menu = tk.Menu(self.menu_button, tearoff=False)
        self.menu.add_command(label='中文', command=lambda: self.set_language('zh'))
        self.menu.add_command(label='English', command=lambda: self.set_language('en'))
        self.menu.add_separator()
        self.menu.add_command(label=self.tr('Custom typing rules…'), command=self.open_rules)
        self.menu.add_command(label=self.tr('AI assistant…'), command=self.open_ai)
        self.menu.add_command(label=self.tr('Undo last AI application'), command=self.undo_ai_application, state='disabled')
        self.menu_button.configure(menu=self.menu)
        self.menu_button.pack(side='right')
        self.controls.append(self.menu_button)

        body = tk.Frame(self.main_page, bg=BG)
        body.pack(fill='both', expand=True, padx=30)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        main = tk.Frame(body, bg=BG)
        main.grid(row=0, column=0, sticky='nsew', padx=(0, 22))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        source_card = tk.Frame(main, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        source_card.grid(row=0, column=0, sticky='nsew', pady=(0, 16))
        bar = tk.Frame(source_card, bg=CARD)
        bar.pack(fill='x', padx=18, pady=(14, 6))
        self.label(bar, '01   YOUR TEXT', 10, weight='bold').pack(side='left')
        self.button(bar, 'Open .txt', self.open_file, small=True).pack(side='right', padx=(6, 0))
        self.button(bar, 'Paste', self.paste, small=True).pack(side='right')
        self.source = self._text(source_card, 5, self.face, 12)
        self.source.insert('1.0', SAMPLE)
        self.source.edit_modified(False)
        source_footer = tk.Frame(source_card, bg=CARD)
        source_footer.pack(fill='x', padx=18, pady=(4, 12))
        self.text_stats = self.label(source_footer, color=MUTED, size=9)
        self.text_stats.pack(side='left')
        self.button(source_footer, 'Clear', self.clear_source, small=True).pack(side='right')

        live_card = tk.Frame(main, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        live_card.grid(row=1, column=0, sticky='nsew')
        bar = tk.Frame(live_card, bg=CARD)
        bar.pack(fill='x', padx=18, pady=(16, 10))
        self.label(bar, '02   LIVE PREVIEW', 10, weight='bold').pack(side='left')
        self.badge = self.label(bar, 'READY', 9, GREEN, 'bold')
        self.badge.pack(side='right')
        self.preview = self._text(live_card, 6, self.mono, 12)
        self.preview.tag_configure('typo', foreground=RED, background='#FCEAE4')
        self.preview.configure(state='disabled')
        preview_footer = tk.Frame(live_card, bg=CARD)
        preview_footer.pack(fill='x', padx=18, pady=(6, 12))
        self.label(preview_footer, 'Mistypes briefly appear in red.', 9, MUTED).pack(side='left')
        self.button(preview_footer, 'Save .txt', self.save_preview, small=True).pack(side='right')
        self.button(preview_footer, 'Copy', self.copy_preview, small=True).pack(side='right', padx=(0, 6))

        settings = tk.Frame(body, bg=BG)
        settings.grid(row=0, column=1, sticky='ns')
        canvas = tk.Canvas(settings, bg=BG, width=298, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y', padx=(7, 0))
        canvas.pack(side='left', fill='both', expand=True)
        side = tk.Frame(canvas, bg=BG)
        item = canvas.create_window((0, 0), window=side, anchor='nw', width=298)
        side.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(item, width=event.width))
        def scroll_settings(event):
            if not canvas.winfo_ismapped():
                return
            if canvas.winfo_rootx() <= event.x_root < canvas.winfo_rootx() + canvas.winfo_width():
                if canvas.winfo_rooty() <= event.y_root < canvas.winfo_rooty() + canvas.winfo_height():
                    units = -1 if getattr(event, 'num', None) == 4 or event.delta > 0 else 1
                    canvas.yview_scroll(units * 2, 'units')
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.root.bind(sequence, scroll_settings, add='+')
        self.label(side, 'Find your rhythm.', 17, weight='bold').pack(anchor='w', pady=(0, 3))
        self.label(side, 'Set the pace. Leave room to hesitate.', 9, MUTED).pack(anchor='w', pady=(0, 18))
        self.label(side, 'PACE', 9, MUTED, 'bold').pack(anchor='w')
        row = tk.Frame(side, bg=BG)
        row.pack(fill='x', pady=(5, 5))
        self._radio(row, 'Words / second', self.mode, 'wps').pack(side='left')
        self.speed_entry = self._entry(row, self.speed)
        self.speed_entry.pack(side='right')
        row = tk.Frame(side, bg=BG)
        row.pack(fill='x', pady=5)
        self._radio(row, 'Finish in minutes', self.mode, 'minutes').pack(side='left')
        self.minutes_entry = self._entry(row, self.minutes)
        self.minutes_entry.pack(side='right')
        self.pace_hint = self.label(side, size=9, color=MUTED, justify='left')
        self.pace_hint.pack(anchor='w', pady=(4, 10))
        self.profile_hint = self.label(side, size=9, color=GREEN, wraplength=290, justify='left')
        self.profile_hint.pack(anchor='w', pady=(0, 8))
        presets = tk.Frame(side, bg=BG)
        presets.pack(fill='x')
        for name, speed, errors, rhythm in [('Relaxed', .6, 3, 70), ('Natural', .8, 2, 55), ('Quick', 1.4, 1, 35)]:
            self.button(presets, name, lambda s=speed, e=errors, r=rhythm: self.preset(s, e, r),
                        small=True).pack(side='left', padx=(0, 5))
        self._divider(side)
        self.error_label = self.label(side, size=10, weight='bold')
        self.error_label.pack(anchor='w')
        self.error_scale = self._scale(side, self.errors, 0, 10, .5)
        self.label(side, 'Nearby-key slips, then backspace + correction.', 9, MUTED,
                   wraplength=290, justify='left').pack(anchor='w')
        self.rhythm_label = self.label(side, size=10, weight='bold')
        self.rhythm_label.pack(anchor='w', pady=(14, 0))
        self._scale(side, self.rhythm, 0, 100, 1)
        self.label(side, 'Even pacing  ← →  Hesitations & punctuation pauses', 9, MUTED,
                   wraplength=290, justify='left').pack(anchor='w')
        self._divider(side)
        self.label(side, 'DESTINATION', 9, MUTED, 'bold').pack(anchor='w')
        self._radio(side, 'Preview here', self.destination, 'preview').pack(fill='x', pady=(5, 0))
        self._radio(side, 'Type into another app', self.destination, 'external').pack(fill='x')
        self.destination_hint = self.label(side, size=9, color=MUTED, wraplength=290,
                                            justify='left', anchor='nw')
        self.destination_hint.pack(fill='x', pady=(7, 0))
        self.label(side, 'Esc stops typing. Pause keeps your place.', 9, MUTED,
                   wraplength=290, justify='left').pack(side='bottom', anchor='w', pady=(10, 4))

        footer = tk.Frame(self.main_page, bg=BG)
        footer.pack(fill='x', padx=30, pady=(19, 19))
        top = tk.Frame(footer, bg=BG)
        top.pack(fill='x', pady=(0, 9))
        self.status = self.label(top, 'Ready when you are.', 10, INK)
        self.status.pack(side='left')
        self.progress_label = self.label(top, '0%', 10, MUTED)
        self.progress_label.pack(side='right')
        self.progress = ttk.Progressbar(footer, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=(0, 14))
        row = tk.Frame(footer, bg=BG)
        row.pack(fill='x')
        self.timing = self.label(row, '0:00 elapsed  /  — remaining', 10, MUTED)
        self.timing.pack(side='left')
        self.start_button = self.button(row, 'Start typing  →', self.start, primary=True, tracked=False)
        self.start_button.pack(side='right', padx=(9, 0))
        self.pause_button = self.button(row, 'Pause', self.pause, tracked=False)
        self.pause_button.pack(side='right', padx=(9, 0))
        self.stop_button = self.button(row, 'Stop', self.stop, tracked=False)
        self.stop_button.pack(side='right')
        self.pause_button.configure(state='disabled')
        self.stop_button.configure(state='disabled')

    def _text(self, parent, height, face, size):
        frame = tk.Frame(parent, bg=CARD)
        frame.pack(fill='both', expand=True, padx=18)
        scroll = ttk.Scrollbar(frame, orient='vertical')
        text = tk.Text(frame, height=height, width=10, bg=CARD, fg=INK,
                       insertbackground=GREEN, selectbackground='#CFE0CD', relief='flat',
                       bd=0, highlightthickness=0, wrap='word', font=(face, size),
                       padx=0, pady=8, spacing1=3, spacing3=3, undo=True,
                       yscrollcommand=scroll.set)
        scroll.configure(command=text.yview)
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        return text

    def _divider(self, parent):
        tk.Frame(parent, bg=LINE, height=1).pack(fill='x', pady=12)

    def _scale(self, parent, variable, start, end, resolution):
        scale = tk.Scale(parent, from_=start, to=end, resolution=resolution,
                         variable=variable, orient='horizontal', showvalue=False,
                         bg=BG, fg=GREEN, troughcolor=LINE, activebackground=GREEN,
                         highlightthickness=0, bd=0, sliderrelief='flat', sliderlength=22,
                         width=10, cursor='hand2')
        scale.pack(fill='x', pady=(5, 5))
        self.controls.append(scale)
        return scale

    def source_text(self):
        return normalized_text(self.source.get('1.0', 'end-1c'))

    def _source_changed(self, event=None):
        if self.source.edit_modified():
            self.source.edit_modified(False)
            self._refresh()

    def _refresh(self, *args):
        text = self.source_text()
        self.text_stats.configure(text=self.tr('{words:,} words  ·  {chars:,} characters', words=len(text.split()), chars=len(text)))
        self.error_label.configure(text=self.tr('Mistakes   {rate:g}%', rate=self.errors.get()))
        self.rhythm_label.configure(text=self.tr('Rhythm variation   {rate:.0f}%', rate=self.rhythm.get()))
        self.profile_hint.configure(text=self.tr('Profile: {name}', name=self.active_profile['name']))
        self.destination_hint.configure(text=self.tr(
            'A local rehearsal. No keyboard permissions needed.' if self.destination.get() == 'preview'
            else '5-second countdown: click the target text field. Esc stops globally. '
                 'Enter and Tab act as real keys; use a plain-text editor.'))
        try:
            plan = self._prepare_plan()
            base = plan.duration - plan.extra_wait
            wpm = len(text) / 5 / base * 60 if base else 0
            self.pace_hint.configure(text=self.tr('≈ {wpm:.0f} WPM · 1 word = 5 characters\nBase {base} + rule waits {extra:.1f}s\nExpected total {total}',
                                      wpm=wpm, base=format_time(base), extra=plan.extra_wait, total=format_time(plan.duration)))
        except (ValueError, OverflowError) as exc:
            self.pace_hint.configure(text=self.error_text(exc) if text.strip() else self.tr('Paste or type some text first.'))
        if self.state in ('idle', 'done', 'stopped', 'error'):
            self.speed_entry.configure(state='normal' if self.mode.get() == 'wps' else 'disabled')
            self.minutes_entry.configure(state='normal' if self.mode.get() == 'minutes' else 'disabled')
            self.error_scale.configure(state='normal' if self.active_profile['neighbor_errors'] else 'disabled')

    def preset(self, speed, errors, rhythm):
        self.mode.set('wps')
        self.speed.set(str(speed))
        self.errors.set(errors)
        self.rhythm.set(rhythm)

    def paste(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(self.tr('Clipboard is empty'), self.tr('Copy some text, then choose Paste.'), parent=self.root)
            return
        self._replace_source(text)

    def _replace_source(self, text):
        if len(text) > MAX_CHARACTERS:
            messagebox.showerror(self.tr('Text is too long'), self.tr('Use at most {limit:,} characters.', limit=MAX_CHARACTERS), parent=self.root)
            return
        self.source.delete('1.0', 'end')
        self.source.insert('1.0', normalized_text(text))
        self._refresh()

    def clear_source(self):
        self._replace_source('')

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[(self.tr('Text files'), '*.txt'), (self.tr('All files'), '*')])
        if path:
            try:
                if Path(path).stat().st_size > MAX_CHARACTERS * 4 + 3:
                    raise ValueError('The file is too large. Use at most 100,000 characters.')
                self._replace_source(Path(path).read_text(encoding='utf-8-sig'))
            except (OSError, UnicodeError, ValueError) as exc:
                messagebox.showerror(self.tr('Could not open file'), self.tr('Choose a UTF-8 text file.\n\n{error}', error=self.error_text(exc)), parent=self.root)

    def copy_preview(self):
        if self.state in ('typing', 'countdown', 'paused'):
            return  # Clipboard ownership must not disturb a running external session.
        self.root.clipboard_clear()
        self.root.clipboard_append(self.preview.get('1.0', 'end-1c'))
        self.set_status('Preview copied to clipboard.')

    def save_preview(self):
        if self.state in ('typing', 'countdown', 'paused'):
            return
        path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile='typecraft-preview.txt',
                                           filetypes=[(self.tr('Text files'), '*.txt')])
        if path:
            try:
                Path(path).write_text(self.preview.get('1.0', 'end-1c'), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror(self.tr('Could not save file'), self.error_text(exc), parent=self.root)

    def _lock(self, locked):
        for item in self.controls:
            item.configure(state='disabled' if locked else 'normal')
        self.source.configure(state='disabled' if locked else 'normal')
        self.start_button.configure(state='disabled' if locked else 'normal')
        self.stop_button.configure(state='normal' if locked else 'disabled')
        if not locked:
            self.pause_button.configure(state='disabled', text=self.tr('Pause'))
            self._refresh()

    def start(self):
        if self.state in ('typing', 'countdown', 'paused'):
            return
        try:
            plan = self._prepare_plan()
            self._refresh()
            # Leave enough time to deliver individual OS events and display corrections.
            max_rate = 60 if self.destination.get() == 'external' else 250
            key_count = sum(stroke.kind != 'wait' for stroke in plan.strokes)
            if key_count / (plan.duration - plan.extra_wait) > max_rate:
                raise ValueError('That is too fast for this destination. Lower the speed or increase the base minutes.')
            if self.destination.get() == 'external':
                from keyboard_output import KeyboardOutput
                self.keyboard = KeyboardOutput()
            self.plan = plan
        except Exception as exc:
            if self.keyboard:
                self.keyboard.close()
                self.keyboard = None
            messagebox.showerror(self.tr('Unable to start'), self.error_text(exc), parent=self.root)
            return
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        self.preview.configure(state='disabled')
        self.index = 0
        self.current_errors = 0
        self.active_elapsed = 0.0
        self.active_since = None
        self.progress['value'] = 0
        self.progress_label.configure(text='0%')
        self.remaining_delay = self.plan.strokes[0].delay
        self._update_timing()
        self._lock(True)
        if self.keyboard:
            self._begin_countdown()
        else:
            self._begin_typing()

    def _begin_countdown(self):
        self.state = 'countdown'
        self.countdown_until = time.monotonic() + 5
        self.badge.configure(text=self.tr('GET READY'), fg=GREEN)
        self.pause_button.configure(state='disabled')

    def _begin_typing(self):
        if self.keyboard:
            focused = self.root.focus_displayof()
            if focused is not None and focused.winfo_toplevel() == self.root:
                self._finish('stopped', 'Select a text field in another app during the countdown, then try again.')
                return
        self.state = 'typing'
        now = time.monotonic()
        self.active_since = now
        self.next_due = now + self.remaining_delay
        self.badge.configure(text=self.tr('TYPING'), fg=GREEN)
        self.pause_button.configure(text=self.tr('Pause'), state='normal')
        self.set_status('Typing into your selected app…' if self.keyboard else 'Finding the rhythm…')

    def elapsed(self):
        return self.active_elapsed + (time.monotonic() - self.active_since if self.active_since is not None else 0)

    def _freeze_clock(self):
        if self.active_since is not None:
            self.active_elapsed += time.monotonic() - self.active_since
            self.active_since = None

    def pause(self):
        if self.state == 'typing':
            self.remaining_delay = max(0, self.next_due - time.monotonic())
            self._freeze_clock()
            self.state = 'paused'
            self.badge.configure(text=self.tr('PAUSED'), fg=MUTED)
            self.set_status('Paused. Resume picks up at the next keystroke.')
            self.pause_button.configure(text=self.tr('Resume'))
        elif self.state == 'paused':
            if self.keyboard:
                self._begin_countdown()
            else:
                self._begin_typing()

    def stop(self):
        if self.state in ('typing', 'countdown', 'paused'):
            self._finish('stopped', 'Stopped. The partial output is kept; starting again types from the beginning.')

    def _finish(self, state, message, **values):
        self._freeze_clock()
        self.state = state
        self.plan_seed = random.SystemRandom().getrandbits(64)
        self.prepared_key = None
        if self.keyboard:
            self.keyboard.close()
            self.keyboard = None
        self.badge.configure(text=self.tr(state.upper()), fg=RED if state == 'error' else GREEN)
        self.set_status(message, **values)
        self._lock(False)
        if state == 'done':
            self.progress['value'] = 100
            self.progress_label.configure(text='100%')
            self.timing.configure(text=self.tr('{elapsed} elapsed  /  {remaining} remaining', elapsed=format_time(self.elapsed()), remaining='0:00'))

    def _emit(self, stroke):
        if self.keyboard and not self.keyboard.write(stroke):
            self.stop()
            return False
        self.preview.configure(state='normal')
        if stroke.kind == 'backspace':
            self.preview.delete('end-2c', 'end-1c')
        elif stroke.kind == 'insert':
            self.preview.insert('end', stroke.text, ('typo',) if stroke.typo else ())
        self.preview.see('end')
        self.preview.configure(state='disabled')
        if stroke.mistake_start:
            self.current_errors += 1
        percent = stroke.completed / self.plan.characters * 100
        self.progress['value'] = percent
        self.progress_label.configure(text=f'{percent:.0f}%')
        return True

    def _tick(self):
        delay = 16
        try:
            now = time.monotonic()
            if self.keyboard and self.keyboard.stop_requested.is_set():
                self.stop()
            if self.state == 'countdown':
                left = math.ceil(self.countdown_until - now)
                if left <= 0:
                    self._begin_typing()
                else:
                    self.set_status('Starting in {seconds}… Click the destination text field. Press Esc to cancel.', seconds=left)
            elif self.state == 'typing':
                # One stroke per event-loop turn keeps Stop/Pause responsive.
                if now >= self.next_due:
                    stroke = self.plan.strokes[self.index]
                    if self._emit(stroke):
                        self.index += 1
                        if self.index == len(self.plan.strokes):
                            self._finish('done', 'Finished. {chars:,} characters processed; {corrected} errors corrected, {retained} kept.',
                                         chars=self.plan.characters, corrected=self.plan.corrected, retained=self.plan.retained)
                        else:
                            if self.plan.strokes[self.index].fixed_delay > 0:
                                self.next_due = max(self.next_due, time.monotonic())
                            self.next_due += self.plan.strokes[self.index].delay
                if self.state == 'typing':
                    self._update_timing()
                    delay = max(1, min(16, math.ceil((self.next_due - time.monotonic()) * 1000)))
        except Exception as exc:
            self._finish('error', 'Typing stopped because the destination could not accept a keystroke.')
            messagebox.showerror(self.tr('Typing stopped'), self.error_text(exc), parent=self.root)
        self.timer_id = self.root.after(delay, self._tick)

    def close(self):
        self.root.after_cancel(self.timer_id)
        if self.ai_page is not None:
            self.ai_page.destroy()
            self.ai_page = None
        self.ai_key = ''
        if self.keyboard:
            self.keyboard.close()
        self.root.destroy()


def main():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f'Typecraft needs a graphical desktop and working Tcl/Tk.\n{exc}')
    Typecraft(root)
    root.mainloop()

