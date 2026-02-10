"""
Modular Static Hold Test - Quick verification of static offset at atmosphere.

This is a minimal test to verify:
1. Both sensors read correctly
2. We can collect unfiltered data at high rate
3. We can see the baseline offset at atmosphere

Usage:
    python scripts/quick_static_test.py --port port_a --duration 30
    python scripts/quick_static_test.py --port port_a --duration 30 --no-filter
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
class Reading:
    timestamp: float
    transducer_voltage: float
    transducer_pressure: float
    transducer_pressure_raw: Optional[float]
    alicat_pressure: float
    alicat_setpoint: float
    alicat_barometric: Optional[float]
    alicat_gauge: float


def build_labjack_controller(
    config: Dict[str, Any],
    port: str,
    filter_alpha_override: Optional[float] = None,
) -> LabJackController:
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
        'transducer_reference': port_cfg.get('transducer_reference', 'absolute'),
        'transducer_offset_psi': port_cfg.get('transducer_offset_psi', 0.0),
    }
    
    return LabJackController(controller_config)


def build_alicat_controller(config: Dict[str, Any], port: str) -> AlicatController:
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


def collect_static_data(
    labjack: LabJackController,
    alicat: AlicatController,
    duration: float,
    target_rate_hz: float = 50.0,
) -> List[Reading]:
    """Collect static hold data at maximum reliable rate."""
    readings: List[Reading] = []
    sample_interval = 1.0 / target_rate_hz
    
    print(f"\nCollecting static data for {duration:.1f} seconds at {target_rate_hz:.1f} Hz...")
    print("Press Ctrl+C to stop early\n")
    
    start_time = time.time()
    last_sample_time = start_time
    last_status_time = start_time
    
    try:
        while time.time() - start_time < duration:
            current_time = time.time()
            
            # Sample at target rate
            if current_time - last_sample_time >= sample_interval:
                trans = labjack.read_transducer()
                alicat_status = alicat.read_status()
                
                if trans and alicat_status:
                    baro = alicat_status.barometric_pressure or 14.7
                    readings.append(Reading(
                        timestamp=current_time,
                        transducer_voltage=trans.voltage,
                        transducer_pressure=trans.pressure,
                        transducer_pressure_raw=getattr(trans, 'pressure_raw', None),
                        alicat_pressure=alicat_status.pressure,
                        alicat_setpoint=alicat_status.setpoint or 0.0,
                        alicat_barometric=alicat_status.barometric_pressure,
                        alicat_gauge=alicat_status.pressure - baro,
                    ))
                
                last_sample_time = current_time
            
            # Print status every 2 seconds
            if current_time - last_status_time >= 2.0:
                if readings:
                    latest = readings[-1]
                    offset = latest.transducer_pressure - latest.alicat_pressure
                    elapsed = current_time - start_time
                    print(f"  t={elapsed:5.1f}s | Transducer: {latest.transducer_pressure:6.2f} PSI | "
                          f"Alicat: {latest.alicat_pressure:6.2f} PSIA | Offset: {offset:+7.4f} PSI | "
                          f"N={len(readings)}")
                last_status_time = current_time
            
            time.sleep(0.001)  # Small sleep to prevent CPU spinning
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    
    return readings


def analyze_static_data(readings: List[Reading]) -> Dict[str, float]:
    """Analyze static hold data."""
    if not readings:
        return {}
    
    offsets = [r.transducer_pressure - r.alicat_pressure for r in readings]
    trans_pressures = [r.transducer_pressure for r in readings]
    alicat_pressures = [r.alicat_pressure for r in readings]
    
    results = {
        'n_samples': len(readings),
        'duration': readings[-1].timestamp - readings[0].timestamp,
        'mean_offset': np.mean(offsets),
        'std_offset': np.std(offsets),
        'min_offset': np.min(offsets),
        'max_offset': np.max(offsets),
        'transducer_noise': np.std(trans_pressures),
        'alicat_noise': np.std(alicat_pressures),
        'mean_transducer_pressure': np.mean(trans_pressures),
        'mean_alicat_pressure': np.mean(alicat_pressures),
        'mean_voltage': np.mean([r.transducer_voltage for r in readings]),
    }
    
    return results


def save_to_csv(readings: List[Reading], output_file: Path) -> None:
    """Save readings to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'transducer_voltage', 'transducer_pressure', 
            'transducer_pressure_raw', 'alicat_pressure_psia', 
            'alicat_setpoint_psia', 'alicat_baro_psia', 'alicat_gauge_psig',
            'offset_psi'
        ])
        
        for r in readings:
            offset = r.transducer_pressure - r.alicat_pressure
            writer.writerow([
                r.timestamp, r.transducer_voltage, r.transducer_pressure,
                r.transducer_pressure_raw, r.alicat_pressure,
                r.alicat_setpoint, r.alicat_barometric, r.alicat_gauge,
                offset
            ])
    
    print(f"\nData saved to: {output_file}")


def print_summary(results: Dict[str, float]) -> None:
    """Print analysis summary."""
    print("\n" + "="*70)
    print("STATIC HOLD ANALYSIS SUMMARY")
    print("="*70)
    print(f"Samples collected: {results['n_samples']} over {results['duration']:.1f} seconds")
    print(f"Effective sample rate: {results['n_samples'] / results['duration']:.1f} Hz")
    print()
    print(f"Mean Transducer Pressure: {results['mean_transducer_pressure']:.4f} PSI")
    print(f"Mean Alicat Pressure:     {results['mean_alicat_pressure']:.4f} PSIA")
    print(f"Mean Voltage:             {results['mean_voltage']:.6f} V")
    print()
    print(f"Mean Offset:              {results['mean_offset']:.4f} PSI (Transducer - Alicat)")
    print(f"Offset Std Dev:           {results['std_offset']:.4f} PSI")
    print(f"Offset Range:             [{results['min_offset']:.4f}, {results['max_offset']:.4f}] PSI")
    print()
    print(f"Transducer Noise (std):   {results['transducer_noise']:.4f} PSI")
    print(f"Alicat Noise (std):       {results['alicat_noise']:.4f} PSI")
    print("="*70)
    
    # Recommendation
    print(f"\nRecommendation:")
    print(f"  Current transducer_offset_psi in config: check stinger_config.yaml")
    print(f"  Observed offset at atmosphere: {results['mean_offset']:.4f} PSI")
    print(f"  If transducer should match Alicat at atmosphere (~14.7 PSIA),")
    print(f"  adjust transducer_offset_psi by {-results['mean_offset']:.2f} PSI")


def main() -> int:
    parser = argparse.ArgumentParser(description='Quick static hold test at atmosphere')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test (default: port_a)')
    parser.add_argument('--duration', type=float, default=30.0,
                       help='Test duration in seconds (default: 30)')
    parser.add_argument('--sample-rate', type=float, default=50.0,
                       help='Target sample rate in Hz (default: 50)')
    parser.add_argument('--no-filter', action='store_true',
                       help='Disable LabJack transducer filtering')
    parser.add_argument('--output-dir', type=str, default='scripts/data/20260203',
                        help='Output directory for CSV files')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*70)
    print("QUICK STATIC HOLD TEST")
    print("="*70)
    print(f"Port: {args.port}")
    print(f"Duration: {args.duration:.1f} seconds")
    print(f"Target Sample Rate: {args.sample_rate:.1f} Hz")
    print(f"Transducer Filter: {'disabled' if args.no_filter else 'enabled'}")
    print("="*70)
    
    # Load config and build controllers
    try:
        config = load_config()
    except Exception as exc:
        print(f"[FAIL] Could not load config: {exc}")
        return 1
    
    filter_override = 0.0 if args.no_filter else None
    labjack = build_labjack_controller(config, args.port, filter_alpha_override=filter_override)
    alicat = build_alicat_controller(config, args.port)
    
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
    
    # Exhaust to atmosphere before collecting
    print("\nExhausting to atmosphere...")
    alicat.exhaust()
    time.sleep(2.0)
    
    # Check initial readings
    print("\nChecking initial sensor readings...")
    trans_test = labjack.read_transducer()
    alicat_test = alicat.read_status()
    
    if trans_test and alicat_test:
        print(f"  Transducer: {trans_test.pressure:.2f} PSI ({trans_test.voltage:.4f} V)")
        print(f"  Alicat: {alicat_test.pressure:.2f} PSIA (setpoint: {alicat_test.setpoint:.2f})")
        print(f"  Initial offset: {trans_test.pressure - alicat_test.pressure:.4f} PSI")
    else:
        print("  [WARNING] Could not read one or both sensors initially")
    
    # Run test
    try:
        readings = collect_static_data(labjack, alicat, args.duration, args.sample_rate)
        
        if readings:
            # Analyze
            results = analyze_static_data(readings)
            print_summary(results)
            
            # Save
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'quick_static_{args.port}_{timestamp}.csv'
            save_to_csv(readings, output_file)
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
            status = alicat.read_status()
            if status and status.barometric_pressure is not None:
                alicat.set_pressure(status.barometric_pressure)
        except:
            pass
        alicat.exhaust()
        time.sleep(1.0)
        alicat.disconnect()
        labjack.cleanup()
    
    print("\nTest complete!")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
