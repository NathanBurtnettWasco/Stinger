#!/usr/bin/env python
"""Test the gauge/absolute pressure reference fix for in-spec evaluation."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.work_order_controller import WorkOrderController

def test_band_to_psi():
    """Test that _band_to_psi correctly converts gauge values to absolute."""
    
    # Create a mock controller instance
    controller = WorkOrderController.__new__(WorkOrderController)
    
    # Test case 1: Gauge reference with 9.0 PSIG target
    band = {'lower': 5.0, 'upper': 9.6}
    barometric_psi = 13.6
    
    # Gauge reference - should add barometric
    result_gauge = controller._band_to_psi(
        band, 'PSI', 0, 100, 'gauge', barometric_psi
    )
    print(f"Gauge reference (9.0 PSIG target):")
    print(f"  Input band: 5.0 - 9.6 PSIG")
    print(f"  Barometric: {barometric_psi} PSI")
    print(f"  Result: {result_gauge[0]:.2f} - {result_gauge[1]:.2f} PSIA")
    print(f"  Expected: {5.0 + barometric_psi:.2f} - {9.6 + barometric_psi:.2f} PSIA")
    
    assert abs(result_gauge[0] - (5.0 + barometric_psi)) < 0.01
    assert abs(result_gauge[1] - (9.6 + barometric_psi)) < 0.01
    print("  PASSED\n")
    
    # Test case 2: Absolute reference - should NOT add barometric
    result_absolute = controller._band_to_psi(
        band, 'PSI', 0, 100, 'absolute', barometric_psi
    )
    print(f"Absolute reference:")
    print(f"  Input band: 5.0 - 9.6 PSIA")
    print(f"  Barometric: {barometric_psi} PSI")
    print(f"  Result: {result_absolute[0]:.2f} - {result_absolute[1]:.2f} PSIA")
    print(f"  Expected: 5.0 - 9.6 PSIA (unchanged)")
    
    assert abs(result_absolute[0] - 5.0) < 0.01
    assert abs(result_absolute[1] - 9.6) < 0.01
    print("  PASSED\n")
    
    # Test case 3: None/empty reference should default to no conversion
    result_none = controller._band_to_psi(
        band, 'PSI', 0, 100, None, barometric_psi
    )
    print(f"None reference (defaults to no conversion):")
    print(f"  Input band: 5.0 - 9.6 PSI")
    print(f"  Barometric: {barometric_psi} PSI")
    print(f"  Result: {result_none[0]:.2f} - {result_none[1]:.2f} PSI")
    print(f"  Expected: 5.0 - 9.6 PSI (unchanged)")
    
    assert abs(result_none[0] - 5.0) < 0.01
    assert abs(result_none[1] - 9.6) < 0.01
    print("  PASSED\n")

if __name__ == '__main__':
    print("="*70)
    print("Testing _band_to_psi() pressure reference conversion")
    print("="*70 + "\n")
    test_band_to_psi()
    print("="*70)
    print("All tests passed!")
    print("="*70)
