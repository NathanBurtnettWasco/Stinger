"""Hardware-check page for the quality calibration wizard."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from app.services import run_async
from quality_cal.ui.styles import neutral_badge_style, status_badge_style


class HardwareCheckPage(QWizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTitle("Hardware Check")
        self.setSubTitle("Verify both ports and the Mensor before starting calibration.")
        self._refresh_in_progress = False
        self._check_passed = False
        self._has_completed_refresh = False
        self._status_labels: dict[str, QLabel] = {}
        self._detail_labels: dict[str, QLabel] = {}
        self._card_frames: dict[str, QFrame] = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._start_check)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(20, 12, 20, 20)
        outer_layout.setSpacing(18)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setSpacing(18)

        header_card = QFrame(container)
        header_card.setProperty("card", True)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(24, 24, 24, 24)
        header_layout.setSpacing(12)

        eyebrow = QLabel("HARDWARE HEALTH")
        eyebrow.setProperty("role", "eyebrow")
        header_layout.addWidget(eyebrow)

        title = QLabel("Live readiness view for both ports and the Mensor.")
        title.setProperty("role", "heroTitle")
        title.setWordWrap(True)
        header_layout.addWidget(title)

        self.status_label = QLabel("Ready to verify hardware.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0f172a;")
        header_layout.addWidget(self.status_label)

        self.summary_label = QLabel("Auto-refresh checks every few seconds while this page is open.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 11pt; color: #475569;")
        header_layout.addWidget(self.summary_label)

        self.discovery_label = QLabel("Discovery diagnostics will appear here during the first refresh.")
        self.discovery_label.setWordWrap(True)
        self.discovery_label.setStyleSheet("font-size: 10.5pt; color: #64748b;")
        header_layout.addWidget(self.discovery_label)

        layout.addWidget(header_card)

        cards_layout = QVBoxLayout()
        cards_layout.setSpacing(14)

        device_names = [
            "port_a LabJack",
            "port_a Alicat",
            "port_b LabJack",
            "port_b Alicat",
            "Mensor",
        ]
        for row, name in enumerate(device_names):
            card = QFrame(container)
            card.setProperty("card", True)
            card.setMinimumHeight(120)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(24, 20, 24, 20)
            card_layout.setSpacing(14)

            top_row = QHBoxLayout()
            top_row.setSpacing(12)
            top_row.setContentsMargins(0, 0, 0, 0)
            name_label = QLabel(name.replace("port_a", "Left").replace("port_b", "Right"))
            name_label.setStyleSheet("font-size: 13pt; font-weight: 700; color: #0f172a;")
            name_label.setWordWrap(True)
            top_row.addWidget(name_label, 1)

            status_label = QLabel("Checking")
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label.setStyleSheet(neutral_badge_style())
            status_label.setMinimumWidth(112)
            top_row.addWidget(status_label, 0)
            self._status_labels[name] = status_label

            card_layout.addLayout(top_row)

            detail_label = QLabel("Waiting for the first hardware refresh.")
            detail_label.setWordWrap(True)
            detail_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            detail_label.setStyleSheet(
                "font-size: 11pt; color: #475569; line-height: 1.45; padding-top: 2px;"
            )
            card_layout.addWidget(detail_label)
            self._detail_labels[name] = detail_label
            self._card_frames[name] = card

            cards_layout.addWidget(card)

        layout.addLayout(cards_layout)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.run_button = QPushButton("Refresh Now")
        self.run_button.setMinimumSize(280, 62)
        self.run_button.clicked.connect(self._start_check)
        button_row.addWidget(self.run_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        outer_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)

    def initializePage(self) -> None:
        wizard = self.wizard()
        interval_ms = wizard.hardware_check_poll_interval_ms() if wizard is not None else 2000
        self._poll_timer.start(interval_ms)
        self._start_check()

    def cleanupPage(self) -> None:
        self._poll_timer.stop()

    def isComplete(self) -> bool:
        return self._check_passed

    def _start_check(self) -> None:
        if self._refresh_in_progress:
            return
        self._refresh_in_progress = True
        if not self._has_completed_refresh:
            self._check_passed = False
            self.status_label.setText("Checking Alicats, transducers, and Mensor...")
            for status_label in self._status_labels.values():
                status_label.setText("Checking")
                status_label.setStyleSheet(neutral_badge_style())
        else:
            self.status_label.setText("Refreshing hardware status...")
            if self._check_passed:
                self.status_label.setStyleSheet("font-size: 13pt; color: #166534; font-weight: 700;")
            else:
                self.status_label.setStyleSheet("font-size: 13pt; color: #b91c1c; font-weight: 700;")

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
                self.status_label.setStyleSheet("font-size: 12pt; color: #b91c1c; font-weight: bold;")
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
                if status_label is None or detail_label is None:
                    continue
                if entry["ok"]:
                    status_label.setText("Ready")
                    status_label.setStyleSheet(status_badge_style(True))
                else:
                    status_label.setText("Check")
                    status_label.setStyleSheet(status_badge_style(False))
                detail_label.setText(entry["detail"])

            if self._check_passed:
                self.status_label.setText("Hardware check passed.")
                self.status_label.setStyleSheet("font-size: 13pt; color: #166534; font-weight: 700;")
            else:
                self.status_label.setText("Hardware check incomplete. Review the cards below.")
                self.status_label.setStyleSheet("font-size: 13pt; color: #b91c1c; font-weight: 700;")
            self.completeChanged.emit()

        run_async(_do_check, _done)
