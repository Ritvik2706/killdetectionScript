"""Run with python -m killcutter.gui, or the killcutter-desktop launcher."""
import os
import sys


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Killcutter Studio desktop")
    parser.add_argument("--config", help="Use a specific TOML settings file")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close the shell to verify a native build")
    args = parser.parse_args(argv)
    # DPI awareness must be requested before creating the first Windows window.
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    try:
        from .app import Application
        app = Application(config_path=args.config)
    except ImportError as exc:
        print(f'Desktop dependency missing: {exc}. Install with: python -m pip install -e ".[gui]"', file=sys.stderr)
        return 1
    if args.smoke_test:
        app.after(300, app.close)
    app.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
