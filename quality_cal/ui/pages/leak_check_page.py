"""Leak-check page for a single port."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from quality_cal.core.leak_check_runner import LeakCheckRunner


class LeakCheckPage(QWizardPage):
    def __init__(self, *, port_id: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.port_id = port_id
        self.setTitle(title)
        self.setSubTitle("Optional leak check using a high-pressure hold.")
        self._completed = False
        self._running = False
        self._thread: QThread | None = None
        self._runner: LeakCheckRunner | None = None

        outer_layout = QVBoxLayout(self)
        outer_layout.addStretch(1)

        container = QWidget(self)
        container.setMaximumWidth(760)
        layout = QVBoxLayout(container)
        self.status_label = QLabel("Leak check not started.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 12pt;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.start_button = QPushButton("Start Leak Check")
        self.start_button.setMinimumSize(280, 58)
        self.start_button.clicked.connect(self._start_run)
        button_row.addWidget(self.start_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        layout.addStretch(1)
        outer_layout.addWidget(container, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer_layout.addStretch(1)

    def initializePage(self) -> None:
        if not self._running and not self._completed:
            self._start_run()

    def isComplete(self) -> bool:
        return self._completed

    def cleanupPage(self) -> None:
        if self._runner is not None:
            self._runner.request_cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None

    def _start_run(self) -> None:
        wizard = self.wizard()
        if wizard is None or self._running:
            return
        self._completed = False
        self._running = True
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting leak check...")
        self.summary_label.setText("")

        port = wizard.port_manager.get_port(self.port_id)
        if port is None:
            self._on_failed(f"Port not available: {self.port_id}")
            return

        self._thread = QThread(self)
        self._runner = LeakCheckRunner(
            port_id=self.port_id,
            port=port,
            settings=wizard.settings,
        )
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.progressChanged.connect(self._on_progress)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.finished.connect(self._thread.quit)
        self._runner.failed.connect(self._thread.quit)
        self._runner.cancelled.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)

    def _on_finished(self, result) -> None:
        wizard = self.wizard()
        if wizard is not None:
            wizard.session.port_result(self.port_id).leak_check = result
        self._running = False
        self._completed = True
        self.start_button.setEnabled(True)
        status = "PASS" if result.passed is True else "FAIL" if result.passed is False else "Recorded"
        self.summary_label.setText(
            f"Leak check complete.\n"
            f"Alicat leak rate: {result.alicat_leak_rate_psi_per_min:.4f} psi/min\n"
            f"Result: {status}"
        )
        self.completeChanged.emit()

    def _on_failed(self, message: str) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        self.status_label.setText("Leak check failed.")
        self.summary_label.setText(message)
        self.summary_label.setStyleSheet("color: #b91c1c; font-weight: bold;")
        self.completeChanged.emit()

    def _on_cancelled(self) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        self.status_label.setText("Leak check cancelled.")
        self.summary_label.setText("")
