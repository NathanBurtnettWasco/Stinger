"""Login/setup page for the quality calibration wizard."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from quality_cal.ui.styles import COLORS, TYPOGRAPHY


class LoginPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Quality Calibration Setup")
        self.setSubTitle("Enter technician information and choose optional checks.")

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 12, 20, 20)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        container.setMaximumWidth(980)
        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(24)

        overview_card = QFrame(container)
        overview_card.setProperty("card", True)
        overview_layout = QVBoxLayout(overview_card)
        overview_layout.setContentsMargins(28, 28, 28, 28)
        overview_layout.setSpacing(18)

        eyebrow = QLabel("QUALITY WORKFLOW")
        eyebrow.setProperty("role", "eyebrow")
        overview_layout.addWidget(eyebrow)

        hero_title = QLabel("Prepare the stand and capture a clean calibration record.")
        hero_title.setWordWrap(True)
        hero_title.setProperty("role", "heroTitle")
        overview_layout.addWidget(hero_title)

        intro = QLabel(
            "Run live hardware verification, optional port leak checks, left and right "
            "Alicat-to-Mensor comparison, and final PDF export from one guided flow."
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "heroBody")
        overview_layout.addWidget(intro)

        steps_panel = QFrame(overview_card)
        steps_panel.setProperty("panel", "soft")
        steps_layout = QVBoxLayout(steps_panel)
        steps_layout.setContentsMargins(18, 18, 18, 18)
        steps_layout.setSpacing(10)
        steps_heading = QLabel("What happens next")
        steps_heading.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
        )
        steps_layout.addWidget(steps_heading)
        steps_copy = QLabel(
            "1. Verify both Alicats, the LabJack, and the Mensor.\n"
            "2. Optionally run leak checks.\n"
            "3. Complete left and right calibration passes.\n"
            "4. Save or print the final report."
        )
        steps_copy.setWordWrap(True)
        steps_copy.setStyleSheet(f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}")
        steps_layout.addWidget(steps_copy)
        overview_layout.addWidget(steps_panel)

        main_layout.addWidget(overview_card)

        form_card = QFrame(container)
        form_card.setProperty("card", True)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(28, 28, 28, 28)
        form_layout.setSpacing(22)

        form_title = QLabel("Session details")
        form_title.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['title']} font-weight: bold;"
        )
        form_layout.addWidget(form_title)

        form_intro = QLabel(
            "Enter the technician and asset information for this calibration run."
        )
        form_intro.setWordWrap(True)
        form_intro.setStyleSheet(f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}")
        form_layout.addWidget(form_intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(20)

        self.technician_input = QLineEdit()
        self.technician_input.setPlaceholderText("Enter your name")
        self.technician_input.setMinimumHeight(54)
        self.technician_input.textChanged.connect(lambda: self.completeChanged.emit())
        form.addRow("Technician:", self.technician_input)

        self.asset_id_input = QLineEdit("222")
        self.asset_id_input.setPlaceholderText("Asset ID")
        self.asset_id_input.setMinimumHeight(54)
        self.asset_id_input.setMaximumWidth(280)
        self.asset_id_input.textChanged.connect(lambda: self.completeChanged.emit())
        form.addRow("Asset ID:", self.asset_id_input)

        self.include_leak_check_checkbox = QCheckBox("Include port leak check")
        self.include_leak_check_checkbox.setChecked(False)
        self.include_leak_check_checkbox.setMinimumHeight(42)
        form.addRow("", self.include_leak_check_checkbox)

        form_layout.addLayout(form)

        note_panel = QFrame(form_card)
        note_panel.setProperty("panel", "soft")
        note_layout = QVBoxLayout(note_panel)
        note_layout.setContentsMargins(16, 16, 16, 16)
        note_layout.setSpacing(6)
        note_title = QLabel("Report output")
        note_title.setStyleSheet(f"font-weight: bold; color: {COLORS['text_primary']};")
        note_body = QLabel(
            "Reports are exported to the calibration certificate folder using the "
            "configured naming template."
        )
        note_body.setWordWrap(True)
        note_body.setStyleSheet(f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}")
        note_layout.addWidget(note_title)
        note_layout.addWidget(note_body)
        form_layout.addWidget(note_panel)

        main_layout.addWidget(form_card)
        main_layout.addStretch(1)

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

        self.registerField("technician_name*", self.technician_input)
        self.registerField("asset_id*", self.asset_id_input)
        self.registerField("include_leak_check", self.include_leak_check_checkbox)

    def isComplete(self) -> bool:
        return bool(self.technician_input.text().strip()) and bool(
            self.asset_id_input.text().strip()
        )

    def validatePage(self) -> bool:
        wizard = self.wizard()
        if wizard is not None:
            wizard.session.technician_name = self.technician_input.text().strip()
            wizard.session.asset_id = self.asset_id_input.text().strip()
            wizard.session.include_leak_check = self.include_leak_check_checkbox.isChecked()
            wizard.session.begin()
        return super().validatePage()
