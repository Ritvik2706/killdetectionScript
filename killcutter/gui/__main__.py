"""Run with python -m killcutter.gui, or the killcutter-desktop launcher."""
import os
import sys


def main(argv=None):
    from .runtime import configure
    configure()
    import argparse
    parser = argparse.ArgumentParser(description="Killcutter Studio desktop")
    parser.add_argument("--config", help="Use a specific TOML settings file")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close the shell to verify a native build")
    parser.add_argument("--wslg", action="store_true",
                        help="On WSL, run inside WSLg instead of handing off to Windows Python")
    args = parser.parse_args(argv)
    from . import wsl
    if not args.wslg and wsl.should_hand_off():
        try:
            return wsl.run_on_windows(args.config, args.smoke_test)
        except wsl.HandoffError as exc:
            print(f'Could not run with Windows Python: {exc}\n'
                  'Falling back to WSLg (the window may stay blank under a Windows tiling window manager).',
                  file=sys.stderr)
    # DPI awareness must be requested before creating the first Windows window.
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Killcutter.Studio')
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        from .app import Application
        app = Application(config_path=args.config)
    except ImportError as exc:
        # tkinter's shared libraries come from the OS, not pip.
        if 'tk' in str(exc).lower() or getattr(exc, 'name', None) in ('tkinter', '_tkinter'):
            print(f'Tk is not installed: {exc}. Install your OS package, e.g. '
                  '"sudo pacman -S tk" (Arch), "sudo apt install python3-tk" (Debian/Ubuntu), '
                  '"sudo dnf install python3-tkinter" (Fedora).', file=sys.stderr)
        else:
            print(f'Desktop dependency missing: {exc}. Install with: python -m pip install -e ".[gui]"', file=sys.stderr)
        return 1
    if args.smoke_test:
        app.after(300, app.close)
    app.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
