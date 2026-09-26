"""Exercise the desktop on a real display and save window-only screenshots."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
import cv2
import numpy as np
from PIL import ImageGrab
from killcutter.gui.app import Application
from killcutter.models import Clip


def pump(app, predicate=lambda: False, seconds=1):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if predicate():
            return
        time.sleep(.02)


def capture(app, path):
    pump(app, seconds=.3)
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x+app.winfo_width(), y+app.winfo_height())).save(path)


def main():
    folder = Path(tempfile.mkdtemp(prefix='killcutter-gui-'))
    app = Application(config_path=str(folder / 'config.toml'))
    app.overrideredirect(True)  # deterministic dimensions even under tiling window managers
    app.geometry('1320x860+30+30')
    try:
        pump(app)
        capture(app, folder / 'workspace.png')
        source = folder / 'test recording.mp4'
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'mp4v'), 30, (640, 360))
        assert writer.isOpened()
        for i in range(90):
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            frame[:] = (35, 25, 20)
            cv2.rectangle(frame, (80+i, 80), (220+i, 240), (180, 100, 30), -1)
            cv2.putText(frame, 'TEST RECORDING', (30, 330), cv2.FONT_HERSHEY_SIMPLEX, .8, (240, 240, 240), 1)
            writer.write(frame)
        writer.release()
        app.open_file(str(source))
        pump(app, lambda: app.state.media is not None and not app.working, 8)
        assert app.state.media and app.preview.image
        app.seek.set(1)
        app._seek_changed(1)
        pump(app, lambda: app.frame_time == 1, 8)
        assert app.frame_time == 1
        app.mark_in()
        assert app._range()[0] == 1
        capture(app, folder / 'recording.png')
        app.working = 'scan'
        app.scan_started = time.monotonic()
        app.jobs.events.put(('highlight', (0, 1, Clip(.5, 2, 'Player One'), False), None))
        app.jobs.events.put(('highlight', (0, 1.5, Clip(.5, 2.5, 'Player One, Player Two'), True), None))
        app.jobs.events.put(('progress', (.5, 1, 4), None))
        pump(app, lambda: bool(app.state.clips))
        assert app.live_table.item('0', 'values') == ('Player One, Player Two',)
        capture(app, folder / 'live-analysis.png')
        app.working = None
        app.show('results')
        app.table.selection_set('0')
        capture(app, folder / 'highlights.png')
        app.state.clips = [Clip(.2, 1, 'Rival One', {'real-player': True}),
                           Clip(1, 2, 'Bot encounter', {'real-player': False}),
                           Clip(2, 2.8, 'Unclassified encounter')]
        app.filter_results()
        app.kill_filter.set('real-player')
        app.select_all_results()
        capture(app, folder / 'kill-filters.png')
        app.geometry('980x680+30+30')
        capture(app, folder / 'kill-filters-compact.png')
        assert app.table.winfo_height() > 60
        app.reset_result_filters()
        app.state.clips = [Clip(.5, 2.5, 'Player One, Player Two')]
        app.filter_results()

        app.show('workspace')
        app.geometry('980x680+30+30')
        capture(app, folder / 'compact.png')
        form = app.pages['workspace'].winfo_children()[0]
        form.canvas.yview_moveto(1)
        pump(app, seconds=.2)
        assert app.scan_button.winfo_rooty() + app.scan_button.winfo_height() < app.winfo_rooty() + app.winfo_height()
        capture(app, folder / 'compact-controls.png')
        form.canvas.yview_moveto(0)
        app.geometry('1320x860+30+30')
        from killcutter.gui.preset_wizard import PresetWizard
        app.show('presets')
        capture(app, folder / 'preset-library.png')
        wizard = PresetWizard(app, str(source))
        wizard.overrideredirect(True)
        wizard.geometry('980x760+60+40')
        pump(app, lambda: wizard.ready, 8)
        assert wizard.ready
        wizard.time_var.set('00:01.500')
        wizard.go_to_time()
        pump(app, lambda: wizard.ready, 8)
        assert wizard.position == 1.5
        capture(wizard, folder / 'preset-choose-frame.png')
        wizard.next_step()
        wizard.kind_var.set('A colour appears')
        wizard.change_kind()
        wizard.name_var.set('Blue indicator')
        wizard.select_region((.1, .15, .65, .65))
        wizard.select_pixel(150, 150, (30, 100, 180))
        capture(wizard, folder / 'preset-setup.png')
        wizard.geometry('720x600+60+40')
        capture(wizard, folder / 'preset-setup-compact.png')
        assert wizard.next_button.winfo_rooty() + wizard.next_button.winfo_height() < wizard.winfo_rooty() + wizard.winfo_height()
        wizard.destroy()
        app.new_preset('color')
        picker = app.pick_preset_colour()
        picker.select_pixel(100, 100, (30, 100, 180))
        capture(picker, folder / 'preset-colour-picker.png')
        picker.confirm()
        assert app.preset_fields['color'].get() == '#1E64B4'
        app.show('results')
        app.table.selection_set('0')
        app.remove_selected()
        assert not app.state.clips
        app.undo_remove()
        assert len(app.state.clips) == 1
        app.show('settings')
        app.save_settings()
        assert (folder / 'config.toml').exists()
        capture(app, folder / 'settings.png')
        for theme, scale in [('Graphite', 1.0), ('Daylight', 1.25)]:
            app.theme_var.set(theme)
            app.scale_var.set(scale)
            app.accent_var.set('#7D5BED' if theme == 'Daylight' else '#22B8A6')
            app.apply_appearance()
            pump(app, seconds=.3)
            capture(app, folder / f'appearance-{theme.lower()}.png')
            app.show('workspace')
            capture(app, folder / f'workspace-{theme.lower()}.png')
            app.show('settings')
        app.new_preset('color')
        app.preset_fields['name'].set('Blue rectangle')
        app.preset_fields['label'].set('Rectangle visible')
        app.preset_fields['color'].set('#1E64B4')
        app.preset_fields['coverage'].set('5')
        app.save_preset()
        assert app.active_preset.detector == 'color'
        capture(app, folder / 'presets.png')
        app.exported = True
        app.full_range()
        app.start_scan()
        pump(app, lambda: not app.working, 10)
        assert not app.working and len(app.state.clips) == 1
        assert app.state.clips[0].name == 'Rectangle visible'
        assert not app.state.player_traits
        assert 'type' not in app.table.cget('displaycolumns')
        capture(app, folder / 'general-results.png')
        app.reset_appearance()
        pump(app, seconds=.3)
        print(f'PASS: import, frame seek, range, live merge, highlights, remove/undo, compact layout, '
              f'preset colour picker, saved settings, themes, presets and real colour detection. Screenshots: {folder}')
    finally:
        app.exported = True
        app.working = None
        app.close()


def controls():
    import tkinter as tk
    from tkinter import ttk
    from killcutter.gui import theme as t
    from killcutter.gui.widgets import Card, label
    folder = Path(tempfile.mkdtemp(prefix='killcutter-controls-'))
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry('700x480+40+60')
    try:
        for palette in t.PALETTES:
            t.configure(palette, '#7D5BED', 1.0)
            t.apply(root)
            root.configure(bg=t.BG)
            card = Card(root)
            card.pack(fill='both', expand=True, padx=18, pady=18)
            label(card.content, palette + ' · controls', size=20, bold=True).pack(anchor='w', pady=(0, 16))
            ttk.Scale(card.content, from_=0, to=100, value=45).pack(fill='x', pady=10)
            disabled = ttk.Scale(card.content, value=.4)
            disabled.state(['disabled'])
            disabled.pack(fill='x', pady=10)
            ttk.Progressbar(card.content, value=65).pack(fill='x', pady=10)
            scroll = ttk.Scrollbar(card.content, orient='horizontal')
            scroll.pack(fill='x', pady=10)
            scroll.set(.15, .55)
            combo = ttk.Combobox(card.content, state='readonly', values=['Text appears', 'A colour appears', 'Movement', 'Scene changes', 'Loud sounds'])
            combo.current(0)
            combo.configure(postcommand=lambda c=combo: t.style_popdown(c))
            combo.pack(fill='x', pady=10)
            ttk.Checkbutton(card.content, text='Include undetermined kills').pack(anchor='w', pady=10)
            capture(root, folder / (palette.lower() + '.png'))
            root.tk.call('ttk::combobox::Post', str(combo))
            capture(root, folder / (palette.lower() + '-dropdown.png'))
            root.tk.call('ttk::combobox::Unpost', str(combo))
            card.destroy()
        print(f'Controls screenshots: {folder}')
    finally:
        root.destroy()


if __name__ == '__main__':
    controls() if '--controls' in sys.argv else main()
