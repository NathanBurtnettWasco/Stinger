"""Leak-check page for a single port."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QWizardPage,
)

from quality_cal.core.leak_check_runner import LeakCheckRunner
from quality_cal.ui.styles import COLORS, STYLES, TYPOGRAPHY


def _estimate_rate_psi_per_min(samples: list[tuple[float, float]], max_points: int = 60) -> float | None:
    """Simple linear regression slope * 60 for psi/min from (elapsed_s, pressure) samples."""
    use = samples[-max_points:] if len(samples) > max_points else samples
    if len(use) < 2:
        return None
    n = len(use)
    sum_x = sum(s[0] for s in use)
    sum_y = sum(s[1] for s in use)
    sum_xx = sum(s[0] * s[0] for s in use)
    sum_xy = sum(s[0] * s[1] for s in use)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    return max(0.0, -slope * 60.0)


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
        self._live_samples: list[tuple[float, float]] = []

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

        # PASS/FAIL banner (hidden until leak check completes)
        self.result_banner = QFrame(container)
        self.result_banner.setProperty("card", True)
        self.result_banner.setVisible(False)
        banner_layout = QVBoxLayout(self.result_banner)
        banner_layout.setContentsMargins(24, 20, 24, 20)
        self.result_banner_label = QLabel()
        self.result_banner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_banner_label.setStyleSheet(
            f"font-weight: bold; {TYPOGRAPHY['headline']}"
        )
        banner_layout.addWidget(self.result_banner_label)
        layout.addWidget(self.result_banner)

        card = QFrame(container)
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(16)

        self.status_label = QLabel("Leak check not started.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['subtitle']}"
        )
        card_layout.addWidget(self.status_label)

        # Live reading panel
        live_panel = QFrame(card)
        live_panel.setProperty("panel", "soft")
        live_layout = QGridLayout(live_panel)
        live_layout.setContentsMargins(16, 16, 16, 16)
        live_layout.setSpacing(12)
        self.elapsed_label = QLabel("Elapsed: —")
        self.elapsed_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}"
        )
        self.alicat_live_label = QLabel("Alicat: — psia")
        self.alicat_live_label.setStyleSheet(
            f"color: {COLORS['accent_blue']}; {TYPOGRAPHY['subtitle']} font-weight: bold;"
        )
        self.transducer_live_label = QLabel("Transducer: — psia")
        self.transducer_live_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; {TYPOGRAPHY['body']}"
        )
        self.rate_live_label = QLabel("Est. rate: — psi/min")
        self.rate_live_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}"
        )
        live_layout.addWidget(self.elapsed_label, 0, 0)
        live_layout.addWidget(self.alicat_live_label, 0, 1)
        live_layout.addWidget(self.transducer_live_label, 1, 0)
        live_layout.addWidget(self.rate_live_label, 1, 1)
        card_layout.addWidget(live_panel)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setStyleSheet(STYLES["progress_bar"])
        card_layout.addWidget(self.progress_bar)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; {TYPOGRAPHY['body']}"
        )
        card_layout.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.start_button = QPushButton("Start Leak Check")
        self.start_button.setMinimumSize(280, 58)
        self.start_button.clicked.connect(self._start_run)
        button_row.addWidget(self.start_button)
        button_row.addStretch(1)
        card_layout.addLayout(button_row)

        layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

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
        # Ensure hardware is initialized (e.g. user navigated here before first hardware poll)
        if wizard.port_manager is None:
            wizard.get_hardware_snapshot()
        if wizard.port_manager is None:
            self._on_failed(
                "Hardware not ready. Go back to Hardware Check and wait for verification."
            )
            return

        self._completed = False
        self._running = True
        self._live_samples = []
        self.result_banner.setVisible(False)
        self.start_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting leak check...")
        self.summary_label.setText("")
        self._update_live_panel(0.0, None, None)

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
        self._runner.sampleData.connect(self._on_sample)
        self._runner.finished.connect(self._on_finished)
        self._runner.failed.connect(self._on_failed)
        self._runner.cancelled.connect(self._on_cancelled)
        self._runner.finished.connect(self._thread.quit)
        self._runner.failed.connect(self._thread.quit)
        self._runner.cancelled.connect(self._thread.quit)
        self._thread.start()

    def _update_live_panel(
        self,
        elapsed_s: float,
        alicat_psia: float | None,
        transducer_psia: float | None,
    ) -> None:
        self.elapsed_label.setText(f"Elapsed: {elapsed_s:.1f} s")
        self.alicat_live_label.setText(
            f"Alicat: {alicat_psia:.3f} psia" if alicat_psia is not None else "Alicat: — psia"
        )
        self.transducer_live_label.setText(
            f"Transducer: {transducer_psia:.3f} psia"
            if transducer_psia is not None
            else "Transducer: — psia"
        )
        rate = _estimate_rate_psi_per_min(self._live_samples)
        if rate is not None:
            self.rate_live_label.setText(f"Est. rate: {rate:.4f} psi/min")
        else:
            self.rate_live_label.setText("Est. rate: — psi/min")

    def _on_sample(self, elapsed_s: float, alicat_psia: float, transducer_psia: float) -> None:
        if alicat_psia > 0:
            self._live_samples.append((elapsed_s, alicat_psia))
        self._update_live_panel(
            elapsed_s,
            alicat_psia if alicat_psia > 0 else None,
            transducer_psia if transducer_psia != 0 else None,
        )

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
        status = (
            "PASS"
            if result.passed is True
            else "FAIL"
            if result.passed is False
            else "Recorded"
        )
        self.result_banner.setVisible(True)
        self.result_banner_label.setText(
            f"{status} — {result.alicat_leak_rate_psi_per_min:.4f} psi/min"
        )
        if result.passed is True:
            self.result_banner.setStyleSheet(
                f"QFrame {{ background: {COLORS['success_muted']}; "
                f"border: 1px solid {COLORS['success']}; "
                f"border-radius: 12px; }}"
            )
            self.result_banner_label.setStyleSheet(
                f"color: {COLORS['success']}; font-weight: bold; {TYPOGRAPHY['headline']}"
            )
        elif result.passed is False:
            self.result_banner.setStyleSheet(
                f"QFrame {{ background: {COLORS['danger_muted']}; "
                f"border: 1px solid {COLORS['danger']}; "
                f"border-radius: 12px; }}"
            )
            self.result_banner_label.setStyleSheet(
                f"color: {COLORS['danger']}; font-weight: bold; {TYPOGRAPHY['headline']}"
            )
        else:
            self.result_banner.setStyleSheet(
                f"QFrame {{ background: {COLORS['bg_surface_2']}; "
                f"border: 1px solid {COLORS['border_muted']}; "
                f"border-radius: 12px; }}"
            )
            self.result_banner_label.setStyleSheet(
                f"color: {COLORS['text_primary']}; font-weight: bold; {TYPOGRAPHY['headline']}"
            )
        limit = getattr(
            getattr(wizard, "settings", None),
            "leak_check_max_rate_psi_per_min",
            None,
        )
        limit_str = f" (limit {limit:.4f})" if limit is not None else ""
        self.summary_label.setText(
            f"Leak check complete.\n"
            f"Alicat leak rate: {result.alicat_leak_rate_psi_per_min:.4f} psi/min{limit_str}\n"
            f"Result: {status}"
        )
        self.completeChanged.emit()

    def _on_failed(self, message: str) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        self.status_label.setText("Leak check failed.")
        self.summary_label.setText(message)
        self.summary_label.setStyleSheet(
            f"color: {COLORS['danger']}; font-weight: bold; {TYPOGRAPHY['body']}"
        )
        self.completeChanged.emit()

    def _on_cancelled(self) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        self.status_label.setText("Leak check cancelled.")
        self.summary_label.setText("")
