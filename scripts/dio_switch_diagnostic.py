"""
DIO Switch Diagnostic — Find and verify pressure switch wiring.

This script bypasses the application layer and talks directly to LabJack LJM
to diagnose why DIO switch reads are unreliable.

Phases:
  1. Baseline DIO scan (nothing driven)
  2. COM-drive test (toggle each candidate COM, look for responsive lines)
  3. Full DIO scan during pressure sweep (Alicat ramps, watch ALL 20 DIOs)

Usage (from repo root, venv active):
    python scripts/dio_switch_diagnostic.py
    python scripts/dio_switch_diagnostic.py --skip-sweep   # skip pressure sweep
    python scripts/dio_switch_diagnostic.py --port port_b --sweep-vacuum
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config

logger = logging.getLogger(__name__)

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False

# DB9 pin-to-DIO mapping from HARDWARE_SPEC
PORT_A_DB9_TO_DIO = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8}
PORT_B_DB9_TO_DIO = {1: 9, 2: 10, 3: 11, 4: 12, 5: 13, 6: 14, 7: 15, 8: 16, 9: 17}
RELAY_DIOS = {'port_a': 18, 'port_b': 19}

# DIO label helpers
DIO_LABELS = {}
for pin, dio in PORT_A_DB9_TO_DIO.items():
    DIO_LABELS[dio] = f'DIO{dio} (PortA DB9-{pin})'
for pin, dio in PORT_B_DB9_TO_DIO.items():
    DIO_LABELS[dio] = f'DIO{dio} (PortB DB9-{pin})'
DIO_LABELS[18] = 'DIO18 (PortA relay/solenoid)'
DIO_LABELS[19] = 'DIO19 (PortB relay/solenoid)'

ALL_DIO = list(range(20))
ALL_DIO_NAMES = [f'DIO{i}' for i in ALL_DIO]


def label(dio: int) -> str:
    return DIO_LABELS.get(dio, f'DIO{dio}')


def read_all_dio(handle: int) -> Dict[int, int]:
    """Read DIO_STATE bitmask for all 20 DIO lines."""
    state = int(ljm.eReadName(handle, 'DIO_STATE'))
    return {i: 1 if state & (1 << i) else 0 for i in ALL_DIO}


def read_all_dio_individual(handle: int) -> Dict[int, int]:
    """Read each DIO individually (sets direction to input)."""
    values = ljm.eReadNames(handle, len(ALL_DIO_NAMES), ALL_DIO_NAMES)
    return {i: int(v) for i, v in zip(ALL_DIO, values)}


def write_dio(handle: int, dio: int, value: int) -> None:
    """Write a single DIO (sets it as output)."""
    ljm.eWriteName(handle, f'DIO{dio}', value)


def print_dio_table(values: Dict[int, int], title: str = '') -> None:
    """Pretty-print all DIO values."""
    if title:
        print(f'\n  {title}')
    print('  ' + '-' * 60)
    for group_name, dio_range in [
        ('FIO (DIO0-7, DB37, PortA DB9 1-8)', range(0, 8)),
        ('EIO (DIO8-15, DB15, PortB DB9 1-7 + PortA DB9-9)', range(8, 16)),
        ('CIO (DIO16-19, DB15)', range(16, 20)),
    ]:
        line_parts = []
        for dio in dio_range:
            v = values.get(dio, -1)
            line_parts.append(f'{dio}={v}')
        print(f'  {group_name}')
        print(f'    {", ".join(line_parts)}')
    print('  ' + '-' * 60)


# ---------------------------------------------------------------------------
# Phase 1: Baseline
# ---------------------------------------------------------------------------

def phase1_baseline(handle: int) -> Dict[int, int]:
    """Read all DIO lines with nothing driven (pure baseline)."""
    print('\n' + '=' * 70)
    print('PHASE 1: BASELINE DIO SCAN (no outputs driven)')
    print('=' * 70)

    # Read via DIO_STATE (doesn't change direction)
    values_mask = read_all_dio(handle)
    print_dio_table(values_mask, 'DIO_STATE bitmask read:')

    # Also read individually (sets direction to input)
    values_individual = read_all_dio_individual(handle)
    print_dio_table(values_individual, 'Individual DIO reads (forces input):')

    # Compare
    diffs = [i for i in ALL_DIO if values_mask[i] != values_individual[i]]
    if diffs:
        print(f'\n  WARNING: DIO_STATE vs individual reads differ on: {diffs}')
        print('  This means some lines were configured as outputs before this test.')
    else:
        print('\n  DIO_STATE and individual reads match (good).')

    # Identify any lines already LOW (could indicate something connected)
    low_lines = [i for i in ALL_DIO if values_individual[i] == 0]
    if low_lines:
        print(f'\n  Lines reading LOW: {[label(i) for i in low_lines]}')
        print('  (These might have something pulling them down)')
    else:
        print('\n  All lines reading HIGH (pulled up by 100k to 3.3V, nothing connected).')

    return values_individual


# ---------------------------------------------------------------------------
# Phase 2: COM-drive test
# ---------------------------------------------------------------------------

def phase2_com_drive(handle: int, baseline: Dict[int, int]) -> Dict[int, List[int]]:
    """
    For each candidate COM DIO, drive it LOW and HIGH, scan all other DIOs.
    Any DIO that changes state when a COM is driven indicates a switch connection.
    """
    print('\n' + '=' * 70)
    print('PHASE 2: COM-DRIVE TEST')
    print('  Driving each candidate COM pin LOW/HIGH and scanning for responsive lines')
    print('=' * 70)

    # Candidate COM pins: from config (DIO3, DIO16) plus all PortA/B DB9 pins
    candidate_coms = sorted(set(
        list(PORT_A_DB9_TO_DIO.values()) +
        list(PORT_B_DB9_TO_DIO.values())
    ))

    responsive: Dict[int, List[int]] = {}

    for com_dio in candidate_coms:
        # First, make sure all other DIOs are inputs
        for dio in ALL_DIO:
            if dio != com_dio and dio not in (18, 19):
                ljm.eReadName(handle, f'DIO{dio}')

        # Drive COM LOW
        write_dio(handle, com_dio, 0)
        time.sleep(0.02)
        state_low = read_all_dio(handle)

        # Drive COM HIGH
        write_dio(handle, com_dio, 1)
        time.sleep(0.02)
        state_high = read_all_dio(handle)

        # Return COM to input (read it to set direction)
        ljm.eReadName(handle, f'DIO{com_dio}')

        # Find lines that changed
        changed = []
        for dio in ALL_DIO:
            if dio == com_dio:
                continue
            if dio in (18, 19):
                continue  # skip relay DIOs
            if state_low[dio] != state_high[dio]:
                changed.append(dio)

        if changed:
            responsive[com_dio] = changed
            print(f'\n  COM={label(com_dio)}:')
            for c in changed:
                print(f'    {label(c)}: LOW_state={state_low[c]} -> HIGH_state={state_high[c]}')

    if not responsive:
        print('\n  NO responsive lines found for any COM candidate.')
        print('  This means either:')
        print('    a) No switches are physically connected to the DB9 connectors')
        print('    b) The switch contacts are open (switch not actuated)')
        print('    c) Wiring issue')
    else:
        print(f'\n  FOUND responsive pairs:')
        for com_dio, lines in responsive.items():
            print(f'    COM={label(com_dio)} -> responds: {[label(l) for l in lines]}')

    return responsive


# ---------------------------------------------------------------------------
# Phase 3: Continuous monitoring (manual toggle or pressure-driven)
# ---------------------------------------------------------------------------

def phase3_manual_monitor(handle: int, duration_s: float = 10.0) -> Dict[int, List[Tuple[float, int, int]]]:
    """
    Monitor all DIO lines at high rate for any changes.
    Useful for detecting a manual switch toggle or external stimulus.
    """
    print('\n' + '=' * 70)
    print(f'PHASE 3: CONTINUOUS DIO MONITOR ({duration_s:.0f} seconds)')
    print('  Watching ALL DIO lines for any state change at ~200 Hz')
    print('  (toggle switch manually or apply pressure now)')
    print('=' * 70)

    # Drive configured COM pins LOW (from config)
    config = load_config()
    port_a_com = config.get('hardware', {}).get('labjack', {}).get('port_a', {}).get('switch_com_dio')
    port_b_com = config.get('hardware', {}).get('labjack', {}).get('port_b', {}).get('switch_com_dio')

    driven_coms = []
    if port_a_com is not None:
        write_dio(handle, port_a_com, 0)
        driven_coms.append(port_a_com)
        print(f'  Driving COM DIO{port_a_com} LOW (Port A config)')
    if port_b_com is not None and port_b_com != port_a_com:
        write_dio(handle, port_b_com, 0)
        driven_coms.append(port_b_com)
        print(f'  Driving COM DIO{port_b_com} LOW (Port B config)')

    # Get initial state
    prev_state = read_all_dio(handle)
    changes: Dict[int, List[Tuple[float, int, int]]] = {i: [] for i in ALL_DIO}

    start = time.perf_counter()
    sample_count = 0
    while time.perf_counter() - start < duration_s:
        state = read_all_dio(handle)
        now = time.perf_counter() - start
        for i in ALL_DIO:
            if i in driven_coms:
                continue
            if state[i] != prev_state[i]:
                changes[i].append((now, prev_state[i], state[i]))
                print(f'  [{now:7.3f}s] {label(i)}: {prev_state[i]} -> {state[i]}')
        prev_state = state
        sample_count += 1
        time.sleep(0.005)  # ~200 Hz

    elapsed = time.perf_counter() - start
    rate = sample_count / elapsed if elapsed > 0 else 0
    print(f'\n  Sampled {sample_count} times in {elapsed:.1f}s ({rate:.0f} Hz)')

    active_changes = {k: v for k, v in changes.items() if v}
    if active_changes:
        print(f'\n  DIOs that changed during monitoring:')
        for dio, evts in active_changes.items():
            print(f'    {label(dio)}: {len(evts)} transitions')
    else:
        print(f'\n  NO DIO changes detected in {duration_s:.0f}s.')

    # Restore COM pins to input
    for com in driven_coms:
        ljm.eReadName(handle, f'DIO{com}')

    return changes


# ---------------------------------------------------------------------------
# Phase 4: Pressure sweep with ALL-DIO monitoring
# ---------------------------------------------------------------------------

def phase4_pressure_sweep(
    handle: int,
    port_key: str,
    config: Dict[str, Any],
    start_psi: float,
    end_psi: float,
    rate_psi_s: float,
    hold_s: float,
    to_vacuum: bool = False,
) -> List[Dict]:
    """
    Ramp pressure using Alicat while monitoring ALL DIO lines.
    Returns list of timestamped samples with pressure + all DIO states.
    """
    from app.hardware.alicat import AlicatController

    print('\n' + '=' * 70)
    print(f'PHASE 4: PRESSURE SWEEP DIO SCAN (port={port_key})')
    print(f'  Sweep: {start_psi:.1f} -> {end_psi:.1f} PSI at {rate_psi_s:.1f} PSI/s')
    print(f'  Monitoring ALL DIO0-19 during sweep')
    print('=' * 70)

    # Load port configs
    lj_port_cfg = config.get('hardware', {}).get('labjack', {}).get(port_key, {})
    alicat_base = config.get('hardware', {}).get('alicat', {})
    alicat_port_cfg = alicat_base.get(port_key, {})

    # Configure COM pins as output LOW
    com_dio = lj_port_cfg.get('switch_com_dio')
    if com_dio is not None:
        write_dio(handle, com_dio, 0)
        print(f'  COM DIO{com_dio} driven LOW')

    # Configure solenoid
    solenoid_dio = lj_port_cfg.get('solenoid_dio')
    if solenoid_dio is not None:
        solenoid_val = 1 if to_vacuum else 0
        write_dio(handle, solenoid_dio, solenoid_val)
        print(f'  Solenoid DIO{solenoid_dio} = {solenoid_val} ({"vacuum" if to_vacuum else "atmosphere"})')

    # Set up transducer reading
    ain_ch = lj_port_cfg.get('transducer_ain')
    ain_neg = lj_port_cfg.get('transducer_ain_neg')
    v_min = lj_port_cfg.get('transducer_voltage_min', 0.5)
    v_max = lj_port_cfg.get('transducer_voltage_max', 4.5)
    p_min = lj_port_cfg.get('transducer_pressure_min', 0.0)
    p_max = lj_port_cfg.get('transducer_pressure_max', 115.0)
    p_offset = float(lj_port_cfg.get('transducer_offset_psi', 0.0))

    if ain_ch is not None and ain_neg is not None:
        ljm.eWriteName(handle, f'AIN{ain_ch}_NEGATIVE_CH', ain_neg)
        print(f'  Transducer: AIN{ain_ch}/AIN{ain_neg} differential')

    def read_pressure() -> Tuple[float, float]:
        if ain_ch is None:
            return 0.0, 0.0
        voltage = ljm.eReadName(handle, f'AIN{ain_ch}')
        v_range = v_max - v_min
        p_range = p_max - p_min
        pressure = (voltage - v_min) / v_range * p_range + p_min + p_offset if v_range > 0 else p_min
        return voltage, pressure

    # Connect Alicat
    alicat_cfg = {
        'com_port': alicat_port_cfg.get('com_port'),
        'address': alicat_port_cfg.get('address'),
        'baudrate': alicat_base.get('baudrate', 19200),
        'timeout_s': max(alicat_base.get('timeout_s', 0.05), 0.1),
        'pressure_index': alicat_base.get('pressure_index'),
        'setpoint_index': alicat_base.get('setpoint_index'),
        'gauge_index': alicat_base.get('gauge_index'),
        'barometric_index': alicat_base.get('barometric_index'),
    }
    alicat = AlicatController(alicat_cfg)
    if not alicat.connect():
        print(f'  [FAIL] Alicat connect failed: {alicat._last_status}')
        return []

    samples: List[Dict] = []
    prev_dio = read_all_dio(handle)

    def sample(phase: str, alicat_pressure: Optional[float] = None) -> Dict:
        nonlocal prev_dio
        voltage, trans_pressure = read_pressure()
        dio_state = read_all_dio(handle)

        # Detect changes
        changed = []
        for i in ALL_DIO:
            if dio_state[i] != prev_dio[i]:
                changed.append(i)
                print(f'  [EDGE] {label(i)}: {prev_dio[i]}->{dio_state[i]} '
                      f'at {trans_pressure:.2f} PSI (alicat={alicat_pressure or 0:.2f})')

        row = {
            'time': time.time(),
            'elapsed': time.perf_counter(),
            'phase': phase,
            'voltage': voltage,
            'trans_psi': trans_pressure,
            'alicat_psi': alicat_pressure,
        }
        for i in ALL_DIO:
            row[f'DIO{i}'] = dio_state[i]
        row['changed'] = changed
        samples.append(row)
        prev_dio = dio_state
        return row

    try:
        # Cancel any hold, set ramp rate to 0 (instant)
        alicat.cancel_hold()
        time.sleep(0.1)
        alicat.set_ramp_rate(0, time_unit='s')
        time.sleep(0.1)

        # Move to start pressure
        print(f'\n  Moving to start pressure {start_psi:.1f} PSI...')
        alicat.set_pressure(start_psi)
        settle_start = time.perf_counter()
        while time.perf_counter() - settle_start < 10.0:
            status = alicat.read_status()
            if status and abs(status.pressure - start_psi) < 2.0:
                break
            time.sleep(0.2)
        time.sleep(2.0)

        # Sample at start
        status = alicat.read_status()
        alicat_p = status.pressure if status else None
        sample('start', alicat_p)
        print(f'  At start: transducer={samples[-1]["trans_psi"]:.2f} PSI, alicat={alicat_p}')

        # Set ramp rate and sweep
        print(f'\n  Starting sweep to {end_psi:.1f} PSI at {rate_psi_s:.1f} PSI/s...')
        alicat.set_ramp_rate(rate_psi_s, time_unit='s')
        time.sleep(0.1)
        alicat.set_pressure(end_psi)

        sweep_start = time.perf_counter()
        pressure_delta = abs(end_psi - start_psi)
        expected_duration = pressure_delta / rate_psi_s if rate_psi_s > 0 else 30.0
        timeout = expected_duration + 15.0

        last_alicat_time = 0.0
        last_alicat_p = alicat_p

        while time.perf_counter() - sweep_start < timeout:
            now = time.perf_counter()

            # Read Alicat at ~5 Hz (serial is slow)
            if now - last_alicat_time >= 0.2:
                status = alicat.read_status()
                if status:
                    last_alicat_p = status.pressure
                last_alicat_time = now

            sample('sweep', last_alicat_p)

            # Check if we've reached the end
            if last_alicat_p is not None and abs(last_alicat_p - end_psi) < 1.0:
                break

            time.sleep(0.02)  # ~50 Hz DIO sampling

        # Hold at end for a bit
        print(f'\n  Holding at {end_psi:.1f} PSI for {hold_s:.0f}s...')
        hold_start = time.perf_counter()
        while time.perf_counter() - hold_start < hold_s:
            now = time.perf_counter()
            if now - last_alicat_time >= 0.2:
                status = alicat.read_status()
                if status:
                    last_alicat_p = status.pressure
                last_alicat_time = now
            sample('hold', last_alicat_p)
            time.sleep(0.02)

        # Return sweep (end -> start)
        print(f'\n  Returning to {start_psi:.1f} PSI...')
        alicat.set_pressure(start_psi)
        return_start = time.perf_counter()
        while time.perf_counter() - return_start < timeout:
            now = time.perf_counter()
            if now - last_alicat_time >= 0.2:
                status = alicat.read_status()
                if status:
                    last_alicat_p = status.pressure
                last_alicat_time = now
            sample('return', last_alicat_p)
            if last_alicat_p is not None and abs(last_alicat_p - start_psi) < 2.0:
                break
            time.sleep(0.02)

        # Hold at start
        print(f'\n  Holding at {start_psi:.1f} PSI for {hold_s:.0f}s...')
        hold_start = time.perf_counter()
        while time.perf_counter() - hold_start < hold_s:
            now = time.perf_counter()
            if now - last_alicat_time >= 0.2:
                status = alicat.read_status()
                if status:
                    last_alicat_p = status.pressure
                last_alicat_time = now
            sample('hold_return', last_alicat_p)
            time.sleep(0.02)

    finally:
        # Safe shutdown
        try:
            alicat.set_ramp_rate(0, time_unit='s')
            alicat.set_pressure(start_psi)
        except Exception:
            pass
        try:
            alicat.disconnect()
        except Exception:
            pass
        if solenoid_dio is not None:
            write_dio(handle, solenoid_dio, 0)
        if com_dio is not None:
            ljm.eReadName(handle, f'DIO{com_dio}')  # set back to input

    return samples


def analyze_sweep(samples: List[Dict]) -> None:
    """Analyze sweep data for DIO transitions."""
    print('\n' + '=' * 70)
    print('SWEEP ANALYSIS')
    print('=' * 70)

    if not samples:
        print('  No samples collected.')
        return

    # Find which DIOs changed at all
    changed_dios: Dict[int, List[Tuple[int, float, float]]] = {}
    for idx, s in enumerate(samples):
        for dio in s.get('changed', []):
            if dio not in changed_dios:
                changed_dios[dio] = []
            changed_dios[dio].append((idx, s['trans_psi'], s.get('alicat_psi', 0) or 0))

    if changed_dios:
        print(f'\n  DIOs that changed during sweep:')
        for dio in sorted(changed_dios.keys()):
            transitions = changed_dios[dio]
            print(f'\n    {label(dio)}: {len(transitions)} transition(s)')
            for idx, trans_p, alicat_p in transitions:
                phase = samples[idx]['phase']
                dio_val = samples[idx][f'DIO{dio}']
                print(f'      [{phase}] -> DIO{dio}={dio_val} at trans={trans_p:.2f} PSI, alicat={alicat_p:.2f} PSI')
    else:
        print('\n  NO DIO changes detected during entire sweep.')
        print('  This means the switch is either:')
        print('    - Not connected to any of DIO0-19')
        print('    - The switch point is outside the sweep range')
        print('    - COM is not properly driven / wired')

    # Show DIO state at key pressures
    print('\n  DIO state at key pressures:')
    for target_p in [14.7, 20.0, 22.0, 25.0, 30.0]:
        closest = min(samples, key=lambda s: abs((s.get('alicat_psi') or 0) - target_p))
        dio_str = ' '.join(f'{i}={closest[f"DIO{i}"]}' for i in ALL_DIO)
        print(f'    ~{target_p:.0f} PSI: {dio_str}')


def save_sweep_csv(samples: List[Dict], output_path: Path) -> None:
    """Save sweep samples to CSV."""
    if not samples:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['time', 'phase', 'voltage', 'trans_psi', 'alicat_psi'] + [f'DIO{i}' for i in ALL_DIO]
    with output_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for s in samples:
            writer.writerow(s)
    print(f'\n  Sweep data saved to: {output_path}')


def main() -> int:
    parser = argparse.ArgumentParser(description='DIO switch diagnostic')
    parser.add_argument('--skip-sweep', action='store_true', help='Skip pressure sweep')
    parser.add_argument('--skip-monitor', action='store_true', help='Skip 10s manual monitor')
    parser.add_argument('--port', default='port_a', choices=['port_a', 'port_b'],
                        help='Port to sweep (default: port_a)')
    parser.add_argument('--start-psi', type=float, default=14.7, help='Sweep start PSI')
    parser.add_argument('--end-psi', type=float, default=35.0, help='Sweep end PSI')
    parser.add_argument('--rate', type=float, default=1.0, help='Ramp rate PSI/s')
    parser.add_argument('--hold', type=float, default=3.0, help='Hold time at endpoints (s)')
    parser.add_argument('--sweep-vacuum', action='store_true', help='Route exhaust to vacuum for sweep')
    parser.add_argument('--monitor-seconds', type=float, default=10.0, help='Manual monitor duration')
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

    if not LJM_AVAILABLE:
        print('[FATAL] labjack.ljm not available. Install LabJack LJM drivers.')
        return 1

    print('=' * 70)
    print('DIO SWITCH DIAGNOSTIC')
    print(f'  Time: {datetime.now().isoformat()}')
    print('=' * 70)

    config = load_config()

    # Print current config for reference
    for pk in ['port_a', 'port_b']:
        pcfg = config.get('hardware', {}).get('labjack', {}).get(pk, {})
        print(f'\n  Config {pk}:')
        print(f'    switch_no_dio:    {pcfg.get("switch_no_dio")}')
        print(f'    switch_nc_dio:    {pcfg.get("switch_nc_dio")}')
        print(f'    switch_com_dio:   {pcfg.get("switch_com_dio")}')
        print(f'    switch_com_state: {pcfg.get("switch_com_state")}')
        print(f'    switch_active_low: {pcfg.get("switch_active_low")}')
        print(f'    solenoid_dio:     {pcfg.get("solenoid_dio")}')

    # Open LabJack
    try:
        lj_cfg = config.get('hardware', {}).get('labjack', {})
        handle = ljm.openS(
            lj_cfg.get('device_type', 'T7'),
            lj_cfg.get('connection_type', 'USB'),
            lj_cfg.get('identifier', 'ANY'),
        )
    except Exception as exc:
        print(f'[FATAL] Cannot open LabJack: {exc}')
        return 1

    info = ljm.getHandleInfo(handle)
    print(f'\n  LabJack opened: type={info[0]} connection={info[1]} serial={info[2]}')

    try:
        # Phase 1
        baseline = phase1_baseline(handle)

        # Phase 2
        responsive = phase2_com_drive(handle, baseline)

        # Phase 3 (manual monitor)
        if not args.skip_monitor:
            phase3_manual_monitor(handle, duration_s=args.monitor_seconds)

        # Phase 4 (pressure sweep)
        if not args.skip_sweep:
            samples = phase4_pressure_sweep(
                handle=handle,
                port_key=args.port,
                config=config,
                start_psi=args.start_psi,
                end_psi=args.end_psi,
                rate_psi_s=args.rate,
                hold_s=args.hold,
                to_vacuum=args.sweep_vacuum,
            )
            analyze_sweep(samples)

            # Save CSV
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            csv_path = Path('scripts/data') / f'dio_diagnostic_{args.port}_{ts}.csv'
            save_sweep_csv(samples, csv_path)

    finally:
        # Safe shutdown: all outputs off
        try:
            write_dio(handle, 18, 0)  # solenoid A off
            write_dio(handle, 19, 0)  # solenoid B off
        except Exception:
            pass
        try:
            ljm.close(handle)
        except Exception:
            pass

    print('\n' + '=' * 70)
    print('DIAGNOSTIC COMPLETE')
    print('=' * 70)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
