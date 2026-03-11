"""
Centralized UI colors and style strings for Stinger.

Light-mode cleanroom / production-lab palette.
Use COLORS for single values; use STYLES for full setStyleSheet strings.
"""

# Common hex colors — light cleanroom palette
COLORS = {
    # Base text colors
    "text_primary": "#1a1a2e",
    "text_secondary": "#4b5563",
    "muted": "#6b7280",
    "muted_placeholder": "#9ca3af",
    "white": "#ffffff",

    # Layered surface colors (light, increasing depth = darker)
    "bg_surface_0": "#f0f2f5",  # Window / deepest background
    "bg_surface_1": "#ffffff",  # Cards, panels
    "bg_surface_2": "#e8eaed",  # Elevated elements, inputs
    "bg_surface_3": "#d1d5db",  # Highest elevation accents

    # Button states (neutral gray)
    "button_default": "#e5e7eb",
    "button_hover": "#d1d5db",
    "button_active": "#c4c8cf",
    "button_disabled": "#f3f4f6",

    # Border colors
    "border": "#d1d5db",
    "border_subtle": "rgba(0, 0, 0, 0.08)",
    "border_muted": "rgba(0, 0, 0, 0.12)",
    "border_strong": "rgba(0, 0, 0, 0.20)",

    # Accent colors
    "accent_blue": "#2563eb",
    "accent_blue_hover": "#1d4ed8",
    "accent_blue_active": "#1e40af",
    "accent_blue_muted": "rgba(37, 99, 235, 0.10)",

    # Status colors (slightly desaturated for clinical feel)
    "success": "#16a34a",
    "success_hover": "#15803d",
    "success_muted": "rgba(22, 163, 74, 0.10)",
    "danger": "#dc2626",
    "danger_hover": "#b91c1c",
    "danger_muted": "rgba(220, 38, 38, 0.10)",
    "warning": "#d97706",
    "warning_hover": "#b45309",
    "warning_muted": "rgba(217, 119, 6, 0.10)",
    "unknown": "#9ca3af",
}

# Typography scale with line-height guidance
TYPOGRAPHY = {
    "caption": "font-size: 10px; line-height: 1.4;",
    "body": "font-size: 13px; line-height: 1.5;",
    "subtitle": "font-size: 15px; line-height: 1.4;",
    "title": "font-size: 18px; line-height: 1.3;",
    "headline": "font-size: 24px; line-height: 1.2;",
    "display": "font-size: 32px; line-height: 1.1;",
}

# Border radius scale
RADIUS = {
    "small": "4px",
    "medium": "8px",
    "large": "12px",
    "xlarge": "16px",
    "pill": "999px",
}

# Status level to background color (for status badges/pills)
STATUS_COLORS = {
    "ok": COLORS["success"],
    "warning": COLORS["warning"],
    "error": COLORS["danger"],
    "unknown": COLORS["unknown"],
}

# Full stylesheet strings for common widgets
STYLES = {
    "main_window_bg": f"QMainWindow {{ background-color: {COLORS['bg_surface_0']}; }}",
    "title_muted_11": f"color: {COLORS['muted']}; {TYPOGRAPHY['caption']}",
    "label_muted_12": f"color: {COLORS['muted']}; {TYPOGRAPHY['body']}",
    "value_white_bold": f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']} font-weight: bold;",
    "status_label": f"color: {COLORS['text_primary']}; font-weight: bold;",

    # Enhanced button styles with better states
    "action_button": (
        f"QPushButton {{ "
        f"background-color: {COLORS['button_default']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"font-weight: bold; "
        f"padding: 8px 16px; "
        f"}}"
        f"QPushButton:hover {{ "
        f"background-color: {COLORS['button_hover']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"}}"
        f"QPushButton:pressed {{ "
        f"background-color: {COLORS['button_active']}; "
        f"}}"
        f"QPushButton:disabled {{ "
        f"background-color: {COLORS['button_disabled']}; "
        f"color: {COLORS['muted']}; "
        f"opacity: 0.5; "
        f"}}"
    ),

    "close_button": (
        f"QPushButton {{ "
        f"background-color: {COLORS['danger']}; "
        f"color: white; "
        f"font-weight: bold; "
        f"border-radius: {RADIUS['medium']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"}}"
        f"QPushButton:hover {{ "
        f"background-color: {COLORS['danger_hover']}; "
        f"}}"
    ),

    "end_wo_button": (
        f"QPushButton {{ "
        f"background-color: {COLORS['button_default']}; "
        f"color: {COLORS['text_primary']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"font-weight: bold; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"}}"
        f"QPushButton:hover {{ "
        f"background-color: {COLORS['warning']}; "
        f"color: white; "
        f"}}"
    ),

    "topbar_meta_chip": (
        f"color: {COLORS['text_primary']}; "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"padding: 2px 8px; "
        f"font-weight: bold;"
    ),

    "compact_panel_shell": (
        f"background-color: {COLORS['bg_surface_1']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['medium']};"
    ),

    "serial_group_shell": (
        "QFrame { "
        f"background-color: {COLORS['bg_surface_2']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['medium']}; "
        "padding: 4px 8px; "
        "}"
    ),

    "serial_stepper_button": (
        "QPushButton { "
        f"background-color: {COLORS['button_hover']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['medium']}; "
        "}"
        "QPushButton:hover { "
        f"background-color: {COLORS['bg_surface_3']}; "
        "}"
        "QPushButton:pressed { "
        f"background-color: {COLORS['button_active']}; "
        "}"
    ),

    # Pill-shaped progress bar (flat, no gradient)
    "progress_bar": (
        f"QProgressBar {{ "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['pill']}; "
        f"background: {COLORS['bg_surface_2']}; "
        f"text-align: center; "
        f"}}"
        f"QProgressBar::chunk {{ "
        f"background-color: {COLORS['success']}; "
        f"border-radius: {RADIUS['pill']}; "
        f"}}"
    ),

    "progress_label": f"color: {COLORS['text_primary']}; font-size: 13px; font-weight: bold;",

    "menu": (
        f"QMenu {{ "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"padding: 4px; "
        f"}}"
        f"QMenu::item {{ "
        f"padding: 8px 16px; "
        f"border-radius: {RADIUS['small']}; "
        f"}}"
        f"QMenu::item:selected {{ "
        f"background-color: {COLORS['bg_surface_2']}; "
        f"}}"
    ),

    # Enhanced card with subtle border
    "card": (
        f"background-color: {COLORS['bg_surface_1']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: {RADIUS['large']};"
    ),

    "card_title": f"color: {COLORS['text_primary']}; {TYPOGRAPHY['title']} font-weight: bold;",
    "placeholder_heading": f"color: {COLORS['muted_placeholder']};",

    "readonly_text_edit": (
        f"QTextEdit {{ "
        f"background-color: {COLORS['bg_surface_0']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"padding: 8px; "
        f"}}"
    ),

    "table_widget": (
        f"QTableWidget {{ "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"gridline-color: {COLORS['border_subtle']}; "
        f"}}"
        f"QHeaderView::section {{ "
        f"background-color: {COLORS['bg_surface_2']}; "
        f"color: {COLORS['text_primary']}; "
        f"font-weight: bold; "
        f"padding: 8px; "
        f"border: none; "
        f"border-bottom: 1px solid {COLORS['border_muted']}; "
        f"}}"
    ),

    # Custom tab widget styling
    "tab_widget": (
        f"QTabWidget::pane {{ "
        f"border: none; "
        f"background: transparent; "
        f"}}"
        f"QTabBar::tab {{ "
        f"background: transparent; "
        f"color: {COLORS['muted']}; "
        f"padding: 12px 24px; "
        f"margin-right: 4px; "
        f"border: none; "
        f"border-bottom: 2px solid transparent; "
        f"}}"
        f"QTabBar::tab:selected {{ "
        f"color: {COLORS['text_primary']}; "
        f"border-bottom: 2px solid {COLORS['accent_blue']}; "
        f"}}"
        f"QTabBar::tab:hover {{ "
        f"color: {COLORS['text_primary']}; "
        f"}}"
    ),

    # Input field styling
    "input_field": (
        f"QLineEdit {{ "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"padding: 8px 12px; "
        f"{TYPOGRAPHY['body']} "
        f"}}"
        f"QLineEdit:focus {{ "
        f"border: 1px solid {COLORS['accent_blue']}; "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"}}"
        f"QLineEdit:disabled {{ "
        f"background-color: {COLORS['button_disabled']}; "
        f"color: {COLORS['muted']}; "
        f"}}"
    ),

    # ComboBox styling
    "combo_box": (
        f"QComboBox {{ "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"border-radius: {RADIUS['medium']}; "
        f"padding: 6px 12px; "
        f"{TYPOGRAPHY['body']} "
        f"}}"
        f"QComboBox:hover {{ "
        f"border: 1px solid {COLORS['border_strong']}; "
        f"}}"
        f"QComboBox::drop-down {{ "
        f"border: none; "
        f"padding-right: 8px; "
        f"}}"
        f"QComboBox::down-arrow {{ "
        f"width: 12px; "
        f"height: 12px; "
        f"}}"
        f"QComboBox QAbstractItemView {{ "
        f"background-color: {COLORS['bg_surface_1']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_muted']}; "
        f"selection-background-color: {COLORS['accent_blue_muted']}; "
        f"selection-color: {COLORS['text_primary']}; "
        f"outline: none; "
        f"}}"
    ),
}


def status_badge_style(level: str) -> str:
    """Build stylesheet for a status badge (pill) from level (ok, warning, error, unknown)."""
    bg = STATUS_COLORS.get(level, COLORS["unknown"])
    return (
        "color: white; font-weight: bold;"
        f" background-color: {bg};"
        " border-radius: 10px; padding: 4px 8px;"
    )


def status_tool_button_style(color: str) -> str:
    """Build stylesheet for compact status tool button."""
    return (
        "QToolButton {"
        f" background-color: {COLORS['bg_surface_1']};"
        f" color: {color};"
        f" border: 1px solid {color};"
        f" border-radius: {RADIUS['medium']};"
        " padding: 7px 12px;"
        " font-weight: bold;"
        " font-size: 11px;"
        " min-width: 118px;"
        " text-align: center; }"
        f"QToolButton:hover {{ border: 1px solid {color}; background-color: {COLORS['bg_surface_0']}; }}"
    )
