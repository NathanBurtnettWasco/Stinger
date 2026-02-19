"""Shared pressure/reference conversion and inference helpers."""

from __future__ import annotations

import math
from typing import Optional

from app.hardware.port import AlicatReading, PortReading
from app.services.ptp_service import convert_pressure

_GAUGE_LABELS = {'PSIG', 'PSI G', 'PSI(G)'}


def is_gauge_unit_label(unit_label: Optional[str]) -> bool:
    """Return True when a display unit label represents gauge pressure."""
    label = (unit_label or '').strip().upper()
    return label in _GAUGE_LABELS


def infer_barometric_pressure(reading: Optional[PortReading]) -> Optional[float]:
    """Infer barometric PSI from an Alicat reading if available."""
    if reading is None or reading.alicat is None:
        return None
    return infer_barometric_pressure_from_alicat(reading.alicat)


def infer_barometric_pressure_from_alicat(reading: Optional[AlicatReading]) -> Optional[float]:
    """Infer barometric PSI directly from Alicat absolute/gauge fields."""
    if reading is None:
        return None
    if reading.barometric_pressure is not None:
        return float(reading.barometric_pressure)
    if reading.pressure is not None and reading.gauge_pressure is not None:
        return float(reading.pressure - reading.gauge_pressure)
    return None


def is_plausible_barometric_psi(
    value: Optional[float],
    minimum: float = 8.0,
    maximum: float = 17.5,
) -> bool:
    """Return True when a barometric PSI value looks physically plausible."""
    if value is None or not math.isfinite(value):
        return False
    return minimum <= value <= maximum


def to_absolute_pressure(value_psi: float, pressure_reference: Optional[str], barometric_psi: float) -> float:
    """Convert a value in PSI from gauge/absolute reference to absolute PSI."""
    if str(pressure_reference or '').strip().lower() == 'gauge':
        return float(value_psi + barometric_psi)
    return float(value_psi)


def to_display_pressure(
    value_abs_psi: Optional[float],
    unit_label: Optional[str],
    barometric_psi: float,
) -> Optional[float]:
    """Convert absolute PSI to requested display units."""
    if value_abs_psi is None:
        return None
    if is_gauge_unit_label(unit_label):
        return float(value_abs_psi - barometric_psi)
    return float(convert_pressure(value_abs_psi, 'PSI', unit_label or 'PSI'))


def resolve_display_reference(unit_label: Optional[str], default_reference: Optional[str]) -> str:
    """Resolve the implied reference frame for a UI unit label."""
    if is_gauge_unit_label(unit_label):
        return 'gauge'
    if (unit_label or '').strip().upper() == 'PSI' and default_reference:
        return str(default_reference).strip().lower()
    return 'absolute'


def infer_setpoint_reference(
    *,
    setpoint: Optional[float],
    absolute_pressure: Optional[float],
    gauge_pressure: Optional[float],
    barometric_psi: float,
    fallback_reference: Optional[str] = None,
) -> str:
    """Infer whether Alicat setpoint appears gauge- or absolute-referenced."""
    if setpoint is None:
        return str(fallback_reference or 'absolute').strip().lower()
    if gauge_pressure is not None:
        absolute_candidate = gauge_pressure + barometric_psi
        if abs(setpoint - absolute_candidate) < abs(setpoint - gauge_pressure):
            return 'absolute'
        return 'gauge'
    if absolute_pressure is not None:
        gauge_candidate = absolute_pressure - barometric_psi
        if abs(setpoint - absolute_pressure) <= abs(setpoint - gauge_candidate):
            return 'absolute'
        return 'gauge'
    return str(fallback_reference or 'absolute').strip().lower()


def infer_setpoint_abs_psi(
    *,
    setpoint: Optional[float],
    absolute_alicat: Optional[float],
    gauge_pressure: Optional[float],
    barometric_psi: float,
) -> Optional[float]:
    """Infer an absolute-PSI setpoint value from available Alicat fields."""
    if setpoint is None:
        return None

    reference = infer_setpoint_reference(
        setpoint=setpoint,
        absolute_pressure=absolute_alicat,
        gauge_pressure=gauge_pressure,
        barometric_psi=barometric_psi,
        fallback_reference='absolute',
    )
    if reference == 'gauge':
        return float(setpoint + barometric_psi)
    return float(setpoint)

