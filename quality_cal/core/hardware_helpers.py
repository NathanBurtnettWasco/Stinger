"""Shared hardware helpers for quality calibration runners."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from app.hardware.port import Port, PortReading

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StabilizedReading:
    elapsed_s: float
    alicat_psia: Optional[float]
    transducer_psia: Optional[float]
    barometric_psia: float


def infer_barometric_psia(reading: Optional[PortReading]) -> float:
    if reading is None or reading.alicat is None:
        return 14.7
    if reading.alicat.barometric_pressure is not None:
        return float(reading.alicat.barometric_pressure)
    if reading.alicat.pressure is not None and reading.alicat.gauge_pressure is not None:
        return float(reading.alicat.pressure - reading.alicat.gauge_pressure)
    return 14.7


def alicat_abs_psia(reading: Optional[PortReading], fallback_barometric_psia: float = 14.7) -> Optional[float]:
    if reading is None or reading.alicat is None:
        return None
    if reading.alicat.pressure is not None:
        return float(reading.alicat.pressure)
    if reading.alicat.gauge_pressure is not None:
        return float(reading.alicat.gauge_pressure + fallback_barometric_psia)
    return None


def transducer_abs_psia(
    reading: Optional[PortReading], fallback_barometric_psia: float = 14.7
) -> Optional[float]:
    if reading is None or reading.transducer is None:
        return None
    value = float(reading.transducer.pressure)
    reference = str(reading.transducer.pressure_reference or "absolute").strip().lower()
    if reference == "gauge":
        return value + fallback_barometric_psia
    return value


def prepare_port_for_target(
    port: Port,
    target_psia: float,
    fallback_barometric_psia: float,
    cancel_event: threading.Event,
) -> tuple[bool, str, float]:
    """Select the route safely before commanding the next target."""
    if cancel_event.is_set():
        return False, "cancelled", fallback_barometric_psia

    latest = port.read_all()
    barometric_psia = infer_barometric_psia(latest) or fallback_barometric_psia
    use_vacuum = target_psia < (barometric_psia - 0.3)
    if not use_vacuum:
        ok = port.set_solenoid(to_vacuum=False)
        return ok, "pressure", barometric_psia

    current_alicat = alicat_abs_psia(latest, barometric_psia)
    if current_alicat is not None and current_alicat > barometric_psia + 2.0:
        port.vent_to_atmosphere()
        wait_until_near_target(
            port=port,
            target_psia=barometric_psia,
            tolerance_psia=1.0,
            hold_s=1.0,
            timeout_s=45.0,
            sample_hz=4.0,
            cancel_event=cancel_event,
            progress_callback=None,
        )
    ok = port.set_solenoid(to_vacuum=True)
    return ok, "vacuum", barometric_psia


def command_target_pressure(port: Port, target_psia: float, ramp_rate_psi_per_s: float) -> None:
    port.alicat.configure_units_from_ptp("1")
    if ramp_rate_psi_per_s > 0:
        port.alicat.set_ramp_rate(ramp_rate_psi_per_s)
    port.alicat.cancel_hold()
    if not port.set_pressure(target_psia):
        raise RuntimeError(f"Failed to command target pressure {target_psia:.3f} psia")


def wait_until_near_target(
    *,
    port: Port,
    target_psia: float,
    tolerance_psia: float,
    hold_s: float,
    timeout_s: float,
    sample_hz: float,
    cancel_event: threading.Event,
    progress_callback: Optional[Callable[[str], None]],
) -> StabilizedReading:
    start = time.perf_counter()
    near_since: Optional[float] = None
    sample_period_s = max(0.05, 1.0 / max(sample_hz, 0.1))
    last_alicat: Optional[float] = None
    last_transducer: Optional[float] = None
    barometric_psia = 14.7

    while time.perf_counter() - start <= timeout_s:
        if cancel_event.is_set():
            raise RuntimeError("Cancelled")

        reading = port.read_all()
        barometric_psia = infer_barometric_psia(reading)
        last_alicat = alicat_abs_psia(reading, barometric_psia)
        last_transducer = transducer_abs_psia(reading, barometric_psia)

        if last_alicat is not None:
            error = abs(last_alicat - target_psia)
            if progress_callback is not None:
                progress_callback(
                    f"Settling at {target_psia:.1f} psia (Alicat {last_alicat:.3f} psia)"
                )
            if error <= tolerance_psia:
                now = time.perf_counter()
                if near_since is None:
                    near_since = now
                elif now - near_since >= hold_s:
                    return StabilizedReading(
                        elapsed_s=now - start,
                        alicat_psia=last_alicat,
                        transducer_psia=last_transducer,
                        barometric_psia=barometric_psia,
                    )
            else:
                near_since = None

        time.sleep(sample_period_s)

    raise TimeoutError(
        f"Timed out waiting for {target_psia:.3f} psia (last Alicat={last_alicat})"
    )


def safe_shutdown_port(port: Port) -> None:
    try:
        port.vent_to_atmosphere()
    except Exception as exc:
        logger.warning("Failed to vent port safely: %s", exc)
