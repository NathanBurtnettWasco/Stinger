"""Helpers for selecting the main pressure measurement source."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from app.core.config import (
    MEASUREMENT_SOURCE_ALICAT,
    MEASUREMENT_SOURCE_TRANSDUCER,
    normalize_measurement_source,
)
from app.hardware.port import PortReading


def get_measurement_settings(config: Dict[str, Any]) -> Tuple[str, bool]:
    """Return normalized source preference and fallback behavior."""
    measurement = config.get('hardware', {}).get('measurement', {})
    if not isinstance(measurement, dict):
        return MEASUREMENT_SOURCE_TRANSDUCER, True
    preferred_source = normalize_measurement_source(measurement.get('preferred_source'))
    fallback_on_unavailable = bool(measurement.get('fallback_on_unavailable', True))
    return preferred_source, fallback_on_unavailable


def _transducer_pressure_abs_psi(reading: PortReading, barometric_psi: Optional[float]) -> Optional[float]:
    transducer = reading.transducer
    if transducer is None:
        return None
    reference = str(transducer.pressure_reference or 'absolute').strip().lower()
    if reference == 'gauge':
        if barometric_psi is None:
            return None
        return transducer.pressure + barometric_psi
    return transducer.pressure


def _alicat_pressure_abs_psi(reading: PortReading, barometric_psi: Optional[float]) -> Optional[float]:
    alicat = reading.alicat
    if alicat is None:
        return None
    if alicat.pressure is not None:
        return alicat.pressure
    if alicat.gauge_pressure is not None and barometric_psi is not None:
        return alicat.gauge_pressure + barometric_psi
    return None


def select_main_pressure_abs_psi(
    reading: PortReading,
    preferred_source: str,
    fallback_on_unavailable: bool,
    barometric_psi: Optional[float],
) -> Tuple[Optional[float], str]:
    """Select pressure in absolute PSI using configured source preference."""
    preferred = normalize_measurement_source(preferred_source)
    primary = (
        _transducer_pressure_abs_psi(reading, barometric_psi)
        if preferred == MEASUREMENT_SOURCE_TRANSDUCER
        else _alicat_pressure_abs_psi(reading, barometric_psi)
    )
    if primary is not None or not fallback_on_unavailable:
        return primary, preferred

    secondary_source = (
        MEASUREMENT_SOURCE_ALICAT
        if preferred == MEASUREMENT_SOURCE_TRANSDUCER
        else MEASUREMENT_SOURCE_TRANSDUCER
    )
    secondary = (
        _transducer_pressure_abs_psi(reading, barometric_psi)
        if secondary_source == MEASUREMENT_SOURCE_TRANSDUCER
        else _alicat_pressure_abs_psi(reading, barometric_psi)
    )
    return secondary, secondary_source
