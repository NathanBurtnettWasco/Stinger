"""Shared styling for the quality calibration wizard. Uses main Stinger design system."""

from __future__ import annotations

from app.ui.styles import (
    COLORS,
    RADIUS,
    STYLES,
    TYPOGRAPHY,
)

# Re-export for pages that need table_widget, progress_bar, card, etc.
__all__ = [
    "APP_STYLESHEET",
    "COLORS",
    "neutral_badge_style",
    "status_badge_style",
    "STYLES",
]

# Build wizard-wide stylesheet from shared palette so quality cal matches main Stinger
APP_STYLESHEET = f"""
QWidget {{
    background: {COLORS['bg_surface_0']};
    color: {COLORS['text_primary']};
    {TYPOGRAPHY['body']}
}}
QWizard {{
    background: {COLORS['bg_surface_0']};
}}
QLabel[role="eyebrow"] {{
    color: {COLORS['accent_blue']};
    {TYPOGRAPHY['caption']}
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}}
QLabel[role="heroTitle"] {{
    color: {COLORS['text_primary']};
    {TYPOGRAPHY['headline']}
    font-weight: 700;
}}
QLabel[role="heroBody"] {{
    color: {COLORS['text_secondary']};
    {TYPOGRAPHY['body']}
}}
QFrame[card="true"] {{
    background: {COLORS['bg_surface_1']};
    border: 1px solid {COLORS['border_subtle']};
    border-radius: {RADIUS['large']};
}}
QFrame[panel="soft"] {{
    background: {COLORS['bg_surface_2']};
    border: 1px solid {COLORS['border_subtle']};
    border-radius: {RADIUS['xlarge']};
}}
QLineEdit {{
    background: {COLORS['bg_surface_1']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_muted']};
    border-radius: {RADIUS['medium']};
    padding: 8px 12px;
    {TYPOGRAPHY['body']}
}}
QLineEdit:focus {{
    border: 1px solid {COLORS['accent_blue']};
}}
QLineEdit:disabled {{
    background: {COLORS['button_disabled']};
    color: {COLORS['muted']};
}}
QPushButton {{
    background: {COLORS['button_default']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border_subtle']};
    border-radius: {RADIUS['medium']};
    padding: 8px 16px;
    font-weight: bold;
}}
QPushButton:hover {{
    background: {COLORS['button_hover']};
    border: 1px solid {COLORS['border_muted']};
}}
QPushButton:pressed {{
    background: {COLORS['button_active']};
}}
QPushButton:disabled {{
    background: {COLORS['button_disabled']};
    color: {COLORS['muted']};
    opacity: 0.5;
}}
QPushButton#primaryButton {{
    background: {COLORS['accent_blue']};
    color: white;
    border: 1px solid {COLORS['accent_blue_hover']};
}}
QPushButton#primaryButton:hover {{
    background: {COLORS['accent_blue_hover']};
}}
QPushButton#primaryButton:pressed {{
    background: {COLORS['accent_blue_active']};
}}
QCheckBox {{
    spacing: 10px;
    color: {COLORS['text_primary']};
    {TYPOGRAPHY['body']}
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
}}
{STYLES['progress_bar']}
"""


def status_badge_style(ok: bool) -> str:
    """Pill-style badge for Ready (ok=True) or Check/Fail (ok=False). Uses shared COLORS."""
    if ok:
        bg = COLORS["success_muted"]
        fg = COLORS["success"]
        border = COLORS["success"]
    else:
        bg = COLORS["danger_muted"]
        fg = COLORS["danger"]
        border = COLORS["danger"]
    return (
        f"background: {bg}; color: {fg}; border: 1px solid {border}; "
        f"border-radius: {RADIUS['pill']}; padding: 8px 14px; font-weight: 700; min-width: 84px;"
    )


def neutral_badge_style() -> str:
    """Pill-style badge for neutral/checking state."""
    return (
        f"background: {COLORS['bg_surface_2']}; color: {COLORS['muted']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['pill']}; padding: 8px 14px; font-weight: 700; min-width: 84px;"
    )
