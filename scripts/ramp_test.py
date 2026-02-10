"""
Controlled Ramp Test - Run ramps at specific rates and collect high-rate data.

Usage:
    python scripts/ramp_test.py --port port_a --rate 5 --direction up --duration 20
    python scripts/ramp_test.py --port port_a --rate 10 --direction down --start 100 --end 14.7
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
class RampReading:
    timestamp: float
    elapsed_time: float
    transducer_voltage: float
    transducer_pressure_calc: float
    alicat_pressure: float
    alicat_setpoint: float
    alicat_gauge: float
    alicat_baro: Optional[float]
    ramp_rate_commanded: float
    phase: str  # 'start', 'ramping', 'settled'


def read_raw_transducer(labjack: LabJackController) -> Optional[tuple[float, float]]:
    """Read transducer voltage and calculated pressure (no offset, no filter)."""
    if not labjack.hardware_available():
        return 0.976, 14.7
    
    if labjack.transducer_ain is None:
        return None
    
    handle = labjack._shared_handle
    if handle is None:
        return None
    
    try:
        from labjack import ljm
        voltage = ljm.eReadName(handle, f'AIN{labjack.transducer_ain}')
        
        voltage_range = labjack.voltage_max - labjack.voltage_min
        pressure_range = labjack.pressure_max - labjack.pressure_min
        if voltage_range > 0:
            pressure_calc = (voltage - labjack.voltage_min) / voltage_range * pressure_range + labjack.pressure_min
        else:
            pressure_calc = labjack.pressure_min
        
        return voltage, pressure_calc
    except Exception:
        return None


def run_ramp_test(
    labjack: LabJackController,
    alicat: AlicatController,
    start_pressure: float,
    end_pressure: float,
    rate_psi_s: float,
    settle_time: float = 3.0,
) -> List[RampReading]:
    """
    Run a single ramp test from start to end pressure.
    
    Returns:
        List of readings collected during the ramp and settle period.
    """
    readings: List[RampReading] = []
    
    print(f"\n{'='*70}")
    print(f"RAMP TEST: {start_pressure:.1f} -> {end_pressure:.1f} PSIA at {rate_psi_s:.1f} PSI/s")
    print(f"{'='*70}")
    
    # First, cancel any hold/exhaust mode and move to start pressure
    print(f"\n[1/4] Moving to start pressure ({start_pressure:.1f} PSIA)...")
    alicat.cancel_hold()  # Exit exhaust/hold mode
    time.sleep(0.1)
    alicat.set_ramp_rate(0, time_unit='s')  # Fast as possible
    time.sleep(0.1)
    alicat.set_pressure(start_pressure)
    
    # Wait to reach start
    start_wait = time.perf_counter()
    while time.perf_counter() - start_wait < 30:  # Max 30 sec wait
        status = alicat.read_status()
        if status and abs(status.pressure - start_pressure) < 2.0:
            print(f"  Reached start pressure: {status.pressure:.2f} PSIA (target: {start_pressure:.1f})")
            break
        time.sleep(0.1)
    else:
        print("  [WARNING] Timeout waiting for start pressure")
        return readings
    
    # Settle at start
    print(f"[2/4] Settling at start for {settle_time:.1f}s...")
    settle_start = time.perf_counter()
    last_alicat_time = 0.0
    last_alicat_status = None
    while time.perf_counter() - settle_start < settle_time:
        trans_data = read_raw_transducer(labjack)
        current_time = time.perf_counter()
        if current_time - last_alicat_time >= 0.05:
            last_alicat_status = alicat.read_status()
            last_alicat_time = current_time
        status = last_alicat_status
        if trans_data and status:
            voltage, pressure_calc = trans_data
            baro = status.barometric_pressure or 14.7
            readings.append(RampReading(
                timestamp=current_time,
                elapsed_time=0.0,
                transducer_voltage=voltage,
                transducer_pressure_calc=pressure_calc,
                alicat_pressure=status.pressure,
                alicat_setpoint=status.setpoint or 0.0,
                alicat_gauge=status.pressure - baro,
                alicat_baro=status.barometric_pressure,
                ramp_rate_commanded=0.0,
                phase='start',
            ))
        time.sleep(0.004)  # 250 Hz LabJack rate
    
    # Start the ramp
    print(f"[3/4] Starting ramp at {rate_psi_s:.1f} PSI/s...")
    ramp_start_time = time.perf_counter()
    
    # Set the ramp rate and target
    alicat.set_ramp_rate(rate_psi_s, time_unit='s')
    alicat.set_pressure(end_pressure)
    
    # Calculate expected ramp duration
    pressure_delta = abs(end_pressure - start_pressure)
    expected_duration = pressure_delta / rate_psi_s if rate_psi_s > 0 else 10.0
    
    # Collect data during ramp
    ramp_complete = False
    last_status_time = ramp_start_time
    
    while not ramp_complete:
        current_time = time.perf_counter()
        elapsed = current_time - ramp_start_time
        
        # Read both sensors
        trans_data = read_raw_transducer(labjack)
        if current_time - last_alicat_time >= 0.05:
            last_alicat_status = alicat.read_status()
            last_alicat_time = current_time
        status = last_alicat_status
        
        if trans_data and status:
            voltage, pressure_calc = trans_data
            baro = status.barometric_pressure or 14.7
            readings.append(RampReading(
                timestamp=current_time,
                elapsed_time=elapsed,
                transducer_voltage=voltage,
                transducer_pressure_calc=pressure_calc,
                alicat_pressure=status.pressure,
                alicat_setpoint=status.setpoint or 0.0,
                alicat_gauge=status.pressure - baro,
                alicat_baro=status.barometric_pressure,
                ramp_rate_commanded=rate_psi_s,
                phase='ramping',
            ))
            
            # Check if we've reached target
            if abs(status.pressure - end_pressure) < 1.0:
                print(f"  Reached target at t={elapsed:.2f}s (P={status.pressure:.2f})")
                ramp_complete = True
            elif elapsed > expected_duration + 10:  # Safety timeout
                print(f"  [WARNING] Timeout at t={elapsed:.2f}s, P={status.pressure:.2f}")
                ramp_complete = True
        
        # Print status every 2 seconds
        if current_time - last_status_time >= 2.0:
            if readings:
                latest = readings[-1]
                print(f"    t={elapsed:5.1f}s | Alicat={latest.alicat_pressure:6.2f} | "
                      f"Transducer={latest.transducer_pressure_calc:6.2f} | N={len(readings)}")
            last_status_time = current_time
        
        time.sleep(0.004)  # 250 Hz target
    
    # Settle at end
    print(f"[4/4] Settling at end pressure for {settle_time:.1f}s...")
    settle_start = time.perf_counter()
    ramp_end_time = time.perf_counter()
    
    while time.perf_counter() - settle_start < settle_time:
        trans_data = read_raw_transducer(labjack)
        current_time = time.perf_counter()
        if current_time - last_alicat_time >= 0.05:
            last_alicat_status = alicat.read_status()
            last_alicat_time = current_time
        status = last_alicat_status
        if trans_data and status:
            voltage, pressure_calc = trans_data
            baro = status.barometric_pressure or 14.7
            readings.append(RampReading(
                timestamp=current_time,
                elapsed_time=current_time - ramp_start_time,
                transducer_voltage=voltage,
                transducer_pressure_calc=pressure_calc,
                alicat_pressure=status.pressure,
                alicat_setpoint=status.setpoint or 0.0,
                alicat_gauge=status.pressure - baro,
                alicat_baro=status.barometric_pressure,
                ramp_rate_commanded=0.0,
                phase='settled',
            ))
        time.sleep(0.004)
    
    print(f"\nRamp complete! Collected {len(readings)} total samples")
    print(f"  Start settle: {sum(1 for r in readings if r.phase == 'start')} samples")
    print(f"  Ramping:      {sum(1 for r in readings if r.phase == 'ramping')} samples")
    print(f"  End settle:   {sum(1 for r in readings if r.phase == 'settled')} samples")
    
    return readings


def save_ramp_data(readings: List[RampReading], output_file: Path, metadata: Dict) -> None:
    """Save ramp data to CSV with metadata header."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write metadata as comments
        for key, value in metadata.items():
            writer.writerow([f'# {key}: {value}'])
        writer.writerow([])  # Empty line
        
        # Write header
        writer.writerow([
            'timestamp', 'elapsed_time', 'phase',
            'transducer_voltage', 'transducer_pressure_calc',
            'alicat_pressure', 'alicat_setpoint', 'alicat_gauge', 'alicat_baro',
            'ramp_rate_commanded',
            'offset_calc'
        ])
        
        # Write data
        for r in readings:
            offset = r.transducer_pressure_calc - r.alicat_pressure
            writer.writerow([
                r.timestamp, r.elapsed_time, r.phase,
                r.transducer_voltage, r.transducer_pressure_calc,
                r.alicat_pressure, r.alicat_setpoint, r.alicat_gauge, r.alicat_baro,
                r.ramp_rate_commanded,
                offset
            ])
    
    print(f"Data saved to: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description='Controlled ramp test')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test')
    parser.add_argument('--rate', type=float, default=5.0,
                       help='Ramp rate in PSI/s (default: 5)')
    parser.add_argument('--start', type=float, default=14.7,
                       help='Start pressure in PSIA (default: 14.7 = atmosphere)')
    parser.add_argument('--end', type=float, default=50.0,
                       help='End pressure in PSIA (default: 50)')
    parser.add_argument('--settle', type=float, default=3.0,
                       help='Settle time in seconds (default: 3)')
    parser.add_argument('--output-dir', type=str, default='scripts/data/20260203',
                        help='Output directory')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*70)
    print("CONTROLLED RAMP TEST")
    print("="*70)
    print(f"Port: {args.port}")
    print(f"Ramp: {args.start:.1f} -> {args.end:.1f} PSIA at {args.rate:.1f} PSI/s")
    print(f"Settle time: {args.settle:.1f}s at each end")
    print("="*70)
    
    # Load config
    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1
    
    # Build controllers
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(args.port, {})
    
    labjack = LabJackController({
        'device_type': labjack_cfg.get('device_type', 'T7'),
        'connection_type': labjack_cfg.get('connection_type', 'USB'),
        'identifier': labjack_cfg.get('identifier', 'ANY'),
        'transducer_ain': port_cfg.get('transducer_ain'),
        'transducer_ain_neg': port_cfg.get('transducer_ain_neg'),
        'transducer_voltage_min': port_cfg.get('transducer_voltage_min', 0.5),
        'transducer_voltage_max': port_cfg.get('transducer_voltage_max', 4.5),
        'transducer_pressure_min': port_cfg.get('transducer_pressure_min', 0.0),
        'transducer_pressure_max': port_cfg.get('transducer_pressure_max', 115.0),
        'transducer_filter_alpha': 0.0,  # No filter
        'transducer_reference': port_cfg.get('transducer_reference', 'absolute'),
        'transducer_offset_psi': 0.0,  # No offset
    })
    
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_alicat_cfg = alicat_cfg.get(args.port, {})
    alicat = AlicatController({
        'com_port': port_alicat_cfg.get('com_port'),
        'address': port_alicat_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': 0.1,
        'pressure_index': alicat_cfg.get('pressure_index'),
        'setpoint_index': alicat_cfg.get('setpoint_index'),
        'gauge_index': alicat_cfg.get('gauge_index'),
        'barometric_index': alicat_cfg.get('barometric_index'),
    })
    
    # Connect
    print("\nConnecting to hardware...")
    if not labjack.configure():
        print(f"[FAIL] LabJack configuration failed")
        return 1
    
    if not alicat.connect():
        print(f"[FAIL] Alicat connection failed")
        labjack.cleanup()
        return 1
    
    print("Connected!")
    
    # Safety check - don't go below atmosphere or above 100 PSI
    safe_start = max(10.0, min(args.start, 100.0))
    safe_end = max(10.0, min(args.end, 100.0))
    
    if safe_start != args.start or safe_end != args.end:
        print(f"\n[SAFETY] Adjusted pressures: {safe_start:.1f} -> {safe_end:.1f} PSIA")
    
    # Run test
    try:
        readings = run_ramp_test(
            labjack, alicat,
            start_pressure=safe_start,
            end_pressure=safe_end,
            rate_psi_s=args.rate,
            settle_time=args.settle,
        )
        
        if readings:
            # Save
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'ramp_{args.port}_r{args.rate:.0f}_{safe_start:.0f}to{safe_end:.0f}_{timestamp}.csv'
            
            metadata = {
                'port': args.port,
                'ramp_rate_psi_s': args.rate,
                'start_pressure_psia': safe_start,
                'end_pressure_psia': safe_end,
                'settle_time_s': args.settle,
                'total_samples': len(readings),
            }
            
            save_ramp_data(readings, output_file, metadata)
        else:
            print("\n[WARNING] No readings collected!")
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as exc:
        print(f"\n[ERROR] Test failed: {exc}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        print("\nCleaning up...")
        try:
            alicat.exhaust()
            time.sleep(1.0)
        except:
            pass
        alicat.disconnect()
        labjack.cleanup()
    
    print("\nTest complete!")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
