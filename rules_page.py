"""A separate rule-editor page, with a draft isolated from the running profile."""
from copy import deepcopy
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from rules import builtin, load_profile, save_profile, validate_profile, typo

BG, CARD, INK, MUTED, GREEN, LINE = '#F4F3EE', '#FFFFFF', '#25362E', '#626C63', '#315E46', '#DCDDD4'


class RulesPage(tk.Frame):
    def __init__(self, app):
        super().__init__(app.root, bg=BG)
        self.app = app
        self.t = app.tr
        self.draft = deepcopy(app.active_profile)
        self.original = deepcopy(self.draft)
        self.selected = None
        self.baseline = None
        self.loading = False
        self.pack(fill='both', expand=True)
        header = tk.Frame(self, bg=BG)
        header.pack(fill='x', padx=24, pady=(18, 12))
        self._button(header, 'Back', self.back).pack(side='left', padx=(0, 14))
        tk.Label(header, text=self.t('Custom typing rules'), font=(app.face, 21, 'bold'), bg=BG, fg=INK).pack(side='left')
        self._button(header, 'Apply and return', self.apply, True).pack(side='right')
        tk.Label(self, text=self.t('Two presets to start. Make a copy your own.'),
                 bg=BG, fg=MUTED, anchor='w').pack(fill='x', padx=24)
        top = tk.Frame(self, bg=BG)
        top.pack(fill='x', padx=24, pady=12)
        self._label(top, 'Profile name').pack(side='left', padx=(0, 8))
        self.name = tk.StringVar()
        ttk.Entry(top, textvariable=self.name, width=27).pack(side='left', fill='x', expand=True)
        for caption, callback in [('English preset', lambda: self.load_builtin('english')),
                                  ('Chinese preset', lambda: self.load_builtin('chinese')),
                                  ('Import JSON', self.import_file), ('Export JSON', self.export_file)]:
            self._button(top, caption, callback).pack(side='left', padx=(7, 0))
        neighbor = tk.LabelFrame(self, text=self.t('Enable nearby-key mistakes (rate set on the main page)'),
                                 bg=BG, fg=INK, padx=10, pady=7)
        neighbor.pack(fill='x', padx=24, pady=(0, 10))
        self.neighbor = tk.BooleanVar()
        ttk.Checkbutton(neighbor, variable=self.neighbor, text=self.t('Enabled')).pack(side='left', padx=(0, 14))
        self.neighbor_ranges = {}
        for caption, key in [('Notice wait', 'neighbor_notice_ms'), ('Backspace interval', 'neighbor_backspace_ms'),
                             ('Before correction', 'neighbor_resume_ms')]:
            pair = self._range(neighbor, caption, horizontal=True)
            self.neighbor_ranges[key] = pair
        self._label(neighbor, 'Min / max (ms)').pack(side='left', padx=4)

        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True, padx=24)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 15))
        table = tk.Frame(left, bg=BG)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('kind', 'chance', 'on'), selectmode='browse')
        self.tree.heading('#0', text=self.t('Rule'))
        self.tree.column('#0', width=170, minwidth=100)
        for key, caption, width in [('kind', 'Type', 80), ('chance', 'Chance', 60), ('on', 'On', 45)]:
            self.tree.heading(key, text=self.t(caption))
            self.tree.column(key, width=width, minwidth=40, stretch=False)
        scroll = ttk.Scrollbar(table, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.select_rule)
        actions = tk.Frame(left, bg=BG)
        actions.pack(fill='x', pady=(10, 0))
        self._button(actions, 'Add rule', self.add_rule).pack(side='left')
        self._button(actions, 'Delete', self.delete_rule).pack(side='left', padx=7)

        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky='nsew')
        canvas = tk.Canvas(right, bg=CARD, highlightthickness=1, highlightbackground=LINE, width=410)
        scroll = ttk.Scrollbar(right, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        form = tk.Frame(canvas, bg=CARD, padx=15, pady=12)
        window = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))
        form.grid_columnconfigure(1, weight=1)
        self.fields = {key: tk.StringVar() for key in ('type', 'name', 'match', 'replacement', 'probability')}
        self.correct = tk.BooleanVar(value=True)
        self.enabled = tk.BooleanVar(value=True)
        self.input_widgets = {}
        for row, (key, caption) in enumerate([('type', 'Type'), ('name', 'Rule name'),
                                              ('match', 'Original / trigger text'), ('replacement', 'Wrong text'),
                                              ('probability', 'Probability (%)')]):
            self._label(form, caption).grid(row=row, column=0, sticky='w', padx=(0, 10), pady=6)
            if key == 'type':
                widget = ttk.Combobox(form, textvariable=self.fields[key], state='readonly',
                                      values=(self.t('Typo'), self.t('Pause only')), width=18)
                widget.bind('<<ComboboxSelected>>', lambda event: self._update_kind())
            else:
                widget = ttk.Entry(form, textvariable=self.fields[key], width=21)
            widget.grid(row=row, column=1, sticky='ew', pady=6)
            self.input_widgets[key] = widget
        self.range_fields = {}
        self.range_widgets = {}
        for row, (key, caption) in enumerate([('wait_ms', 'Wait after typo / trigger'),
                                              ('backspace_ms', 'Backspace interval'),
                                              ('resume_ms', 'Before correction')], 5):
            self._label(form, caption).grid(row=row, column=0, sticky='w', padx=(0, 10), pady=6)
            holder = tk.Frame(form, bg=CARD)
            holder.grid(row=row, column=1, sticky='ew')
            pair = [tk.StringVar(), tk.StringVar()]
            widgets = []
            for var in pair:
                entry = ttk.Entry(holder, textvariable=var, width=6)
                entry.pack(side='left', padx=(0, 4))
                widgets.append(entry)
            self.range_fields[key] = pair
            self.range_widgets[key] = widgets
        self._label(form, 'Min / max (ms)').grid(row=8, column=1, sticky='w', pady=(0, 8))
        ttk.Checkbutton(form, text=self.t('Enabled'), variable=self.enabled).grid(row=9, column=0, columnspan=2, sticky='w', pady=5)
        self.correct_check = ttk.Checkbutton(form, text=self.t('Correct automatically'), variable=self.correct,
                                             command=self._update_kind)
        self.correct_check.grid(row=10, column=0, columnspan=2, sticky='w', pady=5)
        self._button(form, 'Save rule', self.save_rule, True).grid(row=11, column=0, columnspan=2, sticky='w', pady=10)
        self._label(form, 'Waits are added to the base time, never compressed.\nUnchecked “Correct automatically” keeps the wrong text.',
                    wraplength=380, justify='left').grid(row=12, column=0, columnspan=2, sticky='w', pady=(0, 10))
        self.note = tk.Label(self, bg=BG, fg=MUTED, anchor='w')
        self.note.pack(fill='x', padx=24, pady=14)
        self._load(self.draft)

    def _label(self, parent, caption, **kwargs):
        return tk.Label(parent, text=self.t(caption), bg=parent.cget('bg'), fg=INK, **kwargs)

    def _button(self, parent, caption, command, primary=False):
        return tk.Button(parent, text=self.t(caption), command=command, bg=GREEN if primary else '#E8EEE5',
                         fg='white' if primary else INK, relief='flat', padx=10, pady=8, cursor='hand2')

    def _range(self, parent, caption, horizontal=False):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(side='left', padx=(0, 12))
        self._label(frame, caption).pack(anchor='w')
        row = tk.Frame(frame, bg=BG)
        row.pack()
        variables = [tk.StringVar(), tk.StringVar()]
        for var in variables:
            ttk.Entry(row, textvariable=var, width=6).pack(side='left', padx=(0, 3))
        return variables

    def _error(self, caption, exc):
        messagebox.showerror(self.t(caption), self.app.error_text(exc), parent=self.app.root)

    def _snapshot(self):
        return ([v.get() for v in self.fields.values()], self.correct.get(), self.enabled.get(),
                [[v.get() for v in pair] for pair in self.range_fields.values()])

    def _fill(self, rule=None):
        self.loading = True
        if rule is None:
            rule = typo('', '', '', .1)
        for key in self.fields:
            value = rule.get(key, '')
            if key == 'type':
                value = self.t('Typo' if rule['type'] == 'typo' else 'Pause only')
            elif key == 'probability':
                value = f"{rule['probability'] * 100:g}"
            self.fields[key].set(value)
        self.correct.set(rule.get('correct', True))
        self.enabled.set(rule.get('enabled', True))
        for key, pair in self.range_fields.items():
            for var, value in zip(pair, rule.get(key, [0, 0])):
                var.set(f'{value:g}')
        self._update_kind()
        self.baseline = self._snapshot()
        self.loading = False

    def _update_kind(self):
        is_typo = self.fields['type'].get() == self.t('Typo')
        self.input_widgets['replacement'].configure(state='normal' if is_typo else 'disabled')
        self.correct_check.configure(state='normal' if is_typo else 'disabled')
        for key in ('backspace_ms', 'resume_ms'):
            for widget in self.range_widgets[key]:
                widget.configure(state='normal' if is_typo and self.correct.get() else 'disabled')

    def _read_form(self):
        kind = 'typo' if self.fields['type'].get() == self.t('Typo') else 'pause'
        rule = {'type': kind, 'name': self.fields['name'].get(), 'match': self.fields['match'].get(),
                'probability': float(self.fields['probability'].get()) / 100, 'enabled': self.enabled.get(),
                'wait_ms': [float(v.get()) for v in self.range_fields['wait_ms']]}
        if kind == 'typo':
            rule.update(replacement=self.fields['replacement'].get(), correct=self.correct.get(),
                        backspace_ms=[float(v.get()) for v in self.range_fields['backspace_ms']],
                        resume_ms=[float(v.get()) for v in self.range_fields['resume_ms']])
        return rule

    def _flush(self):
        if self.baseline != self._snapshot():
            return self.save_rule()
        return True

    def save_rule(self):
        try:
            rule = self._read_form()
            temporary = deepcopy(self.draft)
            temporary['rules'] = [rule]
            rule = validate_profile(temporary)['rules'][0]
            if self.selected is None:
                if len(self.draft['rules']) >= 200:
                    raise ValueError('A profile can contain at most 200 rules.')
                self.draft['rules'].append(rule)
                self.selected = len(self.draft['rules']) - 1
            else:
                self.draft['rules'][self.selected] = rule
            self.baseline = self._snapshot()
            self._refresh_tree()
            self.note.configure(text=self.t('Rule saved.'))
            return True
        except (ValueError, TypeError) as exc:
            self._error('Invalid configuration', exc)
            return False

    def _refresh_tree(self):
        self.loading = True
        self.tree.delete(*self.tree.get_children())
        for index, rule in enumerate(self.draft['rules']):
            self.tree.insert('', 'end', iid=str(index), text=rule['name'],
                             values=(self.t('Typo' if rule['type'] == 'typo' else 'Pause only'),
                                     f"{rule['probability'] * 100:g}%", self.t('Yes' if rule['enabled'] else 'No')))
        if self.selected is not None:
            self.tree.selection_set(str(self.selected))
        self.loading = False

    def select_rule(self, event=None):
        if self.loading or not self.tree.selection():
            return
        index = int(self.tree.selection()[0])
        if index == self.selected:
            return
        if not self._flush():
            if self.selected is not None:
                self.tree.selection_set(str(self.selected))
            else:
                self.tree.selection_remove(*self.tree.selection())
            return
        self.selected = index
        self._fill(self.draft['rules'][index])
        self.tree.selection_set(str(index))

    def add_rule(self):
        if not self._flush():
            return
        self.selected = None
        self.tree.selection_remove(*self.tree.selection())
        self._fill()
        self.input_widgets['name'].focus_set()

    def delete_rule(self):
        if self.selected is not None:
            del self.draft['rules'][self.selected]
        self.selected = None
        self._fill()
        self._refresh_tree()

    def _read_profile(self):
        if not self._flush():
            return None
        data = deepcopy(self.draft)
        data['name'] = self.name.get()
        data['neighbor_errors'] = self.neighbor.get()
        for key, pair in self.neighbor_ranges.items():
            data[key] = [float(v.get()) for v in pair]
        return validate_profile(data)

    def _load(self, data):
        self.draft = deepcopy(data)
        self.name.set(data['name'])
        self.neighbor.set(data['neighbor_errors'])
        for key, pair in self.neighbor_ranges.items():
            for var, value in zip(pair, data[key]):
                var.set(f'{value:g}')
        self.selected = 0 if data['rules'] else None
        self._fill(data['rules'][0] if data['rules'] else None)
        self._refresh_tree()
        self.note.configure(text=self.t('Changes stay in this draft until you apply them.'))

    def _dirty(self):
        if self._snapshot() != self.baseline or self.draft != self.original:
            return True
        if self.name.get() != self.original['name'] or self.neighbor.get() != self.original['neighbor_errors']:
            return True
        return any([v.get() for v in pair] != [f'{n:g}' for n in self.original[key]]
                   for key, pair in self.neighbor_ranges.items())

    def _can_replace(self):
        return not self._dirty() or messagebox.askyesno(self.t('Discard changes?'),
                    self.t('Replace this draft with the selected profile?'), parent=self.app.root)

    def load_builtin(self, key):
        if self._can_replace():
            self._load(builtin(key))

    def import_file(self):
        path = filedialog.askopenfilename(parent=self.app.root, filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            data = load_profile(path)
            if self._can_replace():
                self._load(data)
        except (ValueError, TypeError, OSError, UnicodeError) as exc:
            self._error('Could not import', exc)

    def export_file(self):
        try:
            data = self._read_profile()
            if data is None:
                return
            path = filedialog.asksaveasfilename(parent=self.app.root, defaultextension='.json',
                    initialfile='my-typecraft-rules.json', filetypes=[('JSON', '*.json')])
            if path:
                save_profile(path, data)
                self.note.configure(text=self.t('Exported successfully.'))
        except (ValueError, TypeError, OSError) as exc:
            self._error('Could not export', exc)

    def apply(self):
        try:
            data = self._read_profile()
            if data is None:
                return
            self.app.apply_profile(data)
            self._return()
        except (ValueError, TypeError, OSError) as exc:
            self._error('Settings could not be saved', exc)

    def back(self):
        if self._dirty() and not messagebox.askyesno(self.t('Discard changes?'),
                self.t('Leave without applying your changes?'), parent=self.app.root):
            return
        self._return()

    def _return(self):
        self.app.rule_page = None
        self.destroy()
        self.app.main_page.pack(fill='both', expand=True)
