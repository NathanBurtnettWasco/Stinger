"""Robust residual-noise estimation for dynamic pressure traces."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median, pstdev
from typing import Any, Deque, Optional


DEFAULT_WINDOW_SAMPLES = 60
DEFAULT_MIN_SAMPLES = 12
DEFAULT_TREND_ALPHA = 0.2
DEFAULT_TRANSITION_SIGMA_FACTOR = 8.0
DEFAULT_MAX_HOLDOFF_MS = 350


def _coerce_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _coerce_float(value: Any, default: float, minimum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


@dataclass(frozen=True)
class DebugNoiseSettings:
    """Configuration values for robust debug noise estimation."""

    window_samples: int = DEFAULT_WINDOW_SAMPLES
    min_samples: int = DEFAULT_MIN_SAMPLES
    trend_alpha: float = DEFAULT_TREND_ALPHA
    transition_sigma_factor: float = DEFAULT_TRANSITION_SIGMA_FACTOR
    max_holdoff_ms: int = DEFAULT_MAX_HOLDOFF_MS


def parse_debug_noise_settings(config: Optional[dict[str, Any]]) -> DebugNoiseSettings:
    """Read debug noise settings safely with defaults."""
    cfg = config or {}
    window = _coerce_int(cfg.get('window_samples'), DEFAULT_WINDOW_SAMPLES, minimum=10)
    min_samples = _coerce_int(cfg.get('min_samples'), DEFAULT_MIN_SAMPLES, minimum=5)
    min_samples = min(min_samples, window)
    trend_alpha = _coerce_float(cfg.get('trend_alpha'), DEFAULT_TREND_ALPHA, minimum=0.01)
    if trend_alpha >= 1.0:
        trend_alpha = DEFAULT_TREND_ALPHA
    sigma_factor = _coerce_float(
        cfg.get('transition_sigma_factor'),
        DEFAULT_TRANSITION_SIGMA_FACTOR,
        minimum=1.0,
    )
    max_holdoff_ms = _coerce_int(cfg.get('max_holdoff_ms'), DEFAULT_MAX_HOLDOFF_MS, minimum=0)
    return DebugNoiseSettings(
        window_samples=window,
        min_samples=min_samples,
        trend_alpha=trend_alpha,
        transition_sigma_factor=sigma_factor,
        max_holdoff_ms=max_holdoff_ms,
    )


class ResidualNoiseEstimator:
    """Estimate jitter by removing trend and using a robust residual scale."""

    def __init__(self, settings: DebugNoiseSettings):
        self._settings = settings
        self._residuals: Deque[float] = deque(maxlen=settings.window_samples)
        self._trend: Optional[float] = None
        self._last_pressure: Optional[float] = None
        self._last_setpoint: Optional[float] = None
        self._noise_sigma: Optional[float] = None
        self._last_output: Optional[float] = None
        self._holdoff_until: float = 0.0

    def reset(self) -> None:
        """Reset estimator state after large contextual changes."""
        self._residuals.clear()
        self._trend = None
        self._last_pressure = None
        self._last_setpoint = None
        self._noise_sigma = None
        self._last_output = None
        self._holdoff_until = 0.0

    def in_holdoff(self, timestamp: float) -> bool:
        return timestamp < self._holdoff_until

    def update(
        self,
        pressure: float,
        timestamp: float,
        setpoint: Optional[float] = None,
    ) -> Optional[float]:
        """Update internal state and return current robust residual noise."""
        if self._trend is None:
            self._trend = pressure
            self._last_pressure = pressure
            self._last_setpoint = setpoint
            return None

        if self._is_large_transition(pressure, setpoint):
            holdoff_s = self._adaptive_holdoff_seconds(pressure, setpoint)
            self._holdoff_until = max(self._holdoff_until, timestamp + holdoff_s)
            self._trend = pressure
            self._residuals.clear()
        else:
            alpha = self._settings.trend_alpha
            self._trend = alpha * pressure + (1.0 - alpha) * self._trend
            self._residuals.append(pressure - self._trend)
            sigma = self._estimate_sigma(self._residuals)
            if sigma is not None:
                self._noise_sigma = sigma

        self._last_pressure = pressure
        self._last_setpoint = setpoint if setpoint is not None else self._last_setpoint

        if timestamp < self._holdoff_until:
            return self._last_output
        if self._noise_sigma is None:
            return None
        self._last_output = self._noise_sigma
        return self._noise_sigma

    def _is_large_transition(self, pressure: float, setpoint: Optional[float]) -> bool:
        if self._noise_sigma is None or self._last_pressure is None:
            return False
        delta_pressure = abs(pressure - self._last_pressure)
        delta_setpoint = 0.0
        if setpoint is not None and self._last_setpoint is not None:
            delta_setpoint = abs(setpoint - self._last_setpoint)
        delta = max(delta_pressure, delta_setpoint)
        threshold = max(
            self._noise_sigma * self._settings.transition_sigma_factor,
            self._noise_sigma * 2.0,
        )
        return delta >= threshold

    def _adaptive_holdoff_seconds(self, pressure: float, setpoint: Optional[float]) -> float:
        if self._last_pressure is None:
            return 0.0
        delta_pressure = abs(pressure - self._last_pressure)
        delta_setpoint = 0.0
        if setpoint is not None and self._last_setpoint is not None:
            delta_setpoint = abs(setpoint - self._last_setpoint)
        delta = max(delta_pressure, delta_setpoint)
        sigma = max(self._noise_sigma or 0.0, 1e-6)
        threshold = max(sigma * self._settings.transition_sigma_factor, sigma * 2.0)
        ratio = max(1.0, min(4.0, delta / max(threshold, 1e-6)))
        holdoff_ms = min(self._settings.max_holdoff_ms, int(90 * ratio))
        return holdoff_ms / 1000.0

    def _estimate_sigma(self, residuals: Deque[float]) -> Optional[float]:
        values = list(residuals)
        if len(values) < self._settings.min_samples:
            return None
        center = median(values)
        abs_dev = [abs(value - center) for value in values]
        mad = median(abs_dev)
        sigma = 1.4826 * mad
        if sigma > 0.0:
            return sigma
        fallback = pstdev(values)
        return fallback if fallback > 0.0 else 0.0
