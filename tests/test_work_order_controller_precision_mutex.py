"""Unit tests for precision mutex coordination in WorkOrderController."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.work_order_controller import WorkOrderController


@dataclass
class _FakePortManager:
    profiles: list[Any] = field(default_factory=list)

    def set_alicat_poll_profile(self, precision_port: Any) -> None:
        self.profiles.append(precision_port)


@dataclass
class _FakeUiBridge:
    updates: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)

    def update_substate(self, port_id: str, substate: str, data: dict[str, Any]) -> None:
        self.updates.append((port_id, substate, data))


class _FakeStateMachine:
    def __init__(self, can_cycles_complete: bool = True) -> None:
        self.current_state = 'cycling'
        self._can_cycles_complete = can_cycles_complete
        self.triggers: list[str] = []

    def can_trigger(self, event_name: str) -> bool:
        if event_name == 'cycles_complete':
            return self._can_cycles_complete
        return False

    def trigger(self, event_name: str) -> bool:
        self.triggers.append(event_name)
        if event_name == 'cycles_complete':
            self.current_state = 'precision_test'
        return True


def _make_controller() -> WorkOrderController:
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._precision_owner_port = None
    controller._precision_wait_queue = []
    controller._port_manager = _FakePortManager()
    controller._ui_bridge = _FakeUiBridge()
    controller._state_machines = {
        'port_a': _FakeStateMachine(can_cycles_complete=True),
        'port_b': _FakeStateMachine(can_cycles_complete=True),
    }
    return controller


def test_cycles_complete_grants_owner_and_blocks_second_port() -> None:
    controller = _make_controller()

    controller._slot_cycles_complete('port_a')
    assert controller._precision_owner_port == 'port_a'
    assert controller._precision_wait_queue == []
    sm_a = controller._state_machines['port_a']
    assert sm_a.triggers == ['cycles_complete']

    controller._slot_cycles_complete('port_b')
    assert controller._precision_owner_port == 'port_a'
    assert controller._precision_wait_queue == ['port_b']
    sm_b = controller._state_machines['port_b']
    assert sm_b.triggers == []
    assert ('port_b', 'cycling.waiting_precision_slot', {}) in controller._ui_bridge.updates


def test_release_promotes_waiting_port_fifo() -> None:
    controller = _make_controller()

    controller._slot_cycles_complete('port_a')
    controller._slot_cycles_complete('port_b')

    # Release owner and ensure waiting port is promoted.
    controller._release_precision_slot('port_a', reason='completed')
    assert controller._precision_owner_port == 'port_b'
    assert controller._precision_wait_queue == []
    sm_b = controller._state_machines['port_b']
    assert sm_b.triggers == ['cycles_complete']

    # Profile calls: owner->normal->next owner
    assert controller._port_manager.profiles[0] == 'port_a'
    assert None in controller._port_manager.profiles
    assert controller._port_manager.profiles[-1] == 'port_b'

