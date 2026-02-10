#!/usr/bin/env python
"""
Unit test for pressure reference handling in in-spec evaluation.
Tests that gauge PTP values are compared to gauge measured values.
"""
import sys
from pathlib import Path
from unittest.mock import Mock

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


def test_gauge_reference_in_spec():
    """Test that gauge PTP bands are compared to gauge measured values."""
    print("\n" + "="*70)
    print("TEST: In-spec evaluation with gauge reference (15018 case)")
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
    
    # Test case: Switch activates at ~9.23 PSIG (measured value from log)
    measured_act_psig = 9.23
    measured_deact_psig = 7.76
    
    print(f"\nTest Setup:")
    print(f"  Part: 15018/399")
    print(f"  PTP Reference: Gauge")
    print(f"  PTP Increasing Band: 5.0 - 9.6 PSIG")
    print(f"  PTP Decreasing Band: 2.0 - 8.0 PSIG")
    
    print(f"\nMeasured Values (from test executor):")
    print(f"  Activation: {measured_act_psig:.2f} PSIG")
    print(f"  Deactivation: {measured_deact_psig:.2f} PSIG")
    
    # Test the band conversion
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup
    )
    
    if bands:
        act_band, deact_band = bands
        print(f"\nPTP Bands (should be in PSIG):")
        print(f"  Activation Band: {act_band[0]:.2f} - {act_band[1]:.2f} PSIG")
        print(f"  Deactivation Band: {deact_band[0]:.2f} - {deact_band[1]:.2f} PSIG")
        
        # Check if measured values are in spec
        act_ok = controller._is_value_within_band(measured_act_psig, act_band)
        deact_ok = controller._is_value_within_band(measured_deact_psig, deact_band)
        
        print(f"\nIn-Spec Check:")
        print(f"  Activation {measured_act_psig:.2f} in [{act_band[0]:.2f}, {act_band[1]:.2f}]: {act_ok}")
        print(f"  Deactivation {measured_deact_psig:.2f} in [{deact_band[0]:.2f}, {deact_band[1]:.2f}]: {deact_ok}")
        print(f"  Overall: {'PASS' if act_ok and deact_ok else 'FAIL'}")
        
        # Assertions
        assert act_ok, f"Activation {measured_act_psig:.2f} should be in band [{act_band[0]:.2f}, {act_band[1]:.2f}]"
        assert deact_ok, f"Deactivation {measured_deact_psig:.2f} should be in band [{deact_band[0]:.2f}, {deact_band[1]:.2f}]"
        
        print("\n  TEST PASSED!")
    else:
        print("\n  ERROR: Could not resolve bands!")
        assert False, "Band resolution failed"


def test_absolute_reference():
    """Test that absolute PTP bands are compared to absolute measured values."""
    print("\n" + "="*70)
    print("TEST: In-spec evaluation with absolute reference")
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
    
    # With absolute reference, measured values are in PSIA
    measured_act_psia = 22.0  # PSIA (within 18.6-23.2 band)
    measured_deact_psia = 20.0  # PSIA
    
    print(f"\nTest Setup:")
    print(f"  PTP Reference: Absolute")
    print(f"  PTP Increasing Band: 18.6 - 23.2 PSIA")
    
    print(f"\nMeasured Values (from test executor):")
    print(f"  Activation: {measured_act_psia:.2f} PSIA")
    print(f"  Deactivation: {measured_deact_psia:.2f} PSIA")
    
    bands = controller._resolve_mapped_acceptance_bands_psi(
        'port_a', 
        controller._current_test_setup
    )
    
    if bands:
        act_band, deact_band = bands
        print(f"\nPTP Bands (should be in PSIA):")
        print(f"  Activation Band: {act_band[0]:.2f} - {act_band[1]:.2f} PSIA")
        
        act_ok = controller._is_value_within_band(measured_act_psia, act_band)
        print(f"\n  In band: {act_ok}")
        assert act_ok, "Should be in spec"
        print("  TEST PASSED!")


if __name__ == '__main__':
    print("="*70)
    print("PRESSURE REFERENCE UNIT TESTS")
    print("="*70)
    
    try:
        test_gauge_reference_in_spec()
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
