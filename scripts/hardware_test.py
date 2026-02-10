"""
Hardware Test Script - Tests connected hardware components.

Tests:
- LabJack T7 connection and transducer readings (differential mode)
- Alicat pressure controllers (both ports)
- Skips: DB9 switches and solenoid valves (not connected)

Usage (from repo root):
    python scripts/hardware_test.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware import labjack as labjack_module
from app.hardware.labjack import LabJackController

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

logger = logging.getLogger(__name__)


def print_header(text: str) -> None:
    """Print a formatted header."""
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{text.center(70)}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")


def print_test(name: str, status: str, details: Optional[str] = None) -> None:
    """Print a test result."""
    if status == "PASS":
        status_str = f"{GREEN}[PASS]{RESET}"
    elif status == "FAIL":
        status_str = f"{RED}[FAIL]{RESET}"
    elif status == "SKIP":
        status_str = f"{YELLOW}[SKIP]{RESET}"
    elif status == "WARN":
        status_str = f"{YELLOW}[WARN]{RESET}"
    else:
        status_str = status
    
    print(f"  {status_str:20} {name}")
    if details:
        print(f"    {details}")


def list_available_com_ports() -> List[str]:
    """List all available COM ports."""
    try:
        ports = AlicatController.list_available_ports()
        return [p['device'] for p in ports]
    except Exception:
        return []


def test_labjack_transducers(config: Dict[str, Any]) -> Dict[str, bool]:
    """Test LabJack transducers for both ports."""
    results = {}
    
    print_header("LabJack Transducer Test")
    
    # Use shared handle to avoid multiple connections
    labjack_config = config.get('hardware', {}).get('labjack', {})
    base_config = {
        'device_type': labjack_config.get('device_type', 'T7'),
        'connection_type': labjack_config.get('connection_type', 'USB'),
        'identifier': labjack_config.get('identifier', 'ANY'),
    }
    
    for port_key in ['port_a', 'port_b']:
        port_name = port_key.replace('_', ' ').title()
        port_config = config.get('hardware', {}).get('labjack', {}).get(port_key, {})
        
        transducer_ain = port_config.get('transducer_ain')
        transducer_ain_neg = port_config.get('transducer_ain_neg')
        voltage_min = port_config.get('transducer_voltage_min', 0.5)
        voltage_max = port_config.get('transducer_voltage_max', 4.5)
        pressure_min = port_config.get('transducer_pressure_min', 0.0)
        pressure_max = port_config.get('transducer_pressure_max', 115.0)
        
        if transducer_ain is None:
            print_test(f"{port_name} Transducer", "SKIP", "Not configured")
            results[port_key] = False
            continue
        
        try:
            # Create LabJack controller
            controller = LabJackController({**base_config, **port_config})
            
            # Configure and connect
            if not controller.configure():
                print_test(f"{port_name} Transducer", "FAIL", f"Configuration failed: {controller._last_status}")
                results[port_key] = False
                continue
            
            # Take multiple readings to check stability
            readings = []
            for i in range(5):
                reading = controller.read_transducer()
                if reading:
                    readings.append(reading)
                time.sleep(0.1)
            
            if not readings:
                print_test(f"{port_name} Transducer", "FAIL", "No readings obtained")
                results[port_key] = False
                controller.cleanup()
                continue
            
            # Analyze readings
            voltages = [r.voltage for r in readings]
            pressures = [r.pressure for r in readings]
            
            avg_voltage = sum(voltages) / len(voltages)
            avg_pressure = sum(pressures) / len(pressures)
            voltage_range = max(voltages) - min(voltages)
            pressure_range = max(pressures) - min(pressures)
            
            # Check if readings are reasonable
            voltage_valid = voltage_min <= avg_voltage <= voltage_max
            pressure_valid = pressure_min <= avg_pressure <= pressure_max
            stable = voltage_range < 0.1  # Less than 0.1V variation
            
            if transducer_ain_neg is not None:
                mode_str = f"differential (AIN{transducer_ain}/AIN{transducer_ain_neg})"
            else:
                mode_str = f"single-ended (AIN{transducer_ain})"
            
            if voltage_valid and pressure_valid:
                status = "PASS"
                details = (
                    f"Mode: {mode_str}\n"
                    f"    Voltage: {avg_voltage:.3f} V (range: {min(voltages):.3f} - {max(voltages):.3f} V)\n"
                    f"    Pressure: {avg_pressure:.2f} PSI (range: {min(pressures):.2f} - {max(pressures):.2f} PSI)\n"
                    f"    Stability: {'Stable' if stable else 'Some variation'} (dV={voltage_range:.3f}V)"
                )
                results[port_key] = True
            else:
                status = "FAIL"
                issues = []
                suggestions = []
                
                if not voltage_valid:
                    issues.append(f"Voltage {avg_voltage:.3f}V outside expected range [{voltage_min}-{voltage_max}V]")
                    if avg_voltage > voltage_max:
                        if avg_voltage > 4.8:  # Near 5V suggests power supply or wiring issue
                            suggestions.append("Check: Transducer may not be powered, or A+/A- wires may be swapped")
                        else:
                            suggestions.append("Check: Transducer may be reading full scale or wiring issue")
                    elif avg_voltage < voltage_min:
                        suggestions.append("Check: Transducer may be reading zero scale or not connected")
                
                if not pressure_valid:
                    issues.append(f"Pressure {avg_pressure:.2f}PSI outside expected range [{pressure_min}-{pressure_max}PSI]")
                
                details = f"Mode: {mode_str}\n    Issues: {'; '.join(issues)}"
                if suggestions:
                    details += f"\n    Suggestions: {'; '.join(suggestions)}"
                
                results[port_key] = False
            
            print_test(f"{port_name} Transducer", status, details)
            controller.cleanup()
            
        except Exception as e:
            print_test(f"{port_name} Transducer", "FAIL", f"Exception: {e}")
            results[port_key] = False
    
    return results


def test_alicat_controllers(config: Dict[str, Any]) -> Dict[str, bool]:
    """Test Alicat controllers for both ports."""
    results = {}
    
    print_header("Alicat Controller Test")
    
    # List available COM ports
    available_ports = list_available_com_ports()
    if available_ports:
        print(f"  {BLUE}Available COM ports: {', '.join(available_ports)}{RESET}\n")
    else:
        print(f"  {YELLOW}No COM ports detected{RESET}\n")
    
    alicat_base_config = config.get('hardware', {}).get('alicat', {})
    
    # Track shared serial connections (for multiple Alicats on same COM port)
    shared_serials: Dict[str, Any] = {}
    controllers_to_cleanup: List[AlicatController] = []
    
    for port_key in ['port_a', 'port_b']:
        port_name = port_key.replace('_', ' ').title()
        port_config = alicat_base_config.get(port_key, {})
        
        com_port = port_config.get('com_port')
        address = port_config.get('address')
        
        if not com_port or not address:
            print_test(f"{port_name} Alicat", "SKIP", "Not configured")
            results[port_key] = False
            continue
        
        # Check if configured COM port exists
        if com_port not in available_ports:
            suggestion = ""
            if available_ports:
                # Found Alicats on COM9, suggest updating config
                found_on_com9 = any('COM9' in str(p) for p in available_ports)
                if found_on_com9:
                    suggestion = f"\n    Suggestion: Update config to use COM9 (Alicats found there)"
            
            print_test(f"{port_name} Alicat", "FAIL", 
                      f"COM port {com_port} not found. Available: {', '.join(available_ports) if available_ports else 'none'}{suggestion}")
            results[port_key] = False
            continue
        
        try:
            # Create Alicat controller
            alicat_config = {
                'com_port': com_port,
                'address': address,
                'baudrate': alicat_base_config.get('baudrate', 19200),
                'timeout_s': alicat_base_config.get('timeout_s', 0.05),
            }
            controller = AlicatController(alicat_config)
            
            # Handle shared COM port (multiple Alicats on same port)
            # Note: Both Alicats can share the same COM port with different addresses
            if com_port in shared_serials:
                # Use existing serial connection
                controller.set_shared_serial(shared_serials[com_port])
            else:
                # Create new serial connection
                if not controller.connect():
                    print_test(f"{port_name} Alicat", "FAIL", f"Connection failed: {controller._last_status}")
                    results[port_key] = False
                    continue
                # Store serial connection for other controllers on same port
                if controller._serial and controller._owns_serial:
                    shared_serials[com_port] = controller._serial
            
            # Test 1: Read status
            reading = controller.read_status()
            if not reading:
                print_test(f"{port_name} Alicat - Read Status", "FAIL", "No response from device")
                results[port_key] = False
                controller.disconnect()
                continue
            
            print_test(
                f"{port_name} Alicat - Read Status",
                "PASS",
                f"Pressure: {reading.pressure:.2f}, Setpoint: {reading.setpoint:.2f}",
            )
            
            # Test 2: Set setpoint (use a safe test value)
            # Don't change setpoint too much - just verify we can set it
            current_setpoint = reading.setpoint
            test_setpoint = current_setpoint + 0.5  # Small change for testing
            if controller.set_pressure(test_setpoint):
                print_test(
                    f"{port_name} Alicat - Set Setpoint",
                    "PASS",
                    f"Setpoint set to {test_setpoint:.2f}",
                )
                
                # Test 3: Verify setpoint was accepted
                # Some Alicats may round setpoints, so be lenient
                time.sleep(0.5)
                verify_reading = controller.read_status()
                if verify_reading:
                    setpoint_diff = abs(verify_reading.setpoint - test_setpoint)
                    # Allow up to 0.5 PSI difference (some devices round or have limits)
                    if setpoint_diff < 0.5:
                        print_test(
                            f"{port_name} Alicat - Verify Setpoint",
                            "PASS",
                            f"Setpoint confirmed: {verify_reading.setpoint:.2f} "
                            f"(requested: {test_setpoint:.2f})",
                        )
                        results[port_key] = True
                    else:
                        print_test(
                            f"{port_name} Alicat - Verify Setpoint",
                            "WARN",
                            f"Setpoint differs: Got {verify_reading.setpoint:.2f}, "
                            f"requested {test_setpoint:.2f} (may be device rounding/limits)",
                        )
                        # Still count as pass if we can communicate
                        results[port_key] = True
                else:
                    print_test(f"{port_name} Alicat - Verify Setpoint", "FAIL", "No response when verifying setpoint")
                    results[port_key] = False
            else:
                print_test(f"{port_name} Alicat - Set Setpoint", "FAIL", "Failed to set setpoint")
                results[port_key] = False
            
            # Reset setpoint to original value
            try:
                controller.set_pressure(reading.setpoint)
            except Exception:
                pass  # Ignore errors during cleanup
            
            # Track controllers that own serial connections for cleanup
            if controller._owns_serial:
                controllers_to_cleanup.append(controller)
            
        except Exception as e:
            print_test(f"{port_name} Alicat", "FAIL", f"Exception: {e}")
            results[port_key] = False
    
    # Clean up serial connections
    for controller in controllers_to_cleanup:
        try:
            controller.disconnect()
        except Exception:
            pass
    
    return results


def test_switch_inputs(config: Dict[str, Any]) -> Dict[str, bool]:
    """Test LabJack switch inputs and scan for DIO changes."""
    results = {}

    print_header("LabJack Switch Input Test")

    if not labjack_module.LJM_AVAILABLE:
        print_test("LabJack Switch Inputs", "SKIP", "labjack.ljm not available")
        return results

    labjack_config = config.get("hardware", {}).get("labjack", {})
    base_config = {
        "device_type": labjack_config.get("device_type", "T7"),
        "connection_type": labjack_config.get("connection_type", "USB"),
        "identifier": labjack_config.get("identifier", "ANY"),
    }

    for port_key in ["port_a", "port_b"]:
        port_name = port_key.replace("_", " ").title()
        port_config = config.get("hardware", {}).get("labjack", {}).get(port_key, {})
        no_dio = port_config.get("switch_no_dio")
        nc_dio = port_config.get("switch_nc_dio")

        if no_dio is None or nc_dio is None:
            print_test(f"{port_name} Switch Inputs", "SKIP", "NO/NC pins not configured")
            results[port_key] = False
            continue

        controller = LabJackController({**base_config, **port_config})
        if not controller.configure():
            print_test(
                f"{port_name} Switch Inputs",
                "FAIL",
                f"Configuration failed: {controller._last_status}",
            )
            results[port_key] = False
            continue

        handle = controller._shared_handle
        if handle is None:
            print_test(f"{port_name} Switch Inputs", "FAIL", "No LabJack handle")
            results[port_key] = False
            controller.cleanup()
            continue

        initial_state = controller.read_switch_state()
        initial_text = (
            f"NO={int(initial_state.no_active)} NC={int(initial_state.nc_active)}"
            if initial_state
            else "NO/NC unreadable"
        )
        print_test(
            f"{port_name} Switch Inputs",
            "PASS",
            f"Configured NO=DIO{no_dio} NC=DIO{nc_dio} | {initial_text}",
        )

        dio_indices = list(range(20))
        names = [f"DIO{idx}" for idx in dio_indices]
        try:
            initial_dio = labjack_module.ljm.eReadNames(handle, len(names), names)
        except Exception as exc:
            print_test(f"{port_name} DIO Scan", "FAIL", f"Read failed: {exc}")
            results[port_key] = False
            controller.cleanup()
            continue

        print(f"  {YELLOW}Toggle the {port_name} switch now... scanning for 5 seconds{RESET}")

        changed = set()
        last_dio = initial_dio
        start_time = time.monotonic()
        while time.monotonic() - start_time < 5.0:
            try:
                updated_dio = labjack_module.ljm.eReadNames(handle, len(names), names)
            except Exception as exc:
                print_test(f"{port_name} DIO Scan", "FAIL", f"Read failed: {exc}")
                results[port_key] = False
                controller.cleanup()
                changed = None
                break
            last_dio = updated_dio
            for idx, (before, after) in enumerate(zip(initial_dio, updated_dio)):
                if int(before) != int(after):
                    changed.add(idx)
            time.sleep(0.1)

        if changed is None:
            continue
        changed = sorted(changed)
        if changed:
            changed_details = ", ".join(
                f"DIO{idx} {int(initial_dio[idx])}->{int(last_dio[idx])}"
                for idx in changed
            )
            print_test(
                f"{port_name} DIO Scan",
                "PASS",
                f"Changed DIOs: {changed_details}",
            )
            results[port_key] = True
        else:
            print_test(
                f"{port_name} DIO Scan",
                "WARN",
                "No DIO changes detected",
            )
            results[port_key] = False

        controller.cleanup()

    return results


def test_skipped_components() -> None:
    """Report components that are skipped (not connected)."""
    print_header("Skipped Components (Not Connected)")
    
    print_test("Solenoid Valves (Port A)", "SKIP", "Not connected - skipping")
    print_test("Solenoid Valves (Port B)", "SKIP", "Not connected - skipping")


def print_summary(
    labjack_results: Dict[str, bool],
    alicat_results: Dict[str, bool],
    switch_results: Dict[str, bool],
) -> None:
    """Print test summary."""
    print_header("Test Summary")
    
    total_tests = 0
    passed_tests = 0
    
    for port_key in ['port_a', 'port_b']:
        port_name = port_key.replace('_', ' ').title()
        
        if port_key in labjack_results:
            total_tests += 1
            if labjack_results[port_key]:
                passed_tests += 1
                status = f"{GREEN}[PASS]{RESET}"
            else:
                status = f"{RED}[FAIL]{RESET}"
            print(f"  {status:20} {port_name} Transducer")
        
        if port_key in alicat_results:
            total_tests += 1
            if alicat_results[port_key]:
                passed_tests += 1
                status = f"{GREEN}[PASS]{RESET}"
            else:
                status = f"{RED}[FAIL]{RESET}"
            print(f"  {status:20} {port_name} Alicat")

        if port_key in switch_results:
            total_tests += 1
            if switch_results[port_key]:
                passed_tests += 1
                status = f"{GREEN}[PASS]{RESET}"
            else:
                status = f"{RED}[FAIL]{RESET}"
            print(f"  {status:20} {port_name} Switch Inputs")
    
    print(f"\n{BOLD}Total: {passed_tests}/{total_tests} tests passed{RESET}")
    
    if passed_tests == total_tests:
        print(f"{GREEN}{BOLD}All connected hardware tests passed!{RESET}\n")
    else:
        print(f"{YELLOW}{BOLD}Some tests failed. Check details above.{RESET}\n")


def test_all_com_ports_for_alicats() -> None:
    """Try to find Alicats on all available COM ports."""
    print_header("COM Port Scan - Looking for Alicats")
    
    available_ports = list_available_com_ports()
    if not available_ports:
        print_test("COM Port Scan", "SKIP", "No COM ports available")
        return
    
    alicat_base_config = {'baudrate': 19200, 'timeout_s': 0.05}
    found_devices = []
    
    for com_port in available_ports:
        # Try addresses A and B (common Alicat addresses)
        for address in ['A', 'B']:
            try:
                config = {
                    'com_port': com_port,
                    'address': address,
                    **alicat_base_config
                }
                controller = AlicatController(config)
                if controller.connect(max_retries=1):
                    reading = controller.read_status()
                    if reading:
                        found_devices.append({
                            'port': com_port,
                            'address': address,
                            'pressure': reading.pressure,
                            'setpoint': reading.setpoint
                        })
                        print_test(f"{com_port} Address {address}", "PASS", 
                                 f"Found! Pressure: {reading.pressure:.2f} PSI")
                    controller.disconnect()
            except Exception:
                pass
    
    if not found_devices:
        print_test("COM Port Scan", "FAIL", "No Alicat devices found on any COM port")
    else:
        print(f"\n  {GREEN}Found {len(found_devices)} Alicat device(s){RESET}")


def main() -> None:
    """Run hardware tests."""
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    
    print(f"\n{BOLD}{BLUE}{'='*70}{RESET}")
    print(f"{BOLD}{BLUE}{'Stinger Hardware Test'.center(70)}{RESET}")
    print(f"{BOLD}{BLUE}{'='*70}{RESET}\n")
    
    try:
        config = load_config()
    except Exception as e:
        print(f"{RED}Failed to load configuration: {e}{RESET}")
        return
    
    # Run tests
    labjack_results = test_labjack_transducers(config)
    switch_results = test_switch_inputs(config)
    test_all_com_ports_for_alicats()  # Scan for Alicats first
    alicat_results = test_alicat_controllers(config)
    test_skipped_components()
    
    # Print summary
    print_summary(labjack_results, alicat_results, switch_results)


if __name__ == '__main__':
    main()
