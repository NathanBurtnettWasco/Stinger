"""
Test script to toggle solenoids individually for wiring verification.

This script cycles through each solenoid (Left/Right) multiple times,
allowing you to verify the wiring by listening to the solenoid clicks.

Usage (from repo root):
    python scripts/test_solenoids.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import load_config, get_port_config
from app.hardware.labjack import LabJackController

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Run solenoid toggle test."""
    print("=" * 60)
    print("SOLENOID TOGGLE TEST")
    print("=" * 60)
    print()
    
    # Load configuration
    try:
        config = load_config()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Get port configurations
    port_a_config = get_port_config(config, 'port_a')
    port_b_config = get_port_config(config, 'port_b')
    
    # Create LabJack controllers
    labjack_a_config = {
        **config['hardware']['labjack'],
        **port_a_config['labjack']
    }
    labjack_b_config = {
        **config['hardware']['labjack'],
        **port_b_config['labjack']
    }
    
    controller_left = LabJackController(labjack_a_config)
    controller_right = LabJackController(labjack_b_config)
    
    # Configure controllers
    print("Initializing LabJack controllers...")
    if not controller_left.configure():
        logger.error(f"Failed to configure LEFT controller: {controller_left._last_status}")
        sys.exit(1)
    
    # Calculate CIO numbers (DIO16-19 = CIO0-3)
    cio_left = controller_left.solenoid_dio - 16 if controller_left.solenoid_dio else None
    cio_right = controller_right.solenoid_dio - 16 if controller_right.solenoid_dio else None
    
    print(f"✓ LEFT controller configured:")
    print(f"    DIO{controller_left.solenoid_dio} = CIO{cio_left} (on DB15 connector)")
    
    if not controller_right.configure():
        logger.error(f"Failed to configure RIGHT controller: {controller_right._last_status}")
        sys.exit(1)
    print(f"✓ RIGHT controller configured:")
    print(f"    DIO{controller_right.solenoid_dio} = CIO{cio_right} (on DB15 connector)")
    print()
    print(f"Expected wiring: Port A on CIO{cio_left}, Port B on CIO{cio_right}")
    print()
    
    # Ensure both start in safe state (atmosphere)
    print("Setting both solenoids to SAFE state (Atmosphere)...")
    controller_left.set_solenoid_safe()
    controller_right.set_solenoid_safe()
    time.sleep(0.5)
    print()
    
    # Number of cycles
    num_cycles = 3
    toggle_delay = 1.0  # seconds between toggles
    hold_time = 0.5  # seconds to hold each state
    
    print(f"Starting {num_cycles} toggle cycles...")
    print(f"Toggle delay: {toggle_delay}s, Hold time: {hold_time}s")
    print()
    
    try:
        for cycle in range(1, num_cycles + 1):
            print(f"--- CYCLE {cycle}/{num_cycles} ---")
            print()
            
            # LEFT solenoid
            print(">>> LEFT solenoid -> VACUUM")
            controller_left.set_solenoid(to_vacuum=True)
            time.sleep(hold_time)
            
            print(">>> LEFT solenoid -> ATMOSPHERE")
            controller_left.set_solenoid(to_vacuum=False)
            time.sleep(toggle_delay)
            print()
            
            # RIGHT solenoid
            print(">>> RIGHT solenoid -> VACUUM")
            controller_right.set_solenoid(to_vacuum=True)
            time.sleep(hold_time)
            
            print(">>> RIGHT solenoid -> ATMOSPHERE")
            controller_right.set_solenoid(to_vacuum=False)
            time.sleep(toggle_delay)
            print()
        
        print("=" * 60)
        print("Test complete! Returning both solenoids to safe state...")
        controller_left.set_solenoid_safe()
        controller_right.set_solenoid_safe()
        print("✓ Both solenoids set to ATMOSPHERE (safe state)")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print()
        print("\nTest interrupted by user. Setting solenoids to safe state...")
        controller_left.set_solenoid_safe()
        controller_right.set_solenoid_safe()
        print("✓ Both solenoids set to ATMOSPHERE (safe state)")
    except Exception as e:
        logger.error(f"Error during test: {e}")
        print("\nError occurred. Setting solenoids to safe state...")
        controller_left.set_solenoid_safe()
        controller_right.set_solenoid_safe()
        print("✓ Both solenoids set to ATMOSPHERE (safe state)")
        sys.exit(1)
    finally:
        # Cleanup
        controller_left.cleanup()
        controller_right.cleanup()


if __name__ == '__main__':
    main()
