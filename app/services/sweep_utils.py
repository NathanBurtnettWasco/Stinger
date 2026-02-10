"""Shared sweep-planning helpers for test execution paths."""
from __future__ import annotations

import math
from typing import Optional

from app.services.ptp_service import TestSetup, convert_pressure


def band_midpoint(band: Optional[dict[str, Optional[float]]]) -> Optional[float]:
    """Return midpoint of a pressure band when both limits exist."""
    if not band:
        return None
    lower = band.get('lower')
    upper = band.get('upper')
    if lower is None or upper is None:
        return None
    return (lower + upper) / 2.0


def resolve_sweep_mode(setup: Optional[TestSetup], atmosphere_psi: float) -> str:
    """Determine whether to sweep in pressure or vacuum direction."""
    if not setup:
        return 'pressure'

    units_label = setup.units_label or 'PSI'
    target = setup.activation_target
    if target is None:
        target = band_midpoint(setup.bands.get('increasing'))
    if target is None:
        target = band_midpoint(setup.bands.get('decreasing'))
    if target is None:
        return 'pressure'

    target_psi = convert_pressure(target, units_label, 'PSI')
    return 'vacuum' if target_psi < atmosphere_psi else 'pressure'


def resolve_sweep_bounds(
    setup: Optional[TestSetup],
    fallback_port_cfg: dict[str, object],
) -> tuple[float, float]:
    """Resolve sweep min/max PSI from PTP setup or hardware fallback config."""
    if setup:
        units_label = setup.units_label or 'PSI'
        candidates = []
        for band_name in ('increasing', 'decreasing', 'reset'):
            band = setup.bands.get(band_name, {})
            for key in ('lower', 'upper'):
                raw = band.get(key)
                if raw is not None and math.isfinite(raw):
                    candidates.append(convert_pressure(raw, units_label, 'PSI'))
        if candidates:
            return (min(candidates), max(candidates))

    min_psi = float(fallback_port_cfg.get('transducer_pressure_min', 0.0))
    max_psi = float(fallback_port_cfg.get('transducer_pressure_max', 115.0))
    return (min_psi, max_psi)


def narrow_bounds(
    activation_psi: float,
    deactivation_psi: float,
    min_bound: float,
    max_bound: float,
    factor: float,
    min_pad: float,
) -> tuple[float, float]:
    """Shrink a sweep window around detected activation/deactivation edges."""
    low = min(activation_psi, deactivation_psi)
    high = max(activation_psi, deactivation_psi)
    pad = max(min_pad, abs(activation_psi - deactivation_psi) * factor)
    return (max(min_bound, low - pad), min(max_bound, high + pad))
