"""Preset library and editor; detector-specific fields stay out of the workspace."""
from dataclasses import replace
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

from killcutter import config, outputs, presets
from . import theme as t
from .widgets import Card, ScrollForm, label


class PresetViews:
    def _init_presets(self):
        self.preset_library = presets.Library(self.config_path)
        key = config.section(self.cfg, 'gui').get('detection_preset', 'warzone')
        self.active_preset = self.preset_library.items.get(key, presets.WARZONE)
        self.preset_var = tk.StringVar(value=self.active_preset.name)
        self.active_preset_text = tk.StringVar(value='Analysis preset · ' + self.active_preset.name)
        self.preset_description = tk.StringVar()
        self.preset_selectors = []

    def _preset_selector(self, parent):
        selector = ttk.Combobox(parent, textvariable=self.preset_var, state='readonly',
                                values=[p.name for p in self.preset_library.items.values()])
        selector.configure(postcommand=lambda: t.style_popdown(selector))
        selector.bind('<<ComboboxSelected>>', self.select_preset)
        self.preset_selectors.append(selector)
        return selector

    def _build_presets(self):
        form = ScrollForm(self._page('presets'))
        form.pack(fill='both', expand=True)
        card = Card(form.body)
        card.pack(fill='x')
        label(card.content, 'Preset for your next analysis', size=20, bold=True).pack(anchor='w')
        label(card.content, 'Choose what to detect. Existing highlights stay unchanged.',
              color=t.MUTED).pack(anchor='w', pady=(5, 16))
        self._preset_selector(card.content).pack(fill='x')
        label(card.content, textvariable=self.preset_description, color=t.MUTED,
              wraplength=700, justify='left').pack(anchor='w', pady=(12, 8))
        self.preset_summary = tk.StringVar()
        label(card.content, textvariable=self.preset_summary, wraplength=700,
              justify='left').pack(anchor='w', pady=(0, 16))
        actions = tk.Frame(card.content, bg=t.CARD)
        actions.pack(fill='x')
        self.preset_new_button = ttk.Button(actions, text='New preset…',
            style='CardPrimary.TButton', command=self.create_preset)
        self.preset_new_button.pack(side='left')
        self.preset_edit_button = ttk.Button(actions, text='Edit preset…', command=self.edit_selected_preset)
        self.preset_edit_button.pack(side='left', padx=8)
        self.preset_more_button = ttk.Button(actions, text='More ▾', command=self.show_preset_menu)
        self.preset_more_button.pack(side='right')
        self.preset_import_button = ttk.Button(actions, text='Import…', command=self.import_preset)
        self.preset_import_button.pack(side='right', padx=8)
        self.preset_action_hint = tk.StringVar()
        label(card.content, textvariable=self.preset_action_hint, color=t.MUTED,
              wraplength=700, justify='left').pack(anchor='w', pady=(14, 0))
        if self.preset_library.errors:
            label(form.body, 'Some presets could not be loaded:\n' + '\n'.join(self.preset_library.errors),
                  color=t.AMBER, wraplength=700, justify='left').pack(anchor='w', pady=12)
        self.update_preset_summary()

    def update_preset_summary(self):
        preset = self.active_preset
        descriptions = {
            'warzone': 'Built-in · Warzone banner detection, player names and player / bot classification.',
            'text': 'Text recognition (OCR) · Finds a phrase in a selected area.',
            'color': 'Colour detection · Finds a colour in a selected area.',
            'motion': 'Motion detection · Finds changes in a selected area. Camera movement also counts.',
            'scene': 'Scene changes · Finds large changes between sampled frames.',
            'audio': 'Audio level · Finds loud sounds, rather than specific words or sound effects.',
        }
        self.preset_description.set(descriptions[preset.detector])
        if preset.detector == 'warzone':
            details = 'Ready to use with its tuned HUD detector.'
        elif preset.detector == 'audio':
            details = f'Threshold: {preset.audio_db:g} dBFS · Highlight label: {preset.label}'
        else:
            area = 'Whole frame' if preset.region == (0, 0, 1, 1) else 'Custom detection area'
            signal = (f'Phrase: “{preset.text}”' if preset.detector == 'text' else
                      'Colour: #%02X%02X%02X' % preset.color if preset.detector == 'color' else
                      f'Changed area: {preset.coverage:.0%}')
            details = f'{signal}\n{area} · Highlight label: {preset.label}'
        self.preset_summary.set(details)
        self.preset_action_hint.set(
            'This detector is built in. Use New preset to create your own from a sample video.'
            if preset.detector == 'warzone' else
            'New and Edit guide you through a sample frame and detection settings. Import loads a saved preset file.')
        self.update_preset_actions()

    def update_preset_actions(self):
        busy = bool(self.working)
        for button in (self.preset_new_button, self.preset_import_button, self.preset_more_button):
            button.state(['disabled'] if busy else ['!disabled'])
        self.preset_edit_button.state(['disabled'] if busy or self.active_preset.detector == 'warzone' else ['!disabled'])

    def preset_menu(self):
        menu = tk.Menu(self, tearoff=0, bg=t.CARD, fg=t.INK,
                       activebackground=t.SELECTED, activeforeground=t.INK)
        editable = not self.working and self.active_preset.id != 'warzone'
        menu.add_command(label='Rename…', command=self.rename_preset, state='normal' if editable else 'disabled')
        menu.add_command(label='Duplicate', command=self.duplicate_preset,
                         state='normal' if not self.working and self.active_preset.detector != 'warzone' else 'disabled')
        menu.add_command(label='Export preset file…', command=self.export_preset,
                         state='disabled' if self.working else 'normal')
        menu.add_separator()
        menu.add_command(label='Delete…', command=self.delete_preset, state='normal' if editable else 'disabled')
        return menu

    def show_preset_menu(self):
        menu = self.preset_menu()
        try:
            menu.tk_popup(self.preset_more_button.winfo_rootx(),
                          self.preset_more_button.winfo_rooty() + self.preset_more_button.winfo_height())
        finally:
            menu.grab_release()

    def rename_preset(self):
        if self.working or self.active_preset.id == 'warzone':
            return
        name = simpledialog.askstring('Rename preset', 'Preset name', initialvalue=self.active_preset.name, parent=self)
        if name is None:
            return
        try:
            preset = replace(self.active_preset, name=name.strip())
            self.preset_library.save(preset)
            self._refresh_presets(preset)
        except Exception as exc:
            self.error('Could not rename preset', str(exc))

    def duplicate_preset(self):
        if self.working or self.active_preset.detector == 'warzone':
            return
        original = self.active_preset
        name = original.name[:93] + ' (copy)'
        names = {p.name for p in self.preset_library.items.values()}
        index = 2
        while name in names:
            suffix = f' (copy {index})'
            name = original.name[:100-len(suffix)] + suffix
            index += 1
        try:
            preset = replace(original, id='recipe-' + uuid4().hex[:12], name=name)
            self.preset_library.save(preset)
            self._refresh_presets(preset)
            self.status.set('Copy created and selected. Use Edit preset to change its detection settings.')
        except Exception as exc:
            self.error('Could not duplicate preset', str(exc))

    def select_preset(self, event=None):
        if self.working:
            self.preset_var.set(self.active_preset.name)
            return
        self.active_preset = next(p for p in self.preset_library.items.values() if p.name == self.preset_var.get())
        self.active_preset_text.set('Analysis preset · ' + self.active_preset.name)
        self.update_preset_summary()
        try:
            config.save_updates(self.config_path, {'gui': {'detection_preset': self.active_preset.id}})
        except Exception as exc:
            self.error('Could not remember preset', str(exc))
        self.status.set(f'Next analysis: {self.active_preset.name}. Existing results keep their original preset.')

    def create_preset(self, preset=None):
        if self.working:
            return
        from .preset_wizard import PresetWizard
        self.show_recording_picker(
            on_select=lambda path: PresetWizard(self, path, preset=preset),
            preset_name=preset.name if preset else None)


    def edit_selected_preset(self):
        if self.working:
            return
        if self.active_preset.detector == 'warzone':
            self.status.set('Warzone is ready to use. Choose New preset to set up your own detection area or signal.')
            return
        return self.create_preset(self.active_preset)

    def _refresh_presets(self, preset):
        for selector in self.preset_selectors:
            selector.configure(values=[p.name for p in self.preset_library.items.values()])
        self.preset_var.set(preset.name)
        self.select_preset()

    def import_preset(self):
        if self.working:
            return
        path = filedialog.askopenfilename(parent=self, title='Import detection preset', filetypes=[('Detection preset', '*.json')])
        if not path:
            return
        try:
            preset = presets.load(path)
            names = {p.name for p in self.preset_library.items.values()}
            name = preset.name
            while name in names:
                name += ' (imported)'
            preset = replace(preset, id='recipe-' + uuid4().hex[:12], name=name)
            self.preset_library.save(preset)
            self._refresh_presets(preset)
        except Exception as exc:
            self.error('Could not import preset', str(exc))

    def export_preset(self):
        if self.working:
            return
        path = filedialog.asksaveasfilename(parent=self, title='Export saved preset',
                                          defaultextension='.json', initialfile=self.active_preset.id+'.json')
        if path:
            try:
                sources = [self.config_path]
                if self.state.media:
                    sources.append(self.state.media.path)
                outputs.validate_paths(sources, [path])
                presets.save(path, self.active_preset)
                self.status.set(f'Preset exported · {path}')
            except Exception as exc:
                self.error('Could not export preset', str(exc))

    def delete_preset(self):
        if self.working:
            return
        preset = self.active_preset
        if preset.id == 'warzone':
            self.status.set('The built-in Warzone preset cannot be deleted.')
            return
        if messagebox.askyesno('Delete preset?', f'Delete "{preset.name}"? Existing analysis results are kept.', parent=self):
            try:
                self.preset_library.delete(preset.id)
                self._refresh_presets(presets.WARZONE)
            except Exception as exc:
                self.error('Could not delete preset', str(exc))
