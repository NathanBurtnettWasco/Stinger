#!/usr/bin/env python3
"""Debug script to test Alicat communication."""

import sys
sys.path.insert(0, '.')

from app.core.config import load_config
from app.hardware.alicat import AlicatController
import time

config = load_config()
alicat_base = config.get('hardware', {}).get('alicat', {})

for port_name, port_key in [('Port A', 'port_a'), ('Port B', 'port_b')]:
    print(f"\n{'='*60}")
    print(f"Testing {port_name}")
    print('='*60)
    
    port_cfg = alicat_base.get(port_key, {})
    alicat_config = {
        'com_port': port_cfg.get('com_port'),
        'address': port_cfg.get('address'),
        'baudrate': alicat_base.get('baudrate', 19200),
        'timeout_s': alicat_base.get('timeout_s', 0.05),
    }
    
    print(f"Config: COM={alicat_config['com_port']}, Addr={alicat_config['address']}")
    
    alicat = AlicatController(alicat_config)
    if not alicat.connect():
        print(f"  ERROR: Failed to connect")
        continue
    
    # Read initial state
    print("\n1. Initial reading:")
    reading = alicat.read_status()
    if reading:
        print(f"   Pressure: {reading.pressure:.2f}")
        print(f"   Setpoint: {reading.setpoint:.2f}")
        print(f"   Raw: {reading.raw_values}")
    
    # Cancel hold
    print("\n2. Canceling hold mode...")
    success = alicat.cancel_hold()
    print(f"   Result: {'Success' if success else 'Failed'}")
    time.sleep(0.5)
    
    # Try setting setpoint
    print("\n3. Setting setpoint to 20.0...")
    success = alicat.set_pressure(20.0)
    print(f"   Command result: {'Success' if success else 'Failed'}")
    time.sleep(1.0)
    
    # Read again
    print("\n4. Reading after setpoint command:")
    reading = alicat.read_status()
    if reading:
        print(f"   Pressure: {reading.pressure:.2f}")
        print(f"   Setpoint: {reading.setpoint:.2f}")
        print(f"   Raw: {reading.raw_values}")
    
    # Check if it changed
    if reading and abs(reading.setpoint - 20.0) < 1.0:
        print("\n   ✓ Setpoint successfully changed!")
    else:
        print("\n   ✗ Setpoint did NOT change - still at", reading.setpoint if reading else "N/A")
    
    alicat.disconnect()

print("\n" + "="*60)
print("Done")
