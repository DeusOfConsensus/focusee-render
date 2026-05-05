"""
focusee-render
==============
A private CLI tool that renders FocuSee screen recordings into
polished MP4 videos — with background, rounded corners, drop shadow,
cursor overlay, click ripples, and auto-zoom effects.
"""

__version__ = "1.0.0"
__author__ = "Asmodeus"

from .render import render

__all__ = ["render"]
