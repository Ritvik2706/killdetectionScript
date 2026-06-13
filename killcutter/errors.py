"""Exception types raised by the core; the CLI turns these into tidy messages."""


class KillcutterError(Exception):
    """Base class for all expected, user-facing failures."""


class VideoError(KillcutterError):
    """A video file could not be opened or read."""


class NoClipsError(KillcutterError):
    """No kill clips were available to export."""
