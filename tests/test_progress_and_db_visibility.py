from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from app.database import operations
from app.services import work_order_controller
from app.services.work_order_controller import WorkOrderController
from app.ui.main_window import MainWindow


class _FakeUiBridge:
    def __init__(self, work_order: dict[str, object]) -> None:
        self._current_work_order = work_order
        self._port_serials = {'port_a': 7}
        self.status_updates: list[dict[str, str]] = []

    def get_pressure_unit(self) -> str:
        return 'PSI'

    def update_database_status(self, status: str, last_write: str = '--', queue: str = '0') -> None:
        self.status_updates.append(
            {
                'status': status,
                'last_write': last_write,
                'queue': queue,
            }
        )


class _FakeStateMachine:
    def __init__(self) -> None:
        self._increasing_activation = 12.3
        self._decreasing_deactivation = 9.8
        self._attempt_count = 0


def _make_save_controller(*, test_mode: bool = False) -> WorkOrderController:
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._ui_bridge = _FakeUiBridge(
        {
            'test_mode': test_mode,
            'shop_order': 'WO-1',
            'part_id': 'PART-1',
            'sequence_id': '1',
            'operator_id': 'OP-1',
        }
    )
    controller._state_machines = {'port_a': _FakeStateMachine()}
    controller._current_test_setup = SimpleNamespace(units_label='PSI', pressure_reference=None)
    controller._config = {'test_parameters': {'equipment_id': 'STINGER_01'}}
    controller._db_connection_status = 'Connected'
    controller._db_last_write = '--'
    controller._db_queue = '0'
    controller._db_activity_status = None
    controller._db_activity_deadline = 0.0
    controller._last_db_status = 'Connected'
    controller._to_display_pressure = lambda _port_id, value, _units, _ref: value
    return controller


def test_format_progress_display_caps_percent_for_overrun() -> None:
    progress_text, percent_text, progress_max, progress_value, tooltip = (
        MainWindow._format_progress_display(16, 1)
    )

    assert progress_text == '16 / 1 (+15)'
    assert percent_text == '100%'
    assert progress_max == 1
    assert progress_value == 1
    assert 'exceed the work order quantity by 15' in tooltip


def test_normalize_progress_counts_uses_completed_when_total_missing() -> None:
    completed, total = WorkOrderController._normalize_progress_counts(
        0,
        5,
        context='test progress',
    )

    assert completed == 5
    assert total == 5


def test_save_result_reports_saved_status(monkeypatch) -> None:
    controller = _make_save_controller()
    monkeypatch.setattr(work_order_controller, 'save_test_result', lambda **_kwargs: True)

    result = controller._save_result('port_a', force_pass=True)

    assert result == 'saved'
    assert controller._ui_bridge.status_updates[-1]['status'] == 'Saved'
    assert controller._ui_bridge.status_updates[-1]['last_write'] != '--'
    assert controller._ui_bridge.status_updates[-1]['queue'] == '0'


def test_save_result_reports_test_mode_skip(monkeypatch) -> None:
    controller = _make_save_controller(test_mode=True)

    def _unexpected_save(**_kwargs):
        raise AssertionError('save_test_result should not be called in test mode')

    monkeypatch.setattr(work_order_controller, 'save_test_result', _unexpected_save)

    result = controller._save_result('port_a', force_pass=False)

    assert result == 'skipped'
    assert controller._ui_bridge.status_updates[-1] == {
        'status': 'Test Mode',
        'last_write': 'Skipped',
        'queue': '0',
    }


def test_save_result_reports_failed_write(monkeypatch) -> None:
    controller = _make_save_controller()

    def _raise_runtime_error(**_kwargs):
        raise RuntimeError('Database not initialized')

    monkeypatch.setattr(work_order_controller, 'save_test_result', _raise_runtime_error)

    result = controller._save_result('port_a', force_pass=True)

    assert result == 'failed'
    assert controller._ui_bridge.status_updates[-1]['status'] == 'Write Failed'
    assert controller._ui_bridge.status_updates[-1]['queue'] == '1'


def test_save_test_result_returns_false_for_unexpected_error(monkeypatch) -> None:
    @contextmanager
    def _broken_scope():
        raise RuntimeError('Database not initialized')
        yield

    monkeypatch.setattr(operations, 'session_scope', _broken_scope)

    result = operations.save_test_result(
        shop_order='WO-1',
        part_id='PART-1',
        sequence_id='1',
        serial_number=1,
        increasing_activation=12.3,
        decreasing_deactivation=9.8,
        in_spec=True,
        temperature_c=25.0,
        units_of_measure='PSI',
        operator_id='OP-1',
        equipment_id='STINGER_01',
    )

    assert result is False


def test_save_test_result_rejects_overlength_fixed_width_fields(caplog) -> None:
    result = operations.save_test_result(
        shop_order='SHOPORDER123',
        part_id='PART-1',
        sequence_id='1',
        serial_number=1,
        increasing_activation=12.3,
        decreasing_deactivation=9.8,
        in_spec=True,
        temperature_c=25.0,
        units_of_measure='PSI',
        operator_id='TOO-LONG',
        equipment_id='STINGER_01',
    )

    assert result is False
    assert 'exceeds max length' in caplog.text
