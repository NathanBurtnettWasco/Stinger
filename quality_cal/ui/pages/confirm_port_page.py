"""Simple confirmation page for moving the Mensor between ports."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QWizardPage


class ConfirmPortPage(QWizardPage):
    def __init__(self, *, title: str, message: str, parent=None) -> None:
        super().__init__(parent)
        self.setTitle(title)
        self.setSubTitle("Confirm the Mensor is connected to the requested port.")

        outer_layout = QVBoxLayout(self)
        outer_layout.addStretch(1)

        container = QWidget(self)
        container.setMaximumWidth(760)
        layout = QVBoxLayout(container)

        label = QLabel(message)
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 14pt; font-weight: bold; color: #1f2937;")
        layout.addWidget(label)
        layout.addStretch(1)
        outer_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch(1)
