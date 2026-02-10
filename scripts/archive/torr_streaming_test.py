"""
Torr Streaming Test - High-speed data collection in Torr units with streaming mode.

Uses Alicat streaming mode (@) for much faster data rates (up to 100 Hz).
Runs ultra-slow ramps (1-10 Torr/s) to characterize static-to-dynamic transition.

Usage:
    python scripts/torr_streaming_test.py --port port_a --rate 5 --duration 60
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import deque

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)

# Unit conversion
PSI_PER_TORR = 0.0193368
TORR_PER_PSI = 51.715

# Alicat unit codes
UNIT_CODE_TORR = 13
UNIT_CODE_PSI = 10


@dataclass
class TorrReading:
    timestamp: float
    transducer_voltage: float
    transducer_pressure_torr: float
    alicat_pressure: float
    alicat_setpoint: float
    alicat_units: str
    is_streaming: bool


class StreamingAlicatReader:
    """High-speed reader using Alicat streaming mode.
    
    NOTE: Based on Alicat Serial Primer, streaming mode sends data continuously
    from unit ID "@" instead of requiring polling. Format: @ +pressure +setpoint ...
    """
    
    def __init__(self, alicat: AlicatController):
        self.alicat = alicat
        self.readings: deque = deque(maxlen=10000)  # Ring buffer
        self._streaming = False
        self._stream_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_reading: Optional[Dict] = None
        
    def start_streaming(self, interval_ms: int = 10) -> bool:
        """Start streaming mode with specified interval (min 5ms)."""
        # Clamp to valid range (5-65535 ms, 0=off)
        interval_ms = max(5, min(65535, interval_ms))
        
        print(f"  Setting streaming interval to {interval_ms}ms...")
        response = self.alicat._send_command(f"NCS {interval_ms}")
        print(f"    Response: {response}")
        time.sleep(0.1)  # Allow command to take effect
        
        print(f"  Starting streaming mode (@ @)...")
        response = self._send_raw_line("@ @")
        print(f"    Response: {response}")
        
        # The device should now auto-send data with "@" prefix
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        
        # Wait a moment and check if we're receiving data
        time.sleep(0.3)
        initial_count = len(self.readings)
        print(f"  Initial stream buffer: {initial_count} readings")
        
        return initial_count > 0
    
    def stop_streaming(self, new_unit_id: str = "A") -> bool:
        """Stop streaming and restore unit ID."""
        print(f"  Stopping streaming mode...")
        self._streaming = False
        
        if self._stream_thread:
            self._stream_thread.join(timeout=1.0)
        
        # Stop streaming - device address is "@" while streaming
        response = self._send_raw_line(f"@@ {new_unit_id}")
        print(f"    Response: {response}")
        
        # Flush any remaining data
        time.sleep(0.1)
        if self.alicat._serial and self.alicat._serial.is_open:
            self.alicat._serial.reset_input_buffer()
        
        return True

    def _send_raw_line(self, line: str) -> Optional[str]:
        """Send a raw command line without prefixing address."""
        if not self.alicat._serial or not self.alicat._serial.is_open:
            return None
        try:
            self.alicat._serial.reset_input_buffer()
            if hasattr(self.alicat._serial, 'reset_output_buffer'):
                self.alicat._serial.reset_output_buffer()
            self.alicat._serial.write(f"{line}\r".encode())
            response = self.alicat._serial.read_until(b'\r').decode().strip()
            return response if response else None
        except Exception:
            return None
    
    def _stream_loop(self):
        """Background thread to read streaming data."""
        consecutive_errors = 0
        
        while self._streaming:
            try:
                if self.alicat._serial and self.alicat._serial.is_open:
                    # Read until CR (Alicat terminates with \r)
                    line = self.alicat._serial.read_until(b'\r').decode().strip()
                    if line:
                        consecutive_errors = 0
                        # Accept streaming data with or without prefix
                        if line.startswith("@") or line.startswith(self.alicat.address) or line[0].isdigit() or line[0] in "+-":
                            with self._lock:
                                self.readings.append({
                                    'timestamp': time.perf_counter(),
                                    'raw': line
                                })
                        else:
                            # Might be an error or status message
                            logger.debug(f"Non-streaming line: {line}")
                else:
                    consecutive_errors += 1
                    if consecutive_errors > 100:
                        logger.error("Serial connection lost in streaming loop")
                        break
                        
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors % 10 == 0:
                    logger.debug(f"Stream read error ({consecutive_errors}): {e}")
            
            # Small sleep to prevent CPU spinning
            time.sleep(0.0005)  # 0.5ms
    
    def get_readings(self) -> List[Dict]:
        """Get accumulated readings and clear buffer."""
        with self._lock:
            readings = list(self.readings)
            self.readings.clear()
            return readings
    
    def get_latest(self) -> Optional[Dict]:
        """Get most recent reading without clearing."""
        with self._lock:
            if self.readings:
                return dict(self.readings[-1])
            return None


def parse_alicat_stream_line(line: str, units: str = "PSI") -> Optional[Dict[str, float]]:
    """Parse a streaming data line from Alicat.
    
    Streaming format (from Alicat primer):
    @ +pressure +setpoint +temp +volumetric_flow +mass_flow +gas +pid_power +pid_setpoint
    """
    try:
        line = line.strip()
        # Remove the leading "@" if present
        if line.startswith("@"):
            line = line[1:].strip()

        # Remove leading address token if present (e.g., "A +013.76 ...")
        parts = line.split()
        if parts and len(parts[0]) == 1 and parts[0].isalpha():
            line = " ".join(parts[1:]).strip()

        parts = line.split()
        if len(parts) < 2:
            return None
        
        # Streaming data fields (space-separated, all positive values with sign)
        # Field 0: pressure (absolute)
        # Field 1: setpoint
        
        pressure = float(parts[0])
        setpoint = float(parts[1]) if len(parts) > 1 else 0.0
        
        return {
            'pressure': pressure,
            'setpoint': setpoint,
        }
    except Exception:
        return None


def set_alicat_units(alicat: AlicatController, unit_code: int) -> bool:
    """Set Alicat units using DCU command."""
    # DCU <statistic> <group> <unit_value> <override>
    # statistic=2 (absolute pressure), group=0, unit_code, override=0
    response = alicat._send_command(f"DCU 2 0 {unit_code} 0")
    print(f"  DCU response: {response}")
    
    if response and response.startswith(alicat.address):
        return True
    return False


def get_alicat_units(alicat: AlicatController) -> str:
    """Query current units."""
    response = alicat._send_command("DCU 2")
    if response:
        parts = response.split()
        if len(parts) >= 2:
            unit_map = {
                "10": "PSI",
                "13": "Torr",
                "12": "mTorr",
            }
            return unit_map.get(parts[1], f"Code_{parts[1]}")
    return "Unknown"


def run_torr_streaming_test(
    labjack: LabJackController,
    alicat: AlicatController,
    ramp_rate_torr_s: float,
    duration_s: float,
) -> List[TorrReading]:
    """Run a ramp test at torr-level rates with streaming."""
    readings: List[TorrReading] = []
    
    # Convert rates
    ramp_rate_psi_s = ramp_rate_torr_s * PSI_PER_TORR
    print(f"\n{'='*70}")
    print(f"TORR STREAMING TEST")
    print(f"Ramp: {ramp_rate_torr_s:.1f} Torr/s ({ramp_rate_psi_s:.4f} PSI/s)")
    print(f"{'='*70}")
    
    # Get current pressure
    status = alicat.read_status()
    if not status:
        print("[FAIL] Cannot read initial status")
        return readings
    
    current_units = get_alicat_units(alicat)
    print(f"\nCurrent units: {current_units}")
    
    # If in Torr, use directly, otherwise convert
    if current_units == "Torr":
        start_pressure = status.pressure
        current_pressure = status.pressure
    else:
        start_pressure = status.pressure * TORR_PER_PSI  # Convert PSI to Torr
        current_pressure = start_pressure
    
    print(f"Start pressure: {start_pressure:.2f} Torr")
    
    # Set target (ramp up by ~100 Torr or to limit)
    target_pressure = min(start_pressure + 100, 5000)  # Max ~100 PSIA in Torr
    
    # Use streaming reader
    streamer = StreamingAlicatReader(alicat)
    
    # Set ramp rate and target before starting streaming (avoids serial contention)
    print(f"Setting ramp to {ramp_rate_torr_s:.1f} Torr/s...")
    alicat.set_ramp_rate(ramp_rate_psi_s, time_unit='s')
    
    if current_units == "Torr":
        alicat.set_pressure(target_pressure)
    else:
        alicat.set_pressure(target_pressure * PSI_PER_TORR)
    
    print("\nStarting streaming mode...")
    streaming_enabled = streamer.start_streaming(interval_ms=10)  # 100 Hz
    if not streaming_enabled:
        print("  [WARNING] No streaming data detected; falling back to polling")
        streamer.stop_streaming(alicat.address)
    
    # Let streaming stabilize
    time.sleep(0.5)
    
    # Collect data
    print(f"Collecting data for {duration_s:.1f} seconds...")
    print("Press Ctrl+C to stop early\n")
    
    start_time = time.perf_counter()
    last_status_time = start_time
    last_lj_time = start_time
    last_alicat_poll_time = start_time
    last_alicat_pressure_torr: Optional[float] = None
    last_alicat_setpoint_torr: Optional[float] = None
    had_stream_data = False
    
    try:
        while time.perf_counter() - start_time < duration_s:
            current_time = time.perf_counter()
            elapsed = current_time - start_time
            
            # Read LabJack at high rate (every 4ms = 250 Hz)
            if current_time - last_lj_time >= 0.004:
                trans_data = read_raw_transducer(labjack)
                if trans_data:
                    voltage, pressure_psi = trans_data
                    
                    # Get latest Alicat reading from stream
                    if streaming_enabled:
                        stream_readings = streamer.get_readings()
                        if stream_readings:
                            had_stream_data = True
                            latest_stream = stream_readings[-1]
                            parsed = parse_alicat_stream_line(latest_stream['raw'], current_units)
                            if parsed:
                                if current_units == "PSI":
                                    last_alicat_pressure_torr = parsed['pressure'] * TORR_PER_PSI
                                    last_alicat_setpoint_torr = parsed['setpoint'] * TORR_PER_PSI
                                else:
                                    last_alicat_pressure_torr = parsed['pressure']
                                    last_alicat_setpoint_torr = parsed['setpoint']
                    
                    # Fallback polling if streaming is not providing data
                    if not had_stream_data and current_time - last_alicat_poll_time >= 0.05:
                        status = alicat.read_status()
                        if status:
                            if current_units == "PSI":
                                last_alicat_pressure_torr = status.pressure * TORR_PER_PSI
                                last_alicat_setpoint_torr = status.setpoint * TORR_PER_PSI
                            else:
                                last_alicat_pressure_torr = status.pressure
                                last_alicat_setpoint_torr = status.setpoint
                        last_alicat_poll_time = current_time
                    
                    if last_alicat_pressure_torr is not None and last_alicat_setpoint_torr is not None:
                        readings.append(TorrReading(
                            timestamp=current_time,
                            transducer_voltage=voltage,
                            transducer_pressure_torr=pressure_psi * TORR_PER_PSI,
                            alicat_pressure=last_alicat_pressure_torr,
                            alicat_setpoint=last_alicat_setpoint_torr,
                            alicat_units=current_units,
                            is_streaming=had_stream_data,
                        ))
                
                last_lj_time = current_time
            
            # Print status every 2 seconds
            if current_time - last_status_time >= 2.0:
                if readings:
                    latest = readings[-1]
                    offset = latest.transducer_pressure_torr - latest.alicat_pressure
                    print(f"  t={elapsed:5.1f}s | LJ={latest.transducer_pressure_torr:8.2f} Torr | "
                          f"Alicat={latest.alicat_pressure:8.2f} Torr | Offset={offset:+6.2f} Torr | "
                          f"N={len(readings)}")
                last_status_time = current_time
            
            time.sleep(0.001)  # 1ms sleep
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    finally:
        print("\nStopping streaming...")
        streamer.stop_streaming(alicat.address)
    
    print(f"\nCollected {len(readings)} samples")
    if readings:
        duration = readings[-1].timestamp - readings[0].timestamp
        rate = len(readings) / duration if duration > 0 else 0
        print(f"Effective rate: {rate:.1f} Hz")
    
    return readings


def read_raw_transducer(labjack: LabJackController) -> Optional[Tuple[float, float]]:
    """Read transducer voltage and calculated pressure."""
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


def analyze_torr_data(readings: List[TorrReading]) -> Dict[str, Any]:
    """Analyze torr-level data."""
    if not readings:
        return {}
    
    # Convert to arrays
    transducer = np.array([r.transducer_pressure_torr for r in readings])
    alicat = np.array([r.alicat_pressure for r in readings])
    offsets = transducer - alicat
    
    # Find static periods (small changes)
    alicat_diffs = np.diff(alicat)
    static_threshold = 0.5  # Torr/s threshold for static
    
    # Analyze resolution by looking at minimum non-zero differences
    transducer_diffs = np.diff(transducer)
    alicat_diffs_nonzero = alicat_diffs[alicat_diffs != 0]
    
    results = {
        'total_samples': len(readings),
        'duration': readings[-1].timestamp - readings[0].timestamp,
        'transducer_mean': np.mean(transducer),
        'transducer_std': np.std(transducer),
        'alicat_mean': np.mean(alicat),
        'alicat_std': np.std(alicat),
        'offset_mean': np.mean(offsets),
        'offset_std': np.std(offsets),
        'transducer_resolution': np.min(np.abs(transducer_diffs[transducer_diffs != 0])) if len(transducer_diffs[transducer_diffs != 0]) > 0 else None,
        'alicat_resolution': np.min(np.abs(alicat_diffs_nonzero)) if len(alicat_diffs_nonzero) > 0 else None,
        'transducer_noise': np.std(transducer),
        'alicat_noise': np.std(alicat),
        'pressure_range': np.max(alicat) - np.min(alicat),
    }
    
    return results


def print_torr_analysis(results: Dict[str, Any]) -> None:
    """Print analysis results."""
    print("\n" + "="*70)
    print("TORR-LEVEL ANALYSIS")
    print("="*70)
    
    print(f"\nSamples: {results['total_samples']} over {results['duration']:.1f}s")
    if results['duration'] > 0:
        print(f"Rate: {results['total_samples']/results['duration']:.1f} Hz")
    else:
        print("Rate: 0.0 Hz")
    
    print(f"\nTransducer:")
    print(f"  Mean: {results['transducer_mean']:.2f} Torr")
    print(f"  Std (noise): {results['transducer_noise']:.4f} Torr")
    if results['transducer_resolution']:
        print(f"  Resolution: {results['transducer_resolution']:.4f} Torr")
    
    print(f"\nAlicat:")
    print(f"  Mean: {results['alicat_mean']:.2f} Torr")
    print(f"  Std (noise): {results['alicat_noise']:.4f} Torr")
    if results['alicat_resolution']:
        print(f"  Resolution: {results['alicat_resolution']:.4f} Torr")
    
    print(f"\nOffset (Transducer - Alicat):")
    print(f"  Mean: {results['offset_mean']:.4f} Torr")
    print(f"  Std: {results['offset_std']:.4f} Torr")
    
    print(f"\nPressure range covered: {results['pressure_range']:.2f} Torr")
    print("="*70)


def save_torr_data(readings: List[TorrReading], output_file: Path, ramp_rate: float) -> None:
    """Save torr data to CSV."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp', 'transducer_voltage', 'transducer_pressure_torr',
            'alicat_pressure', 'alicat_setpoint', 'alicat_units',
            'offset_torr', 'is_streaming'
        ])
        
        for r in readings:
            offset = r.transducer_pressure_torr - r.alicat_pressure
            writer.writerow([
                r.timestamp, r.transducer_voltage, r.transducer_pressure_torr,
                r.alicat_pressure, r.alicat_setpoint, r.alicat_units,
                offset, r.is_streaming
            ])
    
    print(f"\nData saved to: {output_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description='Torr streaming test')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a',
                       help='Port to test')
    parser.add_argument('--rate', type=float, default=5.0,
                       help='Ramp rate in Torr/s (default: 5)')
    parser.add_argument('--duration', type=float, default=30.0,
                       help='Test duration in seconds (default: 30)')
    parser.add_argument('--output-dir', type=str, default='scripts/data/20260203',
                        help='Output directory')
    parser.add_argument('--units', choices=['torr', 'psi'], default='torr',
                       help='Set Alicat units (default: torr)')
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print("\n" + "="*70)
    print("TORR STREAMING TEST")
    print("="*70)
    print(f"Port: {args.port}")
    print(f"Ramp rate: {args.rate:.1f} Torr/s")
    print(f"Duration: {args.duration:.1f} seconds")
    print(f"Target units: {args.units}")
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
        'transducer_offset_psi': 0.0,
    })
    
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_alicat_cfg = alicat_cfg.get(args.port, {})
    alicat = AlicatController({
        'com_port': port_alicat_cfg.get('com_port'),
        'address': port_alicat_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': 0.02,
    })
    
    # Connect
    print("\nConnecting to hardware...")
    
    print("  Connecting to LabJack...")
    if not labjack.configure():
        print("[FAIL] LabJack configuration failed")
        return 1
    print("  [OK] LabJack connected")
    
    print("  Connecting to Alicat...")
    if not alicat.connect():
        print("[FAIL] Alicat connection failed")
        labjack.cleanup()
        return 1
    print("  [OK] Alicat connected")
    
    print("Connected!")
    
    # Set units if requested
    if args.units == 'torr':
        print("\nSetting Alicat to Torr units...")
        if set_alicat_units(alicat, UNIT_CODE_TORR):
            print("  [OK] Units set to Torr")
        else:
            print("  [WARNING] Could not set units, continuing with current units")
    
    # Run test
    try:
        readings = run_torr_streaming_test(
            labjack, alicat,
            ramp_rate_torr_s=args.rate,
            duration_s=args.duration,
        )
        
        if readings:
            # Analyze
            results = analyze_torr_data(readings)
            print_torr_analysis(results)
            
            # Save
            output_dir = Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            output_file = output_dir / f'torr_streaming_{args.port}_r{args.rate:.0f}_{timestamp}.csv'
            save_torr_data(readings, output_file, args.rate)
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
            # Reset to PSI
            if args.units == 'torr':
                print("  Resetting to PSI...")
                set_alicat_units(alicat, UNIT_CODE_PSI)
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
