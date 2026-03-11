"""Calibration runner for the standalone quality calibration app."""

from __future__ import annotations

import statistics
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from app.hardware.port import Port
from quality_cal.config import QualitySettings
from quality_cal.core.hardware_helpers import (
    alicat_abs_psia,
    command_target_pressure,
    prepare_port_for_target,
    safe_shutdown_port,
    transducer_abs_psia,
    wait_until_near_target,
)
from quality_cal.core.mensor_reader import MensorReader
from quality_cal.session import CalibrationPointResult


def _average(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return statistics.fmean(values)


class CalibrationRunner(QObject):
    """Run the static pressure-point calibration workflow for a single port."""

    progressChanged = pyqtSignal(int, str)
    pointMeasured = pyqtSignal(object)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        *,
        port_id: str,
        port: Port,
        mensor: MensorReader,
        settings: QualitySettings,
    ) -> None:
        super().__init__()
        self._port_id = port_id
        self._port = port
        self._mensor = mensor
        self._settings = settings
        self._cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @pyqtSlot()
    def run(self) -> None:
        results: list[CalibrationPointResult] = []
        points = self._settings.pressure_points_psia
        last_barometric = 14.7
        try:
            for index, target_psia in enumerate(points, start=1):
                if self._cancel_event.is_set():
                    self.cancelled.emit()
                    return

                percent = int(((index - 1) / max(len(points), 1)) * 100)
                self.progressChanged.emit(percent, f"Preparing point {index}/{len(points)}")
                route_ok, route, last_barometric = prepare_port_for_target(
                    self._port,
                    target_psia,
                    last_barometric,
                    self._cancel_event,
                )
                if not route_ok:
                    raise RuntimeError(
                        f"Failed to route {self._port_id} for {target_psia:.1f} psia"
                    )

                command_target_pressure(
                    self._port,
                    target_psia=target_psia,
                    ramp_rate_psi_per_s=8.0,
                )
                stabilized = wait_until_near_target(
                    port=self._port,
                    target_psia=target_psia,
                    tolerance_psia=self._settings.settle_tolerance_psia,
                    hold_s=self._settings.settle_hold_s,
                    timeout_s=self._settings.settle_timeout_s,
                    sample_hz=self._settings.sample_hz,
                    cancel_event=self._cancel_event,
                    progress_callback=lambda message: self.progressChanged.emit(percent, message),
                )
                last_barometric = stabilized.barometric_psia

                self.progressChanged.emit(
                    percent,
                    f"Holding point {index}/{len(points)} at {target_psia:.1f} psia",
                )

                mensor_values: list[float] = []
                alicat_values: list[float] = []
                transducer_values: list[float] = []
                hold_start = time.perf_counter()
                sample_period_s = max(0.05, 1.0 / max(self._settings.sample_hz, 0.1))

                while time.perf_counter() - hold_start < self._settings.static_hold_s:
                    if self._cancel_event.is_set():
                        self.cancelled.emit()
                        return

                    reading = self._port.read_all()
                    alicat_value = alicat_abs_psia(reading, last_barometric)
                    transducer_value = transducer_abs_psia(reading, last_barometric)
                    if alicat_value is not None:
                        alicat_values.append(alicat_value)
                    if transducer_value is not None:
                        transducer_values.append(transducer_value)

                    try:
                        mensor_values.append(self._mensor.read_pressure().pressure_psia)
                    except Exception:
                        # Keep collecting Alicat/transducer even if one Mensor sample drops.
                        pass

                    time.sleep(sample_period_s)

                avg_alicat = _average(alicat_values)
                avg_mensor = _average(mensor_values)
                avg_transducer = _average(transducer_values)
                deviation = None if avg_mensor is None or avg_alicat is None else avg_mensor - avg_alicat
                passed = deviation is not None and abs(deviation) <= self._settings.pressure_tolerance_psia
                point_result = CalibrationPointResult(
                    port_id=self._port_id,
                    point_index=index,
                    point_total=len(points),
                    target_psia=target_psia,
                    route=route,
                    mensor_psia=avg_mensor,
                    alicat_psia=avg_alicat,
                    transducer_psia=avg_transducer,
                    deviation_psia=deviation,
                    passed=passed,
                    settle_duration_s=stabilized.elapsed_s,
                    hold_duration_s=self._settings.static_hold_s,
                    sample_count=max(len(alicat_values), len(mensor_values), len(transducer_values)),
                )
                results.append(point_result)
                self.pointMeasured.emit(point_result)
                self.progressChanged.emit(
                    int((index / max(len(points), 1)) * 100),
                    f"Completed point {index}/{len(points)}",
                )

            safe_shutdown_port(self._port)
            self.finished.emit(results)
        except Exception as exc:
            safe_shutdown_port(self._port)
            if str(exc) == "Cancelled":
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))
