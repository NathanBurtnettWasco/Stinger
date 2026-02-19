"""Tests for configurable main pressure measurement source behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from app.core.config import load_config, save_config
from app.services.measurement_source import select_main_pressure_abs_psi
from app.services.ptp_service import TestSetup
from app.services.test_executor import TestExecutor as _TestExecutor
from app.services.ui_bridge import UIBridge
from tests.fixtures.pressure_data import build_port_reading


def _base_config() -> dict[str, Any]:
    return load_config()


def _executor_config(preferred_source: str) -> dict[str, Any]:
    return {
        'hardware': {
            'measurement': {
                'preferred_source': preferred_source,
                'fallback_on_unavailable': True,
            },
        },
        'control': {
            'cycling': {'num_cycles': 1},
            'ramps': {'precision_sweep_rate_torr_per_sec': 10.0},
            'edge_detection': {'timeout_sec': 1.0},
            'debounce': {},
        },
    }


class _FakeAlicat:
    def configure_units_from_ptp(self, _units_code: str) -> bool:
        return True

    def cancel_hold(self) -> bool:
        return True

    def set_ramp_rate(self, _rate: float) -> bool:
        return True


class _FakePort:
    def __init__(self) -> None:
        self.alicat = _FakeAlicat()

    def set_pressure(self, _setpoint: float) -> bool:
        return True

    def set_solenoid(self, _to_vacuum: bool) -> bool:
        return True

    def vent_to_atmosphere(self) -> bool:
        return True


def _build_executor(preferred_source: str) -> _TestExecutor:
    setup = TestSetup(
        part_id='17025',
        sequence_id='399',
        units_code='1',
        units_label='PSI',
        activation_direction='Increasing',
        activation_target=20.0,
        pressure_reference='absolute',
        terminals={},
        bands={
            'increasing': {'lower': 19.0, 'upper': 21.0},
            'decreasing': {'lower': 18.0, 'upper': 20.0},
            'reset': {'lower': 17.0, 'upper': 22.0},
        },
        raw={},
    )
    return _TestExecutor(
        port_id='port_a',
        port=cast(Any, _FakePort()),
        test_setup=setup,
        config=_executor_config(preferred_source),
        get_latest_reading=lambda _pid: None,
        get_barometric_psi=lambda _pid: 14.7,
    )


def test_load_config_applies_measurement_defaults_when_missing(tmp_path: Path) -> None:
    cfg = _base_config()
    cfg['hardware'].pop('measurement', None)
    path = tmp_path / 'stinger_config.yaml'
    with path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)

    loaded = load_config(path)
    measurement_cfg = loaded['hardware']['measurement']
    assert measurement_cfg['preferred_source'] == 'alicat'
    assert measurement_cfg['fallback_on_unavailable'] is False


def test_save_config_persists_normalized_measurement_source(tmp_path: Path) -> None:
    cfg = _base_config()
    cfg.setdefault('hardware', {})['measurement'] = {
        'preferred_source': 'Alicat',
        'fallback_on_unavailable': True,
    }
    source_path = tmp_path / 'in.yaml'
    with source_path.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False)
    loaded = load_config(source_path)

    output_path = tmp_path / 'out.yaml'
    save_config(loaded, output_path)
    with output_path.open('r', encoding='utf-8') as handle:
        persisted = cast(dict[str, Any], yaml.safe_load(handle))
    assert persisted['hardware']['measurement']['preferred_source'] == 'alicat'


def test_select_main_pressure_abs_psi_prefers_requested_source_with_fallback() -> None:
    reading = build_port_reading(transducer_pressure=10.0, alicat_pressure=0.0)
    assert reading.alicat is not None
    reading.alicat.pressure = None
    selected, source = select_main_pressure_abs_psi(
        reading=reading,
        preferred_source='alicat',
        fallback_on_unavailable=True,
        barometric_psi=14.7,
    )
    assert selected == 10.0
    assert source == 'transducer'


def test_ui_bridge_uses_selected_main_source_for_display() -> None:
    bridge = UIBridge(
        {
            'hardware': {
                'measurement': {
                    'preferred_source': 'alicat',
                    'fallback_on_unavailable': True,
                }
            }
        }
    )
    emitted: list[tuple[str, float, str]] = []
    bridge.pressure_updated.connect(
        lambda port_id, pressure, unit: emitted.append((port_id, pressure, unit))
    )
    bridge.set_pressure_unit('PSIA')
    bridge.update_pressure(
        'port_a',
        build_port_reading(transducer_pressure=10.0, alicat_pressure=22.0),
    )

    assert emitted
    assert emitted[-1][1] == 22.0
    assert emitted[-1][2] == 'PSIA'


def test_executor_uses_selected_main_source_for_test_pressure() -> None:
    executor = _build_executor('alicat')
    reading = build_port_reading(transducer_pressure=10.0, alicat_pressure=26.0)
    assert executor._reading_pressure_abs_psi(reading) == 26.0
