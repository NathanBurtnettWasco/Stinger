"""Shared styling helpers for the standalone quality calibration UI."""

from __future__ import annotations


APP_STYLESHEET = """
QWidget {
    background: #eef2f6;
    color: #111827;
    font-size: 11pt;
}
QWizard {
    background: #eef2f6;
}
QLabel[role="eyebrow"] {
    color: #2563eb;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}
QLabel[role="heroTitle"] {
    color: #0f172a;
    font-size: 22pt;
    font-weight: 700;
}
QLabel[role="heroBody"] {
    color: #475569;
    font-size: 11pt;
    line-height: 1.45;
}
QFrame[card="true"] {
    background: #ffffff;
    border: 1px solid #d8e0e8;
    border-radius: 18px;
}
QFrame[panel="soft"] {
    background: #f8fafc;
    border: 1px solid #dbe4ee;
    border-radius: 16px;
}
QLineEdit {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 12pt;
}
QLineEdit:focus {
    border: 2px solid #2563eb;
    padding: 9px 13px;
}
QPushButton {
    background: #e5e7eb;
    color: #111827;
    border: 1px solid #cbd5e1;
    border-radius: 14px;
    padding: 10px 18px;
    font-size: 11pt;
    font-weight: 700;
}
QPushButton:hover {
    background: #dbe3ea;
}
QPushButton:pressed {
    background: #cfd8e3;
}
QCheckBox {
    spacing: 10px;
    color: #111827;
    font-size: 11pt;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
}
"""


def status_badge_style(ok: bool) -> str:
    if ok:
        bg = "#dcfce7"
        fg = "#166534"
        border = "#86efac"
    else:
        bg = "#fee2e2"
        fg = "#b91c1c"
        border = "#fca5a5"
    return (
        f"background: {bg}; color: {fg}; border: 1px solid {border}; "
        "border-radius: 999px; padding: 8px 14px; font-weight: 700; min-width: 84px;"
    )


def neutral_badge_style() -> str:
    return (
        "background: #e2e8f0; color: #475569; border: 1px solid #cbd5e1; "
        "border-radius: 999px; padding: 8px 14px; font-weight: 700; min-width: 84px;"
    )
