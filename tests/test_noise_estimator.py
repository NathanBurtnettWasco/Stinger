"""Tests for robust debug noise estimation under dynamic loads."""

from __future__ import annotations

import random
from pathlib import Path
from statistics import median
from typing import Any

import pytest
import yaml

from app.core.config import load_config
from app.services.noise_estimator import (
    DEFAULT_MAX_HOLDOFF_MS,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_TRANSITION_SIGMA_FACTOR,
    DEFAULT_TREND_ALPHA,
    DEFAULT_WINDOW_SAMPLES,
    ResidualNoiseEstimator,
    parse_debug_noise_settings,
)


def _base_config() -> dict[str, Any]:
    return load_config()


def test_load_config_applies_debug_noise_defaults_when_missing(tmp_path: Path) -> None:
    cfg = _base_config()
    cfg['ui'].pop('debug_noise', None)
    path = tmp_path / 'stinger_config.yaml'
    with path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)

    loaded = load_config(path)
    debug_noise = loaded['ui']['debug_noise']
    assert debug_noise['window_samples'] == DEFAULT_WINDOW_SAMPLES
    assert debug_noise['min_samples'] == DEFAULT_MIN_SAMPLES
    assert debug_noise['trend_alpha'] == DEFAULT_TREND_ALPHA
    assert debug_noise['transition_sigma_factor'] == DEFAULT_TRANSITION_SIGMA_FACTOR
    assert debug_noise['max_holdoff_ms'] == DEFAULT_MAX_HOLDOFF_MS


def test_residual_noise_tracks_jitter_on_steady_signal() -> None:
    estimator = ResidualNoiseEstimator(
        parse_debug_noise_settings(
            {
                'window_samples': 80,
                'min_samples': 16,
                'trend_alpha': 0.2,
                'transition_sigma_factor': 8.0,
                'max_holdoff_ms': 300,
            }
        )
    )
    rng = random.Random(20260218)
    outputs: list[float] = []
    for idx in range(300):
        ts = idx * 0.05
        pressure = 20.0 + rng.gauss(0.0, 0.05)
        noise = estimator.update(pressure, ts, setpoint=20.0)
        if noise is not None:
            outputs.append(noise)

    assert outputs, 'Expected at least one noise estimate'
    assert median(outputs[-40:]) == pytest.approx(0.05, abs=0.02)


def test_residual_noise_stays_stable_on_linear_ramp() -> None:
    estimator = ResidualNoiseEstimator(
        parse_debug_noise_settings(
            {
                'window_samples': 100,
                'min_samples': 20,
                'trend_alpha': 0.22,
                'transition_sigma_factor': 8.0,
                'max_holdoff_ms': 300,
            }
        )
    )
    rng = random.Random(20260219)
    outputs: list[float] = []
    for idx in range(360):
        ts = idx * 0.05
        trend = 8.0 + 0.07 * idx
        pressure = trend + rng.gauss(0.0, 0.05)
        noise = estimator.update(pressure, ts, setpoint=trend)
        if noise is not None:
            outputs.append(noise)

    assert outputs, 'Expected at least one noise estimate'
    assert median(outputs[-40:]) < 0.11


def test_large_step_transition_enters_holdoff_without_runaway_noise() -> None:
    estimator = ResidualNoiseEstimator(
        parse_debug_noise_settings(
            {
                'window_samples': 80,
                'min_samples': 16,
                'trend_alpha': 0.2,
                'transition_sigma_factor': 7.0,
                'max_holdoff_ms': 350,
            }
        )
    )
    rng = random.Random(20260220)
    pre_outputs: list[float] = []

    for idx in range(180):
        ts = idx * 0.05
        pressure = 18.0 + rng.gauss(0.0, 0.04)
        noise = estimator.update(pressure, ts, setpoint=18.0)
        if noise is not None:
            pre_outputs.append(noise)

    assert pre_outputs
    pre_step_noise = pre_outputs[-1]
    step_ts = 180 * 0.05
    held_noise = estimator.update(26.0 + rng.gauss(0.0, 0.04), step_ts, setpoint=26.0)
    assert estimator.in_holdoff(step_ts)
    assert held_noise == pytest.approx(pre_step_noise, rel=1e-6, abs=1e-6)

    post_outputs: list[float] = []
    for idx in range(181, 280):
        ts = idx * 0.05
        pressure = 26.0 + rng.gauss(0.0, 0.04)
        noise = estimator.update(pressure, ts, setpoint=26.0)
        if noise is not None:
            post_outputs.append(noise)

    assert post_outputs
    assert max(post_outputs) < 0.2
