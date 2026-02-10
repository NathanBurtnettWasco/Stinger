"""
Raw Data Collection Test - No offsets, no filtering, just raw sensor readings.

This test:
1. Exhausts Alicat to atmosphere first
2. Collects truly raw transducer voltage and calculated pressure (before offset)
3. Collects Alicat data at maximum possible rate
4. Shows timing statistics

Usage:
    python scripts/raw_data_test.py --port port_a --duration 30
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
class RawReading:
    timestamp: float
    transducer_voltage: float
    transducer_pressure_calc: float  # From voltage, before any offset
    alicat_pressure: float
    alicat_setpoint: float
    alicat_gauge: float
    alicat_baro: Optional[float]


def read_raw_transducer(labjack: LabJackController) -> Optional[tuple[float, float]]:
    """Read transducer voltage and calculated pressure without filtering or offset."""
    if not labjack.hardware_available():
        voltage = 0.976  # Approximate atmosphere voltage
        pressure_calc = 14.7
        return voltage, pressure_calc
    
    if labjack.transducer_ain is None:
        return None
    
    handle = labjack._shared_handle
    if handle is None:
        return None
    
    try:
        from labjack import ljm
        voltage = ljm.eReadName(handle, f'AIN{labjack.transducer_ain}')
        
        # Calculate pressure from voltage (same formula as LabJackController)
        voltage_range = labjack.voltage_max - labjack.voltage_min
        pressure_range = labjack.pressure_max - labjack.pressure_min
        if voltage_range > 0:
            pressure_calc = (voltage - labjack.voltage_min) / voltage_range * pressure_range + labjack.pressure_min
        else:
            pressure_calc = labjack.pressure_min
        
        return voltage, pressure_calc
    except Exception as exc:
        logger.error('Raw transducer read error: %s', exc)
        return None


def collect_raw_data(
    labjack: LabJackController,
    alicat: AlicatController,
    duration: float,
) -> List[RawReading]:
    """Collect raw data at maximum rate with timing statistics."""
    readings: List[RawReading] = []
    
    print(f"\nCollecting data for {duration:.1f} seconds...")
    print("Target: LabJack at ~240 Hz, Alicat at ~12 Hz")
    print("Press Ctrl+C to stop early\n")
    
    start_time = time.perf_counter()
    last_sample_time = start_time
    last_alicat_time = start_time
    last_status_time = start_time
    
    # Target 4ms interval for LabJack (250 Hz)
    lj_interval = 0.004
    # Target 80ms interval for Alicat (12.5 Hz)
    alicat_interval = 0.080
    
    alicat_reading = None
    
    try:
        while time.perf_counter() - start_time < duration:
            current_time = time.perf_counter()
            
            # Read Alicat at its own rate
            if current_time - last_alicat_time >= alicat_interval:
                try:
                    status = alicat.read_status()
                    if status:
                        baro = status.barometric_pressure or 14.7
                        alicat_reading = {
                            'pressure': status.pressure,
                            'setpoint': status.setpoint or 0.0,
                            'gauge': status.pressure - baro,
                            'baro': baro,
                        }
                except Exception as e:
                    logger.debug(f"Alicat read error: {e}")
                last_alicat_time = current_time
            
            # Read LabJack at high rate
            if current_time - last_sample_time >= lj_interval:
                trans_data = read_raw_transducer(labjack)
                if trans_data:
                    voltage, pressure_calc = trans_data
                    
                    # Use last known Alicat reading or zeros
                    if alicat_reading:
                        readings.append(RawReading(
                            timestamp=current_time,
                            transducer_voltage=voltage,
                            transducer_pressure_calc=pressure_calc,
                            alicat_pressure=alicat_reading['pressure'],
                            alicat_setpoint=alicat_reading['setpoint'],
                            alicat_gauge=alicat_reading['gauge'],
                            alicat_baro=alicat_reading['baro'],
                        ))
                    else:
                        readings.append(RawReading(
                            timestamp=current_time,
                            transducer_voltage=voltage,
                            transducer_pressure_calc=pressure_calc,
                            alicat_pressure=0.0,
                            alicat_setpoint=0.0,
                            alicat_gauge=0.0,
                            alicat_baro=None,
                        ))
                
                last_sample_time = current_time
            
            # Print status every 2 seconds
            if current_time - last_status_time >= 2.0:
                elapsed = current_time - start_time
                if readings:
                    latest = readings[-1]
                    lj_rate = len(readings) / elapsed
                    print(f"  t={elapsed:5.1f}s | LJ={latest.transducer_pressure_calc:6.2f} PSI ({latest.transducer_voltage:.4f}V) | "
                          f"Alicat={latest.alicat_pressure:6.2f} PSIA | N={len(readings)} ({lj_rate:.1f} Hz)")
                last_status_time = current_time
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.0001)
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    
    return readings


def analyze_raw_data(readings: List[RawReading]) -> Dict[str, Any]:
    """Analyze raw data collection."""
    if not readings:
        return {}
    
    # Calculate rates
    duration = readings[-1].timestamp - readings[0].timestamp
    total_samples = len(readings)
    overall_rate = total_samples / duration if duration > 0 else 0
    
    # Separate LabJack-only samples from paired samples
    lj_voltages = [r.transducer_voltage for r in readings]
    lj_pressures = [r.transducer_pressure_calc for r in readings]
    
    # Only count Alicat samples where we have valid data
    valid_alicat = [r for r in readings if r.alicat_pressure > 0]
    alicat_pressures = [r.alicat_pressure for r in valid_alicat]
    
    # Calculate deltas
    offsets = []
    for r in readings:
        if r.alicat_pressure > 0:
            offsets.append(r.transducer_pressure_calc - r.alicat_pressure)
    
    results = {
        'total_duration': duration,
        'total_samples': total_samples,
        'overall_rate_hz': overall_rate,
        'valid_alicat_samples': len(valid_alicat),
        'alicat_rate_hz': len(valid_alicat) / duration if duration > 0 else 0,
        'mean_lj_voltage': np.mean(lj_voltages),
        'std_lj_voltage': np.std(lj_voltages),
        'mean_lj_pressure': np.mean(lj_pressures),
        'std_lj_pressure': np.std(lj_pressures),
        'mean_alicat_pressure': np.mean(alicat_pressures) if alicat_pressures else 0,
        'std_alicat_pressure': np.std(alicat_pressures) if alicat_pressures else 0,
        'mean_offset': np.mean(offsets) if offsets else 0,
        'std_offset': np.std(offsets) if offsets else 0,
    }
    
    return results


def save_raw_data(readings: List[RawReading], output_file: Path) -> None:
    """Save raw data to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'transducer_voltage', 'transducer_pressure_calc',
            'alicat_pressure', 'alicat_setpoint', 'alicat_gauge', 'alicat_baro',
            'offset_calc'
        ])
        
        for r in readings:
            offset = r.transducer_pressure_calc - r.alicat_pressure if r.alicat_pressure > 0 else 0
            writer.writerow([
                r.timestamp, r.transducer_voltage, r.transducer_pressure_calc,
                r.alicat_pressure, r.alicat_setpoint, r.alicat_gauge, r.alicat_baro,
                offset
            ])
    
    print(f"\nData saved to: {output_file}")


def print_summary(results: Dict[str, Any]) -> None:
    """Print analysis summary."""
    print("\n" + "="*70)
    print("RAW DATA COLLECTION SUMMARY")
    print("="*70)
    print(f"Duration: {results['total_duration']:.1f} seconds")
    print(f"Total samples: {results['total_samples']}")
    print(f"Overall rate: {results['overall_rate_hz']:.1f} Hz")
    print()
    print(f"Valid Alicat samples: {results['valid_alicat_samples']}")
    print(f"Alicat effective rate: {results['alicat_rate_hz']:.1f} Hz")
    print()
    print(f"LabJack Voltage: {results['mean_lj_voltage']:.6f} ± {results['std_lj_voltage']:.6f} V")
    print(f"LabJack Pressure (calc): {results['mean_lj_pressure']:.4f} ± {results['std_lj_pressure']:.4f} PSI")
    print()
    print(f"Alicat Pressure: {results['mean_alicat_pressure']:.4f} ± {results['std_alicat_pressure']:.4f} PSIA")
    print()
    print(f"Mean Offset: {results['mean_offset']:.4f} PSI")
    print(f"Offset Std:  {results['std_offset']:.4f} PSI")
    print("="*70)


def main() -> int:
    parser = argparse.ArgumentParser(description='Raw data collection test')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test')
    parser.add_argument('--duration', type=float, default=30.0,
                       help='Test duration in seconds')
    parser.add_argument('--output-dir', type=str, default='scripts/data/atmosphere_20260203',
                       help='Output directory')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*70)
    print("RAW DATA COLLECTION TEST")
    print("="*70)
    print(f"Port: {args.port}")
    print(f"Duration: {args.duration:.1f} seconds")
    print("Note: No offsets applied, no filtering")
    print("="*70)
    
    # Load config
    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1
    
    # Build controllers (no filtering, but we still need to init LabJack properly)
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(args.port, {})
    
    labjack_config = {
        'device_type': labjack_cfg.get('device_type', 'T7'),
        'connection_type': labjack_cfg.get('connection_type', 'USB'),
        'identifier': labjack_cfg.get('identifier', 'ANY'),
        'transducer_ain': port_cfg.get('transducer_ain'),
        'transducer_ain_neg': port_cfg.get('transducer_ain_neg'),
        'transducer_voltage_min': port_cfg.get('transducer_voltage_min', 0.5),
        'transducer_voltage_max': port_cfg.get('transducer_voltage_max', 4.5),
        'transducer_pressure_min': port_cfg.get('transducer_pressure_min', 0.0),
        'transducer_pressure_max': port_cfg.get('transducer_pressure_max', 115.0),
        'transducer_filter_alpha': 0.0,  # Disable filter
        'transducer_reference': port_cfg.get('transducer_reference', 'absolute'),
        'transducer_offset_psi': 0.0,  # No offset for raw reading
    }
    labjack = LabJackController(labjack_config)
    
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_alicat_cfg = alicat_cfg.get(args.port, {})
    alicat = AlicatController({
        'com_port': port_alicat_cfg.get('com_port'),
        'address': port_alicat_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': 0.02,  # Shorter timeout for faster reads
        'pressure_index': alicat_cfg.get('pressure_index'),
        'setpoint_index': alicat_cfg.get('setpoint_index'),
        'gauge_index': alicat_cfg.get('gauge_index'),
        'barometric_index': alicat_cfg.get('barometric_index'),
    })
    
    # Connect
    print("\nConnecting to hardware...")
    if not labjack.configure():
        print(f"[FAIL] LabJack configuration failed: {labjack._last_status}")
        return 1
    
    if not alicat.connect():
        print(f"[FAIL] Alicat connection failed: {alicat._last_status}")
        labjack.cleanup()
        return 1
    
    print("Connected successfully!")
    
    # Exhaust to atmosphere first
    print("\nExhausting to atmosphere...")
    alicat.exhaust()
    time.sleep(2.0)
    
    # Check initial state
    print("\nChecking initial readings...")
    trans_test = read_raw_transducer(labjack)
    alicat_test = alicat.read_status()
    
    if trans_test and alicat_test:
        voltage, pressure = trans_test
        print(f"  Transducer: {pressure:.2f} PSI ({voltage:.4f} V)")
        print(f"  Alicat: {alicat_test.pressure:.2f} PSIA")
        print(f"  Current offset: {pressure - alicat_test.pressure:.4f} PSI")
    
    # Run collection
    try:
        readings = collect_raw_data(labjack, alicat, args.duration)
        
        if readings:
            results = analyze_raw_data(readings)
            print_summary(results)
            
            # Save
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'raw_data_{args.port}_{timestamp}.csv'
            save_raw_data(readings, output_file)
        else:
            print("\n[WARNING] No readings collected!")
            
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
