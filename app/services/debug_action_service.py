"""Debug action dispatch extracted from WorkOrderController."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from app.hardware.port import PortManager
from app.services.ptp_service import convert_pressure

logger = logging.getLogger(__name__)


class DebugActionService:
    """Handle debug actions with controller-provided callbacks."""

    def __init__(
        self,
        *,
        port_manager: PortManager,
        get_pressure_unit: Callable[[], str],
        set_debug_alicat_mode: Callable[[str, str], None],
        set_debug_solenoid_mode: Callable[[str, str], None],
        convert_display_to_absolute_psi: Callable[[str, float, str], float],
        resolve_command_reference: Callable[[str], tuple[float, str]],
        on_find_setpoint: Callable[[str, Dict[str, Any]], None],
        on_set_dio_direction: Callable[[str, Dict[str, Any]], None],
        on_read_dio_all: Callable[[str], None],
    ) -> None:
        self._port_manager = port_manager
        self._get_pressure_unit = get_pressure_unit
        self._set_debug_alicat_mode = set_debug_alicat_mode
        self._set_debug_solenoid_mode = set_debug_solenoid_mode
        self._convert_display_to_absolute_psi = convert_display_to_absolute_psi
        self._resolve_command_reference = resolve_command_reference
        self._on_find_setpoint = on_find_setpoint
        self._on_set_dio_direction = on_set_dio_direction
        self._on_read_dio_all = on_read_dio_all

    def handle(self, port_id: str, action: str, payload: Dict[str, Any]) -> None:
        port = self._port_manager.get_port(port_id)
        if not port:
            logger.warning('Port %s not found for debug action: %s', port_id, action)
            return

        if action == 'set_mode':
            mode = str(payload.get('mode', 'pressurize'))
            self._set_debug_alicat_mode(port_id, mode)
            if mode == 'pressurize':
                port.alicat.cancel_hold()
            elif mode == 'hold':
                port.alicat.hold_valve()
            elif mode == 'vent':
                self._set_debug_solenoid_mode(port_id, 'atmosphere')
                port.vent_to_atmosphere()
            return

        if action == 'set_solenoid_mode':
            mode = str(payload.get('mode', 'atmosphere'))
            self._set_debug_solenoid_mode(port_id, mode)
            return

        if action == 'set_solenoid':
            to_vacuum = bool(payload.get('to_vacuum', False))
            self._set_debug_solenoid_mode(port_id, 'vacuum' if to_vacuum else 'atmosphere')
            return

        if action == 'set_setpoint':
            value = float(payload.get('value', 0.0))
            units_label = self._get_pressure_unit()
            value_psi = convert_pressure(value, units_label, 'PSI')
            value_abs_psi = self._convert_display_to_absolute_psi(port_id, value_psi, units_label)
            barometric_psi, alicat_reference = self._resolve_command_reference(port_id)
            command_value = value_abs_psi - barometric_psi if alicat_reference == 'gauge' else value_abs_psi
            port.set_pressure(command_value)
            logger.info(
                '%s: Setpoint %.3f %s (command_ref=%s, command=%.3f)',
                port_id,
                value,
                units_label,
                alicat_reference,
                command_value,
            )
            return

        if action == 'set_ramp_rate':
            value = float(payload.get('value', 0.0))
            units_label = self._get_pressure_unit()
            value_psi = convert_pressure(value, units_label, 'PSI')
            port.alicat.set_ramp_rate(value_psi)
            logger.info('%s: Ramp rate %.3f %s/s (%.3f PSI/s)', port_id, value, units_label, value_psi)
            return

        if action == 'find_setpoint':
            self._on_find_setpoint(port_id, payload)
            return

        if action == 'set_dio_direction':
            self._on_set_dio_direction(port_id, payload)
            return

        if action == 'read_dio_all':
            self._on_read_dio_all(port_id)
            return

        logger.warning('Unknown debug action: %s', action)
