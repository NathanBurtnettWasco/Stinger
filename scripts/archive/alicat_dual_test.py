"""
Alicat Dual-Device Test Script (shared COM port).

Verifies read/write communication to two Alicat devices on the same COM port
using different addresses. Intended for diagnosing timeouts and command errors.

Usage (from repo root):
    python scripts/alicat_dual_test.py
    python scripts/alicat_dual_test.py --com-port COM9 --addr-a A --addr-b B
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController

logger = logging.getLogger(__name__)


def _build_controller(
    com_port: str,
    address: str,
    baudrate: int,
    timeout_s: float,
    pressure_index: Optional[int],
    setpoint_index: Optional[int],
    gauge_index: Optional[int],
    barometric_index: Optional[int],
) -> AlicatController:
    config = {
        'com_port': com_port,
        'address': address,
        'baudrate': baudrate,
        'timeout_s': timeout_s,
        'pressure_index': pressure_index,
        'setpoint_index': setpoint_index,
        'gauge_index': gauge_index,
        'barometric_index': barometric_index,
    }
    return AlicatController(config)


def _test_read_write(
    controller: AlicatController,
    setpoint_delta: float,
    settle_s: float,
) -> Tuple[bool, Optional[float]]:
    """Read status, set a new setpoint, verify, then return original setpoint."""
    reading = controller.read_status()
    if not reading:
        print(f"  [FAIL] {controller.address}: No status response")
        return False, None

    print(
        f"  [PASS] {controller.address}: Read status "
        f"(pressure={reading.pressure:.2f}, setpoint={reading.setpoint:.2f})"
    )
    if reading.raw_response:
        print(f"  [INFO] {controller.address}: Raw frame: {reading.raw_response}")

    target_setpoint = reading.setpoint + setpoint_delta
    if not controller.set_pressure(target_setpoint):
        print(f"  [FAIL] {controller.address}: Failed to set setpoint to {target_setpoint:.2f}")
        return False, reading.setpoint

    print(f"  [PASS] {controller.address}: Set setpoint to {target_setpoint:.2f}")
    time.sleep(settle_s)

    verify = controller.read_status()
    if not verify:
        print(f"  [FAIL] {controller.address}: No response when verifying setpoint")
        return False, reading.setpoint

    if abs(verify.setpoint - target_setpoint) <= 0.5:
        print(
            f"  [PASS] {controller.address}: Verified setpoint "
            f"(got={verify.setpoint:.2f}, requested={target_setpoint:.2f})"
        )
        return True, reading.setpoint

    print(
        f"  [WARN] {controller.address}: Setpoint mismatch "
        f"(got={verify.setpoint:.2f}, requested={target_setpoint:.2f})"
    )
    return True, reading.setpoint


def _send_raw(controller: AlicatController, command: str) -> Optional[str]:
    return controller._send_command(command)


def _query_setpoint_source(controller: AlicatController) -> Optional[str]:
    response = _send_raw(controller, "LSS")
    if response:
        print(f"  [INFO] {controller.address}: Setpoint source -> {response}")
    return response


def _query_setpoint(controller: AlicatController) -> Optional[str]:
    response = _send_raw(controller, "LS")
    if response:
        print(f"  [INFO] {controller.address}: Setpoint query -> {response}")
    return response


def _set_units(
    controller: AlicatController,
    statistic_value: int,
    group: int,
    unit_value: int,
    override: int,
) -> bool:
    command = f"DCU {statistic_value} {group} {unit_value} {override}"
    response = _send_raw(controller, command)
    if response and response.startswith(controller.address):
        print(
            f"  [PASS] {controller.address}: Set units -> "
            f"stat={statistic_value} group={group} unit={unit_value} override={override}"
        )
        return True
    print(
        f"  [FAIL] {controller.address}: Set units failed "
        f"(stat={statistic_value} group={group} unit={unit_value} override={override}) -> {response}"
    )
    return False


def _apply_setpoint(
    controller: AlicatController,
    target_setpoint: float,
    settle_s: float,
) -> bool:
    if not controller.set_pressure(target_setpoint):
        print(f"  [FAIL] {controller.address}: Failed to set setpoint to {target_setpoint:.2f}")
        return False

    print(f"  [PASS] {controller.address}: Set setpoint to {target_setpoint:.2f}")
    time.sleep(settle_s)
    _query_setpoint(controller)

    verify = controller.read_status()
    if not verify:
        print(f"  [FAIL] {controller.address}: No response when verifying setpoint")
        return False

    if abs(verify.setpoint - target_setpoint) <= 0.5:
        print(
            f"  [PASS] {controller.address}: Verified setpoint "
            f"(got={verify.setpoint:.2f}, requested={target_setpoint:.2f})"
        )
        return True

    print(
        f"  [WARN] {controller.address}: Setpoint mismatch "
        f"(got={verify.setpoint:.2f}, requested={target_setpoint:.2f})"
    )
    return True


def _test_command(controller: AlicatController, command: str, label: str) -> bool:
    response = _send_raw(controller, command)
    if response and response.startswith(controller.address):
        print(f"  [PASS] {controller.address}: {label} ({command}) -> {response}")
        return True
    print(f"  [FAIL] {controller.address}: {label} ({command}) -> {response}")
    return False


def _query_data_frame(controller: AlicatController) -> bool:
    response = _send_raw(controller, "??D*")
    if response and response.startswith(controller.address):
        print(f"  [PASS] {controller.address}: Data frame format -> {response}")
        return True
    print(f"  [FAIL] {controller.address}: Data frame format query failed -> {response}")
    return False


def _test_modes(controller: AlicatController) -> bool:
    ok = True
    ok &= _test_command(controller, "HP", "Hold valve at position")
    time.sleep(0.2)
    ok &= _test_command(controller, "HC", "Hold valve closed")
    time.sleep(0.2)
    ok &= _test_command(controller, "C", "Cancel hold")
    time.sleep(0.2)
    ok &= _test_command(controller, "E", "Exhaust")
    time.sleep(0.2)
    ok &= _test_command(controller, "C", "Cancel hold (post-exhaust)")
    return ok


def _measure_rate(controller: AlicatController, seconds: float) -> float:
    end_time = time.perf_counter() + seconds
    reads = 0
    errors = 0
    last_pressure: Optional[float] = None
    while time.perf_counter() < end_time:
        reading = controller.read_status()
        if reading is None:
            errors += 1
            continue
        last_pressure = reading.pressure
        reads += 1
    rate = reads / seconds if seconds > 0 else 0.0
    logger.info(
        'Alicat %s: last=%.3f reads=%s errors=%s rate=%.1f Hz',
        controller.address,
        last_pressure if last_pressure is not None else float('nan'),
        reads,
        errors,
        rate,
    )
    return rate


def _measure_interleaved(controller_a: AlicatController, controller_b: AlicatController, seconds: float) -> float:
    end_time = time.perf_counter() + seconds
    reads = 0
    errors = 0
    last_a: Optional[float] = None
    last_b: Optional[float] = None
    toggle = True
    while time.perf_counter() < end_time:
        if toggle:
            reading = controller_a.read_status()
            if reading is None:
                errors += 1
            else:
                last_a = reading.pressure
                reads += 1
        else:
            reading = controller_b.read_status()
            if reading is None:
                errors += 1
            else:
                last_b = reading.pressure
                reads += 1
        toggle = not toggle
    rate = reads / seconds if seconds > 0 else 0.0
    logger.info(
        'Alicat A/B interleaved: last_a=%.3f last_b=%.3f reads=%s errors=%s rate=%.1f Hz',
        last_a if last_a is not None else float('nan'),
        last_b if last_b is not None else float('nan'),
        reads,
        errors,
        rate,
    )
    return rate


def _load_alicat_config(
    config: Dict[str, Any],
) -> Tuple[str, str, str, int, float, Optional[int], Optional[int], Optional[int], Optional[int]]:
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_a_cfg = alicat_cfg.get('port_a', {})
    port_b_cfg = alicat_cfg.get('port_b', {})

    com_port = port_a_cfg.get('com_port') or port_b_cfg.get('com_port') or ''
    addr_a = port_a_cfg.get('address', 'A')
    addr_b = port_b_cfg.get('address', 'B')
    baudrate = int(alicat_cfg.get('baudrate', 19200))
    timeout_s = float(alicat_cfg.get('timeout_s', 0.05))
    pressure_index = alicat_cfg.get('pressure_index')
    setpoint_index = alicat_cfg.get('setpoint_index')
    gauge_index = alicat_cfg.get('gauge_index')
    barometric_index = alicat_cfg.get('barometric_index')

    return (
        com_port,
        addr_a,
        addr_b,
        baudrate,
        timeout_s,
        pressure_index,
        setpoint_index,
        gauge_index,
        barometric_index,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Test two Alicats on one COM port.")
    parser.add_argument('--com-port', default=None, help='COM port (e.g., COM9)')
    parser.add_argument('--addr-a', default=None, help='Address for device A (e.g., A)')
    parser.add_argument('--addr-b', default=None, help='Address for device B (e.g., B)')
    parser.add_argument('--baudrate', type=int, default=None, help='Baud rate (default from config)')
    parser.add_argument('--timeout', type=float, default=None, help='Timeout seconds (default from config)')
    parser.add_argument('--setpoint-delta', type=float, default=0.5, help='PSI change for test write')
    parser.add_argument('--setpoint-a', type=float, default=None, help='Setpoint for device A (overrides delta)')
    parser.add_argument('--setpoint-b', type=float, default=None, help='Setpoint for device B (overrides delta)')
    parser.add_argument('--settle-s', type=float, default=0.5, help='Seconds to wait after setpoint write')
    parser.add_argument('--skip-modes', action='store_true', help='Skip hold/exhaust mode tests')
    parser.add_argument('--set-psi', action='store_true', help='Set pressure units to PSI before testing')
    parser.add_argument('--units-stat', type=int, default=2, help='DCU statistic value (default: 2=abs pressure)')
    parser.add_argument('--units-group', type=int, default=0, help='DCU group (0=stat only, 1=group)')
    parser.add_argument('--units-value', type=int, default=10, help='DCU unit value (default: 10=PSI)')
    parser.add_argument('--units-override', type=int, default=0, help='DCU override (0=default)')
    parser.add_argument('--no-restore', action='store_true', help='Do not restore original setpoints')
    parser.add_argument('--poll-seconds', type=float, default=0.0, help='Measure status poll rate (seconds)')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1

    (
        cfg_com_port,
        cfg_addr_a,
        cfg_addr_b,
        cfg_baudrate,
        cfg_timeout,
        cfg_pressure_index,
        cfg_setpoint_index,
        cfg_gauge_index,
        cfg_barometric_index,
    ) = _load_alicat_config(config)
    com_port = args.com_port or cfg_com_port
    addr_a = (args.addr_a or cfg_addr_a or 'A').upper()
    addr_b = (args.addr_b or cfg_addr_b or 'B').upper()
    baudrate = args.baudrate or cfg_baudrate
    timeout_s = args.timeout or cfg_timeout

    if not com_port:
        print("[FAIL] COM port not configured. Use --com-port or update stinger_config.yaml")
        return 1

    if timeout_s < 0.1:
        print(f"[WARN] timeout_s={timeout_s:.3f}s is very low. If writes time out, try 0.2-0.5s.")

    print("Alicat Dual-Device Test")
    print(f"  COM port: {com_port}")
    print(f"  Addresses: {addr_a}, {addr_b}")
    print(f"  Baudrate: {baudrate}")
    print(f"  Timeout: {timeout_s:.3f}s\n")

    controller_a = _build_controller(
        com_port,
        addr_a,
        baudrate,
        timeout_s,
        cfg_pressure_index,
        cfg_setpoint_index,
        cfg_gauge_index,
        cfg_barometric_index,
    )
    controller_b = _build_controller(
        com_port,
        addr_b,
        baudrate,
        timeout_s,
        cfg_pressure_index,
        cfg_setpoint_index,
        cfg_gauge_index,
        cfg_barometric_index,
    )

    # Connect first controller (owns serial); share with second
    if not controller_a.connect():
        print(f"[FAIL] {addr_a}: Connection failed: {controller_a._last_status}")
        return 1

    if controller_a._serial is None:
        print(f"[FAIL] {addr_a}: Serial connection not available")
        return 1

    controller_b.set_shared_serial(controller_a._serial)

    results = []
    original_setpoints = {}
    try:
        if args.poll_seconds > 0:
            print(f"\nMeasuring poll rate for {args.poll_seconds:.1f}s...")
            _measure_rate(controller_a, args.poll_seconds)
            _measure_rate(controller_b, args.poll_seconds)
            _measure_interleaved(controller_a, controller_b, args.poll_seconds)
            return 0

        print(f"\nTesting address {addr_a}")
        _query_setpoint_source(controller_a)
        ok_frame_a = _query_data_frame(controller_a)
        ok_units_a = True
        if args.set_psi:
            ok_units_a = _set_units(
                controller_a,
                args.units_stat,
                args.units_group,
                args.units_value,
                args.units_override,
            )
        if args.setpoint_a is not None:
            current_a = controller_a.read_status()
            original_a = current_a.setpoint if current_a else None
            ok_a = _apply_setpoint(controller_a, args.setpoint_a, args.settle_s)
        else:
            ok_a, original_a = _test_read_write(controller_a, args.setpoint_delta, args.settle_s)
        ok_modes_a = True if args.skip_modes else _test_modes(controller_a)
        results.append(ok_frame_a and ok_units_a and ok_a and ok_modes_a)
        if original_a is not None:
            original_setpoints[controller_a.address] = original_a

        print(f"\nTesting address {addr_b}")
        _query_setpoint_source(controller_b)
        ok_frame_b = _query_data_frame(controller_b)
        ok_units_b = True
        if args.set_psi:
            ok_units_b = _set_units(
                controller_b,
                args.units_stat,
                args.units_group,
                args.units_value,
                args.units_override,
            )
        if args.setpoint_b is not None:
            current_b = controller_b.read_status()
            original_b = current_b.setpoint if current_b else None
            ok_b = _apply_setpoint(controller_b, args.setpoint_b, args.settle_s)
        else:
            ok_b, original_b = _test_read_write(controller_b, args.setpoint_delta, args.settle_s)
        ok_modes_b = True if args.skip_modes else _test_modes(controller_b)
        results.append(ok_frame_b and ok_units_b and ok_b and ok_modes_b)
        if original_b is not None:
            original_setpoints[controller_b.address] = original_b

    finally:
        # Restore original setpoints
        if not args.no_restore:
            for addr, value in original_setpoints.items():
                try:
                    if addr == controller_a.address:
                        controller_a.set_pressure(value)
                    elif addr == controller_b.address:
                        controller_b.set_pressure(value)
                except Exception:
                    pass
        controller_a.disconnect()

    if all(results):
        print("\n[PASS] Both Alicats responded to read/write commands.")
        return 0

    print("\n[FAIL] One or more Alicats failed read/write tests.")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
