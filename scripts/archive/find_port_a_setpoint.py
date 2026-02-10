#!/usr/bin/env python
"""
Quick switch setpoint finder for Port A - ramps up from atmosphere and detects activation.

Usage:
    python scripts/find_port_a_setpoint.py
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config
from app.hardware.alicat import AlicatController
from app.hardware.labjack import LabJackController

def main():
    print("="*70)
    print("PORT A SWITCH SETPOINT FINDER")
    print("="*70)
    print("This will ramp pressure from atmosphere to ~30 PSI and detect")
    print("when the switch activates (closes on increasing pressure).")
    print("="*70)
    
    config = load_config()
    
    # Build controllers for port_a
    labjack_cfg = config.get('hardware', {}).get('labjack', {})
    port_cfg = labjack_cfg.get('port_a', {})
    
    labjack = LabJackController({
        'device_type': labjack_cfg.get('device_type', 'T7'),
        'connection_type': labjack_cfg.get('connection_type', 'USB'),
        'identifier': labjack_cfg.get('identifier', 'ANY'),
        'transducer_ain': port_cfg.get('transducer_ain'),
        'transducer_ain_neg': port_cfg.get('transducer_ain_neg'),
        'transducer_voltage_min': port_cfg.get('transducer_voltage_min', 0.5),
        'transducer_voltage_max': port_cfg.get('transducer_voltage_max', 4.5),
        'transducer_pressure_min': port_cfg.get('transducer_pressure_min', 0.0),
        'transducer_pressure_max': port_cfg.get('transducer_pressure_max', 115.0),
        'transducer_filter_alpha': 0.0,  # No filter
        'transducer_reference': port_cfg.get('transducer_reference', 'absolute'),
        'transducer_offset_psi': 0.0,
        'switch_no_dio': port_cfg.get('switch_no_dio'),
        'switch_nc_dio': port_cfg.get('switch_nc_dio'),
        'switch_com_dio': port_cfg.get('switch_com_dio'),
        'switch_com_state': port_cfg.get('switch_com_state'),
        'switch_active_low': port_cfg.get('switch_active_low', True),
        'solenoid_dio': port_cfg.get('solenoid_dio'),
    })
    
    alicat_cfg = config.get('hardware', {}).get('alicat', {})
    port_alicat_cfg = alicat_cfg.get('port_a', {})
    alicat = AlicatController({
        'com_port': port_alicat_cfg.get('com_port'),
        'address': port_alicat_cfg.get('address'),
        'baudrate': alicat_cfg.get('baudrate', 19200),
        'timeout_s': 0.1,
        'pressure_index': alicat_cfg.get('pressure_index'),
        'setpoint_index': alicat_cfg.get('setpoint_index'),
        'gauge_index': alicat_cfg.get('gauge_index'),
        'barometric_index': alicat_cfg.get('barometric_index'),
    })
    
    print("\nConnecting to hardware...")
    if not labjack.configure():
        print("[FAIL] LabJack configuration failed")
        return 1
    
    if not alicat.connect():
        print("[FAIL] Alicat connection failed")
        labjack.cleanup()
        return 1
    
    print("Connected!")
    
    # Get barometric pressure
    status = alicat.read_status()
    baro = status.barometric_pressure if status else 14.7
    print(f"\nBarometric pressure: {baro:.2f} PSIA")
    
    # First, make sure we're at atmosphere
    print("\n[1/3] Exhausting to atmosphere...")
    alicat.exhaust()
    time.sleep(3.0)
    
    # Check initial switch state
    print("\n[2/3] Checking initial switch state...")
    samples = []
    for _ in range(10):
        switch_state = labjack.read_switch_state()
        if switch_state:
            samples.append(switch_state.switch_activated)
        time.sleep(0.05)
    
    if not samples:
        print("[ERROR] Could not read switch state")
        alicat.disconnect()
        labjack.cleanup()
        return 1
    
    initial_active = sum(samples) / len(samples) > 0.5
    print(f"  Initial switch state: {'ACTIVE (closed)' if initial_active else 'INACTIVE (open)'}")
    
    if initial_active:
        print("  [WARNING] Switch is already active at atmosphere!")
        print("  This may indicate wiring issue or wrong switch type.")
    
    # Ramp up and detect activation
    print("\n[3/3] Ramping up pressure to find activation point...")
    print("  Target: ~30 PSIA")
    print("  Rate: ~2 PSI/s")
    print()
    
    # Set solenoid to vacuum to apply pressure
    print("  Setting solenoid to VACUUM...")
    labjack.set_solenoid(to_vacuum=True)
    time.sleep(0.5)
    
    # Set moderate ramp rate and target
    alicat.set_ramp_rate(2.0, time_unit='s')  # 2 PSI/s
    alicat.set_pressure(30.0)  # Target 30 PSIA
    
    activation_pressure = None
    activation_detected = False
    last_status_time = time.time()
    start_time = time.time()
    
    try:
        while time.time() - start_time < 30:  # Max 30 seconds
            current_time = time.time()
            
            # Read pressure and switch state
            trans = labjack.read_transducer()
            alicat_status = alicat.read_status()
            switch_state = labjack.read_switch_state()
            
            if trans and alicat_status and switch_state:
                pressure = alicat_status.pressure
                switch_active = switch_state.switch_activated
                
                # Check for activation (switch becoming active)
                if not initial_active and switch_active and not activation_detected:
                    activation_pressure = pressure
                    activation_detected = True
                    print(f"\n*** SWITCH ACTIVATED at {pressure:.2f} PSIA ***")
                    print(f"    Transducer reading: {trans.pressure:.2f} PSI")
                    break
                
                # Print status every second
                if current_time - last_status_time >= 1.0:
                    print(f"  Pressure: {pressure:6.2f} PSIA | Switch: {'ACTIVE' if switch_active else 'inactive'}")
                    last_status_time = current_time
            
            time.sleep(0.01)  # 100 Hz check rate
            
    except KeyboardInterrupt:
        print("\nStopped by user")
    
    # Cleanup
    print("\nCleaning up...")
    alicat.set_pressure(baro)  # Return to atmosphere
    time.sleep(2.0)
    alicat.exhaust()
    time.sleep(1.0)
    alicat.disconnect()
    labjack.cleanup()
    
    # Summary
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    if activation_detected and activation_pressure:
        print(f"\nSwitch ACTIVATES at approximately: {activation_pressure:.2f} PSIA")
        print(f"                                   ({activation_pressure - baro:.2f} PSIG)")
        print(f"\nThis is the INCREASING activation setpoint.")
        print(f"\nRecommended part numbers for testing:")
        print(f"  - Target range: {activation_pressure - 2:.1f} to {activation_pressure + 2:.1f} PSI")
        
        # Find closest parts from our earlier query
        if activation_pressure < 20:
            print(f"\n  SBA01879-03 / Seq 400 (19.6 PSI target)")
            print(f"  Or: SBA01879-03 / Seq 225 (20.0 PSI target)")
        else:
            print(f"\n  SBA01879-03 / Seq 225 (20.0 PSI target)")
            print(f"  Or: DOE 2001-06 / Seq 0225 (20.5 PSI target)")
    else:
        print("\n[WARNING] No activation detected!")
        print("  Possible causes:")
        print("  - Switch is normally-closed (deactivates on pressure)")
        print("  - Switch has higher setpoint (>30 PSI)")
        print("  - Wiring issue")
        print("  - No switch connected")
    
    print("="*70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
