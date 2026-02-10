#!/usr/bin/env python3
"""Test Port B for vacuum switch behavior."""

import sys
sys.path.insert(0, '.')

from app.core.config import load_config
from app.hardware.labjack import LabJackController
from app.hardware.alicat import AlicatController
import time
import csv
from datetime import datetime
from pathlib import Path

config = load_config()

# Build controllers for Port B
lj_cfg = config.get('hardware', {}).get('labjack', {})
base_config = {
    'device_type': lj_cfg.get('device_type', 'T7'),
    'connection_type': lj_cfg.get('connection_type', 'USB'),
    'identifier': lj_cfg.get('identifier', 'ANY'),
}
port_cfg = lj_cfg.get('port_b', {})
labjack = LabJackController({**base_config, **port_cfg})

alicat_base = config.get('hardware', {}).get('alicat', {})
port_cfg_alicat = alicat_base.get('port_b', {})
alicat_config = {
    'com_port': port_cfg_alicat.get('com_port'),
    'address': port_cfg_alicat.get('address'),
    'baudrate': alicat_base.get('baudrate', 19200),
    'timeout_s': alicat_base.get('timeout_s', 0.05),
}
alicat = AlicatController(alicat_config)

print("Connecting to hardware...")
if not labjack.configure():
    print("Failed to configure LabJack")
    sys.exit(1)
if not alicat.connect():
    print("Failed to connect to Alicat")
    sys.exit(1)

try:
    # For vacuum: set solenoid to vacuum (True)
    print("Setting solenoid to VACUUM mode...")
    labjack.set_solenoid(to_vacuum=True)
    
    # Cancel hold
    print("Canceling hold...")
    alicat.cancel_hold()
    
    # Prepare log
    log_path = Path(f"logs/vacuum_test_port_b_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    log_path.parent.mkdir(exist_ok=True)
    
    dio_names = [f'DIO{i}' for i in range(20)]
    
    with open(log_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'elapsed_s', 'transducer_psia', 'alicat_psia', 'no_active', 'nc_active'] + dio_names)
        
        start = time.monotonic()
        
        # Vacuum sweep: go from atmospheric down to ~5 PSIA (vacuum)
        targets = [
            (14.7, 2),   # Stay at atmosphere for 2s
            (5.0, 10),   # Go to vacuum (5 PSIA = ~-9.7 PSIG) for 10s
            (14.7, 5),   # Return to atmosphere for 5s
        ]
        
        for target_psia, duration in targets:
            print(f"Setting setpoint to {target_psia:.1f} PSIA ({target_psia - 14.7:.1f} PSIG)...")
            alicat.set_pressure(target_psia)
            
            segment_start = time.monotonic()
            while time.monotonic() - segment_start < duration:
                now = time.monotonic()
                
                reading = labjack.read_transducer()
                switch = labjack.read_switch_state()
                alicat_reading = alicat.read_status()
                
                # Read all DIO
                handle = labjack._shared_handle
                if handle:
                    from app.hardware import labjack as labjack_module
                    dio_values = labjack_module.ljm.eReadNames(handle, len(dio_names), dio_names)
                    dio_values = [int(v) for v in dio_values]
                else:
                    dio_values = [0] * 20
                
                writer.writerow([
                    time.time(),
                    now - start,
                    reading.pressure if reading else None,
                    alicat_reading.pressure if alicat_reading else None,
                    int(switch.no_active) if switch else None,
                    int(switch.nc_active) if switch else None,
                ] + dio_values)
                
                time.sleep(0.05)
    
    print(f"Log written: {log_path}")
    
    # Analyze results
    print("\nAnalyzing results...")
    with open(log_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Total samples: {len(rows)}")
    print("\nPressure progression (PSIG):")
    for i in [0, len(rows)//4, len(rows)//2, 3*len(rows)//4, -1]:
        row = rows[i]
        psig = float(row['transducer_psia']) - 14.7
        print(f"  t={float(row['elapsed_s']):.1f}s: {psig:.1f} PSIG, NO={row['no_active']}, NC={row['nc_active']}")
    
    print("\nDIO states:")
    for i in [0, len(rows)//4, len(rows)//2, 3*len(rows)//4, -1]:
        row = rows[i]
        print(f"  t={float(row['elapsed_s']):.1f}s: DIO0={row['DIO0']}, DIO1={row['DIO1']}, DIO11={row['DIO11']}, DIO12={row['DIO12']}, DIO16={row['DIO16']}, DIO17={row['DIO17']}")
    
    # Check for changes
    prev_no = rows[0]['no_active']
    prev_nc = rows[0]['nc_active']
    changes = []
    for row in rows[1:]:
        if row['no_active'] != prev_no or row['nc_active'] != prev_nc:
            psig = float(row['transducer_psia']) - 14.7
            changes.append((float(row['elapsed_s']), prev_no, row['no_active'], prev_nc, row['nc_active'], psig))
            prev_no = row['no_active']
            prev_nc = row['nc_active']
    
    if changes:
        print(f"\n✓ FOUND {len(changes)} SWITCH TRANSITIONS!")
        for t, no_old, no_new, nc_old, nc_new, psig in changes[:5]:
            print(f'  t={t:.1f}s: NO {no_old}->{no_new}, NC {nc_old}->{nc_new} @ {psig:.1f} PSIG')
    else:
        print("\n✗ No switch changes detected")

finally:
    alicat.disconnect()
    labjack.cleanup()
