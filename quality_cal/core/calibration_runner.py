"""Calibration runner for the standalone quality calibration app."""

from __future__ import annotations

import logging
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
    infer_barometric_psia,
    prepare_port_for_target,
    safe_shutdown_port,
    transducer_abs_psia,
    wait_until_near_target,
)
from quality_cal.core.mensor_reader import MensorReader
from quality_cal.session import CalibrationPointResult

logger = logging.getLogger(__name__)

# Reject Mensor samples more than this many psi from target (or median) before averaging.
# Prevents bad serial reads (e.g. 0.16 or 5.26 when sensor shows ~10–11) from pulling the point.
_OUTLIER_TOLERANCE_PSI = 2.0


def _average(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return statistics.fmean(values)


def _robust_average(values: list[float], expected_near: Optional[float] = None) -> Optional[float]:
    """Average after dropping outliers. When expected_near (target) is given, keep only samples
    within tolerance of target so bad reads (e.g. 0.16 at 11 psia) don't pull the result."""
    if not values:
        return None
    if len(values) <= 2:
        return statistics.fmean(values)
    # Prefer target-based filtering when we have a target (e.g. 10–11 psia glitches)
    if expected_near is not None:
        inlier = [v for v in values if abs(v - expected_near) <= _OUTLIER_TOLERANCE_PSI]
        rejected = len(values) - len(inlier)
        if rejected:
            logger.warning(
                "Mensor: rejected %d sample(s) far from target %.1f psia. Dropped: %s",
                rejected,
                expected_near,
                [v for v in values if abs(v - expected_near) > _OUTLIER_TOLERANCE_PSI],
            )
        if inlier:
            return statistics.fmean(inlier)
        # All samples were bad; use median and log
        logger.warning(
            "Mensor: all %d samples far from target %.1f psia; using median %.3f",
            len(values),
            expected_near,
            statistics.median(values),
        )
    median = statistics.median(values)
    inlier = [v for v in values if abs(v - median) <= _OUTLIER_TOLERANCE_PSI]
    if not inlier:
        return statistics.fmean(values)
    return statistics.fmean(inlier)


class CalibrationRunner(QObject):
    """Run the static pressure-point calibration workflow for a single port."""

    progressChanged = pyqtSignal(int, str)
    liveReadingsUpdated = pyqtSignal(object, object, object)  # mensor_psia, alicat_psia, transducer_psia (optional floats)
    pointMeasured = pyqtSignal(object)
    singlePointDone = pyqtSignal(object)  # CalibrationPointResult for retest
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
                def _settle_progress(msg: str, alicat_psia: Optional[float], transducer_psia: Optional[float]) -> None:
                    self.progressChanged.emit(percent, msg)
                    mensor_psia = None
                    try:
                        mensor_psia = self._mensor.read_pressure().pressure_psia
                    except Exception:
                        pass
                    self.liveReadingsUpdated.emit(mensor_psia, alicat_psia, transducer_psia)

                stabilized = wait_until_near_target(
                    port=self._port,
                    target_psia=target_psia,
                    tolerance_psia=self._settings.settle_tolerance_psia,
                    hold_s=self._settings.settle_hold_s,
                    timeout_s=self._settings.settle_timeout_s,
                    sample_hz=self._settings.sample_hz,
                    cancel_event=self._cancel_event,
                    progress_callback=_settle_progress,
                )
                last_barometric = stabilized.barometric_psia

                self.progressChanged.emit(
                    percent,
                    f"Holding point {index}/{len(points)} at {target_psia:.1f} psia",
                )

                # In simulated LabJack mode, drive transducer reading to target for sensible results
                if self._port.daq.get_status().get('simulated'):
                    self._port.daq.sim_set_pressure(target_psia)

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

                    mensor_value = None
                    try:
                        mensor_value = self._mensor.read_pressure().pressure_psia
                        mensor_values.append(mensor_value)
                    except Exception:
                        # Keep collecting Alicat/transducer even if one Mensor sample drops.
                        pass

                    self.liveReadingsUpdated.emit(mensor_value, alicat_value, transducer_value)
                    time.sleep(sample_period_s)

                avg_alicat = _average(alicat_values)
                avg_mensor = _robust_average(mensor_values, expected_near=target_psia)
                avg_transducer = _average(transducer_values)
                # Log tail of readings for diagnostics (e.g. Mensor showing wrong value)
                _tail_size = 10
                logger.info(
                    "Point %d @ %.1f psia tail: mensor(%d)=%s alicat(%d)=%s transducer(%d)=%s",
                    index,
                    target_psia,
                    len(mensor_values),
                    mensor_values[-_tail_size:] if len(mensor_values) >= _tail_size else mensor_values,
                    len(alicat_values),
                    alicat_values[-_tail_size:] if len(alicat_values) >= _tail_size else alicat_values,
                    len(transducer_values),
                    transducer_values[-_tail_size:] if len(transducer_values) >= _tail_size else transducer_values,
                )
                mensor_raw = getattr(self._mensor, "response_tail", None)
                if mensor_raw:
                    logger.info(
                        "Point %d Mensor raw tail (last %d): %s",
                        index,
                        min(5, len(mensor_raw)),
                        mensor_raw[-5:],
                    )
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

    @pyqtSlot(int)
    def run_single_point(self, point_index: int) -> None:
        """Run one calibration point (for manual retest). Emits pointMeasured and singlePointDone."""
        points = self._settings.pressure_points_psia
        if point_index < 1 or point_index > len(points):
            self.failed.emit(f"Point index {point_index} out of range 1..{len(points)}")
            return
        target_psia = points[point_index - 1]
        last_barometric = infer_barometric_psia(self._port.read_all()) or 14.7
        try:
            self.progressChanged.emit(0, f"Retesting point {point_index}/{len(points)} at {target_psia:.1f} psia")
            route_ok, route, last_barometric = prepare_port_for_target(
                self._port,
                target_psia,
                last_barometric,
                self._cancel_event,
            )
            if not route_ok:
                self.failed.emit(f"Failed to route for {target_psia:.1f} psia")
                return

            command_target_pressure(
                self._port,
                target_psia=target_psia,
                ramp_rate_psi_per_s=8.0,
            )
            def _retest_settle_progress(msg: str, alicat_psia: Optional[float], transducer_psia: Optional[float]) -> None:
                self.progressChanged.emit(0, msg)
                mensor_psia = None
                try:
                    mensor_psia = self._mensor.read_pressure().pressure_psia
                except Exception:
                    pass
                self.liveReadingsUpdated.emit(mensor_psia, alicat_psia, transducer_psia)

            stabilized = wait_until_near_target(
                port=self._port,
                target_psia=target_psia,
                tolerance_psia=self._settings.settle_tolerance_psia,
                hold_s=self._settings.settle_hold_s,
                timeout_s=self._settings.settle_timeout_s,
                sample_hz=self._settings.sample_hz,
                cancel_event=self._cancel_event,
                progress_callback=_retest_settle_progress,
            )
            last_barometric = stabilized.barometric_psia

            if self._port.daq.get_status().get("simulated"):
                self._port.daq.sim_set_pressure(target_psia)

            mensor_values = []
            alicat_values = []
            transducer_values = []
            hold_start = time.perf_counter()
            sample_period_s = max(0.05, 1.0 / max(self._settings.sample_hz, 0.1))
            while time.perf_counter() - hold_start < self._settings.static_hold_s:
                if self._cancel_event.is_set():
                    self.cancelled.emit()
                    return
                reading = self._port.read_all()
                av = alicat_abs_psia(reading, last_barometric)
                tv = transducer_abs_psia(reading, last_barometric)
                if av is not None:
                    alicat_values.append(av)
                if tv is not None:
                    transducer_values.append(tv)
                mv = None
                try:
                    mv = self._mensor.read_pressure().pressure_psia
                    mensor_values.append(mv)
                except Exception:
                    pass
                self.liveReadingsUpdated.emit(mv, av, tv)
                time.sleep(sample_period_s)

            avg_alicat = _average(alicat_values)
            avg_mensor = _robust_average(mensor_values, expected_near=target_psia)
            avg_transducer = _average(transducer_values)
            deviation = None if avg_mensor is None or avg_alicat is None else avg_mensor - avg_alicat
            passed = deviation is not None and abs(deviation) <= self._settings.pressure_tolerance_psia
            result = CalibrationPointResult(
                port_id=self._port_id,
                point_index=point_index,
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
            self.pointMeasured.emit(result)
            self.singlePointDone.emit(result)
        except Exception as exc:
            safe_shutdown_port(self._port)
            if str(exc) == "Cancelled":
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))
