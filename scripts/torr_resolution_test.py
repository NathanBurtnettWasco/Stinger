"""
Torr Resolution Analysis - Characterize measurement resolution in Torr units.

This script:
1. Configures Alicat to Torr units (native)
2. Analyzes actual resolution and quantization
3. Measures noise floor in Torr
4. Tests ultra-slow ramps (1-10 Torr/s)

Usage:
    python scripts/torr_resolution_test.py --port port_a --duration 30
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)

# Unit conversion
PSI_PER_TORR = 0.0193368  # 1 Torr = 0.0193368 PSI
TORR_PER_PSI = 51.715  # 1 PSI = 51.715 Torr

# DCU unit codes from PTP service
UNIT_CODE_TORR = 13
UNIT_CODE_PSI = 10


@dataclass
class TorrReading:
    timestamp: float
    transducer_voltage: float
    transducer_pressure_psi: float
    transducer_pressure_torr: float
    alicat_pressure: float  # In current units
    alicat_setpoint: float
    alicat_gauge: float
    alicat_baro: Optional[float]
    alicat_units: str


def read_raw_transducer(labjack: LabJackController) -> Optional[Tuple[float, float]]:
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


def set_alicat_units_torr(alicat: AlicatController) -> bool:
    """Configure Alicat to use Torr units for pressure."""
    # DCU command: DCU <stat> <group> <unit_value> <override>
    # stat=2 (absolute pressure), group=0, unit=13 (Torr), override=0
    # First query current units
    response = alicat._send_command("DCU 2")
    print(f"    Current DCU response: {response}")
    
    # Set to Torr
    response = alicat._send_command(f"DCU 2 0 {UNIT_CODE_TORR} 0")
    print(f"    Set DCU response: {response}")
    time.sleep(0.2)
    
    # Re-query to confirm
    confirm = alicat._send_command("DCU 2")
    print(f"    Confirm DCU response: {confirm}")
    if confirm and (" 13" in confirm or "Torr" in confirm or "TORR" in confirm):
        print(f"  [OK] Set units to Torr (code {UNIT_CODE_TORR})")
        return True
    print(f"  [FAIL] Could not confirm Torr units: {confirm}")
    return False


def get_alicat_units(alicat: AlicatController) -> str:
    """Query current Alicat units."""
    response = alicat._send_command("DCU 2")
    if response:
        parts = response.split()
        # Example responses: "A 10 PSIA" or "A 13 Torr"
        unit_code = None
        for part in parts:
            if part.isdigit():
                unit_code = part
                break
        if unit_code:
            unit_map = {
                "10": "PSI",
                "13": "Torr",
                "21": "Torr",
                "12": "mTorr",
            }
            return unit_map.get(unit_code, f"Code_{unit_code}")
        if any(token.upper().startswith("TORR") for token in parts):
            return "Torr"
    return "Unknown"


def analyze_resolution(readings: List[TorrReading], alicat_units: str) -> Dict[str, Any]:
    """Analyze quantization and resolution."""
    
    # Convert everything to Torr for analysis
    if alicat_units == "Torr":
        alicat_torr = [r.alicat_pressure for r in readings]
        transducer_torr = [r.transducer_pressure_torr for r in readings]
    else:
        # Convert from PSI
        alicat_torr = [r.alicat_pressure * TORR_PER_PSI for r in readings]
        transducer_torr = [r.transducer_pressure_torr for r in readings]
    
    # Calculate differences between consecutive readings to find quantization steps
    alicat_diffs = np.diff(alicat_torr)
    transducer_diffs = np.diff(transducer_torr)
    
    # Find unique values (quantization levels)
    alicat_unique = np.unique(alicat_torr)
    transducer_unique = np.unique(transducer_torr)
    
    # Calculate resolution from voltage steps
    voltages = [r.transducer_voltage for r in readings]
    voltage_diffs = np.diff(voltages)
    
    results = {
        "alicat_resolution_torr": np.min(np.abs(alicat_diffs[alicat_diffs != 0])) if len(alicat_diffs[alicat_diffs != 0]) > 0 else None,
        "alicat_quantization_levels": len(alicat_unique),
        "alicat_noise_torr": np.std(alicat_torr),
        "alicat_mean_torr": np.mean(alicat_torr),
        "transducer_resolution_torr": np.min(np.abs(transducer_diffs[transducer_diffs != 0])) if len(transducer_diffs[transducer_diffs != 0]) > 0 else None,
        "transducer_quantization_levels": len(transducer_unique),
        "transducer_noise_torr": np.std(transducer_torr),
        "transducer_mean_torr": np.mean(transducer_torr),
        "voltage_resolution_mv": np.min(np.abs(voltage_diffs[voltage_diffs != 0])) * 1000 if len(voltage_diffs[voltage_diffs != 0]) > 0 else None,
        "voltage_noise_mv": np.std(voltages) * 1000,
        "total_samples": len(readings),
    }
    
    return results


def print_resolution_analysis(results: Dict[str, Any]) -> None:
    """Print resolution analysis in Torr."""
    print("\n" + "="*70)
    print("RESOLUTION ANALYSIS (in Torr)")
    print("="*70)
    
    print(f"\nAlicat:")
    if results["alicat_resolution_torr"]:
        print(f"  Resolution: {results['alicat_resolution_torr']:.3f} Torr")
    print(f"  Quantization levels: {results['alicat_quantization_levels']}")
    print(f"  Noise (std): {results['alicat_noise_torr']:.3f} Torr")
    print(f"  Mean pressure: {results['alicat_mean_torr']:.2f} Torr")
    
    print(f"\nTransducer (via LabJack):")
    if results["transducer_resolution_torr"]:
        print(f"  Resolution: {results['transducer_resolution_torr']:.4f} Torr")
    print(f"  Quantization levels: {results['transducer_quantization_levels']}")
    print(f"  Noise (std): {results['transducer_noise_torr']:.4f} Torr")
    print(f"  Mean pressure: {results['transducer_mean_torr']:.2f} Torr")
    
    print(f"\nVoltage (LabJack ADC):")
    if results["voltage_resolution_mv"]:
        print(f"  Resolution: {results['voltage_resolution_mv']:.6f} mV")
    print(f"  Noise (std): {results['voltage_noise_mv']:.6f} mV")
    
    print(f"\nTotal samples: {results['total_samples']}")
    print("="*70)


def collect_torr_data(
    labjack: LabJackController,
    alicat: AlicatController,
    duration: float,
    target_rate_hz: float = 50.0,
    alicat_rate_hz: float = 10.0,
) -> Tuple[List[TorrReading], str]:
    """Collect data with Alicat in Torr units."""
    readings: List[TorrReading] = []
    sample_interval = 1.0 / target_rate_hz
    alicat_interval = 1.0 / alicat_rate_hz if alicat_rate_hz > 0 else 0.1
    
    # Get current units
    alicat_units = get_alicat_units(alicat)
    print(f"  Current Alicat units: {alicat_units}")
    
    # Set to Torr if needed
    if alicat_units != "Torr":
        print("  Setting Alicat to Torr units...")
        if set_alicat_units_torr(alicat):
            alicat_units = "Torr"
            time.sleep(0.5)  # Let it settle
    
    print(f"\nCollecting data for {duration:.1f} seconds...")
    print(f"Target rate: {target_rate_hz:.1f} Hz")
    print(f"Units: {alicat_units}")
    print("Press Ctrl+C to stop early\n")
    
    start_time = time.perf_counter()
    last_sample_time = start_time
    last_status_time = start_time
    last_alicat_time = 0.0
    last_alicat_status = None
    
    try:
        while time.perf_counter() - start_time < duration:
            current_time = time.perf_counter()
            
            if current_time - last_sample_time >= sample_interval:
                trans_data = read_raw_transducer(labjack)
                if current_time - last_alicat_time >= alicat_interval:
                    last_alicat_status = alicat.read_status()
                    last_alicat_time = current_time
                status = last_alicat_status
                
                if trans_data and status:
                    voltage, pressure_psi = trans_data
                    
                    readings.append(TorrReading(
                        timestamp=current_time,
                        transducer_voltage=voltage,
                        transducer_pressure_psi=pressure_psi,
                        transducer_pressure_torr=pressure_psi * TORR_PER_PSI,
                        alicat_pressure=status.pressure,
                        alicat_setpoint=status.setpoint or 0.0,
                        alicat_gauge=status.pressure - (status.barometric_pressure or 14.7 * TORR_PER_PSI),
                        alicat_baro=status.barometric_pressure,
                        alicat_units=alicat_units,
                    ))
                
                last_sample_time = current_time
            
            # Print status every 2 seconds
            if current_time - last_status_time >= 2.0:
                if readings:
                    latest = readings[-1]
                    elapsed = current_time - start_time
                    
                    if alicat_units == "Torr":
                        alicat_torr = latest.alicat_pressure
                    else:
                        alicat_torr = latest.alicat_pressure * TORR_PER_PSI
                    
                    offset_torr = latest.transducer_pressure_torr - alicat_torr
                    
                    print(f"  t={elapsed:5.1f}s | Transducer={latest.transducer_pressure_torr:8.2f} Torr | "
                          f"Alicat={alicat_torr:8.2f} Torr | Offset={offset_torr:+6.2f} Torr | N={len(readings)}")
                
                last_status_time = current_time
            
            time.sleep(0.0001)  # Minimal sleep
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    
    return readings, alicat_units


def save_torr_data(readings: List[TorrReading], output_file: Path, alicat_units: str) -> None:
    """Save data with Torr conversion."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'transducer_voltage', 'transducer_pressure_psi', 
            'transducer_pressure_torr', 'alicat_pressure_raw', 'alicat_units',
            'alicat_setpoint', 'alicat_gauge', 'alicat_baro',
            'offset_torr'
        ])
        
        for r in readings:
            if alicat_units == "Torr":
                alicat_torr = r.alicat_pressure
            else:
                alicat_torr = r.alicat_pressure * TORR_PER_PSI
            
            offset = r.transducer_pressure_torr - alicat_torr
            
            writer.writerow([
                r.timestamp, r.transducer_voltage, r.transducer_pressure_psi,
                r.transducer_pressure_torr, r.alicat_pressure, r.alicat_units,
                r.alicat_setpoint, r.alicat_gauge, r.alicat_baro,
                offset
            ])
    
    print(f"\nData saved to: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description='Torr resolution analysis')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test')
    parser.add_argument('--duration', type=float, default=30.0,
                       help='Test duration in seconds')
    parser.add_argument('--sample-rate', type=float, default=50.0,
                        help='Target sample rate in Hz')
    parser.add_argument('--alicat-rate', type=float, default=10.0,
                        help='Alicat poll rate in Hz (default: 10)')
    parser.add_argument('--output-dir', type=str, default='scripts/data/20260203',
                        help='Output directory')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*70)
    print("TORR RESOLUTION ANALYSIS")
    print("="*70)
    print(f"Port: {args.port}")
    print(f"Duration: {args.duration:.1f} seconds")
    print(f"Target Sample Rate: {args.sample_rate:.1f} Hz")
    print(f"Alicat Poll Rate: {args.alicat_rate:.1f} Hz")
    print(f"1 PSI = {TORR_PER_PSI:.3f} Torr")
    print(f"1 Torr = {PSI_PER_TORR:.6f} PSI")
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
        'transducer_filter_alpha': 0.0,
        'transducer_reference': port_cfg.get('transducer_reference', 'absolute'),
        'transducer_offset_psi': 0.0,
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
    
    print("Connected successfully!")
    
    # Exhaust to atmosphere first
    print("\nExhausting to atmosphere...")
    alicat.exhaust()
    time.sleep(2.0)
    
    # Collect data
    try:
        readings, alicat_units = collect_torr_data(
            labjack, alicat, args.duration, args.sample_rate, args.alicat_rate
        )
        
        if readings:
            # Analyze
            results = analyze_resolution(readings, alicat_units)
            print_resolution_analysis(results)
            
            # Save
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'torr_resolution_{args.port}_{timestamp}.csv'
            save_torr_data(readings, output_file, alicat_units)
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
            # Reset to PSI before disconnecting (for compatibility)
            print("  Resetting Alicat to PSI units...")
            alicat._send_command(f"DCU 2 0 {UNIT_CODE_PSI} 0")
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
