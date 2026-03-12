"""Simple confirmation page for moving the Mensor between ports."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from quality_cal.ui.styles import COLORS, TYPOGRAPHY


class ConfirmPortPage(QWizardPage):
    def __init__(self, *, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setTitle(title)
        self.setSubTitle("Confirm the Mensor is connected to the requested port.")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 12, 20, 20)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setMaximumWidth(980)
        layout = QVBoxLayout(container)
        layout.setSpacing(18)

        card = QFrame(container)
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(18)

        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
        )
        card_layout.addWidget(label)

        instructions = QLabel(
            "1. Disconnect the Mensor from the current port.\n"
            "2. Connect the Mensor to the requested port and verify the fitting is snug.\n"
            "3. Confirm the connection is secure, then click Next."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}; "
            "margin: 8px 0; padding-left: 4px;"
        )
        card_layout.addWidget(instructions)

        self.mensor_port_label = QLabel("Mensor COM port: —")
        self.mensor_port_label.setWordWrap(True)
        self.mensor_port_label.setStyleSheet(
            f"color: {COLORS['muted']}; {TYPOGRAPHY['caption']}; "
            "padding: 8px 12px; background: rgba(0,0,0,0.04); border-radius: 6px;"
        )
        card_layout.addWidget(self.mensor_port_label)

        hint = QLabel(
            "Use Refresh Now on the Hardware Check page if you reconnect hardware "
            "and want the app to retry detection."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}")
        card_layout.addWidget(hint)

        layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    def initializePage(self) -> None:
        wizard = self.wizard()
        if wizard is not None:
            mensor_cfg = wizard.config.get("hardware", {}).get("mensor", {})
            port = mensor_cfg.get("port", "")
            display = str(port).strip() if port else "—"
            self.mensor_port_label.setText(f"Mensor COM port: {display}")
