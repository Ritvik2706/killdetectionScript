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
        app.show('inspector')
        app.inspect_pixel(100, 100, (30, 100, 180))
        assert app.sample['x'] == 100
        capture(app, folder / 'inspector.png')
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
        app.reset_appearance()
        pump(app, seconds=.3)
        print(f'PASS: import, frame seek, range, live merge, highlights, remove/undo, compact layout, '
              f'inspector, saved settings, themes and scaling. Screenshots: {folder}')
    finally:
        app.exported = True
        app.working = None
        app.close()


if __name__ == '__main__':
    main()
