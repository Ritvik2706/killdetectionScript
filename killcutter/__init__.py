"""
Killfeed Auto-Cutter
====================
Detect kills in a Call of Duty recording from the "ENEMY DOWNED" banner and
assemble the highlights into a Premiere Pro-ready EDL.

Public entry point is :func:`killcutter.cli.main`, reachable via::

    python -m killcutter detect
    python -m killcutter export
"""

__version__ = "1.0.0"
APP_NAME = "Killfeed Auto-Cutter"
