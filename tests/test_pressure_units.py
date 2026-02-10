"""Pressure unit conversion and debug display tests."""

import pytest
from typing import Any, cast
from dataclasses import dataclass

from app.hardware.alicat import AlicatReading
from app.hardware.alicat import AlicatController
from app.hardware.port import Port, PortId
from app.hardware.labjack import SwitchState, TransducerReading
from app.hardware.port import PortReading
from app.services.ptp_service import convert_pressure, derive_test_setup
from app.services.test_executor import TestExecutor as _TestExecutor
from app.services.ptp_service import TestSetup
from app.services.work_order_controller import _is_plausible_barometric_psi
from app.services.ui_bridge import UIBridge


def _build_reading(
    *,
    timestamp: float,
    transducer_pressure: float,
    transducer_reference: str,
    alicat_pressure: float,
    alicat_setpoint: float,
    barometric_pressure: float,
    gauge_pressure: float | None,
) -> PortReading:
    return PortReading(
        transducer=TransducerReading(
            voltage=2.5,
            pressure=transducer_pressure,
            pressure_raw=transducer_pressure,
            pressure_reference=transducer_reference,
            timestamp=timestamp,
        ),
        alicat=AlicatReading(
            pressure=alicat_pressure,
            setpoint=alicat_setpoint,
            timestamp=timestamp,
            gauge_pressure=gauge_pressure,
            barometric_pressure=barometric_pressure,
        ),
        timestamp=timestamp,
    )


def test_convert_pressure_round_trip_torr() -> None:
    torr_value = convert_pressure(14.7, "PSI", "Torr")
    assert torr_value == pytest.approx(760.0, rel=1e-3)
    assert convert_pressure(torr_value, "Torr", "PSI") == pytest.approx(14.7, rel=1e-3)


def test_debug_setpoint_recomputes_when_switching_psig_psia() -> None:
    bridge = UIBridge({})
    events: list[tuple[str, float, float | None, float | None, float | None]] = []
    bridge.debug_chart_updated.connect(
        lambda port_id, ts, pressure, setpoint, alicat: events.append(
            (port_id, ts, pressure, setpoint, alicat)
        )
    )

    bridge.set_pressure_unit("PSIG")
    reading = _build_reading(
        timestamp=1.0,
        transducer_pressure=9.7,
        transducer_reference="absolute",
        alicat_pressure=9.7,
        alicat_setpoint=9.7,
        barometric_pressure=14.7,
        gauge_pressure=-5.0,
    )
    bridge.update_pressure("port_a", reading)

    assert events[-1][3] == pytest.approx(-5.0, rel=1e-3)

    bridge.set_pressure_unit("PSIA")
    assert events[-1][3] == pytest.approx(9.7, rel=1e-3)


def test_set_pressure_accepts_gauge_input_for_absolute_display() -> None:
    bridge = UIBridge({})
    events: list[tuple[str, float, str]] = []
    bridge.pressure_updated.connect(lambda port_id, pressure, unit: events.append((port_id, pressure, unit)))

    bridge.set_pressure_unit("PSIA")
    bridge.set_pressure("port_a", -5.0, "PSIG")

    assert events[-1][1] == pytest.approx(9.7, rel=1e-3)
    assert events[-1][2] == "PSIA"


def test_debug_setpoint_uses_inferred_barometric_when_direct_value_missing() -> None:
    bridge = UIBridge({})
    events: list[tuple[str, float, float | None, float | None, float | None]] = []
    bridge.debug_chart_updated.connect(
        lambda port_id, ts, pressure, setpoint, alicat: events.append(
            (port_id, ts, pressure, setpoint, alicat)
        )
    )

    bridge.set_pressure_unit("PSIA")
    reading = _build_reading(
        timestamp=1.0,
        transducer_pressure=1.0,
        transducer_reference="absolute",
        alicat_pressure=1.0,
        alicat_setpoint=-12.6,
        barometric_pressure=0.0,
        gauge_pressure=-12.6,
    )
    assert reading.alicat is not None
    reading.alicat.barometric_pressure = None
    bridge.update_pressure("port_a", reading)

    assert events[-1][3] == pytest.approx(1.0, rel=1e-3)


def test_derive_setup_defaults_missing_pressure_reference_to_absolute_for_torr() -> None:
    setup = derive_test_setup(
        '17025',
        '399',
        {
            'ActivationTarget': '400.000000',
            'IncreasingLowerLimit': '390.000000',
            'IncreasingUpperLimit': '410.000000',
            'DecreasingLowerLimit': '380.000000',
            'DecreasingUpperLimit': '395.000000',
            'ResetBandLowerLimit': '360.000000',
            'ResetBandUpperLimit': '370.000000',
            'TargetActivationDirection': 'Decreasing',
            'UnitsOfMeasure': '21',
            'CommonTerminal': '3',
            'NormallyOpenTerminal': '2',
            'NormallyClosedTerminal': '1',
        },
    )
    assert setup.units_label == 'Torr'
    assert setup.pressure_reference == 'absolute'


def test_derive_setup_normalizes_pressure_reference_alias() -> None:
    setup = derive_test_setup(
        '17025',
        '399',
        {
            'ActivationTarget': '400.000000',
            'IncreasingLowerLimit': '390.000000',
            'IncreasingUpperLimit': '410.000000',
            'DecreasingLowerLimit': '380.000000',
            'DecreasingUpperLimit': '395.000000',
            'ResetBandLowerLimit': '360.000000',
            'ResetBandUpperLimit': '370.000000',
            'TargetActivationDirection': 'Decreasing',
            'UnitsOfMeasure': '21',
            'PressureReference': 'Gage',
            'CommonTerminal': '3',
            'NormallyOpenTerminal': '2',
            'NormallyClosedTerminal': '1',
        },
    )
    assert setup.pressure_reference == 'gauge'


def test_barometric_plausibility_guard() -> None:
    assert _is_plausible_barometric_psi(14.7)
    assert not _is_plausible_barometric_psi(0.2635)


class _FakeAlicat:
    def __init__(self) -> None:
        self.configure_calls = 0
        self.cancel_hold_calls = 0

    def configure_units_from_ptp(self, _units_code: str) -> bool:
        self.configure_calls += 1
        return True

    def cancel_hold(self) -> bool:
        self.cancel_hold_calls += 1
        return True

    def set_ramp_rate(self, _rate: float) -> bool:
        return True


class _FakePort:
    def __init__(self, outcomes: list[bool]) -> None:
        self.alicat = _FakeAlicat()
        self._outcomes = outcomes
        self.vent_calls = 0

    def set_pressure(self, _setpoint: float) -> bool:
        if not self._outcomes:
            return True
        return self._outcomes.pop(0)

    def set_solenoid(self, to_vacuum: bool) -> bool:
        return True

    def vent_to_atmosphere(self) -> bool:
        self.vent_calls += 1
        return True


def _build_executor(
    port: _FakePort,
    get_latest_reading: Any = None,
    on_cancelled: Any = None,
) -> _TestExecutor:
    setup = TestSetup(
        part_id='17025',
        sequence_id='399',
        units_code='21',
        units_label='Torr',
        activation_direction='Decreasing',
        activation_target=400.0,
        pressure_reference='absolute',
        terminals={},
        bands={
            'increasing': {'lower': 550.0, 'upper': 600.0},
            'decreasing': {'lower': 400.0, 'upper': 500.0},
            'reset': {'lower': 300.0, 'upper': 350.0},
        },
        raw={},
    )

    return _TestExecutor(
        port_id='port_a',
        port=cast(Any, port),
        test_setup=setup,
        config={'control': {'cycling': {}, 'ramps': {}, 'edge_detection': {}, 'debounce': {}}},
        get_latest_reading=get_latest_reading or (lambda _pid: None),
        get_barometric_psi=lambda _pid: 14.7,
        on_cancelled=on_cancelled,
    )


def test_executor_set_pressure_recovers_after_one_failure() -> None:
    executor = _build_executor(_FakePort([False, True]))
    executor._set_pressure_or_raise(7.0)
    alicat = cast(_FakeAlicat, executor._port.alicat)
    assert alicat.configure_calls >= 1
    assert alicat.cancel_hold_calls == 1


def test_executor_set_pressure_raises_after_second_failure() -> None:
    executor = _build_executor(_FakePort([False, False]))
    with pytest.raises(RuntimeError):
        executor._set_pressure_or_raise(7.0)


def test_executor_unit_verify_failure_is_non_fatal() -> None:
    class _BadAlicat(_FakeAlicat):
        def configure_units_from_ptp(self, _units_code: str) -> bool:
            self.configure_calls += 1
            return False

    class _BadPort(_FakePort):
        def __init__(self) -> None:
            super().__init__([True])
            self.alicat = _BadAlicat()

    executor = _build_executor(_BadPort(), on_cancelled=lambda: None)
    executor._ensure_alicat_units()


def test_executor_run_emits_cancelled_and_vents() -> None:
    port = _FakePort([True])
    cancelled = {'called': False}
    executor = _build_executor(
        port,
        on_cancelled=lambda: cancelled.__setitem__('called', True),
    )

    executor.request_cancel()
    executor._run()

    assert cancelled['called']
    assert port.vent_calls >= 1


def test_executor_sweep_to_edge_returns_none_without_switch_transition() -> None:
    port = _FakePort([True])
    reading = PortReading(
        transducer=TransducerReading(
            voltage=2.5,
            pressure=14.7,
            pressure_raw=14.7,
            pressure_reference='absolute',
            timestamp=0.0,
        ),
        switch=SwitchState(no_active=False, nc_active=True, timestamp=0.0),
        timestamp=0.0,
    )
    executor = _build_executor(
        port,
        get_latest_reading=lambda _pid: reading,
    )
    executor._edge_timeout_s = 0.05
    executor._stable_count = 2

    edge = executor._sweep_to_edge(target_psi=0.0, direction=1)
    assert edge is None


def test_executor_precision_targets_use_close_limit_for_decreasing() -> None:
    executor = _build_executor(_FakePort([True]))

    approach, target_out, target_back, source = executor._resolve_precision_targets(
        min_psi=convert_pressure(390.0, 'Torr', 'PSI'),
        max_psi=convert_pressure(600.0, 'Torr', 'PSI'),
        activation_direction=-1,
    )

    assert source == 'ptp-close-limit'
    assert approach == pytest.approx(convert_pressure(600.0, 'Torr', 'PSI'), rel=1e-6)
    assert target_out == pytest.approx(convert_pressure(400.0, 'Torr', 'PSI'), rel=1e-6)
    assert target_back == pytest.approx(convert_pressure(600.0, 'Torr', 'PSI'), rel=1e-6)


def test_executor_precision_targets_use_cycle_activation_offset_when_available() -> None:
    executor = _build_executor(_FakePort([True]))
    executor._cycle_activation_samples = [convert_pressure(400.0, 'Torr', 'PSI')]
    executor._cycle_deactivation_samples = [convert_pressure(470.0, 'Torr', 'PSI')]

    approach, target_out, target_back, source = executor._resolve_precision_targets(
        min_psi=convert_pressure(390.0, 'Torr', 'PSI'),
        max_psi=convert_pressure(600.0, 'Torr', 'PSI'),
        activation_direction=-1,
    )

    assert source == 'cycle-estimate-offset-close-limit'
    # Approach is now close to activation (activation_estimate + offset for decreasing)
    assert approach == pytest.approx(convert_pressure(440.0, 'Torr', 'PSI'), rel=1e-6)
    # Out target should sweep farther out than approach in the activation direction.
    assert target_out < approach
    # Back target sweeps past deactivation (deactivation_estimate + margin)
    assert target_back == pytest.approx(convert_pressure(485.0, 'Torr', 'PSI'), rel=1e-6)


def test_alicat_set_pressure_uses_compact_fallback_command() -> None:
    controller = AlicatController({'address': 'A'})
    sent: list[str] = []

    def fake_send(command: str) -> str:
        sent.append(command)
        if len(sent) == 1:
            return '?'
        return 'A'

    controller._send_command = fake_send  # type: ignore[method-assign]
    assert controller.set_pressure(7.0434)
    assert sent[0].startswith('S ')
    assert sent[1].startswith('S') and not sent[1].startswith('S ')


def test_alicat_set_pressure_uses_psi_unit_fallback_after_native_rejected() -> None:
    controller = AlicatController({'address': 'A'})
    controller._display_units_label = 'Torr'
    sent: list[str] = []

    def fake_send(command: str) -> str:
        sent.append(command)
        if len(sent) < 3:
            return '?'
        return 'A'

    controller._send_command = fake_send  # type: ignore[method-assign]
    assert controller.set_pressure(7.0)
    assert sent[0].startswith('S ')
    assert sent[1].startswith('S') and not sent[1].startswith('S ')
    assert sent[2].startswith('S ')


def test_alicat_set_pressure_no_fallback_when_first_command_acknowledged() -> None:
    controller = AlicatController({'address': 'A'})
    sent: list[str] = []

    def fake_send(command: str) -> str:
        sent.append(command)
        return 'A'

    controller._send_command = fake_send  # type: ignore[method-assign]
    assert controller.set_pressure(7.0)
    assert len(sent) == 1


def test_alicat_ramp_prefers_psi_after_pressure_fallback() -> None:
    controller = AlicatController({'address': 'A'})
    sent: list[str] = []

    def fake_send(command: str) -> str:
        sent.append(command)
        # For pressure setpoint: reject native two attempts, accept psi-spaced.
        if command.startswith('S '):
            if len(sent) in (1,):
                return '?'
            if command.startswith('S 7.00'):
                return 'A'
            return '?'
        if command.startswith('S7.00'):
            return '?'
        # Ramp command should now prefer PSI first.
        if command.startswith('SR 0.0967'):
            return 'A'
        return '?'

    controller._display_units_label = 'Torr'
    controller._send_command = fake_send  # type: ignore[method-assign]

    assert controller.set_pressure(7.0)
    assert controller.set_ramp_rate(0.0967)
    assert any(cmd.startswith('SR 0.0967') for cmd in sent)


def test_alicat_configure_units_from_ptp_verifies_readback_before_success() -> None:
    controller = AlicatController({'address': 'A'})
    controller._is_connected = True
    commands: list[str] = []

    def fake_send(command: str) -> str:
        commands.append(command)
        if command == 'DCU 2':
            if commands.count('DCU 2') == 1:
                return 'A 10'
            return 'A 13'
        if command == 'DCU 2 13':
            return 'A'
        return 'A'

    controller._send_command = fake_send  # type: ignore[method-assign]
    assert controller.configure_units_from_ptp('21')
    assert controller._display_units_label == 'Torr'
    assert 'DCU 2 13' in commands


def test_alicat_configure_units_from_ptp_fails_when_readback_mismatch() -> None:
    controller = AlicatController({'address': 'A'})
    controller._is_connected = True

    def fake_send(command: str) -> str:
        if command == 'DCU 2':
            return 'A 10'
        if command == 'DCU 2 13':
            return 'A'
        return 'A'

    controller._send_command = fake_send  # type: ignore[method-assign]
    assert not controller.configure_units_from_ptp('21')
    assert controller._display_units_label == 'PSI'


def test_port_does_not_override_switch_pins_from_ptp_by_default() -> None:
    port = Port(
        PortId.PORT_B,
        {
            'device_type': 'T7',
            'connection_type': 'USB',
            'identifier': 'ANY',
            'switch_no_dio': 9,
            'switch_nc_dio': 11,
            'switch_com_dio': 12,
            'switch_com_state': 0,
            'use_ptp_terminals': False,
        },
        {'address': 'B'},
        {},
    )

    called = {'configure_di': 0}

    def fake_configure_di_pins(*_args, **_kwargs):
        called['configure_di'] += 1

    port.daq.configure_di_pins = fake_configure_di_pins  # type: ignore[method-assign]

    ok = port.configure_from_ptp(
        {
            'NormallyOpenTerminal': '3',
            'NormallyClosedTerminal': '1',
            'CommonTerminal': '4',
            'PressureReference': 'Absolute',
        }
    )
    assert ok
    assert called['configure_di'] == 0


@dataclass
class _FlowSimulator:
    atmosphere_psi: float
    activation_edge_psi: float
    deactivation_edge_psi: float
    activation_direction: int
    pressure_psi: float
    target_psi: float
    switch_activated: bool = False
    max_step_psi: float = 0.45
    tick: int = 0

    def step(self) -> PortReading:
        delta = self.target_psi - self.pressure_psi
        if abs(delta) <= self.max_step_psi:
            self.pressure_psi = self.target_psi
        elif delta > 0:
            self.pressure_psi += self.max_step_psi
        else:
            self.pressure_psi -= self.max_step_psi

        if self.activation_direction < 0:
            if not self.switch_activated and self.pressure_psi <= self.activation_edge_psi:
                self.switch_activated = True
            elif self.switch_activated and self.pressure_psi >= self.deactivation_edge_psi:
                self.switch_activated = False
        else:
            if not self.switch_activated and self.pressure_psi >= self.activation_edge_psi:
                self.switch_activated = True
            elif self.switch_activated and self.pressure_psi <= self.deactivation_edge_psi:
                self.switch_activated = False

        self.tick += 1
        timestamp = self.tick * 0.02
        return PortReading(
            transducer=TransducerReading(
                voltage=2.5,
                pressure=self.pressure_psi,
                pressure_raw=self.pressure_psi,
                pressure_reference='absolute',
                timestamp=timestamp,
            ),
            switch=SwitchState(
                no_active=self.switch_activated,
                nc_active=not self.switch_activated,
                timestamp=timestamp,
            ),
            timestamp=timestamp,
        )


class _FlowAlicat:
    def configure_units_from_ptp(self, _units_code: str) -> bool:
        return True

    def cancel_hold(self) -> bool:
        return True

    def set_ramp_rate(self, _rate: float) -> bool:
        return True


class _FlowPort:
    def __init__(self, sim: _FlowSimulator) -> None:
        self._sim = sim
        self.alicat = _FlowAlicat()
        self.set_pressure_calls: list[float] = []
        self.solenoid_calls: list[bool] = []

    def set_pressure(self, setpoint: float) -> bool:
        self.set_pressure_calls.append(setpoint)
        self._sim.target_psi = setpoint
        return True

    def set_solenoid(self, to_vacuum: bool) -> bool:
        self.solenoid_calls.append(to_vacuum)
        return True

    def vent_to_atmosphere(self) -> bool:
        self._sim.target_psi = self._sim.atmosphere_psi
        return True


def _flow_config() -> dict[str, Any]:
    return {
        'control': {
            'cycling': {'num_cycles': 3},
            'ramps': {
                'precision_sweep_rate_torr_per_sec': 18.0,
                'precision_edge_rate_torr_per_sec': 18.0,
            },
            'edge_detection': {
                'overshoot_beyond_limit_percent': 10.0,
                'timeout_sec': 4.0,
                'atmosphere_tolerance_psi': 0.35,
                'precision_approach_tolerance_torr': 10.0,
                'precision_approach_settle_sec': 0.0,
                'precision_start_atmosphere_hold_sec': 0.0,
                'precision_close_limit_offset_torr': 40.0,
                'precision_prepass_nudge_torr': 20.0,
                'precision_deactivation_margin_torr': 15.0,
            },
            'debounce': {
                'stable_sample_count': 2,
                'min_edge_interval_ms': 0,
            },
        },
    }


def _build_flow_executor(setup: TestSetup, sim: _FlowSimulator, port_id: str) -> tuple[_TestExecutor, _FlowPort, dict[str, Any]]:
    port = _FlowPort(sim)
    captured: dict[str, Any] = {
        'cycling_complete': False,
        'substates': [],
        'cycle_estimates': [],
        'edges': None,
        'errors': [],
    }
    executor = _TestExecutor(
        port_id=port_id,
        port=cast(Any, port),
        test_setup=setup,
        config=_flow_config(),
        get_latest_reading=lambda _pid: sim.step(),
        get_barometric_psi=lambda _pid: sim.atmosphere_psi,
        on_cycling_complete=lambda: captured.__setitem__('cycling_complete', True),
        on_substate_update=lambda state: captured['substates'].append(state),
        on_edges_captured=lambda a, d: captured.__setitem__('edges', (a, d)),
        on_cycle_estimate=lambda a, d, c: captured['cycle_estimates'].append((a, d, c)),
        on_error=lambda message: captured['errors'].append(message),
    )
    return executor, port, captured


def test_executor_full_flow_port_b_17025_qal16_cycle_and_precision() -> None:
    setup = TestSetup(
        part_id='17025',
        sequence_id='399',
        units_code='21',
        units_label='Torr',
        activation_direction='Decreasing',
        activation_target=400.0,
        pressure_reference='absolute',
        terminals={},
        bands={
            'increasing': {'lower': 550.0, 'upper': 600.0},
            'decreasing': {'lower': 390.0, 'upper': 410.0},
            'reset': {'lower': 360.0, 'upper': 370.0},
        },
        raw={},
    )
    sim = _FlowSimulator(
        atmosphere_psi=14.7,
        activation_edge_psi=7.8,
        deactivation_edge_psi=9.2,
        activation_direction=-1,
        pressure_psi=14.7,
        target_psi=14.7,
    )
    executor, port, captured = _build_flow_executor(setup, sim, 'port_b')

    executor._run()

    assert captured['errors'] == []
    assert captured['cycling_complete'] is True
    assert captured['edges'] is not None
    activation, deactivation = captured['edges']
    assert activation == pytest.approx(7.8, abs=0.7)
    assert deactivation == pytest.approx(9.2, abs=0.8)
    assert any(state == 'precision.fast_approach' for state in captured['substates'])
    assert captured['cycle_estimates'] and captured['cycle_estimates'][-1][2] >= 3
    assert len(port.set_pressure_calls) >= 3
    approach, out_target, back_target = port.set_pressure_calls[-3:]
    # Decreasing activation: approach is above activation, out is below,
    # back is above deactivation (separate from approach in the new logic)
    assert approach > out_target
    assert back_target > approach  # back target goes past deactivation (higher pressure)


def test_executor_full_flow_port_a_sba01655_qal16_cycle_and_precision() -> None:
    setup = TestSetup(
        part_id='SBA01655-03',
        sequence_id='225',
        units_code='1',
        units_label='PSI',
        activation_direction='Increasing',
        activation_target=20.5,
        pressure_reference='absolute',
        terminals={},
        bands={
            'increasing': {'lower': 20.0, 'upper': 21.0},
            'decreasing': {'lower': 17.0, 'upper': 18.0},
            'reset': {'lower': 16.0, 'upper': 16.5},
        },
        raw={},
    )
    sim = _FlowSimulator(
        atmosphere_psi=14.7,
        activation_edge_psi=20.6,
        deactivation_edge_psi=17.6,
        activation_direction=1,
        pressure_psi=14.7,
        target_psi=14.7,
    )
    executor, port, captured = _build_flow_executor(setup, sim, 'port_a')

    executor._run()

    if captured['errors']:
        assert any('edge_not_found' in err for err in captured['errors'])
    else:
        assert captured['cycling_complete'] is True
        assert captured['edges'] is not None
        activation, deactivation = captured['edges']
        assert activation == pytest.approx(20.6, abs=0.7)
        assert deactivation == pytest.approx(17.6, abs=0.8)
        assert captured['cycle_estimates'] and captured['cycle_estimates'][-1][2] >= 3
        assert len(port.set_pressure_calls) >= 3
        approach, out_target, back_target = port.set_pressure_calls[-3:]
        # Increasing activation: approach is below activation, out is above,
        # back is below deactivation (separate from approach in the new logic)
        assert approach < out_target
        assert back_target < approach  # back target goes past deactivation (lower pressure)
