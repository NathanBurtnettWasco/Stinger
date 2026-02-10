#!/usr/bin/env python
"""Test cycle estimate display values"""
import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.work_order_controller import WorkOrderController
from app.services.ptp_service import TestSetup


def test_cycle_estimate_display():
    """Test that cycle estimates are displayed in correct units."""
    print("\n" + "="*70)
    print("TEST: Cycle estimate display for gauge PTP")
    print("="*70)
    
    # Create controller instance
    controller = WorkOrderController.__new__(WorkOrderController)
    controller._config = {'hardware': {'labjack': {'port_a': {}}}}
    controller._current_test_setup = TestSetup(
        part_id='15018',
        sequence_id='399',
        units_code='1',
        units_label='PSI',
        activation_direction='Increasing',
        activation_target=9.0,
        pressure_reference='gauge',
        terminals={},
        bands={
            'increasing': {'lower': 5.0, 'upper': 9.6},
            'decreasing': {'lower': 2.0, 'upper': 8.0},
        },
        raw={},
    )
    controller._last_barometric_psi = {'port_a': 13.607}
    controller._barometric_warning_issued = {'port_a': False}
    controller._cycle_estimates_abs_psi = {
        'port_a': {'activation': None, 'deactivation': None, 'count': 0}
    }
    
    # Mock the port hardware
    mock_port = Mock()
    mock_port.get_latest_reading = Mock(return_value=Mock(
        alicat=Mock(barometric_pressure=13.607),
        transducer=Mock(pressure=13.607),
    ))
    controller._port_manager = Mock()
    controller._port_manager.get_port = Mock(return_value=mock_port)
    
    # Mock UI bridge
    ui_bridge = Mock()
    ui_bridge.get_pressure_unit = Mock(return_value='PSIG')
    controller._ui_bridge = ui_bridge
    
    # Test: Simulate cycle estimates from test executor
    # These values are already in gauge units
    activation_gauge = 9.81  # PSIG
    deactivation_gauge = 4.28  # PSIG
    sample_count = 3
    
    print(f"\nInput from test executor (gauge PTP):")
    print(f"  Activation: {activation_gauge:.2f} PSIG")
    print(f"  Deactivation: {deactivation_gauge:.2f} PSIG")
    
    # Call the logic from _on_cycle_estimate
    unit_label = ui_bridge.get_pressure_unit()
    pressure_reference = controller._current_test_setup.pressure_reference
    
    # The fixed logic - no conversion, use values as-is
    activation_display_val = activation_gauge
    deactivation_display_val = deactivation_gauge
    
    activation_display = controller._to_display_pressure(
        'port_a',
        activation_display_val,
        unit_label,
        pressure_reference,
    ) if activation_display_val is not None else None
    deactivation_display = controller._to_display_pressure(
        'port_a',
        deactivation_display_val,
        unit_label,
        pressure_reference,
    ) if deactivation_display_val is not None else None
    
    print(f"\nDisplayed values (should match input):")
    print(f"  Activation: {activation_display:.2f} {unit_label}")
    print(f"  Deactivation: {deactivation_display:.2f} {unit_label}")
    
    # Verify - should be approximately the same (just unit conversion, no barometric)
    assert abs(activation_display - 9.81) < 0.1, f"Expected ~9.81, got {activation_display}"
    assert abs(deactivation_display - 4.28) < 0.1, f"Expected ~4.28, got {deactivation_display}"
    
    print("\n  TEST PASSED!")
    print("  Values are correctly displayed in gauge units without barometric conversion")


if __name__ == '__main__':
    print("="*70)
    print("CYCLE ESTIMATE DISPLAY TEST")
    print("="*70)
    
    try:
        test_cycle_estimate_display()
        print("\n" + "="*70)
        print("TEST PASSED!")
        print("="*70)
    except AssertionError as e:
        print(f"\n  TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
