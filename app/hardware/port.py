"""
Port abstraction - combines LabJack + Alicat for a single test port.

Each port (A/B, Left/Right) is an independent test station with its own
hardware and state machine.
"""

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Callable

from .labjack import LabJackController, TransducerReading, SwitchState
from .alicat import AlicatController, AlicatReading

logger = logging.getLogger(__name__)


class PortId(Enum):
    """Identifier for test ports."""
    PORT_A = "port_a"  # Left
    PORT_B = "port_b"  # Right


@dataclass
class PortReading:
    """Combined reading from all port hardware."""
    transducer: Optional[TransducerReading] = None
    switch: Optional[SwitchState] = None
    alicat: Optional[AlicatReading] = None
    dio: Optional[Dict[int, int]] = None
    timestamp: float = 0.0


@dataclass
class EdgeEvent:
    """Record of a switch edge detection."""
    pressure: float
    timestamp: float
    direction: str  # 'increasing' or 'decreasing'
    activated: bool  # True if switch became activated
    

# Nominal atmosphere for absolute-pressure safety check (PSI)
_ATMOSPHERE_PSI = 14.7


class Port:
    """Single test port with LabJack + Alicat hardware."""
    
    def __init__(
        self,
        port_id: PortId,
        labjack_config: Dict[str, Any],
        alicat_config: Dict[str, Any],
        solenoid_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a test port."""
        self.port_id = port_id
        self._solenoid_config = solenoid_config or {}
        self._use_ptp_terminals = bool(labjack_config.get('use_ptp_terminals', False))

        # Initialize hardware controllers
        self.daq = LabJackController(labjack_config)
        self.alicat = AlicatController(alicat_config)
        
        # Edge detection state
        self._last_switch_state: Optional[SwitchState] = None
        self._edge_history: List[EdgeEvent] = []
        self._edge_callbacks: List[Callable[[EdgeEvent], None]] = []

        # Cached Alicat reading for fast polling (updated every Nth cycle)
        self._cached_alicat: Optional[AlicatReading] = None
        
        # Current test context
        self._no_pin: Optional[int] = None
        self._nc_pin: Optional[int] = None
        
        logger.info(f"Port {port_id.value} initialized")
    
    def configure_from_ptp(self, ptp_params: Dict[str, str]) -> bool:
        """Configure port hardware from PTP parameters."""
        try:
            if not self._use_ptp_terminals:
                logger.info(
                    'Port %s: Using configured NO/NC pins (PTP terminal override disabled)',
                    self.port_id.value,
                )
            else:
                # Extract terminal pin assignments
                no_terminal = ptp_params.get('NormallyOpenTerminal')
                nc_terminal = ptp_params.get('NormallyClosedTerminal')
                com_terminal = ptp_params.get('CommonTerminal')

                if no_terminal and nc_terminal:
                    no_pin = self._map_db9_pin_to_dio(int(float(no_terminal)))
                    nc_pin = self._map_db9_pin_to_dio(int(float(nc_terminal)))
                    com_pin = None
                    if com_terminal:
                        com_pin = self._map_db9_pin_to_dio(int(float(com_terminal)))

                    if no_pin is not None and nc_pin is not None:
                        self._no_pin = no_pin
                        self._nc_pin = nc_pin
                        self.daq.configure_di_pins(
                            no_pin,
                            nc_pin,
                            com_pin,
                            com_state=self.daq.switch_com_state,
                        )
                    else:
                        logger.warning(
                            'Port %s: Invalid switch terminal pins (NO=%s, NC=%s)',
                            self.port_id.value,
                            no_terminal,
                            nc_terminal,
                        )
                else:
                    logger.warning('Port %s: Missing terminal pin assignments in PTP', self.port_id.value)
            
            pressure_reference = ptp_params.get('PressureReference')
            if pressure_reference:
                self.daq.set_pressure_reference(pressure_reference)
            logger.info(f"Port {self.port_id.value}: Configured from PTP")
            return True
            
        except Exception as e:
            logger.error(f"Port {self.port_id.value}: PTP configuration error: {e}")
            return False

    def _map_db9_pin_to_dio(self, pin: int) -> Optional[int]:
        if pin < 1 or pin > 9:
            return None
        if self.port_id == PortId.PORT_A:
            return pin - 1
        return pin + 8
    
    def connect(self) -> bool:
        """
        Connect to all hardware for this port.
        
        Returns:
            True if all connections successful.
        """
        success = True
        
        # Configure LabJack
        if not self.daq.configure():
            logger.error(f"Port {self.port_id.value}: LabJack configuration failed")
            success = False
        
        # Connect to Alicat
        if not self.alicat.connect():
            logger.error(f"Port {self.port_id.value}: Alicat connection failed")
            success = False
        
        if success:
            logger.info(f"Port {self.port_id.value}: All hardware connected")
        
        return success
    
    def read_all(self) -> PortReading:
        """Read all sensors for this port."""
        import time
        timestamp = time.time()
        
        reading = PortReading(
            transducer=self.daq.read_transducer(),
            switch=self.daq.read_switch_state(),
            alicat=self.alicat.read_status(),
            dio=self.daq.read_dio_values(max_dio=22),
            timestamp=timestamp
        )

        # Convert transducer absolute -> gauge if configured
        if reading.transducer and reading.alicat:
            if getattr(self.daq, "pressure_reference", "absolute") == "gauge":
                baro = reading.alicat.barometric_pressure
                if baro is not None:
                    reading.transducer.pressure = reading.transducer.pressure - baro
                    reading.transducer.pressure_reference = "gauge"
        
        # Check for edge events
        self._check_for_edge(reading)
        
        return reading
    
    def refresh_alicat(self) -> None:
        """Update the cached Alicat reading (slow serial I/O)."""
        self._cached_alicat = self.alicat.read_status()

    def read_fast(self) -> PortReading:
        """Read LabJack-only sensors (fast path) using cached Alicat.

        Reads transducer, switch state, and DIO from the LabJack but uses
        the most recently cached Alicat reading instead of blocking on serial.
        """
        import time
        timestamp = time.time()

        reading = PortReading(
            transducer=self.daq.read_transducer(),
            switch=self.daq.read_switch_state(),
            alicat=self._cached_alicat,
            dio=self.daq.read_dio_values(max_dio=22),
            timestamp=timestamp,
        )

        # Convert transducer absolute -> gauge if configured
        if reading.transducer and reading.alicat:
            if getattr(self.daq, 'pressure_reference', 'absolute') == 'gauge':
                baro = reading.alicat.barometric_pressure
                if baro is not None:
                    reading.transducer.pressure = reading.transducer.pressure - baro
                    reading.transducer.pressure_reference = 'gauge'

        # Check for edge events
        self._check_for_edge(reading)

        return reading

    def _check_for_edge(self, reading: PortReading) -> None:
        """Check if a switch edge occurred and record it."""
        if reading.switch is None:
            return
        
        current = reading.switch
        previous = self._last_switch_state
        
        if previous is not None and current.switch_activated != previous.switch_activated:
            # Edge detected!
            pressure = reading.transducer.pressure if reading.transducer else 0.0
            
            # Determine direction based on pressure change
            # (Would need to track pressure history for accurate direction)
            direction = "unknown"  # Will be set by state machine based on control direction
            
            edge = EdgeEvent(
                pressure=pressure,
                timestamp=current.timestamp,
                direction=direction,
                activated=current.switch_activated
            )
            
            self._edge_history.append(edge)
            logger.info(f"Port {self.port_id.value}: Edge detected at {pressure:.2f} PSI, "
                       f"activated={current.switch_activated}")
            
            # Notify callbacks
            for callback in self._edge_callbacks:
                try:
                    callback(edge)
                except Exception as e:
                    logger.error(f"Edge callback error: {e}")
        
        self._last_switch_state = current
    
    def register_edge_callback(self, callback: Callable[[EdgeEvent], None]) -> None:
        """Register a callback to be called when an edge is detected."""
        self._edge_callbacks.append(callback)
    
    def clear_edge_history(self) -> None:
        """Clear the edge detection history."""
        self._edge_history.clear()
        self._last_switch_state = None
    
    def get_edge_history(self) -> List[EdgeEvent]:
        """Get the list of detected edges."""
        return self._edge_history.copy()
    
    def set_pressure(self, setpoint: float) -> bool:
        """Set the Alicat pressure setpoint."""
        return self.alicat.set_pressure(setpoint)
    
    def set_ramp_rate(self, rate: float) -> bool:
        """Set the Alicat ramp rate."""
        return self.alicat.set_ramp_rate(rate)
    
    def set_solenoid(self, to_vacuum: bool) -> bool:
        """Set the solenoid state.

        Pump protection: do not switch to vacuum unless port pressure is at or
        below the safe threshold (~atmosphere). Switching with high positive
        pressure can damage the pump.
        """
        if to_vacuum:
            threshold_psi = self._solenoid_config.get(
                "safe_vacuum_switch_threshold_psi", 2.0
            )
            if threshold_psi is not None:
                reading = self.daq.read_transducer()
                if reading is None:
                    logger.warning(
                        "%s: Refusing vacuum - no transducer reading (pump protection)",
                        self.port_id.value,
                    )
                    return False
                ref = (reading.pressure_reference or "gauge").lower()
                if ref == "gauge":
                    safe = reading.pressure <= threshold_psi
                else:
                    safe = reading.pressure <= _ATMOSPHERE_PSI + threshold_psi
                if not safe:
                    logger.warning(
                        "%s: Refusing vacuum - port pressure %.2f exceeds safe threshold %.2f psi (pump protection)",
                        self.port_id.value,
                        reading.pressure,
                        threshold_psi,
                    )
                    return False
        result = self.daq.set_solenoid(to_vacuum)
        if result:
            # Reset EMA filter so it re-seeds from the next sample after the
            # pressure discontinuity caused by the solenoid switch.
            self.daq.reset_filter()
        return result

    def vent_to_atmosphere(self) -> bool:
        """Vent the port to atmosphere (safe state)."""
        # Set solenoid to atmosphere
        self.daq.set_solenoid_safe()
        # Reset filter after solenoid change
        self.daq.reset_filter()
        # Command Alicat to exhaust
        return self.alicat.exhaust()
    
    def disconnect(self) -> None:
        """Disconnect all hardware and set to safe state."""
        # Set to safe state first
        self.daq.set_solenoid_safe()
        try:
            self.alicat.hold_valve()
        except Exception:
            pass
        
        # Cleanup
        self.daq.cleanup()
        self.alicat.disconnect()
        
        logger.info(f"Port {self.port_id.value}: Disconnected")
    
    def get_status(self) -> Dict[str, Any]:
        """Get combined status of all hardware."""
        return {
            "port_id": self.port_id.value,
            "daq": self.daq.get_status(),
            "alicat": self.alicat.get_status(),
        }


class PortManager:
    """Manages test ports (A and B)."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize port manager."""
        self.config = config
        self.ports: Dict[PortId, Port] = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval_ms = config.get('timing', {}).get('hardware_poll_interval_ms', 10)
        self._alicat_poll_divisor = max(1, int(
            config.get('timing', {}).get('alicat_poll_divisor', 10)
        ))
        self._poll_callback: Optional[Callable[[Dict[PortId, PortReading]], None]] = None

        logger.info("PortManager initialized")
    
    def initialize_ports(self) -> bool:
        """Initialize all configured ports."""
        labjack_config = self.config.get('hardware', {}).get('labjack', {})
        alicat_config = self.config.get('hardware', {}).get('alicat', {})

        success = True

        def build_labjack_config(port_key: str) -> Dict[str, Any]:
            # Start with all top-level (non-port) keys from hardware.labjack
            base = {
                key: value
                for key, value in labjack_config.items()
                if key not in {'port_a', 'port_b'}
            }
            # Overlay port-specific keys
            return {**base, **labjack_config.get(port_key, {})}

        def build_alicat_config(port_key: str) -> Dict[str, Any]:
            port_config = alicat_config.get(port_key, {})
            base_config = {
                key: value
                for key, value in alicat_config.items()
                if key not in {'port_a', 'port_b'}
            }
            return {**base_config, **port_config}

        solenoid_config = self.config.get("hardware", {}).get("solenoid", {})

        # Initialize Port A
        if 'port_a' in labjack_config:
            port_a = Port(
                port_id=PortId.PORT_A,
                labjack_config=build_labjack_config('port_a'),
                alicat_config=build_alicat_config('port_a'),
                solenoid_config=solenoid_config,
            )
            self.ports[PortId.PORT_A] = port_a

        # Initialize Port B
        if 'port_b' in labjack_config:
            port_b = Port(
                port_id=PortId.PORT_B,
                labjack_config=build_labjack_config('port_b'),
                alicat_config=build_alicat_config('port_b'),
                solenoid_config=solenoid_config,
            )
            self.ports[PortId.PORT_B] = port_b
        
        logger.info(f"PortManager: {len(self.ports)} ports initialized")
        return success
    
    def connect_all(self) -> bool:
        """Connect to hardware for all ports."""
        import time

        success = True
        overall_start = time.perf_counter()
        for port_id, port in self.ports.items():
            port_start = time.perf_counter()
            if not port.connect():
                logger.error(f"PortManager: Failed to connect {port_id.value}")
                success = False
            logger.info(
                "PortManager: %s connect completed in %.3fs",
                port_id.value,
                time.perf_counter() - port_start,
            )

        logger.info(
            'PortManager: connect_all finished in %.3fs (success=%s)',
            time.perf_counter() - overall_start,
            success,
        )
        
        return success
    
    def get_port(self, port_id: PortId | str) -> Optional[Port]:
        """Get a specific port by ID."""
        if isinstance(port_id, str):
            try:
                port_id = PortId(port_id)
            except ValueError:
                return None
        return self.ports.get(port_id)
    
    def read_all_ports(self) -> Dict[PortId, PortReading]:
        """Read all sensors from all ports."""
        readings = {}
        for port_id, port in self.ports.items():
            readings[port_id] = port.read_all()
        return readings
    
    def disconnect_all(self) -> None:
        """Disconnect all ports and set to safe state."""
        for port_id, port in self.ports.items():
            port.disconnect()
        self.ports.clear()
        logger.info("PortManager: All ports disconnected")
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all ports."""
        return {
            port_id.value: port.get_status()
            for port_id, port in self.ports.items()
        }
    
    def set_poll_callback(self, callback: Callable[[Dict[PortId, PortReading]], None]) -> None:
        """Set callback function to be called with readings on each poll."""
        self._poll_callback = callback
    
    def start_polling(self) -> bool:
        """Start hardware polling loop in background thread."""
        if self._polling:
            logger.warning("PortManager: Polling already started")
            return False
        
        if not self.ports:
            logger.error("PortManager: No ports initialized, cannot start polling")
            return False
        
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info(f"PortManager: Started polling thread (interval={self._poll_interval_ms}ms)")
        return True
    
    def stop_polling(self) -> None:
        """Stop hardware polling loop."""
        if not self._polling:
            return
        
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None
        logger.info("PortManager: Stopped polling")
    
    def _poll_loop(self) -> None:
        """Background thread loop that polls hardware and calls callback.

        LabJack reads (transducer + switch + DIO) run every cycle.  Alicat
        serial reads are performed every Nth cycle (configured by
        ``alicat_poll_divisor``) to avoid blocking the fast loop.
        """
        import time
        interval_s = self._poll_interval_ms / 1000.0
        cycle = 0

        # Seed the Alicat cache on the first cycle so consumers always have data
        for port in self.ports.values():
            try:
                port.refresh_alicat()
            except Exception:
                pass

        while self._polling:
            start_time = time.perf_counter()

            try:
                # Refresh Alicat cache every Nth cycle
                if cycle % self._alicat_poll_divisor == 0:
                    for port in self.ports.values():
                        port.refresh_alicat()

                # Fast path: LabJack-only reads + cached Alicat
                readings: Dict[PortId, PortReading] = {}
                for port_id, port in self.ports.items():
                    readings[port_id] = port.read_fast()

                if self._poll_callback:
                    self._poll_callback(readings)
            except Exception as e:
                logger.error(f"PortManager: Polling error: {e}")

            cycle += 1

            # Calculate sleep time accounting for execution time to maintain consistent interval
            elapsed = time.perf_counter() - start_time
            sleep_time = max(0, interval_s - elapsed)

            if sleep_time > 0:
                time.sleep(sleep_time)
