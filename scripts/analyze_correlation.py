"""
Comprehensive Correlation Analysis

Analyzes data from comprehensive_correlation_test.py to:
1. Find the "perfect" offset from static holds
2. Quantify offset vs ramp rate relationship
3. Quantify noise vs ramp rate for both sensors
4. Determine optimal offset and any pressure-dependent corrections

Usage:
    python scripts/analyze_correlation.py scripts/data/comprehensive_correlation_port_a_*.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats
import matplotlib.pyplot as plt


@dataclass
class Reading:
    timestamp: float
    segment_id: int
    segment_type: str
    ramp_rate: float
    transducer_pressure: float
    alicat_pressure: float
    alicat_baro: float
    offset_absolute: float


def load_data(csv_file: Path) -> List[Reading]:
    """Load correlation data from CSV. Supports optional transducer_pressure_raw_psi column."""
    readings = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            alicat_baro = row.get('alicat_baro_psia') or ''
            alicat_baro_f = float(alicat_baro) if alicat_baro.strip() else 14.7
            readings.append(Reading(
                timestamp=float(row['timestamp']),
                segment_id=int(row['segment_id']),
                segment_type=row['segment_type'],
                ramp_rate=float(row['ramp_rate_psi_s']),
                transducer_pressure=float(row['transducer_pressure_psi']),
                alicat_pressure=float(row['alicat_pressure_psia']),
                alicat_baro=alicat_baro_f,
                offset_absolute=float(row['offset_absolute']),
            ))
    return readings


def analyze_static_holds(readings: List[Reading]) -> Dict:
    """
    Analyze static hold segments to find the 'perfect' offset.
    Static holds at 0 ramp rate give us the most accurate comparison.
    """
    static_readings = [r for r in readings if r.segment_type == 'static']
    
    if not static_readings:
        return {}
    
    # Group by pressure level (within 1 PSI tolerance)
    pressure_groups: Dict[float, List[Reading]] = {}
    for r in static_readings:
        # Round to nearest PSI to group
        pressure_key = round(r.alicat_pressure)
        if pressure_key not in pressure_groups:
            pressure_groups[pressure_key] = []
        pressure_groups[pressure_key].append(r)
    
    results = {
        'by_pressure': {},
        'overall': {}
    }
    
    all_offsets = []
    
    print("\n" + "="*70)
    print("STATIC HOLD ANALYSIS (0 ramp rate = 'truth' readings)")
    print("="*70)
    print(f"{'Pressure (PSIA)':<15} {'N Samples':<12} {'Mean Offset':<15} {'Std Offset':<15} {'Noise Trans':<15} {'Noise Alicat':<15}")
    print("-"*70)
    
    for pressure in sorted(pressure_groups.keys()):
        group = pressure_groups[pressure]
        offsets = [r.offset_absolute for r in group]
        
        mean_offset = np.mean(offsets)
        std_offset = np.std(offsets)
        noise_trans = np.std([r.transducer_pressure for r in group])
        noise_alicat = np.std([r.alicat_pressure for r in group])
        
        results['by_pressure'][pressure] = {
            'mean_offset': mean_offset,
            'std_offset': std_offset,
            'n_samples': len(group),
            'noise_transducer': noise_trans,
            'noise_alicat': noise_alicat
        }
        
        all_offsets.extend(offsets)
        
        print(f"{pressure:<15.1f} {len(group):<12} {mean_offset:<15.4f} {std_offset:<15.4f} {noise_trans:<15.4f} {noise_alicat:<15.4f}")
    
    # Overall statistics
    results['overall'] = {
        'mean_offset': np.mean(all_offsets),
        'std_offset': np.std(all_offsets),
        'n_samples': len(all_offsets)
    }
    
    print("\n" + "-"*70)
    print(f"{'OVERALL':<15} {len(all_offsets):<12} {results['overall']['mean_offset']:<15.4f} {results['overall']['std_offset']:<15.4f}")
    print("="*70)
    
    return results


def analyze_ramp_rate_effects(readings: List[Reading]) -> Dict:
    """
    Analyze how offset changes with ramp rate.
    Also quantify noise at different ramp rates.
    """
    # Group by ramp rate
    rate_groups: Dict[float, List[Reading]] = {}
    for r in readings:
        if r.ramp_rate not in rate_groups:
            rate_groups[r.ramp_rate] = []
        rate_groups[r.ramp_rate].append(r)
    
    results = {}
    
    print("\n" + "="*70)
    print("RAMP RATE ANALYSIS")
    print("="*70)
    print(f"{'Ramp Rate':<12} {'N Samples':<12} {'Mean Offset':<15} {'Std Offset':<15} {'Noise Trans':<15} {'Noise Alicat':<15}")
    print("-"*70)
    
    ramp_rates = []
    mean_offsets = []
    offset_stds = []
    noise_trans_list = []
    noise_alicat_list = []
    
    for rate in sorted(rate_groups.keys()):
        group = rate_groups[rate]
        offsets = [r.offset_absolute for r in group]
        
        mean_offset = np.mean(offsets)
        std_offset = np.std(offsets)
        noise_trans = np.std([r.transducer_pressure for r in group])
        noise_alicat = np.std([r.alicat_pressure for r in group])
        
        results[rate] = {
            'mean_offset': mean_offset,
            'std_offset': std_offset,
            'noise_transducer': noise_trans,
            'noise_alicat': noise_alicat,
            'n_samples': len(group)
        }
        
        ramp_rates.append(rate)
        mean_offsets.append(mean_offset)
        offset_stds.append(std_offset)
        noise_trans_list.append(noise_trans)
        noise_alicat_list.append(noise_alicat)
        
        print(f"{rate:<12.2f} {len(group):<12} {mean_offset:<15.4f} {std_offset:<15.4f} {noise_trans:<15.4f} {noise_alicat:<15.4f}")
    
    print("="*70)
    
    # Linear regression: offset vs ramp rate
    if len(ramp_rates) > 2 and max(ramp_rates) > 0:
        # Exclude 0 for this analysis (static holds are our baseline)
        non_zero_rates = [r for r in ramp_rates if r > 0]
        non_zero_offsets = [mean_offsets[i] for i, r in enumerate(ramp_rates) if r > 0]
        
        if len(non_zero_rates) > 1:
            slope, intercept, r_value, p_value, std_err = stats.linregress(non_zero_rates, non_zero_offsets)
            
            print(f"\nOffset vs Ramp Rate Linear Fit:")
            print(f"  Equation: offset = {slope:.6f} * ramp_rate + {intercept:.4f}")
            print(f"  R-squared: {r_value**2:.4f}")
            print(f"  P-value: {p_value:.6f}")
            print(f"  Std Error: {std_err:.6f}")
            
            results['offset_vs_rate'] = {
                'slope': slope,
                'intercept': intercept,
                'r_squared': r_value**2,
                'p_value': p_value
            }
    
    # Linear regression: noise vs ramp rate
    if len(ramp_rates) > 2:
        slope_trans, _, r_trans, _, _ = stats.linregress(ramp_rates, noise_trans_list)
        slope_alicat, _, r_alicat, _, _ = stats.linregress(ramp_rates, noise_alicat_list)
        
        print(f"\nNoise vs Ramp Rate:")
        print(f"  Transducer: noise increases by {slope_trans:.6f} PSI per PSI/s ramp rate (R²={r_trans**2:.4f})")
        print(f"  Alicat: noise increases by {slope_alicat:.6f} PSI per PSI/s ramp rate (R²={r_alicat**2:.4f})")
        
        results['noise_vs_rate'] = {
            'transducer': {'slope': slope_trans, 'r_squared': r_trans**2},
            'alicat': {'slope': slope_alicat, 'r_squared': r_alicat**2}
        }
    
    return results


def analyze_barometric(readings: List[Reading], port_label: str) -> Dict:
    """Report barometric statistics for a single file/port."""
    if not readings:
        return {}
    baros = [r.alicat_baro for r in readings]
    mean_baro = float(np.mean(baros))
    std_baro = float(np.std(baros))
    return {
        'mean_psia': mean_baro,
        'std_psia': std_baro,
        'n': len(baros),
        'port_label': port_label,
    }


def report_barometric_summary(per_file_results: List[tuple[str, Dict]]) -> None:
    """Print barometric summary across files/ports and optional offset recommendation."""
    if not per_file_results:
        return
    print("\n" + "="*70)
    print("BAROMETRIC SUMMARY")
    print("="*70)
    print(f"{'Port/File':<25} {'Mean baro (PSIA)':<18} {'Std':<10} {'N':<8}")
    print("-"*70)
    ref_psia = 14.7
    for label, res in per_file_results:
        if not res:
            continue
        mean_b = res['mean_psia']
        std_b = res['std_psia']
        n = res['n']
        print(f"{label:<25} {mean_b:<18.4f} {std_b:<10.4f} {n:<8}")
    if len(per_file_results) >= 2:
        means = [r[1]['mean_psia'] for r in per_file_results if r[1]]
        if len(means) >= 2:
            print(f"\nPort-to-port baro difference: {abs(means[0] - means[1]):.4f} PSIA")
    print("\nOptional barometric offset (to reference 14.7 PSIA):")
    for label, res in per_file_results:
        if not res:
            continue
        offset = ref_psia - res['mean_psia']
        print(f"  {label}: barometric_offset_psi = {offset:.4f}")
    print("="*70)


def analyze_pressure_dependence(readings: List[Reading]) -> Dict:
    """
    Check if offset varies with absolute pressure (non-linearity).
    """
    # Bin by pressure
    pressure_bins = np.arange(10, 110, 5)  # 5 PSI bins from 10 to 105
    bin_centers = []
    bin_offsets = []
    
    for i in range(len(pressure_bins) - 1):
        bin_readings = [r for r in readings 
                       if pressure_bins[i] <= r.alicat_pressure < pressure_bins[i+1]]
        if len(bin_readings) > 10:  # Need enough samples
            offsets = [r.offset_absolute for r in bin_readings]
            bin_centers.append((pressure_bins[i] + pressure_bins[i+1]) / 2)
            bin_offsets.append(np.mean(offsets))
    
    results = {}
    
    if len(bin_centers) > 3:
        slope, intercept, r_value, p_value, std_err = stats.linregress(bin_centers, bin_offsets)
        
        print("\n" + "="*70)
        print("PRESSURE-DEPENDENT OFFSET ANALYSIS (Non-linearity check)")
        print("="*70)
        print(f"Linear fit: offset = {slope:.6f} * pressure + {intercept:.4f}")
        print(f"R-squared: {r_value**2:.4f}")
        print(f"P-value: {p_value:.6f}")
        
        if abs(slope) > 0.001 and p_value < 0.05:
            print(f"\n*** SIGNIFICANT PRESSURE DEPENDENCE DETECTED ***")
            print(f"Offset changes by {slope:.4f} PSI per PSI of pressure")
            print(f"At 15 PSIA: offset = {slope*15 + intercept:.4f} PSI")
            print(f"At 100 PSIA: offset = {slope*100 + intercept:.4f} PSI")
            print(f"Difference: {slope*85:.4f} PSI across the range")
        else:
            print(f"\nNo significant pressure dependence (slope {slope:.6f} is negligible)")
        
        results = {
            'slope': slope,
            'intercept': intercept,
            'r_squared': r_value**2,
            'p_value': p_value,
            'significant': abs(slope) > 0.001 and p_value < 0.05
        }
    
    return results


def generate_recommendations(
    static_analysis: Dict,
    ramp_analysis: Dict,
    pressure_analysis: Dict,
    port_label: str = "",
) -> List[str]:
    """Generate calibration recommendations for one port. Returns list of recommendation strings."""
    prefix = f"[{port_label}] " if port_label else ""
    recommendations = []

    # 1. Base offset from static holds at atmosphere
    if 14 in static_analysis.get('by_pressure', {}):
        atmos_data = static_analysis['by_pressure'][14]
        base_offset = atmos_data['mean_offset']
        transducer_offset = -14.7 - base_offset
        recommendations.append(f"transducer_offset_psi = {transducer_offset:.4f}")
    
    # 2. Ramp rate compensation
    if 'offset_vs_rate' in ramp_analysis:
        slope = ramp_analysis['offset_vs_rate']['slope']
        r_squared = ramp_analysis['offset_vs_rate']['r_squared']
        if r_squared > 0.5 and abs(slope) > 0.01:
            recommendations.append(f"ramp_rate_correction_slope = {slope:.4f}")
    # 3. Pressure non-linearity
    if pressure_analysis.get('significant', False):
        slope = pressure_analysis['slope']
        recommendations.append(f"pressure_correction_slope = {slope:.6f}")
    return recommendations


def _print_single_port_recommendations(
    static_analysis: Dict,
    ramp_analysis: Dict,
    pressure_analysis: Dict,
    port_label: str,
) -> List[str]:
    """Print detailed recommendations for one port and return recommendation strings."""
    recommendations = generate_recommendations(
        static_analysis, ramp_analysis, pressure_analysis, port_label=port_label
    )
    print(f"\n--- {port_label} ---")
    print("1. BASE OFFSET (from static hold at ~14.7 PSIA):")
    if 14 in static_analysis.get('by_pressure', {}):
        atmos_data = static_analysis['by_pressure'][14]
        base_offset = atmos_data['mean_offset']
        transducer_offset = -14.7 - base_offset
        print(f"   Observed offset at atmosphere: {base_offset:.4f} PSI")
        print(f"   Recommended transducer_offset_psi: {transducer_offset:.4f}")
    if 'offset_vs_rate' in ramp_analysis:
        r_squared = ramp_analysis['offset_vs_rate']['r_squared']
        print(f"2. RAMP RATE: R²={r_squared:.4f}")
    if pressure_analysis.get('significant', False):
        slope = pressure_analysis['slope']
        intercept = pressure_analysis.get('intercept', 0)
        print(f"3. PRESSURE NON-LINEARITY: offset = {slope:.6f} * pressure + {intercept:.4f}")
    else:
        print("3. PRESSURE NON-LINEARITY: Not significant (good linearity)")
    return recommendations


def plot_results(readings: List[Reading], output_file: str):
    """Generate diagnostic plots."""
    try:
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # Plot 1: Offset vs Time
        ax = axes[0, 0]
        times = [r.timestamp - readings[0].timestamp for r in readings]
        offsets = [r.offset_absolute for r in readings]
        colors = ['red' if r.segment_type == 'static' else 'blue' for r in readings]
        ax.scatter(times, offsets, c=colors, alpha=0.5, s=1)
        ax.axhline(y=np.mean(offsets), color='green', linestyle='--', label='Mean')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Offset (PSI)')
        ax.set_title('Offset vs Time (Red=Static, Blue=Ramp)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Plot 2: Offset vs Pressure
        ax = axes[0, 1]
        pressures = [r.alicat_pressure for r in readings]
        ax.scatter(pressures, offsets, c=colors, alpha=0.5, s=1)
        ax.set_xlabel('Alicat Pressure (PSIA)')
        ax.set_ylabel('Offset (PSI)')
        ax.set_title('Offset vs Pressure')
        ax.grid(True, alpha=0.3)
        
        # Plot 3: Noise vs Ramp Rate
        ax = axes[1, 0]
        # Calculate noise in bins
        rate_bins = sorted(set([r.ramp_rate for r in readings]))
        trans_noise = []
        alicat_noise = []
        
        for rate in rate_bins:
            rate_readings = [r for r in readings if r.ramp_rate == rate]
            if len(rate_readings) > 10:
                trans_noise.append(np.std([r.transducer_pressure for r in rate_readings]))
                alicat_noise.append(np.std([r.alicat_pressure for r in rate_readings]))
            else:
                trans_noise.append(0)
                alicat_noise.append(0)
        
        ax.plot(rate_bins, trans_noise, 'o-', label='Transducer', color='blue')
        ax.plot(rate_bins, alicat_noise, 's-', label='Alicat', color='red')
        ax.set_xlabel('Ramp Rate (PSI/s)')
        ax.set_ylabel('Noise (std dev, PSI)')
        ax.set_title('Noise vs Ramp Rate')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Plot 4: Offset vs Ramp Rate
        ax = axes[1, 1]
        rate_means = []
        rate_stds = []
        for rate in rate_bins:
            rate_readings = [r for r in readings if r.ramp_rate == rate]
            if rate_readings:
                offsets = [r.offset_absolute for r in rate_readings]
                rate_means.append(np.mean(offsets))
                rate_stds.append(np.std(offsets))
            else:
                rate_means.append(0)
                rate_stds.append(0)
        
        ax.errorbar(rate_bins, rate_means, yerr=rate_stds, fmt='o', capsize=5, color='green')
        ax.axhline(y=np.mean([r.offset_absolute for r in readings if r.segment_type == 'static']), 
                   color='red', linestyle='--', label='Static hold mean')
        ax.set_xlabel('Ramp Rate (PSI/s)')
        ax.set_ylabel('Mean Offset (PSI)')
        ax.set_title('Offset vs Ramp Rate')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plot_file = output_file.replace('.csv', '_analysis.png')
        plt.savefig(plot_file, dpi=150)
        print(f"\nPlots saved to: {plot_file}")
        plt.close()
        
    except Exception as e:
        print(f"\nCould not generate plots: {e}")


def infer_port_from_path(csv_path: Path) -> str:
    """Infer port label from filename, e.g. comprehensive_correlation_port_a_*.csv -> port_a."""
    stem = csv_path.stem
    if 'port_a' in stem:
        return 'port_a'
    if 'port_b' in stem:
        return 'port_b'
    return stem[:20] if len(stem) > 20 else stem


def run_analyze(
    csv_paths: List[Path],
    no_plots: bool = False,
) -> int:
    """Analyze one or more correlation CSVs; print recommendations and optionally plot. Returns 0 on success, 1 on error."""
    for p in csv_paths:
        if not p.exists():
            print(f"File not found: {p}")
            return 1

    per_file_baro: List[tuple[str, Dict]] = []
    all_recommendations: List[tuple[str, List[str]]] = []

    for csv_path in csv_paths:
        port_label = infer_port_from_path(csv_path)
        print(f"\nLoading data from: {csv_path} (port: {port_label})")
        readings = load_data(csv_path)
        print(f"Loaded {len(readings)} readings")

        static_analysis = analyze_static_holds(readings)
        ramp_analysis = analyze_ramp_rate_effects(readings)
        pressure_analysis = analyze_pressure_dependence(readings)

        baro_res = analyze_barometric(readings, port_label)
        if baro_res:
            per_file_baro.append((port_label, baro_res))

        recs = _print_single_port_recommendations(
            static_analysis, ramp_analysis, pressure_analysis, port_label
        )
        all_recommendations.append((port_label, recs))

        rec_file = csv_path.parent / (csv_path.stem + '_recommendations.txt')
        with open(rec_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(recs))
        print(f"Recommendations saved to: {rec_file}")

        if not no_plots:
            plot_results(readings, str(csv_path))

    report_barometric_summary(per_file_baro)

    print("\n" + "="*70)
    print("COMBINED SUMMARY RECOMMENDATIONS")
    print("="*70)
    for port_label, recs in all_recommendations:
        print(f"\n{port_label}:")
        for r in recs:
            print(f"   {r}")
    print("="*70)

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Analyze comprehensive correlation CSV(s); supports multiple files for both ports.'
    )
    parser.add_argument(
        'csv_files',
        type=Path,
        nargs='+',
        help='One or more comprehensive_correlation_*.csv files',
    )
    parser.add_argument('--no-plots', action='store_true', help='Skip generating plots')
    args = parser.parse_args()

    return run_analyze(csv_paths=args.csv_files, no_plots=args.no_plots)


if __name__ == '__main__':
    sys.exit(main())
