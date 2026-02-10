"""
LabJack T-series controller (T7-Pro).

Handles:
- Analog input (ratiometric transducer)
- Digital input (switch NO/NC states)
- Digital output (solenoid control)
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ljm: Any = None
try:
    from labjack import ljm as _ljm
    ljm = _ljm
    LJM_AVAILABLE = True
except ImportError:
    logger.warning('labjack.ljm not available - LabJack hardware unavailable')
    LJM_AVAILABLE = False


@dataclass
class TransducerReading:
    """Result of a transducer reading."""

    voltage: float
    pressure: float
    pressure_raw: Optional[float]
    pressure_reference: str
    timestamp: float


@dataclass
class SwitchState:
    """State of the switch terminals."""

    no_active: bool  # Normally Open terminal is active (closed)
    nc_active: bool  # Normally Closed terminal is active (closed)
    timestamp: float

    @property
    def is_valid(self) -> bool:
        """Check if state is valid (not both active or both inactive for SPDT)."""
        return self.no_active != self.nc_active

    @property
    def switch_activated(self) -> bool:
        """Returns True if switch is in activated state (NO closed, NC open)."""
        return self.no_active and not self.nc_active


class LabJackController:
    """
    Controls a single LabJack device with per-port channel assignments.

    A single LabJack is shared across all ports; each controller instance
    references a shared LJM handle and uses its own channel mapping.
    """

    _handle_lock = threading.Lock()
    _shared_handle: Optional[int] = None
    _handle_ref_count = 0

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config

        self.device_type = config.get('device_type', 'T7')
        self.connection_type = config.get('connection_type', 'USB')
        self.identifier = config.get('identifier', 'ANY')

        self.transducer_ain = config.get('transducer_ain')
        self.transducer_ain_neg = config.get('transducer_ain_neg')  # Negative channel for differential
        self.voltage_min = config.get('transducer_voltage_min', 0.5)
        self.voltage_max = config.get('transducer_voltage_max', 4.5)
        self.pressure_min = config.get('transducer_pressure_min', 0.0)
        self.pressure_max = config.get('transducer_pressure_max', 115.0)
        self.pressure_reference = str(config.get('transducer_reference', 'absolute')).lower()
        self.pressure_offset = float(config.get('transducer_offset_psi', 0.0))

        self.switch_no_dio = config.get('switch_no_dio')
        self.switch_nc_dio = config.get('switch_nc_dio')
        self.switch_com_dio = config.get('switch_com_dio')
        self.switch_com_state = int(config.get('switch_com_state', 1))
        self.switch_active_low = bool(config.get('switch_active_low', False))
        self.solenoid_dio = config.get('solenoid_dio')

        self._lock = threading.RLock()
        self._is_configured = False
        self._last_status = 'Not Initialized'
        self._io_retries = max(0, int(config.get('io_retries', 2)))
        self._io_retry_delay_s = max(0.0, float(config.get('io_retry_delay_s', 0.02)))

        # Resolution index: 0=device default, 1-8=16-bit ADC, 9-12=24-bit ADC (T7-Pro)
        self._resolution_index = int(config.get('resolution_index', 0))

        # EMA pressure filter: alpha in (0, 1]. 0 disables filtering, 1 = no smoothing.
        self._filter_alpha = float(config.get('pressure_filter_alpha', 0.4))
        self._ema_pressure: Optional[float] = None

        self._sim_pressure = 14.7
        self._sim_switch_activated = False

        logger.info(
            'LabJackController initialized for %s/%s',
            self.connection_type,
            self.identifier,
        )

    @classmethod
    def _open_handle(cls, device_type: str, connection_type: str, identifier: str) -> Optional[int]:
        if not LJM_AVAILABLE:
            return None

        with cls._handle_lock:
            if cls._shared_handle is None:
                cls._shared_handle = ljm.openS(device_type, connection_type, identifier)
                cls._handle_ref_count = 0
            cls._handle_ref_count += 1
            return cls._shared_handle

    @classmethod
    def _close_handle(cls) -> None:
        if not LJM_AVAILABLE:
            return

        with cls._handle_lock:
            if cls._handle_ref_count > 0:
                cls._handle_ref_count -= 1
            if cls._handle_ref_count == 0 and cls._shared_handle is not None:
                try:
                    ljm.close(cls._shared_handle)
                finally:
                    cls._shared_handle = None

    def configure_di_pins(
        self,
        no_pin: int,
        nc_pin: int,
        com_pin: Optional[int] = None,
        com_state: Optional[int] = None,
    ) -> None:
        """Configure digital input pins for NO/NC terminals."""
        self.switch_no_dio = no_pin
        self.switch_nc_dio = nc_pin
        if com_pin is not None:
            self.switch_com_dio = com_pin
        if com_state is not None:
            self.switch_com_state = 1 if int(com_state) else 0
        logger.info('LabJack: NO=DIO%s, NC=DIO%s', self.switch_no_dio, self.switch_nc_dio)
        self._apply_switch_directions()

    def set_dio_direction(self, dio: int, is_output: bool, output_state: Optional[int] = None) -> bool:
        """Configure a DIO line as input or output.

        On T-series, individual DIO read sets the line to input; write sets it to output
        and the state. There is no per-channel DIO{n}_DIRECTION register; direction is
        implied by read vs write.
        """
        if not LJM_AVAILABLE:
            return True

        handle = self._shared_handle
        if handle is None:
            return False

        try:
            if is_output:
                return self._write_name_with_retry(f'DIO{dio}', 1 if output_state else 0)
            else:
                return self._read_name_with_retry(f'DIO{dio}') is not None
        except Exception as exc:
            logger.error('LabJack DIO direction set failed: %s', exc)
            return False

    def read_dio_values(self, max_dio: int = 19) -> Optional[Dict[int, int]]:
        """Read all DIO values from 0..max_dio inclusive."""
        if not LJM_AVAILABLE:
            return {dio: 0 for dio in range(max_dio + 1)}

        handle = self._shared_handle
        if handle is None:
            return None

        try:
            state_value = self._read_name_with_retry('DIO_STATE')
            if state_value is None:
                return None
            state_mask = int(state_value)
            return {dio: 1 if state_mask & (1 << dio) else 0 for dio in range(max_dio + 1)}
        except Exception as exc:
            logger.error('LabJack DIO read failed: %s', exc)
            return None

    def set_pressure_reference(self, reference: str) -> None:
        """Set pressure reference (absolute or gauge)."""
        self.pressure_reference = str(reference or 'absolute').lower()

    def configure(self) -> bool:
        """Open the LabJack connection and set to safe state."""
        if not LJM_AVAILABLE:
            self._is_configured = True
            self._last_status = 'Configured (no hardware)'
            return True

        with self._lock:
            try:
                handle = self._open_handle(self.device_type, self.connection_type, self.identifier)
                if handle is None:
                    self._last_status = 'Config Error: LJM unavailable'
                    return False

                # Configure differential mode for transducer if negative channel is specified
                if self.transducer_ain is not None and self.transducer_ain_neg is not None:
                    # Set the negative channel for differential measurement
                    # AIN#_NEGATIVE_CH register: value = negative channel number, or 199 for single-ended (GND)
                    ljm.eWriteName(handle, f'AIN{self.transducer_ain}_NEGATIVE_CH', self.transducer_ain_neg)
                    logger.info(
                        'LabJack: Configured AIN%d as differential (negative=AIN%d)',
                        self.transducer_ain,
                        self.transducer_ain_neg,
                    )
                elif self.transducer_ain is not None:
                    # Single-ended mode (negative = GND)
                    ljm.eWriteName(handle, f'AIN{self.transducer_ain}_NEGATIVE_CH', 199)
                    logger.info('LabJack: Configured AIN%d as single-ended', self.transducer_ain)

                # Set AIN resolution index (0 = device default)
                if self._resolution_index > 0 and self.transducer_ain is not None:
                    ljm.eWriteName(
                        handle,
                        f'AIN{self.transducer_ain}_RESOLUTION_INDEX',
                        self._resolution_index,
                    )
                    logger.info(
                        'LabJack: Set AIN%d resolution index to %d',
                        self.transducer_ain,
                        self._resolution_index,
                    )

                if self.solenoid_dio is not None:
                    self.set_dio_direction(self.solenoid_dio, True, 0)

                self._apply_switch_directions()

                self._is_configured = True
                self._last_status = 'Configured'
                return True
            except Exception as exc:
                logger.error('LabJack configuration failed: %s', exc)
                self._last_status = f'Config Error: {exc}'
                self.cleanup()
                return False

    @staticmethod
    def _is_transient_ljm_error(exc: Exception) -> bool:
        message = str(exc)
        return 'LJME_RECONNECT_FAILED' in message or '1239' in message

    def _recover_handle(self) -> bool:
        if not LJM_AVAILABLE:
            return False

        with self._lock:
            try:
                self._close_handle()
                handle = self._open_handle(self.device_type, self.connection_type, self.identifier)
                if handle is None:
                    return False
                if self.transducer_ain is not None and self.transducer_ain_neg is not None:
                    ljm.eWriteName(handle, f'AIN{self.transducer_ain}_NEGATIVE_CH', self.transducer_ain_neg)
                elif self.transducer_ain is not None:
                    ljm.eWriteName(handle, f'AIN{self.transducer_ain}_NEGATIVE_CH', 199)
                if self._resolution_index > 0 and self.transducer_ain is not None:
                    ljm.eWriteName(
                        handle,
                        f'AIN{self.transducer_ain}_RESOLUTION_INDEX',
                        self._resolution_index,
                    )
                self._apply_switch_directions()
                return True
            except Exception as recovery_exc:
                logger.error('LabJack recovery failed: %s', recovery_exc)
                return False

    def _read_name_with_retry(self, name: str) -> Optional[float]:
        handle = self._shared_handle
        if handle is None:
            return None

        for attempt in range(self._io_retries + 1):
            try:
                return float(ljm.eReadName(handle, name))
            except Exception as exc:
                if attempt < self._io_retries and self._is_transient_ljm_error(exc):
                    logger.warning('LabJack transient read error (%s), retrying %s', exc, name)
                    if self._recover_handle():
                        handle = self._shared_handle
                    time.sleep(self._io_retry_delay_s)
                    continue
                raise
        return None

    def _read_names_with_retry(self, names: list[str]) -> Optional[list[float]]:
        handle = self._shared_handle
        if handle is None:
            return None

        for attempt in range(self._io_retries + 1):
            try:
                values = ljm.eReadNames(handle, len(names), names)
                return [float(v) for v in values]
            except Exception as exc:
                if attempt < self._io_retries and self._is_transient_ljm_error(exc):
                    logger.warning('LabJack transient read error (%s), retrying %s', exc, names)
                    if self._recover_handle():
                        handle = self._shared_handle
                    time.sleep(self._io_retry_delay_s)
                    continue
                raise
        return None

    def _write_name_with_retry(self, name: str, value: float) -> bool:
        handle = self._shared_handle
        if handle is None:
            return False

        for attempt in range(self._io_retries + 1):
            try:
                ljm.eWriteName(handle, name, value)
                return True
            except Exception as exc:
                if attempt < self._io_retries and self._is_transient_ljm_error(exc):
                    logger.warning('LabJack transient write error (%s), retrying %s', exc, name)
                    if self._recover_handle():
                        handle = self._shared_handle
                    time.sleep(self._io_retry_delay_s)
                    continue
                logger.error('LabJack write failed for %s: %s', name, exc)
                return False
        return False

    def _apply_ema(self, pressure: float) -> float:
        """Apply exponential moving average filter to pressure.

        Returns the filtered value.  When the filter is disabled
        (alpha <= 0 or alpha >= 1) or on the very first sample, the raw
        value is returned unchanged.
        """
        alpha = self._filter_alpha
        if alpha <= 0.0 or alpha >= 1.0:
            # Filtering disabled — pass through raw value
            self._ema_pressure = pressure
            return pressure
        if self._ema_pressure is None:
            # First sample — seed the filter
            self._ema_pressure = pressure
            return pressure
        self._ema_pressure = alpha * pressure + (1.0 - alpha) * self._ema_pressure
        return self._ema_pressure

    def read_transducer(self) -> Optional[TransducerReading]:
        """Read pressure from the ratiometric transducer.

        Returns a TransducerReading with EMA-filtered pressure in
        ``pressure`` and the unfiltered value in ``pressure_raw``.
        """
        timestamp = time.time()

        if not LJM_AVAILABLE:
            voltage_range = self.voltage_max - self.voltage_min
            pressure_range = self.pressure_max - self.pressure_min
            voltage = self.voltage_min + (
                (self._sim_pressure - self.pressure_min) / pressure_range * voltage_range
                if pressure_range > 0
                else 0.0
            )
            pressure_raw = self._sim_pressure + self.pressure_offset
            pressure_filtered = self._apply_ema(pressure_raw)
            return TransducerReading(
                voltage=voltage,
                pressure=pressure_filtered,
                pressure_raw=pressure_raw,
                pressure_reference=self.pressure_reference,
                timestamp=timestamp,
            )

        if self.transducer_ain is None:
            return None

        handle = self._shared_handle
        if handle is None:
            return None

        try:
            voltage = self._read_name_with_retry(f'AIN{self.transducer_ain}')
            if voltage is None:
                return None
            voltage_range = self.voltage_max - self.voltage_min
            pressure_range = self.pressure_max - self.pressure_min
            if voltage_range > 0:
                pressure = (voltage - self.voltage_min) / voltage_range * pressure_range + self.pressure_min
            else:
                pressure = self.pressure_min
            pressure_raw = pressure + self.pressure_offset
            pressure_filtered = self._apply_ema(pressure_raw)
            return TransducerReading(
                voltage=voltage,
                pressure=pressure_filtered,
                pressure_raw=pressure_raw,
                pressure_reference=self.pressure_reference,
                timestamp=timestamp,
            )
        except Exception as exc:
            logger.error('LabJack transducer read error: %s', exc)
            return None

    def read_switch_state(self) -> Optional[SwitchState]:
        """Read the current state of the switch terminals."""
        timestamp = time.time()

        if not LJM_AVAILABLE:
            return SwitchState(
                no_active=self._sim_switch_activated,
                nc_active=not self._sim_switch_activated,
                timestamp=timestamp,
            )

        if self.switch_no_dio is None or self.switch_nc_dio is None:
            return None

        handle = self._shared_handle
        if handle is None:
            return None

        try:
            names = [f'DIO{self.switch_no_dio}', f'DIO{self.switch_nc_dio}']
            states = self._read_names_with_retry(names)
            if isinstance(states, list) and len(states) >= 2:
                no_raw = bool(states[0])
                nc_raw = bool(states[1])
                if self.switch_active_low:
                    no_active = not no_raw
                    nc_active = not nc_raw
                else:
                    no_active = no_raw
                    nc_active = nc_raw
                return SwitchState(
                    no_active=no_active,
                    nc_active=nc_active,
                    timestamp=timestamp,
                )
            return None
        except Exception as exc:
            logger.error('LabJack switch read error: %s', exc)
            return None

    def set_solenoid(self, to_vacuum: bool) -> bool:
        """Set solenoid state."""
        if not LJM_AVAILABLE:
            logger.debug('LabJack solenoid -> %s', 'Vacuum' if to_vacuum else 'Atmosphere')
            return True

        if self.solenoid_dio is None:
            return False

        handle = self._shared_handle
        if handle is None:
            return False

        try:
            if not self._write_name_with_retry(f'DIO{self.solenoid_dio}', 1 if to_vacuum else 0):
                return False
            logger.debug('LabJack solenoid -> %s', 'Vacuum' if to_vacuum else 'Atmosphere')
            return True
        except Exception as exc:
            logger.error('LabJack solenoid control error: %s', exc)
            return False

    def set_solenoid_safe(self) -> bool:
        """Set solenoid to safe state (atmosphere)."""
        return self.set_solenoid(to_vacuum=False)

    def _apply_switch_directions(self) -> None:
        if not LJM_AVAILABLE:
            return
        if self.switch_no_dio is not None:
            self.set_dio_direction(self.switch_no_dio, False)
        if self.switch_nc_dio is not None:
            self.set_dio_direction(self.switch_nc_dio, False)
        if self.switch_com_dio is not None:
            self.set_dio_direction(self.switch_com_dio, True, self.switch_com_state)

    def reset_filter(self) -> None:
        """Reset the EMA pressure filter state.

        Call after large pressure discontinuities (e.g. solenoid switch) so
        the filter re-seeds from the next raw sample instead of slowly
        converging from the old value.
        """
        self._ema_pressure = None

    def sim_set_pressure(self, pressure: float) -> None:
        """Set simulated pressure (for testing)."""
        self._sim_pressure = pressure

    def sim_set_switch(self, activated: bool) -> None:
        """Set simulated switch state (for testing)."""
        self._sim_switch_activated = activated

    def cleanup(self) -> None:
        """Release LabJack resources."""
        with self._lock:
            if LJM_AVAILABLE:
                try:
                    if self.solenoid_dio is not None and self._shared_handle is not None:
                        ljm.eWriteName(self._shared_handle, f'DIO{self.solenoid_dio}', 0)
                except Exception:
                    pass
                self._close_handle()

            self._is_configured = False
            self._last_status = 'Closed'

        logger.info('LabJack resources cleaned up')

    def hardware_available(self) -> bool:
        """Return True if the LabJack library is available and hardware can be used."""
        return LJM_AVAILABLE

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the LabJack controller."""
        return {
            'device_type': self.device_type,
            'connection_type': self.connection_type,
            'identifier': self.identifier,
            'configured': self._is_configured,
            'status': self._last_status,
        }
