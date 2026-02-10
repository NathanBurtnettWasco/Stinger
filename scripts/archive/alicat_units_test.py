#!/usr/bin/env python3
"""Alicat utilities: unit probing and headless executor run."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, '.')

from app.core.config import load_config
from app.database.session import close_database, initialize_database
from app.hardware.alicat import AlicatController
from app.hardware.port import PortId, PortManager
from app.services.ptp_service import derive_test_setup, load_ptp_from_db
from app.services.test_executor import TestExecutor


logger = logging.getLogger(__name__)


def _build_alicat_controller(config: dict[str, Any], port_key: str) -> AlicatController:
    alicat_base = config.get('hardware', {}).get('alicat', {})
    port_cfg = alicat_base.get(port_key, {})
    return AlicatController(
        {
            'com_port': port_cfg.get('com_port'),
            'address': port_cfg.get('address'),
            'baudrate': alicat_base.get('baudrate', 19200),
            'timeout_s': alicat_base.get('timeout_s', 0.05),
            'pressure_units_stat': alicat_base.get('pressure_units_stat', 2),
            'pressure_units_group': alicat_base.get('pressure_units_group', 0),
            'pressure_units_override': alicat_base.get('pressure_units_override', 0),
        }
    )


def run_units_test(config: dict[str, Any], target: int, restore: int) -> int:
    alicat_base = config.get('hardware', {}).get('alicat', {})
    stat = int(alicat_base.get('pressure_units_stat', 2))

    print('\n' + '=' * 60)
    print('Alicat DCU Unit Test')
    print('=' * 60)
    for label, key in [('Port A', 'port_a'), ('Port B', 'port_b')]:
        controller = _build_alicat_controller(config, key)
        print(f'\n--- {label} ---')
        if not controller.connect():
            print('  connect failed')
            continue
        print('  baseline ', controller._send_command(f'DCU {stat}'))
        print('  set cmd  ', controller._send_command(f'DCU {stat} {target}'))
        time.sleep(0.2)
        print('  readback ', controller._send_command(f'DCU {stat}'))
        print('  restore  ', controller._send_command(f'DCU {stat} {restore}'))
        time.sleep(0.2)
        print('  restored ', controller._send_command(f'DCU {stat}'))
        controller.disconnect()
    return 0


def _row_from_reading(ts: float, port_id: str, reading: Any) -> dict[str, Any]:
    return {
        'ts': ts,
        'port': port_id,
        'transducer_psi': reading.transducer.pressure if reading and reading.transducer else None,
        'transducer_ref': reading.transducer.pressure_reference if reading and reading.transducer else None,
        'alicat_psi': reading.alicat.pressure if reading and reading.alicat else None,
        'alicat_setpoint_psi': reading.alicat.setpoint if reading and reading.alicat else None,
        'barometric_psi': reading.alicat.barometric_pressure if reading and reading.alicat else None,
        'switch_no': bool(reading.switch.no_active) if reading and reading.switch else None,
        'switch_nc': bool(reading.switch.nc_active) if reading and reading.switch else None,
    }


def run_headless_executor(
    config: dict[str, Any],
    part: str,
    sequence: str,
    port_id: str,
    sample_interval_ms: int,
    max_duration_s: float,
    out_dir: str,
) -> int:
    if not initialize_database(config.get('database', {})):
        raise RuntimeError('Database initialization failed')

    params = load_ptp_from_db(part, sequence)
    if not params:
        raise RuntimeError(f'No PTP parameters for {part}/{sequence}')
    setup = derive_test_setup(part, sequence, params)

    logger.info(
        'Headless executor: part=%s seq=%s port=%s units=%s direction=%s reference=%s',
        setup.part_id,
        setup.sequence_id,
        port_id,
        setup.units_label,
        setup.activation_direction,
        setup.pressure_reference,
    )

    pm = PortManager(config)
    pm.initialize_ports()
    pm.connect_all()

    port = pm.get_port(PortId(port_id))
    if port is None:
        raise RuntimeError(f'Port not available: {port_id}')
    port.configure_from_ptp(setup.raw)

    samples: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    lock = threading.Lock()
    stop = threading.Event()

    def add_event(name: str, **payload: Any) -> None:
        events.append({'ts': time.time(), 'event': name, 'payload': payload})
        logger.info('EVENT %s %s', name, payload)

    def get_latest(_pid: str):
        return port.read_all()

    def get_baro(_pid: str) -> float:
        reading = port.read_all()
        if reading and reading.alicat and reading.alicat.barometric_pressure is not None:
            return float(reading.alicat.barometric_pressure)
        return 14.7

    def sample_loop() -> None:
        interval_s = max(0.005, sample_interval_ms / 1000.0)
        while not stop.is_set():
            now = time.time()
            row = _row_from_reading(now, port_id, port.read_all())
            with lock:
                samples.append(row)
            time.sleep(interval_s)

    sampler = threading.Thread(target=sample_loop, daemon=True)
    sampler.start()

    executor = TestExecutor(
        port_id=port_id,
        port=port,
        test_setup=setup,
        config=config,
        get_latest_reading=get_latest,
        get_barometric_psi=get_baro,
        on_cycling_complete=lambda: add_event('cycling_complete'),
        on_substate_update=lambda s: add_event('substate', state=s),
        on_edges_captured=lambda a, d: add_event('edges_captured', activation_psi=a, deactivation_psi=d),
        on_cycle_estimate=lambda a, d, c: add_event(
            'cycle_estimate', activation_psi=a, deactivation_psi=d, count=c
        ),
        on_error=lambda m: add_event('error', message=m),
        on_cancelled=lambda: add_event('cancelled'),
    )

    add_event('run_start', part=part, sequence=sequence, port=port_id)
    start = time.time()
    timed_out = False
    executor.start()
    while executor.is_running:
        if time.time() - start > max_duration_s:
            timed_out = True
            add_event('timeout', elapsed_s=time.time() - start)
            executor.request_cancel()
            break
        time.sleep(0.1)
    while executor.is_running:
        time.sleep(0.05)

    stop.set()
    sampler.join(timeout=1.0)
    duration = time.time() - start

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f'headless_{part}_{sequence}_{port_id}_{stamp}'
    csv_path = out_path / f'{base}.csv'
    json_path = out_path / f'{base}.json'

    with lock:
        rows = list(samples)
    if rows:
        with csv_path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    summary = {
        'part': part,
        'sequence': sequence,
        'port': port_id,
        'units': setup.units_label,
        'direction': setup.activation_direction,
        'reference': setup.pressure_reference,
        'duration_s': duration,
        'timed_out': timed_out,
        'sample_count': len(rows),
        'event_count': len(events),
        'events': events,
        'csv': str(csv_path),
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    print('\nHeadless run complete')
    print(f'  duration_s : {duration:.2f}')
    print(f'  sample_count: {len(rows)}')
    print(f'  event_count : {len(events)}')
    print(f'  csv        : {csv_path}')
    print(f'  summary    : {json_path}')

    pm.disconnect_all()
    close_database()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Alicat utilities')
    parser.add_argument('--log-level', default='INFO')
    sub = parser.add_subparsers(dest='mode', required=True)

    units = sub.add_parser('units', help='Probe DCU unit switching')
    units.add_argument('--target', type=int, default=13)
    units.add_argument('--restore', type=int, default=10)

    headless = sub.add_parser('headless', help='Run TestExecutor without UI')
    headless.add_argument('--part', required=True)
    headless.add_argument('--sequence', required=True)
    headless.add_argument('--port', choices=['port_a', 'port_b'], default='port_b')
    headless.add_argument('--sample-interval-ms', type=int, default=20)
    headless.add_argument('--max-duration-s', type=float, default=180.0)
    headless.add_argument('--out-dir', default='logs/headless_runs')

    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format='%(asctime)s %(levelname)s %(name)s - %(message)s')
    config = load_config()

    if args.mode == 'units':
        return run_units_test(config, args.target, args.restore)
    return run_headless_executor(
        config=config,
        part=args.part,
        sequence=args.sequence,
        port_id=args.port,
        sample_interval_ms=args.sample_interval_ms,
        max_duration_s=args.max_duration_s,
        out_dir=args.out_dir,
    )


if __name__ == '__main__':
    raise SystemExit(main())
