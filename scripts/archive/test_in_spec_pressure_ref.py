#!/usr/bin/env python
"""
Unit test for pressure reference handling in in-spec evaluation.
This tests the complete flow from edge detection to in-spec evaluation.
"""
import sys
import math
from pathlib import Path
from unittest.mock import Mock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.work_order_controller import WorkOrderController
from app.services.ptp_service import TestSetup


def create_mock_test_setup(
    activation_target: float = 9.0,
    pressure_reference: str = 'gauge',
    units_label: str = 'PSI',
    increasing_lower: float = 5.0,
    increasing_upper: float = 9.6,
    decreasing_lower: float = 2.0,
    decreasing_upper: float = 8.0,
) -> TestSetup:
    """Create a mock TestSetup similar to 15018/399."""
    return TestSetup(
        part_id='15018',
        sequence_id='399',
        units_code='1',
        units_label=units_label,
        activation_direction='Increasing',
        activation_target=activation_target,
        pressure_reference=pressure_reference,
        terminals={'CommonTerminal': 4, 'NormallyOpenTerminal': 1, 'NormallyClosedTerminal': 3},
        bands={
            'increasing': {'lower': increasing_lower, 'upper': increasing_upper},
            'decreasing': {'lower': decreasing_lower, 'upper': decreasing_upper},
        },
        raw={},
    )


def test_in_spec_evaluation():
    """Test in-spec evaluation with gauge reference (15018 case)."""
    print("\n" + "="*70)
    print("TEST: In-spec evaluation with gauge reference")
    print("="*70)
    
    # Create controller instance
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._config = {'hardware': {'labjack': {'port_a': {}}}}
    controller._current_test_setup = create_mock_test_setup(
        activation_target=9.0,
        pressure_reference='gauge',
        increasing_lower=5.0,
        increasing_upper=9.6,
        decreasing_lower=2.0,
        decreasing_upper=8.0,
    )
    controller._last_barometric_psi = {'port_a': 13.607}
    controller._barometric_warning_issued = {'port_a': False}
    
    # Mock the port hardware
    mock_port = Mock()
    mock_port.get_latest_reading = Mock(return_value=Mock(
        alicat=Mock(barometric_pressure=13.607),
        transducer=Mock(pressure=13.607),
    ))
    controller._port_manager = Mock()
    controller._port_manager.get_port = Mock(return_value=mock_port)
    
    # Test case 1: Switch activates at expected gauge pressure (~10.2 PSIG)
    # This should be ~23.8 PSIA with 13.6 baro
    measured_act_gauge = 10.2  # PSIG
    measured_deact_gauge = 4.5  # PSIG
    baro = 13.607
    
    measured_act_abs = measured_act_gauge + baro  # 23.807 PSIA
    measured_deact_abs = measured_deact_gauge + baro  # 18.107 PSIA
    
    print(f"\nTest Setup:")
    print(f"  Part: 15018/399")
    print(f"  PTP Reference: Gauge")
    print(f"  PTP Increasing Band: 5.0 - 9.6 PSIG")
    print(f"  PTP Decreasing Band: 2.0 - 8.0 PSIG")
    print(f"  Barometric Pressure: {baro:.3f} PSIA")
    
    print(f"\nMeasured Values:")
    print(f"  Activation: {measured_act_gauge:.2f} PSIG = {measured_act_abs:.2f} PSIA")
    print(f"  Deactivation: {measured_deact_gauge:.2f} PSIG = {measured_deact_abs:.2f} PSIA")
    
    # Manually verify the band conversion
    print(f"\nExpected PTP Bands (converted to absolute):")
    print(f"  Increasing: {5.0 + baro:.2f} - {9.6 + baro:.2f} PSIA")
    print(f"  Decreasing: {2.0 + baro:.2f} - {8.0 + baro:.2f} PSIA")
    
    # Test the band conversion
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup,
        baro
    )
    
    if bands:
        act_band, deact_band = bands
        print(f"\nActual Converted Bands:")
        print(f"  Activation Band: {act_band[0]:.2f} - {act_band[1]:.2f} PSIA")
        print(f"  Deactivation Band: {deact_band[0]:.2f} - {deact_band[1]:.2f} PSIA")
        
        # Check if measured values are in spec
        act_ok = controller._is_value_within_band(measured_act_abs, act_band)
        deact_ok = controller._is_value_within_band(measured_deact_abs, deact_band)
        
        print(f"\nIn-Spec Check:")
        print(f"  Activation {measured_act_abs:.2f} in [{act_band[0]:.2f}, {act_band[1]:.2f}]: {act_ok}")
        print(f"  Deactivation {measured_deact_abs:.2f} in [{deact_band[0]:.2f}, {deact_band[1]:.2f}]: {deact_ok}")
        print(f"  Overall: {'PASS' if act_ok and deact_ok else 'FAIL'}")
        
        # Assertions
        assert act_ok, f"Activation {measured_act_abs:.2f} should be in band [{act_band[0]:.2f}, {act_band[1]:.2f}]"
        assert deact_ok, f"Deactivation {measured_deact_abs:.2f} should be in band [{deact_band[0]:.2f}, {deact_band[1]:.2f}]"
        
        print("\n  TEST PASSED!")
    else:
        print("\n  ERROR: Could not resolve bands!")
        assert False, "Band resolution failed"


def test_in_spec_out_of_range():
    """Test that values outside the band are correctly flagged as out-of-spec."""
    print("\n" + "="*70)
    print("TEST: Out-of-spec detection")
    print("="*70)
    
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._config = {'hardware': {'labjack': {'port_a': {}}}}
    controller._current_test_setup = create_mock_test_setup()
    controller._last_barometric_psi = {'port_a': 13.607}
    controller._barometric_warning_issued = {'port_a': False}
    
    mock_port = Mock()
    mock_port.get_latest_reading = Mock(return_value=Mock(
        alicat=Mock(barometric_pressure=13.607),
        transducer=Mock(pressure=13.607),
    ))
    controller._port_manager = Mock()
    controller._port_manager.get_port = Mock(return_value=mock_port)
    
    baro = 13.607
    
    # Test with activation too low (3.0 PSIG = 16.6 PSIA, below 18.6 min)
    measured_act_gauge = 3.0  # Too low
    measured_deact_gauge = 4.5  # OK
    
    measured_act_abs = measured_act_gauge + baro
    measured_deact_abs = measured_deact_gauge + baro
    
    print(f"\nTest with activation TOO LOW:")
    print(f"  Measured: {measured_act_gauge:.2f} PSIG = {measured_act_abs:.2f} PSIA")
    print(f"  Expected band: {5.0 + baro:.2f} - {9.6 + baro:.2f} PSIA")
    
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup,
        baro
    )
    
    if bands:
        act_band, deact_band = bands
        act_ok = controller._is_value_within_band(measured_act_abs, act_band)
        
        print(f"  In band: {act_ok}")
        assert not act_ok, f"Activation {measured_act_abs:.2f} should be OUT of band"
        print("  TEST PASSED - Correctly detected out-of-spec!")
    
    # Test with activation too high (15.0 PSIG = 28.6 PSIA, above 23.2 max)
    measured_act_gauge = 15.0  # Too high
    measured_act_abs = measured_act_gauge + baro
    
    print(f"\nTest with activation TOO HIGH:")
    print(f"  Measured: {measured_act_gauge:.2f} PSIG = {measured_act_abs:.2f} PSIA")
    print(f"  Expected band: {5.0 + baro:.2f} - {9.6 + baro:.2f} PSIA")
    
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup,
        baro
    )
    
    if bands:
        act_band, _ = bands
        act_ok = controller._is_value_within_band(measured_act_abs, act_band)
        
        print(f"  In band: {act_ok}")
        assert not act_ok, f"Activation {measured_act_abs:.2f} should be OUT of band"
        print("  TEST PASSED - Correctly detected out-of-spec!")


def test_absolute_reference():
    """Test that absolute reference doesn't add barometric pressure."""
    print("\n" + "="*70)
    print("TEST: Absolute reference (no conversion)")
    print("="*70)
    
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._config = {'hardware': {'labjack': {'port_a': {}}}}
    controller._current_test_setup = create_mock_test_setup(
        activation_target=22.6,  # PSIA
        pressure_reference='absolute',
        increasing_lower=18.6,
        increasing_upper=23.2,
    )
    controller._last_barometric_psi = {'port_a': 13.607}
    controller._barometric_warning_issued = {'port_a': False}
    
    mock_port = Mock()
    mock_port.get_latest_reading = Mock(return_value=Mock(
        alicat=Mock(barometric_pressure=13.607),
        transducer=Mock(pressure=13.607),
    ))
    controller._port_manager = Mock()
    controller._port_manager.get_port = Mock(return_value=mock_port)
    
    baro = 13.607
    
    # With absolute reference, measured values are already in PSIA
    measured_act_abs = 23.8  # PSIA
    measured_deact_abs = 18.1  # PSIA
    
    print(f"\nTest Setup:")
    print(f"  PTP Reference: Absolute")
    print(f"  PTP Increasing Band: 18.6 - 23.2 PSIA")
    print(f"  Barometric Pressure: {baro:.3f} PSIA (should be ignored)")
    
    print(f"\nMeasured Values:")
    print(f"  Activation: {measured_act_abs:.2f} PSIA")
    print(f"  Deactivation: {measured_deact_abs:.2f} PSIA")
    
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup,
        baro
    )
    
    if bands:
        act_band, deact_band = bands
        print(f"\nActual Bands (should NOT include baro):")
        print(f"  Activation Band: {act_band[0]:.2f} - {act_band[1]:.2f} PSIA")
        
        # Bands should be unchanged (no barometric added)
        assert abs(act_band[0] - 18.6) < 0.01, f"Lower bound should be 18.6, got {act_band[0]}"
        assert abs(act_band[1] - 23.2) < 0.01, f"Upper bound should be 23.2, got {act_band[1]}"
        
        act_ok = controller._is_value_within_band(measured_act_abs, act_band)
        print(f"\n  In band: {act_ok}")
        assert act_ok, "Should be in spec"
        print("  TEST PASSED!")


if __name__ == '__main__':
    print("="*70)
    print("PRESSURE REFERENCE UNIT TESTS")
    print("="*70)
    
    try:
        test_in_spec_evaluation()
        test_in_spec_out_of_range()
        test_absolute_reference()
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED!")
        print("="*70)
    except AssertionError as e:
        print(f"\n  TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
