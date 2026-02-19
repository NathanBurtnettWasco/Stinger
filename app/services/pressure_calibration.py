"""Pressure calibration helpers for offline fitting and runtime correction."""

from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

TORR_PER_PSI = 51.71493256

REQUIRED_ALIGNMENT_COLUMNS = {
    'timestamp',
    'port_id',
    'phase',
    'target_abs_psi',
    'transducer_abs_psi',
    'alicat_abs_psi',
}


@dataclass
class CalibrationSample:
    """Single alignment sample used by calibration fitting/scoring."""

    index: int
    timestamp: float
    port_id: str
    phase: str
    target_abs_psi: Optional[float]
    transducer_abs_psi: Optional[float]
    alicat_abs_psi: Optional[float]


def psi_to_torr(psi: float) -> float:
    """Convert PSI to Torr."""
    return psi * TORR_PER_PSI


def torr_to_psi(torr: float) -> float:
    """Convert Torr to PSI."""
    return torr / TORR_PER_PSI


def _is_static_phase(phase: str) -> bool:
    return phase.startswith('static_')


def select_near_target_samples(
    samples: Sequence[CalibrationSample],
    *,
    tolerance_psi: float = 0.2,
    static_only: bool = True,
) -> List[CalibrationSample]:
    """Select samples where Alicat is near commanded target pressure.

    Rule:
    - target_abs_psi and alicat_abs_psi must be present
    - |alicat_abs_psi - target_abs_psi| <= tolerance_psi
    - optionally restrict to static phases only
    """
    selected: List[CalibrationSample] = []
    for sample in samples:
        if static_only and not _is_static_phase(sample.phase):
            continue
        if sample.target_abs_psi is None or sample.alicat_abs_psi is None:
            continue
        if abs(sample.alicat_abs_psi - sample.target_abs_psi) <= tolerance_psi:
            selected.append(sample)
    return selected


def split_train_validation(
    samples: Sequence[CalibrationSample],
    *,
    holdout_stride: int = 5,
) -> Tuple[List[CalibrationSample], List[CalibrationSample]]:
    """Deterministic split by sample index for reproducible holdout."""
    if holdout_stride < 2:
        raise ValueError('holdout_stride must be >= 2')
    train: List[CalibrationSample] = []
    validation: List[CalibrationSample] = []
    for i, sample in enumerate(samples):
        if i % holdout_stride == 0:
            validation.append(sample)
        else:
            train.append(sample)
    return train, validation


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError('Cannot compute quantile of empty values')
    if q <= 0:
        return min(values)
    if q >= 1:
        return max(values)
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def _linear_fit(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float]:
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError('Need at least two samples for linear fit')
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    if ss_xx <= 0:
        return 0.0, mean_y
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _percentile_candidates(segment_count: int) -> List[Tuple[float, ...]]:
    if segment_count == 3:
        grid = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]
        return list(itertools.combinations(grid, 2))
    if segment_count == 5:
        grid = [0.08, 0.16, 0.24, 0.32, 0.40, 0.52, 0.64, 0.76, 0.88]
        return list(itertools.combinations(grid, 4))
    raise ValueError(f'Unsupported segment_count={segment_count}')


def _fit_piecewise_for_breakpoints(
    xs: Sequence[float],
    ys: Sequence[float],
    breakpoints: Sequence[float],
    *,
    min_segment_size: int = 20,
) -> Optional[List[Tuple[float, float]]]:
    lines: List[Tuple[float, float]] = []
    lower = -float('inf')
    for upper in list(breakpoints) + [float('inf')]:
        seg_x = [x for x in xs if lower <= x < upper]
        seg_y = [y for x, y in zip(xs, ys) if lower <= x < upper]
        if len(seg_x) < min_segment_size:
            return None
        slope, intercept = _linear_fit(seg_x, seg_y)
        lines.append((slope, intercept))
        lower = upper
    return lines


def evaluate_error_model(pressure_psi: float, model: Optional[Dict[str, Any]]) -> float:
    """Return modeled sensor error(psi) at the given pressure."""
    if not model:
        return 0.0
    model_type = str(model.get('type', '')).strip().lower()
    if model_type == 'piecewise_linear':
        segments = model.get('segments', [])
        if not isinstance(segments, list) or not segments:
            return 0.0
        for segment in segments:
            max_psi = segment.get('max_psi')
            if max_psi is not None and pressure_psi >= float(max_psi):
                continue
            slope = float(segment.get('slope_error_per_psi', 0.0))
            intercept = float(segment.get('intercept_error_psi', 0.0))
            return slope * pressure_psi + intercept
        last = segments[-1]
        slope = float(last.get('slope_error_per_psi', 0.0))
        intercept = float(last.get('intercept_error_psi', 0.0))
        return slope * pressure_psi + intercept
    if model_type == 'quadratic':
        a = float(model.get('a_error_per_psi2', 0.0))
        b = float(model.get('b_error_per_psi', 0.0))
        c = float(model.get('c_error_psi', 0.0))
        return a * pressure_psi * pressure_psi + b * pressure_psi + c
    return 0.0


def apply_error_model(pressure_psi: float, model: Optional[Dict[str, Any]]) -> float:
    """Apply error model as corrected = measured - modeled_error."""
    return pressure_psi - evaluate_error_model(pressure_psi, model)


def build_legacy_two_band_model(
    *,
    breakpoint_psi: float,
    low_slope_error_per_psi: float,
    low_intercept_error_psi: float,
    high_slope_error_per_psi: float,
    high_intercept_error_psi: float,
) -> Dict[str, Any]:
    """Convert existing two-band config fields to generic piecewise config."""
    return {
        'type': 'piecewise_linear',
        'segments': [
            {
                'max_psi': float(breakpoint_psi),
                'slope_error_per_psi': float(low_slope_error_per_psi),
                'intercept_error_psi': float(low_intercept_error_psi),
            },
            {
                'max_psi': None,
                'slope_error_per_psi': float(high_slope_error_per_psi),
                'intercept_error_psi': float(high_intercept_error_psi),
            },
        ],
    }


def replay_corrected_series(
    measured_pressures_psi: Sequence[float],
    *,
    model: Optional[Dict[str, Any]],
    ema_alpha: float,
) -> List[float]:
    """Replay correction + optional EMA over a pressure series."""
    corrected: List[float] = []
    ema_value: Optional[float] = None
    alpha = float(ema_alpha)
    for raw in measured_pressures_psi:
        adjusted = apply_error_model(float(raw), model)
        if alpha <= 0.0 or alpha >= 1.0:
            ema_value = adjusted
        elif ema_value is None:
            ema_value = adjusted
        else:
            ema_value = alpha * adjusted + (1.0 - alpha) * ema_value
        corrected.append(float(ema_value))
    return corrected


def fit_piecewise_linear_error_model(
    train_samples: Sequence[CalibrationSample],
    *,
    segment_count: int,
    min_segment_size: int = 20,
) -> Dict[str, Any]:
    """Fit piecewise-linear model for error vs measured pressure."""
    if segment_count not in {3, 5}:
        raise ValueError('segment_count must be 3 or 5')
    xs = [float(s.transducer_abs_psi) for s in train_samples if s.transducer_abs_psi is not None and s.alicat_abs_psi is not None]
    ys = [float(s.transducer_abs_psi - s.alicat_abs_psi) for s in train_samples if s.transducer_abs_psi is not None and s.alicat_abs_psi is not None]
    if len(xs) < min_segment_size * segment_count:
        raise ValueError('Not enough training samples for requested segment count')

    breakpoint_quantiles = _percentile_candidates(segment_count)
    best_model: Optional[Dict[str, Any]] = None
    best_mae = float('inf')
    for q_tuple in breakpoint_quantiles:
        breakpoints = [_quantile(xs, q) for q in q_tuple]
        # Ensure strict increasing breakpoints.
        if any(b2 <= b1 for b1, b2 in zip(breakpoints, breakpoints[1:])):
            continue
        lines = _fit_piecewise_for_breakpoints(xs, ys, breakpoints, min_segment_size=min_segment_size)
        if lines is None:
            continue

        segments = []
        for i, (slope, intercept) in enumerate(lines):
            segments.append(
                {
                    'max_psi': (breakpoints[i] if i < len(breakpoints) else None),
                    'slope_error_per_psi': slope,
                    'intercept_error_psi': intercept,
                }
            )
        model = {'type': 'piecewise_linear', 'segments': segments}
        residuals = [abs(apply_error_model(x, model) - ref) for x, ref in zip(xs, (x - y for x, y in zip(xs, ys)))]
        mae = statistics.fmean(residuals)
        if mae < best_mae:
            best_mae = mae
            best_model = model

    if best_model is None:
        raise ValueError('Unable to fit piecewise-linear model with current constraints')
    return best_model


def fit_quadratic_error_model(train_samples: Sequence[CalibrationSample]) -> Dict[str, Any]:
    """Fit quadratic error model for error vs measured pressure."""
    xs = np.array(
        [float(s.transducer_abs_psi) for s in train_samples if s.transducer_abs_psi is not None and s.alicat_abs_psi is not None],
        dtype=float,
    )
    ys = np.array(
        [float(s.transducer_abs_psi - s.alicat_abs_psi) for s in train_samples if s.transducer_abs_psi is not None and s.alicat_abs_psi is not None],
        dtype=float,
    )
    if len(xs) < 3:
        raise ValueError('Need at least 3 samples to fit quadratic model')
    a, b, c = np.polyfit(xs, ys, deg=2)
    return {
        'type': 'quadratic',
        'a_error_per_psi2': float(a),
        'b_error_per_psi': float(b),
        'c_error_psi': float(c),
    }


def _quantile_abs(values: Sequence[float], q: float) -> float:
    if not values:
        return float('nan')
    return _quantile([abs(v) for v in values], q)


def score_error_series_torr(errors_psi: Sequence[float]) -> Dict[str, float]:
    """Compute absolute error metrics in Torr from psi errors."""
    if not errors_psi:
        return {
            'n': 0,
            'mean_abs_torr': float('nan'),
            'p95_abs_torr': float('nan'),
            'p99_abs_torr': float('nan'),
            'max_abs_torr': float('nan'),
        }
    abs_torr = [psi_to_torr(abs(e)) for e in errors_psi]
    return {
        'n': float(len(errors_psi)),
        'mean_abs_torr': float(statistics.fmean(abs_torr)),
        'p95_abs_torr': float(_quantile(abs_torr, 0.95)),
        'p99_abs_torr': float(_quantile(abs_torr, 0.99)),
        'max_abs_torr': float(max(abs_torr)),
    }


def score_replay(
    samples: Sequence[CalibrationSample],
    *,
    model: Optional[Dict[str, Any]],
    ema_alpha: float,
    include_mask: Optional[Sequence[bool]] = None,
) -> Dict[str, float]:
    """Replay a model over ordered samples and score selected points."""
    measured = [float(s.transducer_abs_psi) for s in samples]
    reference = [float(s.alicat_abs_psi) for s in samples]
    replayed = replay_corrected_series(measured, model=model, ema_alpha=ema_alpha)
    if include_mask is None:
        include_mask = [True] * len(samples)
    errors = [pred - ref for pred, ref, include in zip(replayed, reference, include_mask) if include]
    return score_error_series_torr(errors)

