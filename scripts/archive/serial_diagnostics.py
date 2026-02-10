"""
Minimal serial port diagnostic script.
"""

import serial.tools.list_ports
import time

print("="*60)
print("SERIAL PORT DIAGNOSTICS")
print("="*60)

# List all available ports
print("\n1. Available serial ports:")
for p in serial.tools.list_ports.comports():
    print(f"  {p.device}: {p.description}")
    print(f"    hwid: {p.hwid}")

# Try to open COM9
print("\n2. Attempting to open COM9 with different settings:")

# Try 1: Minimal settings
print("\n  Try 1: Minimal settings...")
try:
    s1 = serial.Serial('COM9', baudrate=19200, timeout=0.5, write_timeout=0.5)
    print(f"    Opened successfully!")
    print(f"    Port: {s1.name}, Baud: {s1.baudrate}")
    print(f"    Is open: {s1.is_open}")
    
    # Try to write and read
    s1.reset_input_buffer()
    s1.write(b'A\r')
    time.sleep(0.1)
    line = s1.readline().decode(errors='ignore')
    print(f"    Response: {repr(line.strip())}")
    
    s1.close()
    print(f"    Closed successfully")
except Exception as e:
    print(f"    ERROR: {type(e).__name__}: {e}")

# Try 2: Without explicit write_timeout
print("\n  Try 2: Without write_timeout...")
try:
    s2 = serial.Serial('COM9', baudrate=19200, timeout=1.0)
    print(f"    Opened successfully!")
    s2.close()
except Exception as e:
    print(f"    ERROR: {type(e).__name__}: {e}")

# Try 3: With explicit RTS/DTR settings
print("\n  Try 3: With RTS/DTR disabled...")
try:
    s3 = serial.Serial(
        port='COM9',
        baudrate=19200,
        timeout=0.5,
        rtscts=False,
        dsrdtr=False,
    )
    print(f"    Opened successfully!")
    s3.close()
except Exception as e:
    print(f"    ERROR: {type(e).__name__}: {e}")

print("\n" + "="*60)
print("DIAGNOSTICS COMPLETE")
print("="*60)
