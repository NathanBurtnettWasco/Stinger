"""
Transducer vs Alicat Correlation Test.

Tests the equivalence between the pressure transducer (LabJack) and Alicat readings
at different ramp rates. Collects data during ramps from atmosphere to target pressure.

Note: ramp_rate=0 means "as fast as possible" (maximum speed) on the Alicat.

Usage (from repo root):
    python scripts/transducer_alicat_correlation_test.py
    python scripts/transducer_alicat_correlation_test.py --port port_a --ramp-rates 0.5 1 2 5 10
    python scripts/transducer_alicat_correlation_test.py --port port_a --target-pressure 10.0
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)


@dataclass
class PressureReading:
    """Single pressure reading from both sensors."""
    timestamp: float
    transducer_voltage: float
    transducer_pressure: float
    alicat_pressure: float
    alicat_setpoint: float
    alicat_barometric: Optional[float]
    ramp_rate: float
    elapsed_time: float


@dataclass
class RampTestResult:
    """Results from a single ramp rate test."""
    ramp_rate: float
    readings: List[PressureReading]
    mean_offset: float
    std_offset: float
    max_offset: float
    min_offset: float
    offset_reference: str


def build_labjack_controller(
    config: Dict[str, Any],
    port: str,
    filter_alpha_override: Optional[float] = None,
) -> LabJackController:
    """Build LabJack controller for specified port."""
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(port, {})
    
    filter_alpha = labjack_cfg.get('transducer_filter_alpha', 0.2)
    if filter_alpha_override is not None:
        filter_alpha = filter_alpha_override

    controller_config = {
        'device_type': labjack_cfg.get('device_type', 'T7'),
        'connection_type': labjack_cfg.get('connection_type', 'USB'),
        'identifier': labjack_cfg.get('identifier', 'ANY'),
        'transducer_ain': port_cfg.get('transducer_ain'),
        'transducer_ain_neg': port_cfg.get('transducer_ain_neg'),
        'transducer_voltage_min': port_cfg.get('transducer_voltage_min', 0.5),
        'transducer_voltage_max': port_cfg.get('transducer_voltage_max', 4.5),
        'transducer_pressure_min': port_cfg.get('transducer_pressure_min', 0.0),
        'transducer_pressure_max': port_cfg.get('transducer_pressure_max', 115.0),
        'transducer_filter_alpha': filter_alpha,
    }
    
    return LabJackController(controller_config)

def verify_transducer_config(config: Dict[str, Any], port: str) -> None:
    """Print transducer scaling configuration."""
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(port, {})
    vmin = port_cfg.get('transducer_voltage_min', 0.5)
    vmax = port_cfg.get('transducer_voltage_max', 4.5)
    pmin = port_cfg.get('transducer_pressure_min', 0.0)
    pmax = port_cfg.get('transducer_pressure_max', 115.0)
    pref = str(port_cfg.get('transducer_reference', 'absolute')).lower()
    poff = float(port_cfg.get('transducer_offset_psi', 0.0))
    ain = port_cfg.get('transducer_ain')
    ain_neg = port_cfg.get('transducer_ain_neg')
    print("[CONFIG] Transducer scaling:")
    print(f"  AIN+ / AIN-: {ain} / {ain_neg}")
    print(f"  Voltage range: {vmin}–{vmax} V")
    print(f"  Pressure range: {pmin}–{pmax} PSI")
    print(f"  Reference: {pref}")
    print(f"  Offset (psi): {poff:+.2f}")
    if vmin == 0.5 and vmax == 4.5 and pmin == 0.0 and pmax == 115.0:
        print("  [OK] Matches 0.5–4.5V => 0–115 PSI")
    else:
        print("  [WARNING] Scaling differs from expected 0.5–4.5V => 0–115 PSI")


def build_alicat_controller(config: Dict[str, Any], port: str) -> AlicatController:
    """Build Alicat controller for specified port."""
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_cfg = alicat_cfg.get(port, {})
    
    controller_config = {
        'com_port': port_cfg.get('com_port'),
        'address': port_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': alicat_cfg.get('timeout_s', 0.05),
        'pressure_index': alicat_cfg.get('pressure_index'),
        'setpoint_index': alicat_cfg.get('setpoint_index'),
        'gauge_index': alicat_cfg.get('gauge_index'),
        'barometric_index': alicat_cfg.get('barometric_index'),
    }
    
    return AlicatController(controller_config)


def wait_for_atmosphere(alicat: AlicatController, target_pressure: float = 14.7, tolerance: float = 0.5, timeout: float = 30.0) -> bool:
    """Wait for pressure to stabilize near atmosphere (absolute pressure)."""
    start_time = time.time()
    stable_count = 0
    required_stable = 5
    last_log_time = start_time
    
    while time.time() - start_time < timeout:
        reading = alicat.read_status()
        if reading:
            # If barometric pressure is available, use it as the atmosphere target
            if reading.barometric_pressure is not None:
                target_pressure = reading.barometric_pressure
            diff = abs(reading.pressure - target_pressure)
            elapsed = time.time() - start_time
            
            # Log progress every 2 seconds
            if time.time() - last_log_time >= 2.0:
                print(f"    Waiting... Pressure: {reading.pressure:.2f} PSIA (target: {target_pressure:.2f}±{tolerance:.2f}), "
                      f"diff: {diff:.3f} PSI, stable: {stable_count}/{required_stable}")
                last_log_time = time.time()
            
            if diff <= tolerance:
                stable_count += 1
                if stable_count >= required_stable:
                    print(f"    Stabilized! Pressure: {reading.pressure:.2f} PSIA (stable for {stable_count} readings)")
                    return True
            else:
                stable_count = 0
        time.sleep(0.2)
    
    final_reading = alicat.read_status()
    if final_reading:
        print(f"    Timeout reached. Final pressure: {final_reading.pressure:.2f} PSIA")
    return False


def _get_status_mode(raw_response: Optional[str]) -> str:
    if not raw_response:
        return "UNKNOWN"
    raw_upper = raw_response.upper()
    if "EXH" in raw_upper:
        return "EXHAUST"
    if "HLD" in raw_upper or "HOLD" in raw_upper:
        return "HOLD"
    return "CONTROL"


def ensure_control_mode(alicat: AlicatController, retries: int = 5, delay_s: float = 1.0) -> bool:
    """Ensure Alicat is out of EXH/HLD and in control mode."""
    for attempt in range(retries):
        status = alicat.read_status()
        mode = _get_status_mode(status.raw_response if status else None)
        if status:
            print(
                f"  [MODE] Status check {attempt + 1}/{retries}: "
                f"Pressure={status.pressure:.2f} PSI, Setpoint={status.setpoint:.2f} PSI, Mode={mode}"
            )
            print(f"  [RAW] {status.raw_response}")
        if mode == "CONTROL":
            return True

        print("  [COMMAND] Sending cancel valve hold (C)...")
        alicat.cancel_hold()
        time.sleep(delay_s)

    print("  [ERROR] Failed to exit EXHAUST/HOLD mode after retries.")
    return False


def ensure_setpoint_source_serial(alicat: AlicatController) -> None:
    """Ensure setpoint source is serial/display (LSS S)."""
    try:
        response = alicat._send_command("LSS")
        print(f"  [QUERY] LSS -> {response}")
        if response and response.split()[-1].upper() != "S":
            print("  [COMMAND] Setting LSS to S (serial/display)...")
            set_resp = alicat._send_command("LSS S")
            print(f"  [OK] LSS S -> {set_resp}")
    except Exception as exc:
        print(f"  [WARNING] Unable to query/set LSS: {exc}")

def ensure_ramping_enabled(alicat: AlicatController) -> None:
    """Ensure ramping options are enabled (LSRC)."""
    try:
        response = alicat._send_command("LSRC")
        print(f"  [QUERY] LSRC -> {response}")
        if response:
            parts = response.split()
            # Expect: unit_id ramp_up ramp_down zero_ramp power_up_ramp
            if len(parts) >= 5:
                ramp_flags = parts[-4:]
                if any(flag == "0" for flag in ramp_flags):
                    print("  [COMMAND] Enabling ramping (LSRC 1 1 1 1)...")
                    set_resp = alicat._send_command("LSRC 1 1 1 1")
                    print(f"  [OK] LSRC set -> {set_resp}")
    except Exception as exc:
        print(f"  [WARNING] Unable to query/set LSRC: {exc}")

def wait_for_pressure(
    alicat: AlicatController,
    target_psia: float,
    tolerance: float = 0.5,
    timeout: float = 60.0,
    label: str = "target",
) -> bool:
    """Wait for Alicat absolute pressure to reach target."""
    start = time.time()
    while time.time() - start < timeout:
        reading = alicat.read_status()
        if not reading:
            time.sleep(0.2)
            continue
        diff = abs(reading.pressure - target_psia)
        if diff <= tolerance:
            print(f"  [OK] Reached {label}: {reading.pressure:.2f} PSIA (diff {diff:.2f})")
            return True
        time.sleep(0.2)
    print(f"  [WARNING] Timeout waiting for {label} ({target_psia:.2f} PSIA)")
    return False

def validate_valve_modes(alicat: AlicatController) -> None:
    """Quick sanity check for hold/exhaust/cancel."""
    print("  [MODE TEST] Hold valve (HP)...")
    alicat._send_command("HP")
    time.sleep(0.2)
    print("  [MODE TEST] Hold valve closed (HC)...")
    alicat._send_command("HC")
    time.sleep(0.2)
    print("  [MODE TEST] Cancel hold (C)...")
    alicat._send_command("C")
    time.sleep(0.2)
    print("  [MODE TEST] Exhaust (E)...")
    alicat._send_command("E")
    time.sleep(0.2)
    print("  [MODE TEST] Cancel exhaust/hold (C)...")
    alicat._send_command("C")
    time.sleep(0.2)


def _get_alicat_gauge_pressure(reading: AlicatReading, fallback_baro: float) -> float:
    baro = reading.barometric_pressure if reading.barometric_pressure is not None else fallback_baro
    return reading.pressure - baro


def _compute_offset(
    transducer_pressure: float,
    alicat_reading: AlicatReading,
    fallback_baro: float,
    transducer_absolute: bool,
) -> float:
    if transducer_absolute:
        return transducer_pressure - alicat_reading.pressure
    return transducer_pressure - _get_alicat_gauge_pressure(alicat_reading, fallback_baro)


def _compute_offset_from_pressure_reading(
    reading: PressureReading,
    fallback_baro: float,
    transducer_absolute: bool,
) -> float:
    baro = reading.alicat_barometric if reading.alicat_barometric is not None else fallback_baro
    if transducer_absolute:
        return reading.transducer_pressure - reading.alicat_pressure
    return reading.transducer_pressure - (reading.alicat_pressure - baro)

def run_ramp_test(
    labjack: LabJackController,
    alicat: AlicatController,
    ramp_rate: float,
    target_pressure: float,
    sample_rate_hz: float = 10.0,
    target_is_psig: bool = True,
    transducer_absolute: bool = False,
) -> List[PressureReading]:
    """
    Run a single ramp test from atmosphere to target pressure.
    
    Args:
        labjack: LabJack controller for transducer readings
        alicat: Alicat controller
        ramp_rate: Ramp rate in PSI/s
        target_pressure: Target pressure in PSI
        sample_rate_hz: Sampling rate in Hz
        
    Returns:
        List of pressure readings collected during the ramp
    """
    readings: List[PressureReading] = []
    sample_interval = 1.0 / sample_rate_hz
    
    # Start from atmosphere (exhaust mode)
    print(f"  [COMMAND] Setting exhaust mode (E command)...")
    if alicat.exhaust():
        print(f"  [OK] Exhaust command acknowledged")
    else:
        print(f"  [ERROR] Exhaust command failed")
    time.sleep(2.0)
    
    # Check initial state
    initial_status = alicat.read_status()
    if initial_status:
        print(f"  [STATUS] Initial pressure: {initial_status.pressure:.2f} PSI, setpoint: {initial_status.setpoint:.2f} PSI")
    
    # Wait for atmosphere
    print(f"  [WAIT] Waiting for pressure to stabilize at atmosphere...")
    if not wait_for_atmosphere(alicat, timeout=30.0):
        print(f"  [WARNING] Did not stabilize at atmosphere")
    else:
        final_atm = alicat.read_status()
        if final_atm:
            print(f"  [OK] Stabilized at {final_atm.pressure:.2f} PSI")
    
    # Ensure setpoint source is serial
    ensure_setpoint_source_serial(alicat)
    # Ensure ramping options are enabled
    ensure_ramping_enabled(alicat)

    # Read current atmosphere pressure (absolute) while in exhaust
    initial_reading = alicat.read_status()
    initial_pressure = initial_reading.pressure if initial_reading else 14.7
    baro_pressure = initial_reading.barometric_pressure if initial_reading else None
    if baro_pressure is None:
        baro_pressure = 14.7
    print(f"  [INITIAL] Atmosphere pressure: {initial_pressure:.2f} PSIA (baro: {baro_pressure:.2f} PSIA)")

    # Enter control mode BEFORE applying target setpoint (so ramping is honored)
    print("  [MODE] Attempting to enter control mode before target setpoint...")
    if not ensure_control_mode(alicat):
        return readings

    # Set ramp rate in control mode
    # Note: ramp_rate=0 means "as fast as possible" (maximum speed)
    if ramp_rate == 0:
        print(f"  [COMMAND] Setting ramp rate to maximum speed (SR 0 4)...")
        if not alicat.set_ramp_rate(0, time_unit='s'):
            print(f"  [ERROR] Failed to set ramp rate to maximum")
            return readings
        print(f"  [OK] Ramp rate set to maximum speed")
    else:
        print(f"  [COMMAND] Setting ramp rate to {ramp_rate} PSI/s (SR {ramp_rate} 4)...")
        if not alicat.set_ramp_rate(ramp_rate, time_unit='s'):
            print(f"  [ERROR] Failed to set ramp rate")
            return readings
        print(f"  [OK] Ramp rate set to {ramp_rate} PSI/s")
    time.sleep(0.5)

    # Read initial pressure (absolute) in control mode
    initial_reading = alicat.read_status()
    initial_pressure = initial_reading.pressure if initial_reading else initial_pressure
    baro_pressure = initial_reading.barometric_pressure if initial_reading else baro_pressure
    print(f"  [INITIAL] Starting pressure (control mode): {initial_pressure:.2f} PSIA (baro: {baro_pressure:.2f} PSIA)")

    # Reset setpoint to atmosphere in control mode to clear stale setpoint,
    # then wait until we actually settle near atmosphere before ramping up.
    print(f"  [COMMAND] Setting setpoint to atmosphere ({baro_pressure:.4f} PSIA) before ramp...")
    alicat.set_pressure(baro_pressure)
    wait_for_pressure(alicat, baro_pressure, tolerance=0.5, timeout=90.0, label="atmosphere")

    # Re-read after settling to start ramp from low pressure
    initial_reading = alicat.read_status()
    initial_pressure = initial_reading.pressure if initial_reading else baro_pressure
    baro_pressure = initial_reading.barometric_pressure if initial_reading else baro_pressure
    print(f"  [INITIAL] Starting pressure after settle: {initial_pressure:.2f} PSIA (baro: {baro_pressure:.2f} PSIA)")

    # Convert target pressure to absolute setpoint if needed
    if target_is_psig:
        target_setpoint = baro_pressure + target_pressure
        print(f"  [TARGET] Requested {target_pressure:.2f} PSIG -> Setpoint {target_setpoint:.2f} PSIA")
    else:
        target_setpoint = target_pressure
        print(f"  [TARGET] Requested {target_pressure:.2f} PSIA")

    # Set target pressure in control mode
    print(f"  [COMMAND] Setting target pressure to {target_setpoint:.4f} PSIA (S{target_setpoint:.4f})...")
    if not alicat.set_pressure(target_setpoint):
        print(f"  [ERROR] Failed to set target pressure")
        return readings
    print(f"  [OK] Target pressure set to {target_setpoint:.2f} PSIA")

    # Verify setpoint was accepted
    verify_status = alicat.read_status()
    if verify_status:
        print(f"  [VERIFY] Setpoint: {verify_status.setpoint:.2f} PSIA (target: {target_setpoint:.2f} PSIA)")
        if abs(verify_status.setpoint - target_setpoint) > 0.1:
            print(f"  [WARNING] Setpoint mismatch! Expected {target_setpoint:.2f}, got {verify_status.setpoint:.2f}")
    time.sleep(0.5)
    
    # Calculate expected ramp time
    pressure_delta = target_setpoint - initial_pressure
    if ramp_rate == 0:
        # Maximum speed - estimate based on typical Alicat performance (~5-10 seconds for small changes)
        expected_time = max(abs(pressure_delta) * 0.5, 5.0)  # Rough estimate
    else:
        expected_time = abs(pressure_delta / ramp_rate) if ramp_rate > 0 else 0
    expected_time += 10.0  # Add buffer for settling
    
    print(f"  [START] Starting ramp from {initial_pressure:.2f} to {target_setpoint:.2f} PSIA")
    print(f"  [INFO] Expected ramp time: {expected_time:.1f} seconds")
    print(f"  [INFO] Sampling at {sample_rate_hz} Hz ({sample_interval*1000:.1f} ms intervals)")
    
    # Wait a moment and check if pressure is starting to change
    print(f"  [WAIT] Waiting 2 seconds to verify ramp has started...")
    time.sleep(2.0)
    startup_check = alicat.read_status()
    if startup_check:
        pressure_change = startup_check.pressure - initial_pressure
        print(f"  [CHECK] After 2s: Pressure={startup_check.pressure:.2f} PSI (change: {pressure_change:+.2f} PSI)")
        if abs(pressure_change) < 0.1:
            print(f"  [WARNING] Pressure not changing! May not be in control mode.")
        else:
            print(f"  [OK] Pressure is changing, ramp appears to be active")
    
    start_time = time.time()
    last_sample_time = start_time
    last_status_time = start_time
    status_interval = 2.0  # Print status every 2 seconds
    alicat_reading = None  # Initialize for loop check
    sample_count = 0
    
    # Collect data during ramp
    while True:
        current_time = time.time()
        elapsed = current_time - start_time
        
        # Sample at specified rate
        if current_time - last_sample_time >= sample_interval:
            # Read transducer
            transducer_reading = labjack.read_transducer()
            transducer_pressure = transducer_reading.pressure if transducer_reading else None
            
            # Read Alicat
            alicat_reading = alicat.read_status()
            alicat_pressure = alicat_reading.pressure if alicat_reading else None
            alicat_setpoint = alicat_reading.setpoint if alicat_reading else None
            
            if transducer_pressure is not None and alicat_pressure is not None:
                readings.append(PressureReading(
                    timestamp=current_time,
                    transducer_voltage=transducer_reading.voltage,
                    transducer_pressure=transducer_pressure,
                    alicat_pressure=alicat_pressure,
                    alicat_setpoint=alicat_setpoint or 0.0,
                    alicat_barometric=alicat_reading.barometric_pressure,
                    ramp_rate=ramp_rate,
                    elapsed_time=elapsed,
                ))
                sample_count += 1
            
            last_sample_time = current_time
        
        # Print status updates periodically
        if current_time - last_status_time >= status_interval:
            if alicat_reading and transducer_reading:
                offset = _compute_offset(
                    transducer_reading.pressure,
                    alicat_reading,
                    baro_pressure,
                    transducer_absolute,
                )
                progress_pct = ((alicat_reading.pressure - initial_pressure) / pressure_delta * 100) if pressure_delta != 0 else 0
                baro_live = alicat_reading.barometric_pressure if alicat_reading.barometric_pressure is not None else baro_pressure
                alicat_gauge = alicat_reading.pressure - baro_live
                setpoint_gauge = alicat_reading.setpoint - baro_live
                print(f"  [STATUS] t={elapsed:6.1f}s | "
                      f"Transducer: {transducer_reading.pressure:6.2f} PSI ({transducer_reading.voltage:.3f} V) | "
                      f"Alicat: {alicat_reading.pressure:6.2f} PSIA ({alicat_gauge:+6.2f} PSIG) | "
                      f"Setpoint: {alicat_reading.setpoint:6.2f} PSIA ({setpoint_gauge:+6.2f} PSIG) | "
                      f"Offset: {offset:+7.4f} PSI | "
                      f"Progress: {progress_pct:5.1f}% | "
                      f"Samples: {sample_count}")
            last_status_time = current_time
        
        # Check if we've reached target or exceeded timeout
        if alicat_reading:
            pressure_diff = abs(alicat_reading.pressure - target_pressure)
            if pressure_diff <= 0.5:  # Within 0.5 PSI of target
                print(f"  [TARGET] Reached target pressure (diff: {pressure_diff:.3f} PSI)")
                print(f"  [WAIT] Waiting 2 seconds for settling...")
                time.sleep(2.0)
                break
        
        if elapsed > expected_time:
            print(f"  [WARNING] Timeout reached ({elapsed:.1f}s)")
            break
        
        time.sleep(0.01)  # Small sleep to avoid tight loop
    
    # Collect a few more samples after reaching target
    print(f"  [SETTLE] Collecting final settling samples...")
    for i in range(10):
        time.sleep(sample_interval)
        transducer_reading = labjack.read_transducer()
        alicat_reading = alicat.read_status()
        
        if transducer_reading and alicat_reading:
            offset = _compute_offset(
                transducer_reading.pressure,
                alicat_reading,
                baro_pressure,
                transducer_absolute,
            )
            readings.append(PressureReading(
                timestamp=time.time(),
                transducer_voltage=transducer_reading.voltage,
                transducer_pressure=transducer_reading.pressure,
                alicat_pressure=alicat_reading.pressure,
                alicat_setpoint=alicat_reading.setpoint or 0.0,
                alicat_barometric=alicat_reading.barometric_pressure,
                ramp_rate=ramp_rate,
                elapsed_time=time.time() - start_time,
            ))
            if i % 3 == 0:  # Print every 3rd sample
                print(f"    Settle sample {i+1}/10: Transducer={transducer_reading.pressure:.2f} PSI, "
                      f"Alicat={alicat_reading.pressure:.2f} PSI, Offset={offset:+.4f} PSI")
    
    print(f"  [COMPLETE] Collected {len(readings)} total samples")
    if readings:
        final_transducer = readings[-1].transducer_pressure
        final_alicat = readings[-1].alicat_pressure
        final_offset = _compute_offset_from_pressure_reading(
            readings[-1],
            baro_pressure,
            transducer_absolute,
        )
        print(f"  [FINAL] Final readings: Transducer={final_transducer:.2f} PSI, "
              f"Alicat={final_alicat:.2f} PSIA, Offset={final_offset:+.4f} PSI")
    return readings


def run_dual_ramp_test(
    labjack_a: LabJackController,
    alicat_a: AlicatController,
    labjack_b: LabJackController,
    alicat_b: AlicatController,
    ramp_rate: float,
    target_pressure: float,
    sample_rate_hz: float = 10.0,
    target_is_psig: bool = True,
    transducer_absolute: bool = False,
) -> Dict[str, List[PressureReading]]:
    """Run a simultaneous ramp test on both ports."""
    readings_a: List[PressureReading] = []
    readings_b: List[PressureReading] = []
    sample_interval = 1.0 / sample_rate_hz

    print("  [DUAL] Setting exhaust mode on both ports...")
    alicat_a.exhaust()
    alicat_b.exhaust()
    time.sleep(2.0)

    print("  [DUAL] Waiting for both ports to stabilize at atmosphere...")
    wait_for_atmosphere(alicat_a, timeout=30.0)
    wait_for_atmosphere(alicat_b, timeout=30.0)

    ensure_setpoint_source_serial(alicat_a)
    ensure_setpoint_source_serial(alicat_b)
    ensure_ramping_enabled(alicat_a)
    ensure_ramping_enabled(alicat_b)

    print("  [DUAL] Entering control mode on both ports...")
    if not ensure_control_mode(alicat_a) or not ensure_control_mode(alicat_b):
        return {"port_a": readings_a, "port_b": readings_b}

    # Set ramp rate on both ports
    if ramp_rate == 0:
        print("  [DUAL] Setting ramp rate to maximum speed on both ports...")
        alicat_a.set_ramp_rate(0, time_unit='s')
        alicat_b.set_ramp_rate(0, time_unit='s')
    else:
        print(f"  [DUAL] Setting ramp rate to {ramp_rate} PSI/s on both ports...")
        alicat_a.set_ramp_rate(ramp_rate, time_unit='s')
        alicat_b.set_ramp_rate(ramp_rate, time_unit='s')
    time.sleep(0.5)

    # Read barometric pressures
    status_a = alicat_a.read_status()
    status_b = alicat_b.read_status()
    baro_a = status_a.barometric_pressure if status_a and status_a.barometric_pressure is not None else 14.7
    baro_b = status_b.barometric_pressure if status_b and status_b.barometric_pressure is not None else 14.7

    # Reset setpoints to atmosphere and wait to settle
    print("  [DUAL] Resetting both setpoints to atmosphere...")
    alicat_a.set_pressure(baro_a)
    alicat_b.set_pressure(baro_b)
    wait_for_pressure(alicat_a, baro_a, tolerance=0.5, timeout=90.0, label="port_a atmosphere")
    wait_for_pressure(alicat_b, baro_b, tolerance=0.5, timeout=90.0, label="port_b atmosphere")

    # Compute absolute targets
    target_a = baro_a + target_pressure if target_is_psig else target_pressure
    target_b = baro_b + target_pressure if target_is_psig else target_pressure
    print(f"  [DUAL] Target setpoints: port_a={target_a:.2f} PSIA, port_b={target_b:.2f} PSIA")

    alicat_a.set_pressure(target_a)
    alicat_b.set_pressure(target_b)

    # Start sampling loop
    start_time = time.time()
    last_sample_time = start_time
    last_status_time = start_time
    status_interval = 2.0
    expected_time = abs((target_a - baro_a) / ramp_rate) if ramp_rate > 0 else 10.0
    expected_time = max(expected_time, abs((target_b - baro_b) / ramp_rate) if ramp_rate > 0 else 10.0)
    expected_time += 15.0

    while True:
        now = time.time()
        elapsed = now - start_time

        if now - last_sample_time >= sample_interval:
            tr_a = labjack_a.read_transducer()
            tr_b = labjack_b.read_transducer()
            al_a = alicat_a.read_status()
            al_b = alicat_b.read_status()

            if tr_a and al_a:
                readings_a.append(PressureReading(
                    timestamp=now,
                    transducer_voltage=tr_a.voltage,
                    transducer_pressure=tr_a.pressure,
                    alicat_pressure=al_a.pressure,
                    alicat_setpoint=al_a.setpoint or 0.0,
                    alicat_barometric=al_a.barometric_pressure,
                    ramp_rate=ramp_rate,
                    elapsed_time=elapsed,
                ))
            if tr_b and al_b:
                readings_b.append(PressureReading(
                    timestamp=now,
                    transducer_voltage=tr_b.voltage,
                    transducer_pressure=tr_b.pressure,
                    alicat_pressure=al_b.pressure,
                    alicat_setpoint=al_b.setpoint or 0.0,
                    alicat_barometric=al_b.barometric_pressure,
                    ramp_rate=ramp_rate,
                    elapsed_time=elapsed,
                ))

            last_sample_time = now

        if now - last_status_time >= status_interval:
            if readings_a:
                ra = readings_a[-1]
                offset_a = _compute_offset_from_pressure_reading(ra, baro_a, transducer_absolute)
                print(f"  [A] t={elapsed:6.1f}s | Transducer={ra.transducer_pressure:6.2f} PSI ({ra.transducer_voltage:.3f} V) | "
                      f"Alicat={ra.alicat_pressure:6.2f} PSIA | Offset={offset_a:+7.4f} PSI")
            if readings_b:
                rb = readings_b[-1]
                offset_b = _compute_offset_from_pressure_reading(rb, baro_b, transducer_absolute)
                print(f"  [B] t={elapsed:6.1f}s | Transducer={rb.transducer_pressure:6.2f} PSI ({rb.transducer_voltage:.3f} V) | "
                      f"Alicat={rb.alicat_pressure:6.2f} PSIA | Offset={offset_b:+7.4f} PSI")
            last_status_time = now

        # Stop when both reach target or timeout
        if elapsed > expected_time:
            print("  [DUAL] Timeout reached.")
            break

        if readings_a and readings_b:
            if abs(readings_a[-1].alicat_pressure - target_a) <= 0.5 and abs(readings_b[-1].alicat_pressure - target_b) <= 0.5:
                print("  [DUAL] Both ports reached target.")
                time.sleep(2.0)
                break

        time.sleep(0.01)

    return {"port_a": readings_a, "port_b": readings_b}

def analyze_ramp_results(
    readings: List[PressureReading],
    transducer_absolute: bool,
    fallback_baro: float,
) -> RampTestResult:
    """Analyze readings to compute offset statistics."""
    if not readings:
        return RampTestResult(
            ramp_rate=0.0,
            readings=[],
            mean_offset=0.0,
            std_offset=0.0,
            max_offset=0.0,
            min_offset=0.0,
            offset_reference="unknown",
        )
    
    offsets = [
        _compute_offset_from_pressure_reading(r, fallback_baro, transducer_absolute)
        for r in readings
    ]
    offset_reference = "absolute" if transducer_absolute else "gauge"
    
    return RampTestResult(
        ramp_rate=readings[0].ramp_rate,
        readings=readings,
        mean_offset=np.mean(offsets),
        std_offset=np.std(offsets),
        max_offset=np.max(offsets),
        min_offset=np.min(offsets),
        offset_reference=offset_reference,
    )


def save_results_to_csv(results: List[RampTestResult], output_file: Path, fallback_baro: float) -> None:
    """Save all test results to CSV file."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Ramp Rate (PSI/s)',
            'Elapsed Time (s)',
            'Transducer Voltage (V)',
            'Transducer Pressure (PSI)',
            'Alicat Pressure (PSIA)',
            'Alicat Gauge (PSIG)',
            'Alicat Barometric (PSIA)',
            'Alicat Setpoint (PSIA)',
            'Offset Gauge (Transducer - AlicatGauge)',
            'Offset Absolute (Transducer - AlicatAbs)',
        ])
        
        for result in results:
            for reading in result.readings:
                baro = reading.alicat_barometric if reading.alicat_barometric is not None else fallback_baro
                alicat_gauge = reading.alicat_pressure - baro
                offset_gauge = reading.transducer_pressure - alicat_gauge
                offset_abs = reading.transducer_pressure - reading.alicat_pressure
                writer.writerow([
                    reading.ramp_rate,
                    reading.elapsed_time,
                    reading.transducer_voltage,
                    reading.transducer_pressure,
                    reading.alicat_pressure,
                    alicat_gauge,
                    baro,
                    reading.alicat_setpoint,
                    offset_gauge,
                    offset_abs,
                ])


def print_summary(results: List[RampTestResult]) -> None:
    """Print summary of test results."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"{'Ramp Rate':<12} {'Mean Offset':<15} {'Std Dev':<15} {'Min':<12} {'Max':<12} {'Ref':<8}")
    print("-"*80)
    
    for result in results:
        print(f"{result.ramp_rate:<12.2f} {result.mean_offset:<15.4f} {result.std_offset:<15.4f} "
              f"{result.min_offset:<12.4f} {result.max_offset:<12.4f} {result.offset_reference:<8}")
    
    print("\n" + "="*80)
    print("OFFSET ANALYSIS BY RAMP RATE")
    print("="*80)
    
    # Analyze how offset changes with ramp rate
    rates = [r.ramp_rate for r in results]
    mean_offsets = [r.mean_offset for r in results]
    
    if len(rates) > 1:
        # Linear regression to see if offset depends on rate
        coeffs = np.polyfit(rates, mean_offsets, 1)
        print(f"Linear fit: Offset = {coeffs[0]:.6f} * Rate + {coeffs[1]:.6f}")
        print(f"Correlation coefficient: {np.corrcoef(rates, mean_offsets)[0,1]:.4f}")
        
        if abs(coeffs[0]) < 0.001:
            print("\nCONCLUSION: Offset appears independent of ramp rate")
        else:
            print(f"\nCONCLUSION: Offset changes by {coeffs[0]:.6f} PSI per PSI/s ramp rate")
    
    # Overall statistics
    all_offsets = []
    for result in results:
        fallback_baro = result.readings[0].alicat_barometric if result.readings else 14.7
        for reading in result.readings:
            all_offsets.append(
                _compute_offset_from_pressure_reading(
                    reading,
                    fallback_baro,
                    result.offset_reference == "absolute",
                )
            )
    
    if all_offsets:
        print(f"\nOverall Statistics:")
        print(f"  Mean offset: {np.mean(all_offsets):.4f} PSI")
        print(f"  Std deviation: {np.std(all_offsets):.4f} PSI")
        print(f"  Min offset: {np.min(all_offsets):.4f} PSI")
        print(f"  Max offset: {np.max(all_offsets):.4f} PSI")
        print(f"\nRecommended offset correction: {np.mean(all_offsets):.4f} PSI")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test transducer vs Alicat correlation at different ramp rates")
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test (default: port_a)')
    parser.add_argument('--ramp-rates', nargs='+', type=float, default=[0.5, 1.0, 2.0, 5.0, 10.0],
                       help='Ramp rates in PSI/s (default: 0.5 1 2 5 10)')
    parser.add_argument('--target-pressure', type=float, default=100.0,
                       help='Target pressure in PSIG by default (default: 100.0)')
    parser.add_argument('--target-absolute', action='store_true',
                       help='Interpret target-pressure as PSIA (absolute)')
    parser.add_argument('--transducer-absolute', action='store_true',
                       help='Treat transducer readings as PSIA (default: PSIG)')
    parser.add_argument('--validate-modes', action='store_true',
                       help='Send HP/HC/E/C to verify mode control')
    parser.add_argument('--both-ports', action='store_true',
                       help='Run both ports simultaneously')
    parser.add_argument('--sample-rate', type=float, default=10.0,
                       help='Sampling rate in Hz (default: 10.0)')
    parser.add_argument('--no-filter', action='store_true',
                       help='Disable LabJack transducer filtering')
    parser.add_argument('--output-dir', type=str, default=None,
                       help='Output directory for CSV files (default: scripts/data)')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    
    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1
    
    filter_override = 0.0 if args.no_filter else None

    if args.both_ports:
        print("Building controllers for both ports...")
        labjack_a = build_labjack_controller(
            config,
            "port_a",
            filter_alpha_override=filter_override,
        )
        labjack_b = build_labjack_controller(
            config,
            "port_b",
            filter_alpha_override=filter_override,
        )
        alicat_a = build_alicat_controller(config, "port_a")
        alicat_b = build_alicat_controller(config, "port_b")
    else:
        print(f"Building controllers for {args.port}...")
        labjack = build_labjack_controller(
            config,
            args.port,
            filter_alpha_override=filter_override,
        )
        alicat = build_alicat_controller(config, args.port)
    
    # Connect
    print("Connecting to hardware...")
    if args.both_ports:
        if not labjack_a.configure() or not labjack_b.configure():
            print("[FAIL] LabJack configuration failed on one of the ports")
            return 1
        if not alicat_a.connect():
            print(f"[FAIL] Alicat A connection failed: {alicat_a._last_status}")
            labjack_a.cleanup()
            labjack_b.cleanup()
            return 1
        if alicat_a._serial is None:
            print("[FAIL] Alicat A serial connection not available")
            return 1
        alicat_b.set_shared_serial(alicat_a._serial)
        print("Connected successfully!\n")
    else:
        if not labjack.configure():
            print(f"[FAIL] LabJack configuration failed: {labjack._last_status}")
            return 1
        if not alicat.connect():
            print(f"[FAIL] Alicat connection failed: {alicat._last_status}")
            labjack.cleanup()
            return 1
        print("Connected successfully!\n")
    
    # Print test plan
    print("="*80)
    print("TEST PLAN")
    print("="*80)
    print(f"Port: {'both' if args.both_ports else args.port}")
    print(f"Target Pressure: {args.target_pressure} {'PSIA' if args.target_absolute else 'PSIG'}")
    print(f"Transducer Reference: {'PSIA' if args.transducer_absolute else 'PSIG'}")
    print(f"Sample Rate: {args.sample_rate} Hz")
    print(f"Transducer Filter: {'disabled' if args.no_filter else 'enabled'}")
    print(f"Ramp Rates to Test: {', '.join([f'{r} PSI/s' + (' (max)' if r == 0 else '') for r in args.ramp_rates])}")
    print(f"Total Tests: {len(args.ramp_rates)}")
    if args.target_absolute:
        delta_est = abs(args.target_pressure - 14.7)
    else:
        delta_est = abs(args.target_pressure)
    estimated_time = sum([max(delta_est / r if r > 0 else 5, 5) + 10 for r in args.ramp_rates])
    print(f"Estimated Total Time: ~{estimated_time/60:.1f} minutes")
    print("="*80 + "\n")
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = PROJECT_ROOT / 'scripts' / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Run tests for each ramp rate
    results: List[RampTestResult] = []
    
    try:
        if args.both_ports:
            verify_transducer_config(config, "port_a")
            verify_transducer_config(config, "port_b")
        else:
            verify_transducer_config(config, args.port)
        for ramp_rate in args.ramp_rates:
            print(f"\n{'='*80}")
            print(f"TEST {args.ramp_rates.index(ramp_rate) + 1}/{len(args.ramp_rates)}: Ramp Rate = {ramp_rate} PSI/s")
            print(f"{'='*80}")
            print(f"[TEST PARAMETERS]")
            print(f"  Port: {args.port}")
            print(f"  Ramp Rate: {ramp_rate} PSI/s {'(maximum speed)' if ramp_rate == 0 else ''}")
            print(f"  Target Pressure: {args.target_pressure} {'PSIA' if args.target_absolute else 'PSIG'}")
            print(f"  Sample Rate: {args.sample_rate} Hz")
            print(f"  Transducer Reference: {'PSIA' if args.transducer_absolute else 'PSIG'}")
            print(f"  Starting from: Atmosphere (~14.7 PSI)")
            print(f"{'='*80}\n")
            
            if args.validate_modes:
                if args.both_ports:
                    print("  [DUAL] Validating modes on port_a...")
                    validate_valve_modes(alicat_a)
                    print("  [DUAL] Validating modes on port_b...")
                    validate_valve_modes(alicat_b)
                else:
                    validate_valve_modes(alicat)

            if args.both_ports:
                dual_readings = run_dual_ramp_test(
                    labjack_a=labjack_a,
                    alicat_a=alicat_a,
                    labjack_b=labjack_b,
                    alicat_b=alicat_b,
                    ramp_rate=ramp_rate,
                    target_pressure=args.target_pressure,
                    sample_rate_hz=args.sample_rate,
                    target_is_psig=not args.target_absolute,
                    transducer_absolute=args.transducer_absolute,
                )
                readings = dual_readings.get("port_a", [])
                readings_b = dual_readings.get("port_b", [])
            else:
                readings = run_ramp_test(
                    labjack=labjack,
                    alicat=alicat,
                    ramp_rate=ramp_rate,
                    target_pressure=args.target_pressure,
                    sample_rate_hz=args.sample_rate,
                    target_is_psig=not args.target_absolute,
                    transducer_absolute=args.transducer_absolute,
                )
            
            if readings:
                fallback_baro = readings[0].alicat_barometric or 14.7
                result = analyze_ramp_results(
                    readings,
                    transducer_absolute=args.transducer_absolute,
                    fallback_baro=fallback_baro,
                )
                results.append(result)
                print(f"\n  Results for {ramp_rate} PSI/s:")
                print(f"    Mean offset ({result.offset_reference}): {result.mean_offset:.4f} PSI")
                print(f"    Std deviation: {result.std_offset:.4f} PSI")
                print(f"    Range: [{result.min_offset:.4f}, {result.max_offset:.4f}] PSI")
            else:
                print(f"  WARNING: No readings collected for {ramp_rate} PSI/s")

            if args.both_ports and readings_b:
                fallback_baro_b = readings_b[0].alicat_barometric or 14.7
                result_b = analyze_ramp_results(
                    readings_b,
                    transducer_absolute=args.transducer_absolute,
                    fallback_baro=fallback_baro_b,
                )
                results.append(result_b)
            
            # Wait between tests
            if ramp_rate != args.ramp_rates[-1]:
                print("\n  Waiting 5 seconds before next test...")
                time.sleep(5.0)
        
        # Save results
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        fallback_baro = results[0].readings[0].alicat_barometric if results and results[0].readings else 14.7
        if args.both_ports:
            if readings:
                csv_a = output_dir / f'transducer_alicat_correlation_port_a_{timestamp}.csv'
                save_results_to_csv([result], csv_a, fallback_baro=fallback_baro)
                print(f"\nResults saved to: {csv_a}")
            if 'readings_b' in locals() and readings_b:
                csv_b = output_dir / f'transducer_alicat_correlation_port_b_{timestamp}.csv'
                save_results_to_csv([result_b], csv_b, fallback_baro=fallback_baro)
                print(f"\nResults saved to: {csv_b}")
        else:
            csv_file = output_dir / f'transducer_alicat_correlation_{args.port}_{timestamp}.csv'
            save_results_to_csv(results, csv_file, fallback_baro=fallback_baro)
            print(f"\nResults saved to: {csv_file}")
        
        # Print summary
        print_summary(results)
        
    finally:
        # Cleanup
        print("\nCleaning up...")
        if args.both_ports:
            try:
                status = alicat_a.read_status()
                if status and status.barometric_pressure is not None:
                    print(f"  [CLEANUP] Port A setpoint to baro ({status.barometric_pressure:.3f} PSIA)")
                    alicat_a.set_pressure(status.barometric_pressure)
                    time.sleep(0.3)
                alicat_a.cancel_hold()
            except Exception:
                pass
            try:
                status = alicat_b.read_status()
                if status and status.barometric_pressure is not None:
                    print(f"  [CLEANUP] Port B setpoint to baro ({status.barometric_pressure:.3f} PSIA)")
                    alicat_b.set_pressure(status.barometric_pressure)
                    time.sleep(0.3)
                alicat_b.cancel_hold()
            except Exception:
                pass
            alicat_a.exhaust()
            alicat_b.exhaust()
            time.sleep(2.0)
            alicat_a.disconnect()
            alicat_b.disconnect()
            labjack_a.cleanup()
            labjack_b.cleanup()
        else:
            try:
                status = alicat.read_status()
                if status and status.barometric_pressure is not None:
                    print(f"  [CLEANUP] Resetting setpoint to baro ({status.barometric_pressure:.3f} PSIA)")
                    alicat.set_pressure(status.barometric_pressure)
                    time.sleep(0.3)
                alicat.cancel_hold()
            except Exception:
                pass
            alicat.exhaust()  # Return to safe state
            time.sleep(2.0)
            alicat.disconnect()
            labjack.cleanup()
    
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
