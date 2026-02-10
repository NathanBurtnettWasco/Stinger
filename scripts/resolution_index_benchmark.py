"""
Resolution Index Benchmark — compare noise, rate, and latency across AIN
resolution indices on the LabJack T7-Pro for both Stinger ports.

For each resolution index (1, 4, 6, 8, 9, 10) and each port (A=AIN0, B=AIN2):
  1. Set AIN#_RESOLUTION_INDEX
  2. Burst-read N samples as fast as possible
  3. Report: read rate (Hz), per-read latency (ms), voltage noise (std, uV),
     min/max voltage, and equivalent pressure noise (mPSI / Torr).

Usage (from repo root, venv activated):
    python scripts/resolution_index_benchmark.py
    python scripts/resolution_index_benchmark.py --samples 1000 --indices 1 8 9
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config

try:
    from labjack import ljm
    LJM_AVAILABLE = True
except ImportError:
    LJM_AVAILABLE = False


# --- Transducer scaling constants (from stinger_config) ---
VOLTAGE_MIN = 0.5
VOLTAGE_MAX = 4.5
PRESSURE_MIN_PSI = 0.0
PRESSURE_MAX_PSI = 115.0
VOLTAGE_SPAN = VOLTAGE_MAX - VOLTAGE_MIN  # 4.0 V
PRESSURE_SPAN_PSI = PRESSURE_MAX_PSI - PRESSURE_MIN_PSI  # 115.0 PSI
PSI_PER_VOLT = PRESSURE_SPAN_PSI / VOLTAGE_SPAN  # 28.75 PSI/V
TORR_PER_PSI = 51.7149


def open_handle(device_type: str, connection_type: str, identifier: str) -> Optional[int]:
    if not LJM_AVAILABLE:
        return None
    try:
        return ljm.openS(device_type, connection_type, identifier)
    except Exception as exc:
        print(f'[ERROR] LJM open failed ({device_type}/{connection_type}/{identifier}): {exc}')
        return None


def benchmark_index(
    handle: int,
    ain: int,
    ain_neg: int,
    resolution_index: int,
    num_samples: int,
) -> dict:
    """Run a burst read at the given resolution index and return stats."""

    # Configure resolution index for this specific AIN channel
    ljm.eWriteName(handle, f'AIN{ain}_RESOLUTION_INDEX', resolution_index)
    # Ensure differential mode
    ljm.eWriteName(handle, f'AIN{ain}_NEGATIVE_CH', ain_neg)

    ain_name = f'AIN{ain}'

    # Warm-up: discard first few reads (ADC settling after config change)
    for _ in range(5):
        ljm.eReadName(handle, ain_name)

    # Collect samples
    voltages: List[float] = []
    latencies: List[float] = []
    errors = 0

    t_burst_start = time.perf_counter()
    for _ in range(num_samples):
        t0 = time.perf_counter()
        try:
            v = ljm.eReadName(handle, ain_name)
            t1 = time.perf_counter()
            voltages.append(v)
            latencies.append(t1 - t0)
        except Exception:
            errors += 1
    t_burst_end = time.perf_counter()

    elapsed = t_burst_end - t_burst_start
    good_reads = len(voltages)
    rate_hz = good_reads / elapsed if elapsed > 0 else 0.0

    if good_reads < 2:
        return {
            'resolution_index': resolution_index,
            'ain': ain,
            'samples': good_reads,
            'errors': errors,
            'rate_hz': 0,
            'latency_mean_ms': 0,
            'latency_p50_ms': 0,
            'latency_p99_ms': 0,
            'noise_std_uv': 0,
            'noise_pp_uv': 0,
            'noise_std_mpsi': 0,
            'noise_std_torr': 0,
            'voltage_mean': 0,
        }

    v_mean = statistics.mean(voltages)
    v_std = statistics.stdev(voltages)
    v_min = min(voltages)
    v_max = max(voltages)

    lat_mean = statistics.mean(latencies) * 1000  # ms
    lat_sorted = sorted(latencies)
    lat_p50 = lat_sorted[len(lat_sorted) // 2] * 1000
    lat_p99 = lat_sorted[int(len(lat_sorted) * 0.99)] * 1000

    noise_uv = v_std * 1e6
    noise_pp_uv = (v_max - v_min) * 1e6
    noise_mpsi = v_std * PSI_PER_VOLT * 1000  # milli-PSI
    noise_torr = noise_mpsi / 1000 * TORR_PER_PSI

    return {
        'resolution_index': resolution_index,
        'ain': ain,
        'samples': good_reads,
        'errors': errors,
        'rate_hz': rate_hz,
        'latency_mean_ms': lat_mean,
        'latency_p50_ms': lat_p50,
        'latency_p99_ms': lat_p99,
        'noise_std_uv': noise_uv,
        'noise_pp_uv': noise_pp_uv,
        'noise_std_mpsi': noise_mpsi,
        'noise_std_torr': noise_torr,
        'voltage_mean': v_mean,
    }


def print_header() -> None:
    print()
    print('=' * 120)
    print(f'{"Idx":>3}  {"Port":<6}  {"Rate(Hz)":>9}  {"Lat mean":>9}  '
          f'{"Lat p50":>9}  {"Lat p99":>9}  {"Noise std":>10}  '
          f'{"Noise p-p":>10}  {"std mPSI":>9}  {"std Torr":>9}  '
          f'{"V mean":>9}  {"Errors":>6}')
    print(f'{"":>3}  {"":>6}  {"":>9}  {"(ms)":>9}  '
          f'{"(ms)":>9}  {"(ms)":>9}  {"(uV)":>10}  '
          f'{"(uV)":>10}  {"":>9}  {"":>9}  '
          f'{"(V)":>9}  {"":>6}')
    print('-' * 120)


def print_row(r: dict, port_label: str) -> None:
    print(f'{r["resolution_index"]:>3}  {port_label:<6}  {r["rate_hz"]:>9.1f}  '
          f'{r["latency_mean_ms"]:>9.3f}  {r["latency_p50_ms"]:>9.3f}  '
          f'{r["latency_p99_ms"]:>9.3f}  {r["noise_std_uv"]:>10.2f}  '
          f'{r["noise_pp_uv"]:>10.2f}  {r["noise_std_mpsi"]:>9.3f}  '
          f'{r["noise_std_torr"]:>9.4f}  {r["voltage_mean"]:>9.6f}  '
          f'{r["errors"]:>6}')


def main() -> None:
    parser = argparse.ArgumentParser(description='LabJack T7-Pro resolution index benchmark')
    parser.add_argument('--samples', type=int, default=500,
                        help='Number of samples per index per port (default: 500)')
    parser.add_argument('--indices', type=int, nargs='+', default=[1, 4, 6, 8, 9, 10],
                        help='Resolution indices to test (default: 1 4 6 8 9 10)')
    args = parser.parse_args()

    if not LJM_AVAILABLE:
        print('[ERROR] labjack.ljm not available. Is the LJM driver installed?')
        sys.exit(1)

    config = load_config()
    lj_cfg = config.get('hardware', {}).get('labjack', {})
    device_type = lj_cfg.get('device_type', 'T7')
    connection_type = lj_cfg.get('connection_type', 'USB')
    identifier = lj_cfg.get('identifier', 'ANY')

    port_a_ain = lj_cfg.get('port_a', {}).get('transducer_ain', 0)
    port_a_neg = lj_cfg.get('port_a', {}).get('transducer_ain_neg', 1)
    port_b_ain = lj_cfg.get('port_b', {}).get('transducer_ain', 2)
    port_b_neg = lj_cfg.get('port_b', {}).get('transducer_ain_neg', 3)

    handle = open_handle(device_type, connection_type, identifier)
    if handle is None:
        sys.exit(1)

    ports = [
        ('Port A', port_a_ain, port_a_neg),
        ('Port B', port_b_ain, port_b_neg),
    ]

    print()
    print('=' * 120)
    print('  LabJack T7-Pro Resolution Index Benchmark')
    print(f'  Device: {device_type} / {connection_type} / {identifier}')
    print(f'  Samples per test: {args.samples}')
    print(f'  Indices to test: {args.indices}')
    print(f'  Port A: AIN{port_a_ain} (neg=AIN{port_a_neg})')
    print(f'  Port B: AIN{port_b_ain} (neg=AIN{port_b_neg})')
    print('=' * 120)

    all_results = []

    try:
        print_header()

        for res_idx in sorted(args.indices):
            for port_label, ain, ain_neg in ports:
                result = benchmark_index(handle, ain, ain_neg, res_idx, args.samples)
                print_row(result, port_label)
                all_results.append((port_label, result))
            # Separator between index groups
            if res_idx != sorted(args.indices)[-1]:
                print()

        print('=' * 120)

        # Summary: best rate and best noise
        print('\n--- Summary ---')
        for port_label in ['Port A', 'Port B']:
            port_results = [r for lbl, r in all_results if lbl == port_label]
            if not port_results:
                continue
            fastest = max(port_results, key=lambda r: r['rate_hz'])
            quietest = min(port_results, key=lambda r: r['noise_std_uv']) if port_results else None
            print(f'\n  {port_label}:')
            print(f'    Fastest:  index {fastest["resolution_index"]} '
                  f'@ {fastest["rate_hz"]:.0f} Hz '
                  f'(noise std = {fastest["noise_std_uv"]:.1f} uV / {fastest["noise_std_mpsi"]:.2f} mPSI)')
            if quietest:
                print(f'    Quietest: index {quietest["resolution_index"]} '
                      f'@ {quietest["rate_hz"]:.0f} Hz '
                      f'(noise std = {quietest["noise_std_uv"]:.1f} uV / {quietest["noise_std_mpsi"]:.2f} mPSI)')

        # Filtering analysis
        print('\n--- Oversampling + Filter Estimates ---')
        print('  (If you drop to a faster index and average N samples, estimated effective noise:)')
        for port_label in ['Port A', 'Port B']:
            port_results = [r for lbl, r in all_results if lbl == port_label]
            if not port_results:
                continue
            print(f'\n  {port_label}:')
            for r in port_results:
                idx = r['resolution_index']
                rate = r['rate_hz']
                noise = r['noise_std_uv']
                if rate == 0 or noise == 0:
                    continue
                for avg_n in [4, 8, 16]:
                    filtered_noise = noise / (avg_n ** 0.5)
                    effective_rate = rate / avg_n
                    print(f'    Index {idx}: avg {avg_n:>2} samples -> '
                          f'{effective_rate:>7.0f} Hz effective, '
                          f'std ~ {filtered_noise:>6.1f} uV '
                          f'({filtered_noise * PSI_PER_VOLT / 1000:.3f} mPSI)')

    finally:
        # Restore default (index 0 = auto) before closing
        try:
            ljm.eWriteName(handle, 'AIN_ALL_RESOLUTION_INDEX', 0)
        except Exception:
            pass
        try:
            ljm.close(handle)
        except Exception:
            pass

    print('\n[Done] Resolution index restored to default (0=auto).')


if __name__ == '__main__':
    main()
