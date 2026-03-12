"""Combined setup + hardware check: login/session on the left, hardware status on the right."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from app.services import run_async
from quality_cal.ui.styles import (
    COLORS,
    TYPOGRAPHY,
    neutral_badge_style,
    status_badge_style,
)

_CARD_BASE = (
    f"QFrame {{ background: {COLORS['bg_surface_1']}; "
    f"border: 1px solid {COLORS['border_subtle']}; "
    f"border-radius: 12px; "
    f"border-left: 4px solid {COLORS['border_muted']}; "
    f"padding: 0; }}"
)


def _card_accent_style(ok: bool) -> str:
    accent = COLORS["success"] if ok else COLORS["danger"]
    return (
        f"QFrame {{ background: {COLORS['bg_surface_1']}; "
        f"border: 1px solid {COLORS['border_subtle']}; "
        f"border-radius: 12px; "
        f"border-left: 4px solid {accent}; "
        f"padding: 0; }}"
    )


class LoginHardwarePage(QWizardPage):
    """Single page: session details (left column), hardware check (right column)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Setup & Hardware")
        self.setSubTitle("Enter session details and verify hardware before continuing.")
        self._refresh_in_progress = False
        self._check_passed = False
        self._has_completed_refresh = False
        self._status_labels: dict[str, QLabel] = {}
        self._detail_labels: dict[str, QLabel] = {}
        self._card_frames: dict[str, QFrame] = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._start_check)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 12, 20, 20)
        outer.setSpacing(24)

        # —— Left column: Login / session ——
        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMaximumWidth(420)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(18)

        form_card = QFrame(left_widget)
        form_card.setProperty("card", True)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(24, 24, 24, 24)
        form_layout.setSpacing(18)

        form_title = QLabel("Session details")
        form_title.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['title']} font-weight: bold;"
        )
        form_layout.addWidget(form_title)

        form_intro = QLabel(
            "Enter technician and asset information for this calibration run."
        )
        form_intro.setWordWrap(True)
        form_intro.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}"
        )
        form_layout.addWidget(form_intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(16)

        self.technician_input = QLineEdit()
        self.technician_input.setPlaceholderText("Enter your name")
        self.technician_input.setMinimumHeight(44)
        self.technician_input.textChanged.connect(lambda: self.completeChanged.emit())
        form.addRow("Technician:", self.technician_input)

        self.asset_id_input = QLineEdit("222")
        self.asset_id_input.setPlaceholderText("Asset ID")
        self.asset_id_input.setMinimumHeight(44)
        self.asset_id_input.setMaximumWidth(220)
        self.asset_id_input.textChanged.connect(lambda: self.completeChanged.emit())
        form.addRow("Asset ID:", self.asset_id_input)

        self.include_leak_check_checkbox = QCheckBox("Include port leak check")
        self.include_leak_check_checkbox.setChecked(False)
        form.addRow("", self.include_leak_check_checkbox)

        form_layout.addLayout(form)

        note = QLabel(
            "From the final report page you can save PDF, export CSV data for quality, or print—each to your chosen location."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color: {COLORS['muted']}; {TYPOGRAPHY['caption']}; margin-top: 8px;"
        )
        form_layout.addWidget(note)
        left_layout.addWidget(form_card)
        left_layout.addStretch(1)
        left_scroll.setWidget(left_widget)
        outer.addWidget(left_scroll, 0)

        # —— Right column: Hardware check ——
        right_scroll = QScrollArea(self)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setMaximumWidth(440)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(14)

        header_card = QFrame(right_widget)
        header_card.setProperty("card", True)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 20, 20, 20)
        header_layout.setSpacing(8)

        eyebrow = QLabel("HARDWARE HEALTH")
        eyebrow.setProperty("role", "eyebrow")
        header_layout.addWidget(eyebrow)

        self.status_label = QLabel("Ready to verify hardware.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
        )
        header_layout.addWidget(self.status_label)

        self.summary_label = QLabel(
            "Auto-refresh runs every few seconds. Use Refresh Now to re-detect."
        )
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}"
        )
        header_layout.addWidget(self.summary_label)

        self.discovery_label = QLabel("First refresh will show discovery details.")
        self.discovery_label.setWordWrap(True)
        self.discovery_label.setStyleSheet(
            f"color: {COLORS['muted']}; {TYPOGRAPHY['caption']}"
        )
        header_layout.addWidget(self.discovery_label)

        right_layout.addWidget(header_card)

        device_names = [
            "port_a LabJack",
            "port_a Alicat",
            "port_b LabJack",
            "port_b Alicat",
            "Mensor",
        ]
        for name in device_names:
            card = QFrame(right_widget)
            card.setStyleSheet(_CARD_BASE)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(20, 16, 20, 16)
            card_layout.setSpacing(10)

            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            name_label = QLabel(
                name.replace("port_a", "Left").replace("port_b", "Right")
            )
            name_label.setStyleSheet(
                f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
            )
            name_label.setWordWrap(True)
            top_row.addWidget(name_label, 1)

            status_label = QLabel("Checking")
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label.setStyleSheet(neutral_badge_style())
            status_label.setMinimumWidth(90)
            top_row.addWidget(status_label, 0)
            self._status_labels[name] = status_label

            card_layout.addLayout(top_row)

            detail_label = QLabel("Waiting for first refresh.")
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            detail_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']} padding-top: 2px;"
            )
            card_layout.addWidget(detail_label)
            self._detail_labels[name] = detail_label
            self._card_frames[name] = card
            right_layout.addWidget(card)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.run_button = QPushButton("Refresh Now")
        self.run_button.setMinimumSize(200, 48)
        self.run_button.clicked.connect(self._retry_check)
        btn_row.addWidget(self.run_button)
        btn_row.addStretch(1)
        right_layout.addLayout(btn_row)

        right_scroll.setWidget(right_widget)
        outer.addWidget(right_scroll, 1)

        self.registerField("technician_name*", self.technician_input)
        self.registerField("asset_id*", self.asset_id_input)
        self.registerField("include_leak_check", self.include_leak_check_checkbox)

    def initializePage(self) -> None:
        wizard = self.wizard()
        interval_ms = wizard.hardware_check_poll_interval_ms() if wizard else 2000
        self._poll_timer.start(interval_ms)
        self._start_check()

    def cleanupPage(self) -> None:
        self._poll_timer.stop()

    def isComplete(self) -> bool:
        login_ok = bool(self.technician_input.text().strip()) and bool(
            self.asset_id_input.text().strip()
        )
        return login_ok and self._check_passed

    def validatePage(self) -> bool:
        wizard = self.wizard()
        if wizard is not None:
            wizard.session.technician_name = self.technician_input.text().strip()
            wizard.session.asset_id = self.asset_id_input.text().strip()
            wizard.session.include_leak_check = self.include_leak_check_checkbox.isChecked()
            wizard.session.begin()
        return super().validatePage()

    def _start_check(self) -> None:
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        if not self._has_completed_refresh:
            self._check_passed = False
            self.status_label.setText("Checking Alicats, transducers, and Mensor...")
            for name, status_label in self._status_labels.items():
                status_label.setText("Checking")
                status_label.setStyleSheet(neutral_badge_style())
                card_frame = self._card_frames.get(name)
                if card_frame is not None:
                    card_frame.setStyleSheet(_CARD_BASE)
        else:
            self.status_label.setText("Refreshing hardware status...")
            self.status_label.setStyleSheet(
                f"color: {COLORS['success'] if self._check_passed else COLORS['danger']}; "
                f"{TYPOGRAPHY['subtitle']} font-weight: bold;"
            )

        wizard = self.wizard()
        if wizard is None:
            self._refresh_in_progress = False
            return

        def _do_check():
            return wizard.get_hardware_snapshot()

        def _done(result, error):
            self._refresh_in_progress = False
            if error is not None:
                self.status_label.setText("Hardware check failed.")
                self.status_label.setStyleSheet(
                    f"color: {COLORS['danger']}; {TYPOGRAPHY['body']} font-weight: bold;"
                )
                self.summary_label.setText(str(error))
                self.completeChanged.emit()
                return

            self._check_passed = bool(result.get("overall_ok", False))
            self._has_completed_refresh = True
            self.summary_label.setText(result.get("summary", ""))
            self.discovery_label.setText(result.get("discovery_note", ""))
            for entry in result.get("entries", []):
                name = entry["name"]
                status_label = self._status_labels.get(name)
                detail_label = self._detail_labels.get(name)
                card_frame = self._card_frames.get(name)
                if status_label is None or detail_label is None:
                    continue
                ok = entry["ok"]
                if card_frame is not None:
                    card_frame.setStyleSheet(_card_accent_style(ok))
                if ok:
                    status_label.setText("Ready")
                    status_label.setStyleSheet(status_badge_style(True))
                else:
                    status_label.setText("Check")
                    status_label.setStyleSheet(status_badge_style(False))
                detail_label.setText(entry["detail"])

            if self._check_passed:
                self.status_label.setText("Hardware check passed.")
                self.status_label.setStyleSheet(
                    f"color: {COLORS['success']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
                )
            else:
                self.status_label.setText(
                    "Hardware check incomplete. Review the cards and use Refresh Now."
                )
                self.status_label.setStyleSheet(
                    f"color: {COLORS['danger']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
                )
            self.completeChanged.emit()

        run_async(_do_check, _done)

    def _retry_check(self) -> None:
        wizard = self.wizard()
        if wizard is not None:
            wizard.cleanup_hardware()
        self._start_check()
