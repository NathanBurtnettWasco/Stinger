"""Minimal Mensor serial reader for the quality calibration workflow."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import serial

    SERIAL_AVAILABLE = True
except ImportError:  # pragma: no cover - hardware dependency
    serial = None
    SERIAL_AVAILABLE = False


@dataclass(slots=True)
class MensorReading:
    pressure_psia: float
    timestamp: float


class MensorReader:
    """Simple serial client for a Mensor pressure reference."""

    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._port = str(config.get("port", "COM10"))
        self._baudrate = int(config.get("baudrate", 57600))
        self._timeout_s = float(config.get("timeout_s", 1.0))
        self._serial = None
        self._last_status = "Not Connected"

    @property
    def status(self) -> str:
        return self._last_status

    def connect(self) -> bool:
        if not SERIAL_AVAILABLE:
            self._last_status = "Connected (simulated)"
            return True

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=8,
                parity=serial.PARITY_NONE,
                stopbits=1,
                timeout=self._timeout_s,
            )
            time.sleep(0.3)
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            for command in ("MODE MEASURE",):
                self._send(command)
            self._last_status = "Connected"
            return True
        except Exception as exc:  # pragma: no cover - hardware dependency
            self._last_status = f"Error: {exc}"
            logger.error("Failed to connect Mensor: %s", exc)
            self.close()
            return False

    def close(self) -> None:
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass
        self._serial = None
        if self._last_status != "Connected (simulated)":
            self._last_status = "Disconnected"

    def read_pressure(self) -> MensorReading:
        if not SERIAL_AVAILABLE:
            return MensorReading(pressure_psia=14.7, timestamp=time.time())

        response = self._send("?")
        pressure = self._parse_pressure(response)
        if pressure is None:
            raise RuntimeError("Mensor read_pressure failed")
        return MensorReading(pressure_psia=pressure, timestamp=time.time())

    def _send(self, command: str) -> Optional[str]:
        if self._serial is None:
            return None
        try:
            self._serial.reset_input_buffer()
            self._serial.write(f"{command}\r".encode())
            self._serial.flush()
            time.sleep(0.05)
            response = self._serial.read_all().decode(errors="ignore").strip()
            return response or None
        except Exception as exc:  # pragma: no cover - hardware dependency
            logger.error("Mensor communication error: %s", exc)
            return None

    @staticmethod
    def _parse_pressure(response: Optional[str]) -> Optional[float]:
        if not response:
            return None
        first_field = response.split(",")[0].strip()
        try:
            value = float(first_field)
        except ValueError:
            match = re.search(r"[+-]?\d*\.?\d+(?:[Ee][+-]?\d+)?", first_field)
            if not match:
                return None
            value = float(match.group())

        # Functional Stand heuristics preserved here:
        # large values sometimes arrive in Pa or mbar before units settle.
        if value > 100.0:
            return value * 0.0001450377
        if value > 10.0:
            return value * 0.01450377
        return value

    @staticmethod
    def list_available_ports() -> list[str]:
        if not SERIAL_AVAILABLE or serial is None:
            return []
        tools_module = getattr(serial, "tools", None)
        if tools_module is None:
            return []
        list_ports_module = getattr(tools_module, "list_ports", None)
        if list_ports_module is None:
            return []
        try:
            return [port.device for port in list_ports_module.comports()]
        except Exception as exc:  # pragma: no cover - hardware dependency
            logger.error("Failed to enumerate Mensor serial ports: %s", exc)
            return []
