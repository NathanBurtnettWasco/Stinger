"""Debug panel widget for manual hardware control."""
from typing import Any, Optional, cast

from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QGridLayout, QTabWidget
)

from app.services.noise_estimator import (
    ResidualNoiseEstimator,
    parse_debug_noise_settings,
)
from app.ui.widgets.pressure_chart import PressureChartWidget

class LEDIndicator(QWidget):
    """Refined LED-style indicator widget with ring effect."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._state = False
        self.setFixedSize(12, 12)  # Smaller, more refined
        
    def set_state(self, state: bool) -> None:
        """Set LED state (True=ON/Green, False=OFF/Gray)."""
        self._state = state
        self.update()
        
    def paintEvent(self, a0):
        """Paint the LED indicator with ring effect."""
        from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Choose color based on state
        if self._state:
            fill_color = QColor('#16a34a')
            ring_color = QColor('#16a34a')
        else:
            fill_color = QColor('#d1d5db')
            ring_color = QColor('#9ca3af')
        
        # Draw ring border
        painter.setPen(QPen(ring_color, 2))
        painter.setBrush(QBrush(fill_color))
        
        # Draw circle
        painter.drawEllipse(1, 1, 10, 10)


class DebugPortPanel(QFrame):
    """
    Debug panel for a single port with controls and real-time chart.
    
    Signals:
        action_requested(action: str, payload: dict): Emitted when user triggers an action
    """
    
    action_requested = pyqtSignal(str, dict)
    
    def __init__(
        self,
        port_id: str,
        title: str,
        noise_config: Optional[dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._port_id = port_id
        self._title = title
        
        # Control references
        self._mode_combo: Optional[QComboBox] = None
        self._solenoid_mode_combo: Optional[QComboBox] = None
        self._setpoint_input: Optional[QLineEdit] = None
        self._ramp_input: Optional[QLineEdit] = None
        self._setpoint_label: Optional[QLabel] = None
        self._ramp_label: Optional[QLabel] = None
        self._pressure_value: Optional[QLabel] = None
        self._setpoint_value: Optional[QLabel] = None
        self._units_label = "PSI"
        self._no_led: Optional[LEDIndicator] = None
        self._nc_led: Optional[LEDIndicator] = None
        self._no_pin_label: Optional[QLabel] = None
        self._nc_pin_label: Optional[QLabel] = None
        self._no_state_label: Optional[QLabel] = None
        self._nc_state_label: Optional[QLabel] = None
        self._no_pin: Optional[int] = None
        self._nc_pin: Optional[int] = None
        self._noise_indicator: Optional[QLabel] = None
        self._noise_value: Optional[QLabel] = None
        self._noise_estimator = ResidualNoiseEstimator(parse_debug_noise_settings(noise_config))
        self._last_setpoint_value: Optional[float] = None
        self._sweep_mode_combo: Optional[QComboBox] = None
        self._find_setpoint_btn: Optional[QPushButton] = None
        self._chart: Optional[PressureChartWidget] = None
        self._dio_select: Optional[QComboBox] = None
        self._dio_mode_combo: Optional[QComboBox] = None
        self._dio_state_combo: Optional[QComboBox] = None
        self._dio_read_btn: Optional[QPushButton] = None
        self._dio_state_labels: dict[int, QLabel] = {}
        self._dio_mapping: list[tuple[int, str]] = []
        self._setpoint_apply_timer = QTimer(self)
        self._setpoint_apply_timer.setSingleShot(True)
        self._setpoint_apply_timer.timeout.connect(self._on_apply_setpoint)
        self._ramp_apply_timer = QTimer(self)
        self._ramp_apply_timer.setSingleShot(True)
        self._ramp_apply_timer.timeout.connect(self._on_apply_ramp)
        
        self._setup_ui()
        
    def _create_readout(self, parent: QHBoxLayout, label: str, initial: str, font_size: str) -> QLabel:
        """Create a pressure/setpoint readout widget."""
        group = QVBoxLayout()
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
        group.addWidget(lbl)
        value = QLabel(initial)
        value.setStyleSheet(f"color: #1a1a2e; font-size: {font_size}; font-weight: bold;")
        group.addWidget(value)
        parent.addLayout(group)
        return value

    def _create_noise_readout(self) -> QVBoxLayout:
        """Create the noise indicator readout."""
        group = QVBoxLayout()
        lbl = QLabel("Transducer Noise")
        lbl.setStyleSheet("color: #6b7280; font-size: 12px;")
        group.addWidget(lbl)
        row = QHBoxLayout()
        row.setSpacing(6)
        self._noise_indicator = QLabel()
        self._noise_indicator.setFixedSize(10, 10)
        self._noise_indicator.setStyleSheet("background-color: #16a34a; border-radius: 5px;")
        row.addWidget(self._noise_indicator)
        self._noise_value = QLabel("--")
        self._noise_value.setStyleSheet("color: #1a1a2e; font-size: 12px; font-weight: bold;")
        row.addWidget(self._noise_value)
        row.addStretch()
        group.addLayout(row)
        return group

    def _setup_ui(self) -> None:
        """Initialize the panel UI."""
        self.setStyleSheet("background-color: #ffffff; border: 1px solid rgba(0, 0, 0, 0.08); border-radius: 12px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Header
        header = QLabel(self._title)
        header.setStyleSheet("color: #1a1a2e; font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        readout_row = QHBoxLayout()
        readout_row.setSpacing(16)

        self._pressure_value = self._create_readout(readout_row, "Pressure", "-- PSI", "20px")
        self._setpoint_value = self._create_readout(readout_row, "Setpoint", "-- PSI", "18px")

        readout_row.addStretch()

        noise_group = self._create_noise_readout()
        readout_row.addLayout(noise_group)
        layout.addLayout(readout_row)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(12)
        toggle_label = QLabel("Show:")
        toggle_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        toggle_row.addWidget(toggle_label)

        self._toggle_transducer = QCheckBox("Transducer")
        self._toggle_transducer.setChecked(True)
        self._toggle_transducer.setStyleSheet("color: #1a1a2e;")
        self._toggle_transducer.toggled.connect(
            lambda checked: self._chart.set_transducer_visible(checked) if self._chart else None
        )
        toggle_row.addWidget(self._toggle_transducer)

        self._toggle_alicat = QCheckBox("Alicat")
        self._toggle_alicat.setChecked(True)
        self._toggle_alicat.setStyleSheet("color: #1a1a2e;")
        self._toggle_alicat.toggled.connect(
            lambda checked: self._chart.set_alicat_visible(checked) if self._chart else None
        )
        toggle_row.addWidget(self._toggle_alicat)

        self._toggle_setpoint = QCheckBox("Setpoint")
        self._toggle_setpoint.setChecked(True)
        self._toggle_setpoint.setStyleSheet("color: #1a1a2e;")
        self._toggle_setpoint.toggled.connect(
            lambda checked: self._chart.set_setpoint_visible(checked) if self._chart else None
        )
        toggle_row.addWidget(self._toggle_setpoint)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)
        
        # Pressure chart
        self._chart = PressureChartWidget()
        self._chart.setMinimumHeight(200)
        layout.addWidget(self._chart)

        controls_tabs = QTabWidget()
        controls_tabs.setDocumentMode(True)
        controls_tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 8px;
                background-color: #f9fafb;
            }
            QTabBar::tab {
                background-color: #e8eaed;
                color: #4b5563;
                padding: 6px 14px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #2563eb;
                color: white;
            }
            """
        )

        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)
        live_layout.setContentsMargins(12, 10, 12, 10)
        live_layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_label = QLabel("Alicat Mode:")
        mode_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        mode_row.addWidget(mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Control", "Hold", "Vent"])
        self._mode_combo.setStyleSheet(self._combo_style())
        self._mode_combo.setFixedWidth(140)
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self._mode_combo.setCurrentText("Hold")
        self._on_mode_changed("Hold")
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        live_layout.addLayout(mode_row)

        solenoid_row = QHBoxLayout()
        solenoid_row.setSpacing(8)
        solenoid_label = QLabel("Solenoid Routing:")
        solenoid_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        solenoid_row.addWidget(solenoid_label)

        self._solenoid_mode_combo = QComboBox()
        self._solenoid_mode_combo.addItems(["Auto", "Atmosphere", "Vacuum"])
        self._solenoid_mode_combo.setStyleSheet(self._combo_style())
        self._solenoid_mode_combo.setFixedWidth(160)
        self._solenoid_mode_combo.currentTextChanged.connect(self._on_solenoid_mode_changed)
        solenoid_row.addWidget(self._solenoid_mode_combo)
        solenoid_row.addStretch()
        live_layout.addLayout(solenoid_row)

        setpoint_row = QHBoxLayout()
        setpoint_row.setSpacing(8)
        self._setpoint_label = QLabel("Setpoint (PSI):")
        self._setpoint_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        setpoint_row.addWidget(self._setpoint_label)

        self._setpoint_input = QLineEdit()
        self._setpoint_input.setValidator(QDoubleValidator(-100.0, 999.0, 2))
        self._setpoint_input.setFixedWidth(120)
        self._setpoint_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #f9fafb;
                color: #1a1a2e;
                padding: 6px;
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 4px;
            }
            """
        )
        self._setpoint_input.textChanged.connect(self._schedule_setpoint_apply)
        self._setpoint_input.returnPressed.connect(self._on_apply_setpoint)
        self._setpoint_input.editingFinished.connect(self._on_apply_setpoint)
        setpoint_row.addWidget(self._setpoint_input)

        setpoint_hint = QLabel("Auto-apply")
        setpoint_hint.setStyleSheet("color: #9ca3af; font-size: 12px;")
        setpoint_row.addWidget(setpoint_hint)
        setpoint_row.addStretch()
        live_layout.addLayout(setpoint_row)

        ramp_row = QHBoxLayout()
        ramp_row.setSpacing(8)
        self._ramp_label = QLabel("Ramp Rate (PSI/s):")
        self._ramp_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        ramp_row.addWidget(self._ramp_label)

        self._ramp_input = QLineEdit()
        self._ramp_input.setValidator(QDoubleValidator(0.0, 999.0, 2))
        self._ramp_input.setFixedWidth(120)
        self._ramp_input.setStyleSheet(
            """
            QLineEdit {
                background-color: #f9fafb;
                color: #1a1a2e;
                padding: 6px;
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 4px;
            }
            """
        )
        self._ramp_input.textChanged.connect(self._schedule_ramp_apply)
        self._ramp_input.returnPressed.connect(self._on_apply_ramp)
        self._ramp_input.editingFinished.connect(self._on_apply_ramp)
        ramp_row.addWidget(self._ramp_input)

        ramp_hint = QLabel("Auto-apply")
        ramp_hint.setStyleSheet("color: #9ca3af; font-size: 12px;")
        ramp_row.addWidget(ramp_hint)
        ramp_row.addStretch()
        live_layout.addLayout(ramp_row)
        live_layout.addStretch()

        controls_tabs.addTab(live_tab, "Live Control")

        io_tab = QWidget()
        io_layout = QVBoxLayout(io_tab)
        io_layout.setContentsMargins(12, 10, 12, 10)
        io_layout.setSpacing(10)

        diagnostics_label = QLabel("Diagnostics")
        diagnostics_label.setStyleSheet("color: #1a1a2e; font-size: 13px; font-weight: bold;")
        io_layout.addWidget(diagnostics_label)

        sweep_mode_row = QHBoxLayout()
        sweep_mode_row.setSpacing(8)
        sweep_mode_label = QLabel("Sweep Mode:")
        sweep_mode_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        sweep_mode_row.addWidget(sweep_mode_label)

        self._sweep_mode_combo = QComboBox()
        self._sweep_mode_combo.addItems(["Auto (PTP)", "Pressure", "Vacuum"])
        self._sweep_mode_combo.setFixedWidth(140)
        self._sweep_mode_combo.setStyleSheet(self._combo_style())
        sweep_mode_row.addWidget(self._sweep_mode_combo)
        sweep_mode_row.addStretch()
        io_layout.addLayout(sweep_mode_row)

        find_row = QHBoxLayout()
        find_row.setSpacing(8)
        find_label = QLabel("Find Setpoint:")
        find_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        find_row.addWidget(find_label)

        self._find_setpoint_btn = QPushButton("Run")
        self._find_setpoint_btn.setStyleSheet(self._button_style())
        self._find_setpoint_btn.clicked.connect(self._on_find_setpoint)
        find_row.addWidget(self._find_setpoint_btn)
        find_row.addStretch()
        io_layout.addLayout(find_row)

        dio_controls = QHBoxLayout()
        dio_controls.setSpacing(8)
        dio_label = QLabel("DIO Control:")
        dio_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        dio_controls.addWidget(dio_label)

        self._dio_select = QComboBox()
        self._dio_select.setStyleSheet(self._combo_style())
        self._dio_select.setFixedWidth(170)
        for dio, label in self._get_dio_mapping():
            self._dio_select.addItem(f"DIO{dio} ({label})", dio)
        dio_controls.addWidget(self._dio_select)

        self._dio_mode_combo = QComboBox()
        self._dio_mode_combo.addItems(["Input", "Output"])
        self._dio_mode_combo.setStyleSheet(self._combo_style())
        self._dio_mode_combo.setFixedWidth(90)
        self._dio_mode_combo.currentTextChanged.connect(self._on_dio_mode_changed)
        dio_controls.addWidget(self._dio_mode_combo)

        self._dio_state_combo = QComboBox()
        self._dio_state_combo.addItems(["Low", "High"])
        self._dio_state_combo.setStyleSheet(self._combo_style())
        self._dio_state_combo.setFixedWidth(80)
        self._dio_state_combo.setEnabled(False)
        dio_controls.addWidget(self._dio_state_combo)

        dio_apply_btn = QPushButton("Apply")
        dio_apply_btn.setStyleSheet(self._button_style())
        dio_apply_btn.clicked.connect(self._on_apply_dio)
        dio_controls.addWidget(dio_apply_btn)

        self._dio_read_btn = QPushButton("Read DIOs")
        self._dio_read_btn.setStyleSheet(self._button_style())
        self._dio_read_btn.clicked.connect(self._on_read_dio)
        dio_controls.addWidget(self._dio_read_btn)

        dio_controls.addStretch()
        io_layout.addLayout(dio_controls)

        dio_grid = QGridLayout()
        dio_grid.setHorizontalSpacing(12)
        dio_grid.setVerticalSpacing(6)
        mapping = self._get_dio_mapping()
        for index, (dio, label) in enumerate(mapping):
            row = index // 3
            col = (index % 3) * 2
            name_label = QLabel(f"DIO{dio}")
            name_label.setStyleSheet("color: #6b7280; font-size: 12px;")
            dio_grid.addWidget(name_label, row, col)
            state_label = QLabel("-")
            state_label.setStyleSheet("color: #1a1a2e; font-size: 12px; font-weight: bold;")
            state_label.setToolTip(label)
            dio_grid.addWidget(state_label, row, col + 1)
            self._dio_state_labels[dio] = state_label
        io_layout.addLayout(dio_grid)
        io_layout.addStretch()

        controls_tabs.addTab(io_tab, "I/O & Diagnostics")

        no_nc_header = QWidget()
        switch_row = QHBoxLayout(no_nc_header)
        switch_row.setContentsMargins(8, 4, 12, 4)
        switch_row.setSpacing(20)
        no_layout = QHBoxLayout()
        no_layout.setSpacing(8)
        no_label = QLabel("NO:")
        no_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        no_layout.addWidget(no_label)
        self._no_pin_label = QLabel("DIO--")
        self._no_pin_label.setStyleSheet("color: #1a1a2e; font-size: 12px;")
        no_layout.addWidget(self._no_pin_label)
        self._no_led = LEDIndicator()
        no_layout.addWidget(self._no_led)
        self._no_state_label = QLabel("LOW")
        self._no_state_label.setStyleSheet("color: #1a1a2e; font-size: 12px; font-weight: bold;")
        no_layout.addWidget(self._no_state_label)
        switch_row.addLayout(no_layout)
        nc_layout = QHBoxLayout()
        nc_layout.setSpacing(8)
        nc_label = QLabel("NC:")
        nc_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        nc_layout.addWidget(nc_label)
        self._nc_pin_label = QLabel("DIO--")
        self._nc_pin_label.setStyleSheet("color: #1a1a2e; font-size: 12px;")
        nc_layout.addWidget(self._nc_pin_label)
        self._nc_led = LEDIndicator()
        nc_layout.addWidget(self._nc_led)
        self._nc_state_label = QLabel("LOW")
        self._nc_state_label.setStyleSheet("color: #1a1a2e; font-size: 12px; font-weight: bold;")
        nc_layout.addWidget(self._nc_state_label)
        switch_row.addLayout(nc_layout)
        switch_row.addStretch()
        controls_tabs.setCornerWidget(no_nc_header, Qt.Corner.TopRightCorner)

        layout.addWidget(controls_tabs)
        
    def _button_style(self) -> str:
        """Return button stylesheet."""
        return """
            QPushButton {
                background-color: #2563eb;
                color: white;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:pressed {
                background-color: #1e40af;
            }
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #f9fafb;
                color: #1a1a2e;
                padding: 6px;
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 4px;
                min-width: 80px;
            }
            QComboBox:hover {
                border: 1px solid rgba(0, 0, 0, 0.20);
            }
            QComboBox:disabled {
                background-color: #f3f4f6;
                color: #9ca3af;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #4b5563;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #1a1a2e;
                border: 1px solid rgba(0, 0, 0, 0.12);
                selection-background-color: #dbeafe;
                selection-color: #1a1a2e;
                outline: none;
            }
        """

    def _get_dio_mapping(self) -> list[tuple[int, str]]:
        if self._dio_mapping:
            return self._dio_mapping
        if self._port_id == "port_a":
            self._dio_mapping = [
                (0, "Pin1/FIO0"),
                (1, "Pin2/FIO1"),
                (2, "Pin3/FIO2"),
                (3, "Pin4/FIO3"),
                (4, "Pin5/FIO4"),
                (5, "Pin6/FIO5"),
                (6, "Pin7/FIO6"),
                (7, "Pin8/FIO7"),
                (8, "Pin9/EIO0"),
            ]
        else:
            self._dio_mapping = [
                (9, "Pin1/EIO1"),
                (10, "Pin2/EIO2"),
                (11, "Pin3/EIO3"),
                (12, "Pin4/EIO4"),
                (13, "Pin5/EIO5"),
                (14, "Pin6/EIO6"),
                (15, "Pin7/EIO7"),
                (16, "Pin8/CIO0"),
                (17, "Pin9/CIO1"),
            ]
        return self._dio_mapping
        
    def _on_mode_changed(self, mode_text: str) -> None:
        """Handle Alicat mode change."""
        mode_map = {
            "Control": "pressurize",
            "Hold": "hold",
            "Vent": "vent"
        }
        mode = mode_map.get(mode_text, "pressurize")
        self.action_requested.emit("set_mode", {"mode": mode})

    def _on_solenoid_mode_changed(self, mode_text: str) -> None:
        """Handle solenoid routing mode change."""
        normalized = mode_text.strip().lower()
        if normalized.startswith("auto"):
            mode = "auto"
        elif normalized.startswith("vac"):
            mode = "vacuum"
        else:
            mode = "atmosphere"
        self.action_requested.emit("set_solenoid_mode", {"mode": mode})

    def _schedule_setpoint_apply(self, text: str) -> None:
        if not text.strip() or self._setpoint_input is None:
            return
        if not self._setpoint_input.hasAcceptableInput():
            return
        self._setpoint_apply_timer.start(250)

    def _schedule_ramp_apply(self, text: str) -> None:
        if not text.strip() or self._ramp_input is None:
            return
        if not self._ramp_input.hasAcceptableInput():
            return
        self._ramp_apply_timer.start(250)
        
    def _on_apply_setpoint(self) -> None:
        """Handle setpoint apply button."""
        if self._setpoint_input is None:
            return
        if not self._setpoint_input.hasAcceptableInput():
            return
        text = self._setpoint_input.text()
        if text:
            try:
                value = float(text)
                self._last_setpoint_value = value
                if self._setpoint_value is not None:
                    self._setpoint_value.setText(f"{value:.2f} {self._units_label}")
                if self._chart:
                    self._chart.set_manual_setpoint(value)
                self.action_requested.emit("set_setpoint", {"value": value})
            except ValueError:
                return
                
    def _on_apply_ramp(self) -> None:
        """Handle ramp rate apply button."""
        if self._ramp_input is None:
            return
        if not self._ramp_input.hasAcceptableInput():
            return
        text = self._ramp_input.text()
        if text:
            try:
                value = float(text)
                self.action_requested.emit("set_ramp_rate", {"value": value})
            except ValueError:
                return

    def _on_dio_mode_changed(self, mode_text: str) -> None:
        if self._dio_state_combo is None:
            return
        self._dio_state_combo.setEnabled(mode_text.strip().lower() == "output")

    def _on_apply_dio(self) -> None:
        if self._dio_select is None or self._dio_mode_combo is None:
            return
        dio = self._dio_select.currentData()
        if dio is None:
            return
        is_output = self._dio_mode_combo.currentText().strip().lower() == "output"
        output_state = None
        if is_output and self._dio_state_combo is not None:
            output_state = 1 if self._dio_state_combo.currentText().strip().lower() == "high" else 0
        self.action_requested.emit(
            "set_dio_direction",
            {
                "dio": int(dio),
                "is_output": is_output,
                "output_state": output_state,
            },
        )

    def _on_read_dio(self) -> None:
        self.action_requested.emit("read_dio_all", {})

    def _on_find_setpoint(self) -> None:
        """Run a find setpoint sweep."""
        mode = self._get_sweep_mode_override()
        self.action_requested.emit("find_setpoint", {"mode": mode})

    def _get_sweep_mode_override(self) -> str:
        if self._sweep_mode_combo is None:
            return "auto"
        current = self._sweep_mode_combo.currentText().strip().lower()
        if current.startswith("pressure"):
            return "pressure"
        if current.startswith("vacuum"):
            return "vacuum"
        return "auto"
    
    # Public interface
    
    def update_chart(
        self,
        timestamp: float,
        pressure: Optional[float],
        setpoint: Optional[float],
        alicat_pressure: Optional[float],
    ) -> None:
        """Update the pressure chart with new data."""
        if self._chart:
            self._chart.add_data_point(timestamp, pressure, setpoint, alicat_pressure)
        if self._pressure_value and pressure is not None:
            self._pressure_value.setText(f"{pressure:.2f} {self._units_label}")
        if self._setpoint_value and setpoint is not None:
            self._setpoint_value.setText(f"{setpoint:.2f} {self._units_label}")
            self._last_setpoint_value = setpoint
        elif self._setpoint_value and self._last_setpoint_value is not None:
            self._setpoint_value.setText(f"{self._last_setpoint_value:.2f} {self._units_label}")
        if pressure is not None:
            noise = self._noise_estimator.update(pressure, timestamp, setpoint=setpoint)
            in_holdoff = self._noise_estimator.in_holdoff(timestamp)
            if noise is not None:
                self._update_noise_indicator(noise)
            if in_holdoff:
                self._set_noise_indicator_hold()
            
    def update_switch_states(self, no_active: bool, nc_active: bool) -> None:
        """Update the NO/NC switch LED indicators."""
        if self._no_led:
            self._no_led.set_state(no_active)
        if self._nc_led:
            self._nc_led.set_state(nc_active)
        if self._no_state_label:
            self._no_state_label.setText("HIGH" if no_active else "LOW")
        if self._nc_state_label:
            self._nc_state_label.setText("HIGH" if nc_active else "LOW")

    def update_dio_values(self, dio_values: dict[int, int]) -> None:
        for dio, label in self._dio_state_labels.items():
            value = dio_values.get(dio)
            if value is None:
                label.setText("-")
                continue
            label.setText("HIGH" if value else "LOW")
            
    def clear_chart(self) -> None:
        """Clear the pressure chart data."""
        if self._chart:
            self._chart.clear()
        self._noise_estimator.reset()
        if self._noise_value is not None:
            self._noise_value.setText("--")
        self._set_noise_indicator_hold()

    def set_units_label(self, units_label: str) -> None:
        """Update unit labels for chart and controls."""
        label = units_label or "PSI"
        self._units_label = label
        if self._setpoint_label:
            self._setpoint_label.setText(f"Setpoint ({label}):")
        if self._ramp_label:
            self._ramp_label.setText(f"Ramp Rate ({label}/s):")
        if self._chart:
            self._chart.set_units_label(label)
        self._noise_estimator.reset()
        self._set_noise_indicator_hold()
        if self._pressure_value is not None:
            pressure_value = cast(QLabel, self._pressure_value)
            if pressure_value.text().startswith("--"):
                pressure_value.setText(f"-- {label}")
        if self._setpoint_value is not None:
            setpoint_value = cast(QLabel, self._setpoint_value)
            if setpoint_value.text().startswith("--"):
                setpoint_value.setText(f"-- {label}")

    def set_switch_pins(self, no_dio: Optional[int], nc_dio: Optional[int]) -> None:
        self._no_pin = no_dio
        self._nc_pin = nc_dio
        if self._no_pin_label:
            self._no_pin_label.setText(f"DIO{no_dio}" if no_dio is not None else "DIO--")
        if self._nc_pin_label:
            self._nc_pin_label.setText(f"DIO{nc_dio}" if nc_dio is not None else "DIO--")

    def _update_noise_indicator(self, noise: float) -> None:
        if self._noise_value is not None:
            self._noise_value.setText(f"{noise:.3f} {self._units_label}")
        if self._noise_indicator is not None:
            if noise < 0.05:
                color = "#16a34a"
            elif noise < 0.2:
                color = "#f59e0b"
            else:
                color = "#ef4444"
            self._noise_indicator.setStyleSheet(
                f"background-color: {color}; border-radius: 5px;"
            )

    def _set_noise_indicator_hold(self) -> None:
        """Show holdoff state during large transitions."""
        if self._noise_indicator is not None:
            self._noise_indicator.setStyleSheet("background-color: #9ca3af; border-radius: 5px;")
            
    def get_port_id(self) -> str:
        """Get the port ID for this panel."""
        return self._port_id
