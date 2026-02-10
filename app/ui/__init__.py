"""
UI layer for Stinger.

PyQt6-based touch-first interface with:
- Main production workflow
- Debug mode for engineering
- Admin mode for observability
"""

from .main_window import MainWindow

__all__ = ['MainWindow']
