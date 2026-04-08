#!/usr/bin/env python3
"""Manual live monitor for transducer raw volts and computed pressure.

Usage:
    python scripts/manual_transducer_monitor.py --port port_a --duration 30
    python scripts/manual_transducer_monitor.py --port port_a --duration 0 --sample-rate 5
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware import labjack as labjack_module
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

logger = logging.getLogger(__name__)


@dataclass
class RawAnalogReading:
    """Low-level LabJack analog values for the transducer channel."""

    ain_pos_single_ended_v: float
    ain_neg_single_ended_v: Optional[float]
    differential_v: float
    single_ended_delta_v: Optional[float]


@dataclass
class MonitorSample:
    """One monitor sample combining raw, scaled, and Alicat readings."""

    timestamp: float
    elapsed_s: float
    ain_pos_single_ended_v: float
    ain_neg_single_ended_v: Optional[float]
    differential_v: float
    single_ended_delta_v: Optional[float]
    transducer_voltage_v: Optional[float]
    transducer_psia: Optional[float]
    transducer_reference: Optional[str]
    alicat_psia: Optional[float]
    alicat_psig: Optional[float]
    alicat_setpoint_psia: Optional[float]
    barometric_psia: Optional[float]


def build_labjack_controller(config: Dict[str, Any], port: str) -> LabJackController:
    """Build LabJack controller for the selected port."""
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get(port, {})

    controller_config = {
        'device_type': labjack_cfg.get('device_type', 'T7'),
        'connection_type': labjack_cfg.get('connection_type', 'USB'),
        'identifier': labjack_cfg.get('identifier', 'ANY'),
        'resolution_index': labjack_cfg.get('resolution_index', 0),
        'pressure_filter_alpha': labjack_cfg.get('pressure_filter_alpha', 0.0),
        **port_cfg,
    }
    return LabJackController(controller_config)


def build_alicat_controller(config: Dict[str, Any], port: str) -> AlicatController:
    """Build Alicat controller for the selected port."""
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
        'pressure_units_stat': alicat_cfg.get('pressure_units_stat'),
        'pressure_units_group': alicat_cfg.get('pressure_units_group'),
        'pressure_units_value': alicat_cfg.get('pressure_units_value'),
        'pressure_units_override': alicat_cfg.get('pressure_units_override'),
        'auto_tare_on_connect': alicat_cfg.get('auto_tare_on_connect', True),
        'auto_tare_max_delta_psi': alicat_cfg.get('auto_tare_max_delta_psi', 0.5),
        'auto_tare_delay_s': alicat_cfg.get('auto_tare_delay_s', 0.5),
    }
    return AlicatController(controller_config)


def read_raw_analog(labjack: LabJackController) -> Optional[RawAnalogReading]:
    """Read AIN+, AIN-, and differential voltage directly from the LabJack."""
    if not labjack_module.LJM_AVAILABLE:
        return None

    handle = labjack._shared_handle
    pos = labjack.transducer_ain
    neg = labjack.transducer_ain_neg
    if handle is None or pos is None:
        return None

    if neg is None:
        single_ended = labjack._read_name_with_retry(f'AIN{pos}')
        if single_ended is None:
            return None
        return RawAnalogReading(
            ain_pos_single_ended_v=single_ended,
            ain_neg_single_ended_v=None,
            differential_v=single_ended,
            single_ended_delta_v=None,
        )

    with labjack._lock:
        if not labjack._write_name_with_retry(f'AIN{pos}_NEGATIVE_CH', 199):
            return None
        ain_pos = labjack._read_name_with_retry(f'AIN{pos}')
        if ain_pos is None:
            return None

        if not labjack._write_name_with_retry(f'AIN{neg}_NEGATIVE_CH', 199):
            return None
        ain_neg = labjack._read_name_with_retry(f'AIN{neg}')
        if ain_neg is None:
            return None

        if not labjack._write_name_with_retry(f'AIN{pos}_NEGATIVE_CH', neg):
            return None
        differential = labjack._read_name_with_retry(f'AIN{pos}')
        if differential is None:
            return None

    return RawAnalogReading(
        ain_pos_single_ended_v=ain_pos,
        ain_neg_single_ended_v=ain_neg,
        differential_v=differential,
        single_ended_delta_v=ain_pos - ain_neg,
    )


def collect_sample(
    labjack: LabJackController,
    alicat: AlicatController,
    start_time: float,
) -> Optional[MonitorSample]:
    """Collect one combined sample."""
    raw = read_raw_analog(labjack)
    transducer = labjack.read_transducer()
    alicat_status = alicat.read_status()
    if raw is None and transducer is None and alicat_status is None:
        return None

    barometric = None
    alicat_psig = None
    alicat_psia = None
    alicat_setpoint = None
    if alicat_status is not None:
        alicat_psia = alicat_status.pressure
        alicat_setpoint = alicat_status.setpoint
        barometric = alicat_status.barometric_pressure
        if alicat_psia is not None and barometric is not None:
            alicat_psig = alicat_psia - barometric

    return MonitorSample(
        timestamp=time.time(),
        elapsed_s=time.perf_counter() - start_time,
        ain_pos_single_ended_v=raw.ain_pos_single_ended_v if raw is not None else 0.0,
        ain_neg_single_ended_v=raw.ain_neg_single_ended_v if raw is not None else None,
        differential_v=raw.differential_v if raw is not None else 0.0,
        single_ended_delta_v=raw.single_ended_delta_v if raw is not None else None,
        transducer_voltage_v=transducer.voltage if transducer is not None else None,
        transducer_psia=transducer.pressure if transducer is not None else None,
        transducer_reference=transducer.pressure_reference if transducer is not None else None,
        alicat_psia=alicat_psia,
        alicat_psig=alicat_psig,
        alicat_setpoint_psia=alicat_setpoint,
        barometric_psia=barometric,
    )


def print_sample(sample: MonitorSample) -> None:
    """Print one sample in a compact hardware-focused format."""
    ain_neg = (
        f'{sample.ain_neg_single_ended_v:+7.4f}V'
        if sample.ain_neg_single_ended_v is not None else '   n/a '
    )
    se_delta = (
        f'{sample.single_ended_delta_v:+7.4f}V'
        if sample.single_ended_delta_v is not None else '   n/a '
    )
    transducer_psia = (
        f'{sample.transducer_psia:7.3f}psia'
        if sample.transducer_psia is not None else '    n/a '
    )
    transducer_voltage = (
        f'{sample.transducer_voltage_v:+7.4f}V'
        if sample.transducer_voltage_v is not None else '   n/a '
    )
    alicat_psia = f'{sample.alicat_psia:7.3f}psia' if sample.alicat_psia is not None else '    n/a '
    alicat_psig = f'{sample.alicat_psig:+6.3f}psig' if sample.alicat_psig is not None else '   n/a '
    setpoint = (
        f'{sample.alicat_setpoint_psia:7.3f}'
        if sample.alicat_setpoint_psia is not None else '   n/a '
    )

    print(
        f't={sample.elapsed_s:6.1f}s '
        f'AIN+={sample.ain_pos_single_ended_v:+7.4f}V '
        f'AIN-={ain_neg} '
        f'diff={sample.differential_v:+7.4f}V '
        f'se_delta={se_delta} '
        f'trans={transducer_psia} rawV={transducer_voltage} '
        f'alicat={alicat_psia} ({alicat_psig}) '
        f'setpoint={setpoint}'
    )


def save_csv(samples: List[MonitorSample], output_file: Path, port: str) -> None:
    """Save collected samples to CSV."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open('w', newline='', encoding='utf-8') as file_handle:
        writer = csv.writer(file_handle)
        writer.writerow([f'# port: {port}'])
        writer.writerow([
            'timestamp',
            'elapsed_s',
            'ain_pos_single_ended_v',
            'ain_neg_single_ended_v',
            'differential_v',
            'single_ended_delta_v',
            'transducer_voltage_v',
            'transducer_psia',
            'transducer_reference',
            'alicat_psia',
            'alicat_psig',
            'alicat_setpoint_psia',
            'barometric_psia',
        ])
        for sample in samples:
            writer.writerow([
                sample.timestamp,
                sample.elapsed_s,
                sample.ain_pos_single_ended_v,
                sample.ain_neg_single_ended_v,
                sample.differential_v,
                sample.single_ended_delta_v,
                sample.transducer_voltage_v,
                sample.transducer_psia,
                sample.transducer_reference,
                sample.alicat_psia,
                sample.alicat_psig,
                sample.alicat_setpoint_psia,
                sample.barometric_psia,
            ])


def print_summary(samples: List[MonitorSample]) -> None:
    """Print compact summary statistics."""
    if not samples:
        print('\nNo samples collected.')
        return

    differential_values = [sample.differential_v for sample in samples]
    transducer_values = [
        sample.transducer_psia for sample in samples if sample.transducer_psia is not None
    ]
    alicat_values = [sample.alicat_psia for sample in samples if sample.alicat_psia is not None]

    print('\n' + '=' * 70)
    print('MONITOR SUMMARY')
    print('=' * 70)
    print(
        f'Differential volts: {min(differential_values):.4f} .. '
        f'{max(differential_values):.4f} V'
    )
    if transducer_values:
        print(f'Transducer PSIA:   {min(transducer_values):.3f} .. {max(transducer_values):.3f}')
    if alicat_values:
        print(f'Alicat PSIA:       {min(alicat_values):.3f} .. {max(alicat_values):.3f}')
    if transducer_values and alicat_values:
        count = min(len(transducer_values), len(alicat_values))
        offsets = [transducer_values[i] - alicat_values[i] for i in range(count)]
        print(f'Mean offset:       {sum(offsets) / len(offsets):+.3f} PSI')
    print('=' * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description='Manual live transducer monitor')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_a')
    parser.add_argument(
        '--duration',
        type=float,
        default=30.0,
        help='Seconds to run. Use 0 to run until Ctrl+C.',
    )
    parser.add_argument('--sample-rate', type=float, default=4.0, help='Samples per second.')
    parser.add_argument(
        '--output-dir',
        type=str,
        default='scripts/data/manual_monitor',
        help='Directory for CSV output.',
    )
    parser.add_argument('--no-save', action='store_true', help='Do not save CSV output.')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        config = load_config()
    except Exception as exc:
        print(f'[FAIL] Could not load config: {exc}')
        return 1

    labjack = build_labjack_controller(config, args.port)
    alicat = build_alicat_controller(config, args.port)

    print('\n' + '=' * 70)
    print('MANUAL TRANSDUCER MONITOR')
    print('=' * 70)
    print(f'Port: {args.port}')
    print(f'AIN+ / AIN-: {labjack.transducer_ain} / {labjack.transducer_ain_neg}')
    print(f'Scaling: {labjack.voltage_min}..{labjack.voltage_max} V -> '
          f'{labjack.pressure_min}..{labjack.pressure_max} PSI')
    print(f'Duration: {"until Ctrl+C" if args.duration <= 0 else f"{args.duration:.1f} s"}')
    print(f'Sample rate: {args.sample_rate:.1f} Hz')
    print('=' * 70 + '\n')

    if not labjack.configure():
        print(f'[FAIL] LabJack configuration failed: {labjack._last_status}')
        return 1
    if not alicat.connect():
        print(f'[FAIL] Alicat connection failed: {alicat._last_status}')
        labjack.cleanup()
        return 1

    samples: List[MonitorSample] = []
    sample_interval = 1.0 / max(args.sample_rate, 0.1)
    start_time = time.perf_counter()
    last_sample = start_time - sample_interval

    try:
        while True:
            now = time.perf_counter()
            if args.duration > 0 and now - start_time >= args.duration:
                break
            if now - last_sample < sample_interval:
                time.sleep(0.01)
                continue

            sample = collect_sample(labjack, alicat, start_time)
            if sample is not None:
                samples.append(sample)
                print_sample(sample)
            last_sample = now
    except KeyboardInterrupt:
        print('\nStopped by user.')
    finally:
        alicat.disconnect()
        labjack.cleanup()

    print_summary(samples)

    if not args.no_save and samples:
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_file = PROJECT_ROOT / args.output_dir / f'manual_transducer_monitor_{args.port}_{timestamp}.csv'
        save_csv(samples, output_file, args.port)
        print(f'\nSaved CSV to: {output_file}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
