"""Unit tests for pressure calibration helpers."""

from __future__ import annotations

import math

import pytest

from app.services.pressure_calibration import (
    apply_error_model,
    fit_piecewise_linear_error_model,
    fit_quadratic_error_model,
    psi_to_torr,
    replay_corrected_series,
    score_replay,
    select_near_target_samples,
    split_train_validation,
    torr_to_psi,
)
from tests.fixtures.pressure_data import calibration_sample


def _sample(idx: int, *, phase: str = 'static_10', target: float = 10.0, transducer: float = 10.0, alicat: float = 10.0):
    return calibration_sample(
        idx,
        phase=phase,
        target=target,
        transducer=transducer,
        alicat=alicat,
    )


def test_psi_torr_round_trip() -> None:
    psi = 2.5
    torr = psi_to_torr(psi)
    assert torr_to_psi(torr) == pytest.approx(psi)


def test_select_near_target_static_only() -> None:
    samples = [
        _sample(0, phase='static_10', target=10.0, alicat=10.1, transducer=10.2),
        _sample(1, phase='dynamic_up', target=10.0, alicat=10.0, transducer=10.3),
        _sample(2, phase='static_10', target=10.0, alicat=10.4, transducer=10.3),
    ]
    selected = select_near_target_samples(samples, tolerance_psi=0.2, static_only=True)
    assert [s.index for s in selected] == [0]


def test_split_train_validation_stride() -> None:
    samples = [_sample(i) for i in range(10)]
    train, val = split_train_validation(samples, holdout_stride=4)
    assert [s.index for s in val] == [0, 4, 8]
    assert len(train) == 7


def test_apply_error_model_piecewise_and_replay_ema() -> None:
    model = {
        'type': 'piecewise_linear',
        'segments': [
            {'max_psi': 15.0, 'slope_error_per_psi': 0.0, 'intercept_error_psi': 1.0},
            {'max_psi': None, 'slope_error_per_psi': 0.0, 'intercept_error_psi': 2.0},
        ],
    }
    assert apply_error_model(10.0, model) == pytest.approx(9.0)
    assert apply_error_model(20.0, model) == pytest.approx(18.0)

    series = replay_corrected_series([10.0, 20.0], model=model, ema_alpha=0.5)
    # corrected raw = [9.0, 18.0], EMA(alpha=0.5) => [9.0, 13.5]
    assert series == pytest.approx([9.0, 13.5])


def test_fit_models_and_score_replay() -> None:
    # Synthetic linear error model: error = 0.01*x + 0.2
    # alicat = transducer - error
    samples = []
    for idx, transducer in enumerate([float(v) for v in range(1, 101)]):
        error = 0.01 * transducer + 0.2
        alicat = transducer - error
        samples.append(_sample(idx, target=transducer, transducer=transducer, alicat=alicat))

    near = select_near_target_samples(samples, tolerance_psi=2.0, static_only=True)
    train, validation = split_train_validation(near, holdout_stride=5)
    validation_idx = {s.index for s in validation}
    mask = [s.index in validation_idx for s in near]

    piecewise3 = fit_piecewise_linear_error_model(train, segment_count=3, min_segment_size=10)
    quadratic = fit_quadratic_error_model(train)

    piecewise_score = score_replay(near, model=piecewise3, ema_alpha=0.0, include_mask=mask)
    quadratic_score = score_replay(near, model=quadratic, ema_alpha=0.0, include_mask=mask)

    assert piecewise_score['p99_abs_torr'] < 0.5
    assert quadratic_score['p99_abs_torr'] < 0.5
    assert math.isfinite(piecewise_score['mean_abs_torr'])
    assert math.isfinite(quadratic_score['mean_abs_torr'])
