"""Run repeated switch-edge sweeps and benchmark pressure estimators offline."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_port_config, load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController
from app.services.sweep_primitives import DebounceState, observe_debounced_transition

TORR_PER_PSI = 51.71493256


@dataclass
class Sample:
    run_id: int
    phase: str
    elapsed_s: float
    transducer_psi: Optional[float]
    transducer_raw_psi: Optional[float]
    alicat_psi: Optional[float]
    switch_activated: Optional[bool]


@dataclass
class Edge:
    method: str
    run_id: int
    direction: str
    pressure_psi: float
    alicat_psi: float


def _as_bool(value: Optional[bool]) -> Optional[bool]:
    return bool(value) if value is not None else None


def _collect_sweep_stream(
    *,
    labjack: LabJackController,
    alicat: AlicatController,
    run_id: int,
    start_psi: float,
    end_psi: float,
    rate_psi_s: float,
    sample_dt_s: float,
) -> List[Sample]:
    samples: List[Sample] = []
    alicat.cancel_hold()
    time.sleep(0.1)
    alicat.set_ramp_rate(0, time_unit='s')
    time.sleep(0.1)
    alicat.set_pressure(start_psi)
    time.sleep(4.0)

    t0 = time.perf_counter()
    alicat.set_ramp_rate(rate_psi_s, time_unit='s')
    alicat.set_pressure(end_psi)
    timeout_s = abs(end_psi - start_psi) / max(rate_psi_s, 1e-3) + 20.0
    last_alicat_p = start_psi

    while time.perf_counter() - t0 < timeout_s:
        status = alicat.read_status()
        if status is not None:
            last_alicat_p = status.pressure
        trans = labjack.read_transducer()
        sw = labjack.read_switch_state()
        samples.append(
            Sample(
                run_id=run_id,
                phase='out',
                elapsed_s=time.perf_counter() - t0,
                transducer_psi=(trans.pressure if trans else None),
                transducer_raw_psi=(trans.pressure_raw if trans else None),
                alicat_psi=last_alicat_p,
                switch_activated=_as_bool(sw.switch_activated if sw else None),
            )
        )
        if abs(last_alicat_p - end_psi) <= 0.6:
            break
        time.sleep(sample_dt_s)

    time.sleep(1.0)
    alicat.set_pressure(start_psi)
    t1 = time.perf_counter()
    while time.perf_counter() - t1 < timeout_s:
        status = alicat.read_status()
        if status is not None:
            last_alicat_p = status.pressure
        trans = labjack.read_transducer()
        sw = labjack.read_switch_state()
        samples.append(
            Sample(
                run_id=run_id,
                phase='back',
                elapsed_s=(time.perf_counter() - t0),
                transducer_psi=(trans.pressure if trans else None),
                transducer_raw_psi=(trans.pressure_raw if trans else None),
                alicat_psi=last_alicat_p,
                switch_activated=_as_bool(sw.switch_activated if sw else None),
            )
        )
        if abs(last_alicat_p - start_psi) <= 1.0:
            break
        time.sleep(sample_dt_s)

    return samples


def _extract_edges(
    samples: List[Sample],
    *,
    method: str,
    pressure_selector: str,
    ema_alpha: float,
    stable_count: int,
    min_edge_interval_s: float,
    sample_dt_s: float,
) -> List[Edge]:
    out: List[Edge] = []
    debounce = DebounceState()
    last_state: Optional[bool] = None
    ema_value: Optional[float] = None

    for i, s in enumerate(samples):
        if s.switch_activated is None or s.alicat_psi is None:
            continue

        if pressure_selector == 'transducer':
            p = s.transducer_psi
        elif pressure_selector == 'transducer_raw':
            p = s.transducer_raw_psi
        elif pressure_selector == 'alicat':
            p = s.alicat_psi
        else:
            p = s.transducer_psi
        if p is None:
            continue

        if ema_alpha > 0.0:
            if ema_value is None:
                ema_value = p
            else:
                ema_value = ema_alpha * p + (1.0 - ema_alpha) * ema_value
            p_eval = ema_value
        else:
            p_eval = p

        if method == 'instant':
            if last_state is not None and s.switch_activated != last_state:
                out.append(
                    Edge(
                        method=f'instant:{pressure_selector}:a{ema_alpha:.2f}',
                        run_id=s.run_id,
                        direction=('ACTIVATED' if s.switch_activated else 'DEACTIVATED'),
                        pressure_psi=p_eval,
                        alicat_psi=s.alicat_psi,
                    )
                )
            last_state = s.switch_activated
            continue

        debounce, committed_state, committed_pressure = observe_debounced_transition(
            debounce,
            s.switch_activated,
            stable_count,
            min_edge_interval_s,
            i * sample_dt_s,
            track_last_sample=True,
            update_edge_time_on_reject=True,
            current_pressure=p_eval,
        )
        if committed_state is None:
            continue
        out.append(
            Edge(
                method=f'debounce:{pressure_selector}:a{ema_alpha:.2f}',
                run_id=s.run_id,
                direction=('ACTIVATED' if committed_state else 'DEACTIVATED'),
                pressure_psi=(committed_pressure if committed_pressure is not None else p_eval),
                alicat_psi=s.alicat_psi,
            )
        )
    return out


def _score_edges(edges: List[Edge]) -> Dict[str, float]:
    if not edges:
        return {'n': 0.0, 'mean_abs_torr': float('nan'), 'p95_abs_torr': float('nan'), 'p99_abs_torr': float('nan')}
    errors_torr = [abs(e.pressure_psi - e.alicat_psi) * TORR_PER_PSI for e in edges]
    s = sorted(errors_torr)
    idx95 = min(len(s) - 1, int(round(0.95 * (len(s) - 1))))
    idx99 = min(len(s) - 1, int(round(0.99 * (len(s) - 1))))
    return {
        'n': float(len(edges)),
        'mean_abs_torr': float(statistics.fmean(errors_torr)),
        'p95_abs_torr': float(s[idx95]),
        'p99_abs_torr': float(s[idx99]),
    }


def _repeatability(edges: List[Edge]) -> Dict[str, Optional[float]]:
    if not edges:
        return {'activation_std_psi': None, 'deactivation_std_psi': None}
    act = [e.pressure_psi for e in edges if e.direction == 'ACTIVATED']
    deact = [e.pressure_psi for e in edges if e.direction == 'DEACTIVATED']
    return {
        'activation_std_psi': (statistics.pstdev(act) if len(act) > 1 else None),
        'deactivation_std_psi': (statistics.pstdev(deact) if len(deact) > 1 else None),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Repeated Port switch sweep edge-estimator benchmark')
    parser.add_argument('--port', choices=['port_a', 'port_b'], default='port_b')
    parser.add_argument('--runs', type=int, default=8)
    parser.add_argument('--start-psi', type=float, default=20.0)
    parser.add_argument('--end-psi', type=float, default=0.1)
    parser.add_argument('--rate', type=float, default=1.0)
    parser.add_argument('--sample-dt', type=float, default=0.01)
    parser.add_argument('--output-dir', default='scripts/data/edge_campaign_port_b')
    parser.add_argument('--stable-count', type=int, default=3)
    parser.add_argument('--min-edge-ms', type=float, default=50.0)
    args = parser.parse_args()

    config = load_config()
    port_cfg = get_port_config(config, args.port)
    lj_cfg = {**config['hardware']['labjack'], **port_cfg['labjack']}
    alicat_cfg = {**config['hardware']['alicat'], **port_cfg['alicat']}

    labjack = LabJackController(lj_cfg)
    if not labjack.configure():
        raise RuntimeError(f'LabJack configure failed: {labjack._last_status}')
    labjack.configure_di_pins(
        no_pin=port_cfg['labjack']['switch_no_dio'],
        nc_pin=port_cfg['labjack']['switch_nc_dio'],
        com_pin=port_cfg['labjack']['switch_com_dio'],
        com_state=port_cfg['labjack'].get('switch_com_state', 0),
    )
    labjack.set_solenoid(to_vacuum=True)

    alicat = AlicatController(alicat_cfg)
    if not alicat.connect():
        labjack.cleanup()
        raise RuntimeError(f'Alicat connect failed: {alicat._last_status}')

    samples: List[Sample] = []
    try:
        for run_id in range(1, args.runs + 1):
            print(f'run {run_id}/{args.runs}...')
            samples.extend(
                _collect_sweep_stream(
                    labjack=labjack,
                    alicat=alicat,
                    run_id=run_id,
                    start_psi=args.start_psi,
                    end_psi=args.end_psi,
                    rate_psi_s=args.rate,
                    sample_dt_s=args.sample_dt,
                )
            )
    finally:
        try:
            alicat.set_ramp_rate(0, time_unit='s')
            alicat.set_pressure(args.start_psi)
        except Exception:
            pass
        try:
            alicat.disconnect()
        except Exception:
            pass
        labjack.set_solenoid_safe()
        labjack.cleanup()

    alphas = [0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8]
    candidates: List[Tuple[str, Dict[str, float], Dict[str, Optional[float]]]] = []
    for method in ('instant', 'debounce'):
        for src in ('transducer', 'transducer_raw', 'alicat'):
            for alpha in alphas:
                if src == 'alicat' and alpha > 0.0:
                    continue
                edges = _extract_edges(
                    samples,
                    method=method,
                    pressure_selector=src,
                    ema_alpha=alpha,
                    stable_count=args.stable_count,
                    min_edge_interval_s=args.min_edge_ms / 1000.0,
                    sample_dt_s=args.sample_dt,
                )
                if not edges:
                    continue
                name = edges[0].method
                score = _score_edges(edges)
                rep = _repeatability(edges)
                candidates.append((name, score, rep))

    candidates.sort(key=lambda x: (x[1]['p99_abs_torr'], x[1]['mean_abs_torr']))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    csv_path = output_dir / f'edge_campaign_stream_{args.port}_{ts}.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as h:
        w = csv.writer(h)
        w.writerow(['run_id', 'phase', 'elapsed_s', 'transducer_psi', 'transducer_raw_psi', 'alicat_psi', 'switch_activated'])
        for s in samples:
            w.writerow([s.run_id, s.phase, s.elapsed_s, s.transducer_psi, s.transducer_raw_psi, s.alicat_psi, s.switch_activated])

    summary = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'port': args.port,
        'runs': args.runs,
        'stream_csv': str(csv_path),
        'top_candidates': [
            {
                'method': n,
                **sc,
                **rep,
            }
            for n, sc, rep in candidates[:10]
        ],
    }
    json_path = output_dir / f'edge_campaign_summary_{args.port}_{ts}.json'
    json_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
