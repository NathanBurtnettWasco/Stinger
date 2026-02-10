"""
Comprehensive Transducer-Alicat Correlation Test Design

This script runs a systematic test to:
1. Determine the "perfect" offset by including static holds (0 ramp rate)
2. Quantify offset vs ramp rate relationship  
3. Quantify noise vs ramp rate for both sensors

Usage:
    python scripts/comprehensive_correlation_test.py --port port_a
    python scripts/comprehensive_correlation_test.py --both-ports
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
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)


@dataclass
class TestSegment:
    """A segment of the test with specific parameters."""
    segment_type: str  # 'static', 'ramp_up', 'ramp_down'
    ramp_rate: float  # 0 for static, positive for ramps
    target_pressure: float
    duration: float  # seconds for static, calculated for ramps
    settle_time: float = 2.0  # seconds to settle before recording


@dataclass
class CorrelationReading:
    """A single synchronized reading."""
    timestamp: float
    segment_id: int
    segment_type: str
    ramp_rate: float
    transducer_voltage: float
    transducer_pressure: float
    alicat_pressure: float
    alicat_setpoint: float
    offset_absolute: float
    offset_gauge: float
    transducer_pressure_raw: Optional[float] = None  # before offset (raw for calibration)
    alicat_barometric: Optional[float] = None


def design_test_sequence() -> List[TestSegment]:
    """
    Design a comprehensive test sequence.
    
    Strategy:
    1. Start at atmosphere
    2. Static holds at key pressures (0 ramp rate = "truth")
    3. Ramps at multiple rates between static holds
    4. Include bidirectional ramps to check hysteresis
    """
    segments = []
    
    # Static baseline at atmosphere (most important for offset calibration)
    segments.append(TestSegment('static', 0.0, 14.7, 30.0, 5.0))
    
    # Test pressures to visit
    test_pressures = [20.0, 30.0, 50.0, 80.0, 100.0, 80.0, 50.0, 30.0, 20.0, 14.7]
    
    # Ramp rates to test (including very slow for comparison)
    ramp_rates = [0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    
    current_pressure = 14.7
    
    for target in test_pressures:
        # Static hold at this pressure (the "truth" reading)
        segments.append(TestSegment('static', 0.0, target, 20.0, 3.0))
        
        # Ramps at different rates to next target
        if target != current_pressure:
            direction = 'ramp_up' if target > current_pressure else 'ramp_down'
            
            # For each ramp rate, do a partial ramp then return
            for rate in ramp_rates[1:]:  # Skip 0
                # Ramp to target
                delta = abs(target - current_pressure)
                duration = delta / rate if rate > 0 else 10.0
                segments.append(TestSegment(direction, rate, target, duration, 0.5))
                
                # Brief static hold
                segments.append(TestSegment('static', 0.0, target, 5.0, 2.0))
                
                # Return to previous pressure (to check hysteresis)
                segments.append(TestSegment(
                    'ramp_down' if direction == 'ramp_up' else 'ramp_up',
                    rate, current_pressure, duration, 0.5
                ))
                
                # Brief static hold
                segments.append(TestSegment('static', 0.0, current_pressure, 5.0, 2.0))
        
        current_pressure = target
    
    # Final static at atmosphere
    segments.append(TestSegment('static', 0.0, 14.7, 30.0, 5.0))
    
    return segments


def run_comprehensive_test(
    labjack: LabJackController,
    alicat: AlicatController,
    segments: List[TestSegment],
    sample_rate_hz: float = 50.0,  # Higher sample rate for noise analysis
    output_file: Optional[Path] = None
) -> List[CorrelationReading]:
    """
    Run the comprehensive test sequence.
    """
    readings: List[CorrelationReading] = []
    sample_interval = 1.0 / sample_rate_hz
    
    print(f"Starting comprehensive test with {len(segments)} segments")
    print(f"Sample rate: {sample_rate_hz} Hz ({sample_interval*1000:.1f} ms interval)")
    
    for seg_idx, segment in enumerate(segments):
        print(f"\n{'='*60}")
        print(f"Segment {seg_idx + 1}/{len(segments)}: {segment.segment_type}")
        print(f"  Ramp rate: {segment.ramp_rate} PSI/s")
        print(f"  Target: {segment.target_pressure:.2f} PSIA")
        print(f"  Duration: {segment.duration:.1f}s")
        
        # Execute the segment
        if segment.segment_type == 'static':
            readings.extend(_run_static_segment(
                labjack, alicat, segment, seg_idx, sample_interval
            ))
        else:
            readings.extend(_run_ramp_segment(
                labjack, alicat, segment, seg_idx, sample_interval
            ))
    
    return readings


def _run_static_segment(
    labjack: LabJackController,
    alicat: AlicatController,
    segment: TestSegment,
    seg_id: int,
    sample_interval: float
) -> List[CorrelationReading]:
    """Run a static hold segment."""
    readings = []
    
    # Set pressure and wait for settle
    print(f"  Setting pressure to {segment.target_pressure:.2f} PSIA...")
    alicat.set_pressure(segment.target_pressure)
    
    print(f"  Settling for {segment.settle_time:.1f}s...")
    time.sleep(segment.settle_time)
    
    # Record data
    print(f"  Recording for {segment.duration:.1f}s...")
    start_time = time.time()
    last_sample = start_time
    
    while time.time() - start_time < segment.duration:
        current_time = time.time()
        if current_time - last_sample >= sample_interval:
            reading = _take_reading(labjack, alicat, seg_id, segment)
            if reading:
                readings.append(reading)
            last_sample = current_time
        time.sleep(0.001)
    
    # Calculate and display statistics for this segment
    if readings:
        offsets = [r.offset_absolute for r in readings]
        noise_transducer = np.std([r.transducer_pressure for r in readings])
        noise_alicat = np.std([r.alicat_pressure for r in readings])
        
        print(f"  Static hold complete:")
        print(f"    Mean offset: {np.mean(offsets):.4f} PSI")
        print(f"    Offset std: {np.std(offsets):.4f} PSI")
        print(f"    Transducer noise (std): {noise_transducer:.4f} PSI")
        print(f"    Alicat noise (std): {noise_alicat:.4f} PSI")
        print(f"    Samples: {len(readings)}")
    
    return readings


def _run_ramp_segment(
    labjack: LabJackController,
    alicat: AlicatController,
    segment: TestSegment,
    seg_id: int,
    sample_interval: float
) -> List[CorrelationReading]:
    """Run a ramp segment."""
    readings = []
    
    # Set ramp rate
    if segment.ramp_rate > 0:
        alicat.set_ramp_rate(segment.ramp_rate, time_unit='s')
    
    # Start the ramp
    alicat.set_pressure(segment.target_pressure)
    
    print(f"  Ramping to {segment.target_pressure:.2f} PSIA at {segment.ramp_rate} PSI/s...")
    
    start_time = time.time()
    last_sample = start_time
    last_status = start_time
    
    while time.time() - start_time < segment.duration + 5.0:  # Extra buffer
        current_time = time.time()
        
        # Sample at specified rate
        if current_time - last_sample >= sample_interval:
            reading = _take_reading(labjack, alicat, seg_id, segment)
            if reading:
                readings.append(reading)
            last_sample = current_time
        
        # Status update every 2 seconds
        if current_time - last_status >= 2.0:
            if readings:
                latest = readings[-1]
                print(f"    t={current_time-start_time:.1f}s | "
                      f"P_alicat={latest.alicat_pressure:.2f} | "
                      f"P_transducer={latest.transducer_pressure:.2f} | "
                      f"Offset={latest.offset_absolute:+.3f}")
            last_status = current_time
        
        # Check if we've reached target
        status = alicat.read_status()
        if status and abs(status.pressure - segment.target_pressure) < 0.3:
            print(f"  Reached target (diff: {abs(status.pressure - segment.target_pressure):.3f} PSI)")
            break
        
        time.sleep(0.001)
    
    if readings:
        # Calculate noise during ramp
        noise_transducer = np.std([r.transducer_pressure for r in readings])
        noise_alicat = np.std([r.alicat_pressure for r in readings])
        
        print(f"  Ramp complete:")
        print(f"    Transducer noise (std): {noise_transducer:.4f} PSI")
        print(f"    Alicat noise (std): {noise_alicat:.4f} PSI")
        print(f"    Samples: {len(readings)}")
    
    return readings


def _take_reading(
    labjack: LabJackController,
    alicat: AlicatController,
    seg_id: int,
    segment: TestSegment
) -> Optional[CorrelationReading]:
    """Take a synchronized reading from both sensors."""
    trans = labjack.read_transducer()
    alicat_status = alicat.read_status()
    
    if not trans or not alicat_status:
        return None
    
    baro = alicat_status.barometric_pressure or 14.7
    pressure_raw = getattr(trans, 'pressure_raw', None)
    if pressure_raw is None:
        pressure_raw = trans.pressure

    return CorrelationReading(
        timestamp=time.time(),
        segment_id=seg_id,
        segment_type=segment.segment_type,
        ramp_rate=segment.ramp_rate,
        transducer_voltage=trans.voltage,
        transducer_pressure=trans.pressure,
        transducer_pressure_raw=pressure_raw,
        alicat_pressure=alicat_status.pressure,
        alicat_setpoint=alicat_status.setpoint or 0.0,
        alicat_barometric=alicat_status.barometric_pressure,
        offset_absolute=trans.pressure - alicat_status.pressure,
        offset_gauge=trans.pressure - (alicat_status.pressure - baro),
    )


def save_correlation_data(readings: List[CorrelationReading], output_file: Path) -> None:
    """Save all correlation data to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'segment_id', 'segment_type', 'ramp_rate_psi_s',
            'transducer_voltage', 'transducer_pressure_psi', 'transducer_pressure_raw_psi',
            'alicat_pressure_psia', 'alicat_setpoint_psia', 'alicat_baro_psia',
            'offset_absolute', 'offset_gauge',
        ])
        for r in readings:
            writer.writerow([
                r.timestamp, r.segment_id, r.segment_type, r.ramp_rate,
                r.transducer_voltage, r.transducer_pressure,
                r.transducer_pressure_raw if r.transducer_pressure_raw is not None else '',
                r.alicat_pressure, r.alicat_setpoint, r.alicat_barometric,
                r.offset_absolute, r.offset_gauge,
            ])
    print(f"\nData saved to: {output_file}")


def _build_labjack_config(
    config: Dict[str, Any],
    port: str,
    use_raw: bool = True,
) -> Dict[str, Any]:
    """Build LabJack config for a port. use_raw=True means no filter, offset=0 for calibration."""
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(port, {})
    filter_alpha = 1.0 if use_raw else float(labjack_cfg.get('transducer_filter_alpha', 0.2))
    return {
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
        'transducer_offset_psi': 0.0,
    }


def _build_alicat_config(config: Dict[str, Any], port: str) -> Dict[str, Any]:
    """Build Alicat config for a port."""
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_cfg = alicat_cfg.get(port, {})
    return {
        'com_port': port_cfg.get('com_port'),
        'address': port_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': alicat_cfg.get('timeout_s', 0.05),
        'pressure_index': alicat_cfg.get('pressure_index'),
        'setpoint_index': alicat_cfg.get('setpoint_index'),
        'gauge_index': alicat_cfg.get('gauge_index'),
        'barometric_index': alicat_cfg.get('barometric_index'),
    }


def _run_one_port(
    config: Dict[str, Any],
    port: str,
    segments: List[TestSegment],
    sample_rate: float,
    output_dir: Path,
    timestamp: str,
    use_raw: bool,
    auto_start: bool,
) -> Optional[Path]:
    """Run comprehensive test for a single port; return path to saved CSV or None on failure."""
    labjack = LabJackController(_build_labjack_config(config, port, use_raw=use_raw))
    alicat = AlicatController(_build_alicat_config(config, port))
    if not labjack.configure():
        print(f"{port}: LabJack failed")
        return None
    if not alicat.connect():
        print(f"{port}: Alicat failed")
        labjack.cleanup()
        return None
    readings = run_comprehensive_test(labjack, alicat, segments, sample_rate)
    output_file = output_dir / f'comprehensive_correlation_{port}_{timestamp}.csv'
    save_correlation_data(readings, output_file)
    alicat.exhaust()
    time.sleep(2.0)
    alicat.disconnect()
    labjack.cleanup()
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Comprehensive transducer-Alicat correlation test (raw data for calibration).'
    )
    parser.add_argument('--port', default=None, help='Single port (e.g. port_a). Ignored if --both-ports.')
    parser.add_argument('--both-ports', action='store_true', help='Run test on port_a then port_b')
    parser.add_argument('--sample-rate', type=float, default=50.0)
    parser.add_argument('--output-dir', default='scripts/data')
    parser.add_argument('--no-filter', action='store_true', help='Deprecated: raw is always used for this script')
    parser.add_argument('--auto-start', action='store_true', help='Skip start prompt')
    args = parser.parse_args()

    ports = ['port_a', 'port_b'] if args.both_ports else [args.port or 'port_a']
    config = load_config()
    segments = design_test_sequence()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime('%Y%m%d_%H%M%S')

    print(f"Test design: {len(segments)} segments")
    estimated_time = sum(s.duration + s.settle_time for s in segments) * len(ports)
    print(f"Estimated duration: {estimated_time/60:.1f} minutes")
    print(f"Transducer: raw (no filter, offset=0) for calibration")
    print(f"Ports: {', '.join(ports)}")

    if not args.auto_start:
        input("Press Enter to start test...")

    saved_files: List[Path] = []
    for port in ports:
        print(f"\n{'#'*60}\n# {port}\n{'#'*60}")
        path = _run_one_port(
            config, port, segments, args.sample_rate,
            output_dir, timestamp, use_raw=True, auto_start=args.auto_start,
        )
        if path:
            saved_files.append(path)

    if not saved_files:
        print("No data saved (all ports failed).")
        return 1

    print("\nTest complete! Run analysis on the saved file(s):")
    for p in saved_files:
        print(f"  {p}")
    if len(saved_files) > 1:
        print(f"  python scripts/analyze_correlation.py {' '.join(str(p) for p in saved_files)}")
    else:
        print(f"  python scripts/analyze_correlation.py {saved_files[0]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
