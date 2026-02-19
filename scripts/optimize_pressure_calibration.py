"""Offline optimizer for transducer correction/filter calibration.

Usage:
  python scripts/optimize_pressure_calibration.py \
    --input-csv scripts/data/offset_validation_20260210/alignment_static_verify_nonlinear_forced_abs.csv \
    --output-dir scripts/data/offline_opt_20260210

Input schema (required columns):
  - timestamp
  - port_id
  - phase
  - target_abs_psi
  - alicat_abs_psi
  - transducer_abs_psi

Optional preferred raw signal:
  - transducer_raw_abs_psi (if present, optimizer uses this column instead of transducer_abs_psi)

Near-target rule:
  - target_abs_psi and alicat_abs_psi both present
  - abs(alicat_abs_psi - target_abs_psi) <= tolerance_psi (default 0.2)
  - static phase only by default (phase starts with "static_")
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.pressure_calibration import (  # noqa: E402
    CalibrationSample,
    REQUIRED_ALIGNMENT_COLUMNS,
    fit_piecewise_linear_error_model,
    fit_quadratic_error_model,
    score_replay,
    select_near_target_samples,
    split_train_validation,
)


@dataclass
class CandidateResult:
    port_id: str
    family: str
    candidate_name: str
    ema_alpha: float
    parameter_count: int
    p99_abs_torr: float
    mean_abs_torr: float
    max_abs_torr: float
    p95_abs_torr: float
    n_validation: int
    passed: bool
    model: Dict[str, Any]


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _load_samples(paths: Sequence[Path], port_id: str) -> List[CalibrationSample]:
    samples: List[CalibrationSample] = []
    idx = 0
    for path in paths:
        with path.open('r', newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            columns = set(reader.fieldnames or [])
            missing = sorted(REQUIRED_ALIGNMENT_COLUMNS - columns)
            if missing:
                raise ValueError(f'{path} missing required columns: {missing}')
            for row in reader:
                if str(row.get('port_id', '')).strip().lower() != port_id:
                    continue
                trans_raw = _parse_float(row.get('transducer_raw_abs_psi'))
                trans_measured = trans_raw if trans_raw is not None else _parse_float(row.get('transducer_abs_psi'))
                sample = CalibrationSample(
                    index=idx,
                    timestamp=_parse_float(row.get('timestamp')) or 0.0,
                    port_id=port_id,
                    phase=str(row.get('phase', '')).strip(),
                    target_abs_psi=_parse_float(row.get('target_abs_psi')),
                    transducer_abs_psi=trans_measured,
                    alicat_abs_psi=_parse_float(row.get('alicat_abs_psi')),
                )
                idx += 1
                if sample.transducer_abs_psi is None or sample.alicat_abs_psi is None:
                    continue
                samples.append(sample)
    if not samples:
        raise ValueError(f'No samples loaded for {port_id}.')
    return samples


def _parameter_count(model: Dict[str, Any]) -> int:
    model_type = str(model.get('type', '')).strip().lower()
    if model_type == 'quadratic':
        return 3
    if model_type == 'piecewise_linear':
        segments = model.get('segments', [])
        if not isinstance(segments, list):
            return 0
        finite_breakpoints = sum(1 for s in segments if s.get('max_psi') is not None)
        return len(segments) * 2 + finite_breakpoints
    return 0


def _score_candidate(
    *,
    port_id: str,
    family: str,
    candidate_name: str,
    model: Dict[str, Any],
    alpha: float,
    samples: Sequence[CalibrationSample],
    validation_mask: Sequence[bool],
    pass_threshold_torr: float,
) -> CandidateResult:
    score = score_replay(samples, model=model, ema_alpha=alpha, include_mask=validation_mask)
    n_validation = int(score['n'])
    p99 = float(score['p99_abs_torr'])
    return CandidateResult(
        port_id=port_id,
        family=family,
        candidate_name=candidate_name,
        ema_alpha=float(alpha),
        parameter_count=_parameter_count(model),
        p99_abs_torr=p99,
        mean_abs_torr=float(score['mean_abs_torr']),
        max_abs_torr=float(score['max_abs_torr']),
        p95_abs_torr=float(score['p95_abs_torr']),
        n_validation=n_validation,
        passed=bool(n_validation > 0 and p99 <= pass_threshold_torr),
        model=model,
    )


def _as_dict(result: CandidateResult) -> Dict[str, Any]:
    return {
        'port_id': result.port_id,
        'family': result.family,
        'candidate_name': result.candidate_name,
        'ema_alpha': result.ema_alpha,
        'parameter_count': result.parameter_count,
        'p99_abs_torr': result.p99_abs_torr,
        'mean_abs_torr': result.mean_abs_torr,
        'p95_abs_torr': result.p95_abs_torr,
        'max_abs_torr': result.max_abs_torr,
        'n_validation': result.n_validation,
        'passed': result.passed,
        'model': result.model,
    }


def _rank_results(results: List[CandidateResult]) -> List[CandidateResult]:
    return sorted(
        results,
        key=lambda r: (r.p99_abs_torr, r.mean_abs_torr, r.parameter_count, r.max_abs_torr),
    )


def _write_ranking_csv(path: Path, ranked: Sequence[CandidateResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                'port_id',
                'family',
                'candidate_name',
                'ema_alpha',
                'parameter_count',
                'p99_abs_torr',
                'mean_abs_torr',
                'p95_abs_torr',
                'max_abs_torr',
                'n_validation',
                'passed',
            ],
        )
        writer.writeheader()
        for result in ranked:
            writer.writerow(
                {
                    'port_id': result.port_id,
                    'family': result.family,
                    'candidate_name': result.candidate_name,
                    'ema_alpha': f'{result.ema_alpha:.4f}',
                    'parameter_count': result.parameter_count,
                    'p99_abs_torr': f'{result.p99_abs_torr:.6f}',
                    'mean_abs_torr': f'{result.mean_abs_torr:.6f}',
                    'p95_abs_torr': f'{result.p95_abs_torr:.6f}',
                    'max_abs_torr': f'{result.max_abs_torr:.6f}',
                    'n_validation': result.n_validation,
                    'passed': str(result.passed).lower(),
                }
            )


def _format_top(results: Sequence[CandidateResult], top_n: int) -> List[Dict[str, Any]]:
    return [_as_dict(item) for item in results[:top_n]]


def _unique_alpha_grid(alpha_grid_text: str) -> List[float]:
    values = []
    for chunk in alpha_grid_text.split(','):
        text = chunk.strip()
        if not text:
            continue
        values.append(float(text))
    if not values:
        values = [0.0]
    unique = sorted(set(max(0.0, min(1.0, v)) for v in values))
    return unique


def _optimize_for_port(
    *,
    port_id: str,
    samples: Sequence[CalibrationSample],
    tolerance_psi: float,
    static_only: bool,
    holdout_stride: int,
    alpha_grid: Sequence[float],
    pass_threshold_torr: float,
) -> Dict[str, Any]:
    selected = select_near_target_samples(samples, tolerance_psi=tolerance_psi, static_only=static_only)
    if len(selected) < 50:
        raise ValueError(
            f'{port_id}: not enough near-target samples ({len(selected)}) for robust optimization; '
            'capture denser data or increase tolerance.'
        )
    train, validation = split_train_validation(selected, holdout_stride=holdout_stride)
    validation_index_set = {s.index for s in validation}
    validation_mask = [s.index in validation_index_set for s in selected]

    piecewise3 = fit_piecewise_linear_error_model(train, segment_count=3)
    piecewise5 = fit_piecewise_linear_error_model(train, segment_count=5)
    quadratic = fit_quadratic_error_model(train)

    candidates: List[CandidateResult] = []
    candidates.append(
        _score_candidate(
            port_id=port_id,
            family='piecewise3_no_filter',
            candidate_name='piecewise3_a0',
            model=piecewise3,
            alpha=0.0,
            samples=selected,
            validation_mask=validation_mask,
            pass_threshold_torr=pass_threshold_torr,
        )
    )
    candidates.append(
        _score_candidate(
            port_id=port_id,
            family='piecewise5_no_filter',
            candidate_name='piecewise5_a0',
            model=piecewise5,
            alpha=0.0,
            samples=selected,
            validation_mask=validation_mask,
            pass_threshold_torr=pass_threshold_torr,
        )
    )
    for alpha in alpha_grid:
        candidates.append(
            _score_candidate(
                port_id=port_id,
                family='piecewise_plus_filter',
                candidate_name=f'piecewise3_a{alpha:.3f}',
                model=piecewise3,
                alpha=alpha,
                samples=selected,
                validation_mask=validation_mask,
                pass_threshold_torr=pass_threshold_torr,
            )
        )
        candidates.append(
            _score_candidate(
                port_id=port_id,
                family='piecewise_plus_filter',
                candidate_name=f'piecewise5_a{alpha:.3f}',
                model=piecewise5,
                alpha=alpha,
                samples=selected,
                validation_mask=validation_mask,
                pass_threshold_torr=pass_threshold_torr,
            )
        )
        candidates.append(
            _score_candidate(
                port_id=port_id,
                family='poly2_plus_filter',
                candidate_name=f'quadratic_a{alpha:.3f}',
                model=quadratic,
                alpha=alpha,
                samples=selected,
                validation_mask=validation_mask,
                pass_threshold_torr=pass_threshold_torr,
            )
        )

    ranked = _rank_results(candidates)
    return {
        'port_id': port_id,
        'sample_counts': {
            'raw_total': len(samples),
            'near_target_total': len(selected),
            'near_target_train': len(train),
            'near_target_validation': len(validation),
        },
        'ranked': ranked,
        'best': ranked[0],
    }


def _build_config_snippet(best_by_port: Dict[str, CandidateResult]) -> Dict[str, Any]:
    common_alpha: Optional[float] = None
    alpha_values = {round(result.ema_alpha, 6) for result in best_by_port.values()}
    if len(alpha_values) == 1:
        common_alpha = float(next(iter(alpha_values)))
    else:
        # config currently has a single global alpha; default to no filtering
        common_alpha = 0.0

    labjack = {
        'pressure_filter_alpha': common_alpha,
    }
    for port_id, result in best_by_port.items():
        labjack[port_id] = {
            'transducer_error_model': result.model,
        }
    return {'hardware': {'labjack': labjack}}


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline optimizer for transducer calibration models.')
    parser.add_argument('--input-csv', action='append', required=True, help='Alignment CSV path; repeat to add more files.')
    parser.add_argument('--ports', default='port_a,port_b', help='Comma-separated port ids (default: port_a,port_b).')
    parser.add_argument('--output-dir', required=True, help='Output directory for ranking/report files.')
    parser.add_argument('--near-target-tolerance-psi', type=float, default=0.2)
    parser.add_argument('--include-dynamic', action='store_true', help='Include dynamic phases in scoring.')
    parser.add_argument('--holdout-stride', type=int, default=5, help='Every Nth near-target sample goes to validation.')
    parser.add_argument(
        '--alpha-grid',
        default='0.0,0.05,0.1,0.2,0.3,0.4,0.6,0.8',
        help='Comma-separated EMA alpha values to evaluate.',
    )
    parser.add_argument('--pass-threshold-torr', type=float, default=1.2)
    parser.add_argument('--top-n', type=int, default=3)
    args = parser.parse_args()

    started = time.time()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    input_paths = [Path(p) for p in args.input_csv]
    ports = [p.strip().lower() for p in args.ports.split(',') if p.strip()]
    alpha_grid = _unique_alpha_grid(args.alpha_grid)

    report: Dict[str, Any] = {
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'inputs': [str(p) for p in input_paths],
        'ports': {},
        'schema': {
            'required_columns': sorted(REQUIRED_ALIGNMENT_COLUMNS),
            'optional_preferred_columns': ['transducer_raw_abs_psi'],
            'near_target_rule': {
                'tolerance_psi': args.near_target_tolerance_psi,
                'static_only': not args.include_dynamic,
            },
        },
        'ranking_rule': ['p99_abs_torr', 'mean_abs_torr', 'parameter_count', 'max_abs_torr'],
        'pass_threshold_torr': args.pass_threshold_torr,
    }

    best_by_port: Dict[str, CandidateResult] = {}
    for port_id in ports:
        samples = _load_samples(input_paths, port_id)
        result = _optimize_for_port(
            port_id=port_id,
            samples=samples,
            tolerance_psi=args.near_target_tolerance_psi,
            static_only=not args.include_dynamic,
            holdout_stride=args.holdout_stride,
            alpha_grid=alpha_grid,
            pass_threshold_torr=args.pass_threshold_torr,
        )
        ranked = result['ranked']
        best: CandidateResult = result['best']
        best_by_port[port_id] = best

        csv_path = output_dir / f'ranking_{port_id}.csv'
        _write_ranking_csv(csv_path, ranked)
        report['ports'][port_id] = {
            'sample_counts': result['sample_counts'],
            'best': _as_dict(best),
            'top': _format_top(ranked, args.top_n),
            'ranking_csv': str(csv_path),
        }

    config_snippet = _build_config_snippet(best_by_port)
    report['recommended_config_snippet'] = config_snippet
    report['elapsed_s'] = round(time.time() - started, 3)

    summary_json = output_dir / 'optimization_summary.json'
    summary_json.write_text(json.dumps(report, indent=2), encoding='utf-8')
    snippet_yaml = output_dir / 'recommended_calibration.yaml'
    snippet_yaml.write_text(yaml.safe_dump(config_snippet, sort_keys=False), encoding='utf-8')

    print(json.dumps(report, indent=2))
    print(f'\nWrote summary: {summary_json}')
    print(f'Wrote config snippet: {snippet_yaml}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
