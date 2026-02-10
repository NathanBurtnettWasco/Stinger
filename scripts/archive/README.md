# Archived scripts

These scripts were consolidated into the main entry points or archived as one-off utilities. Use the following instead:

## Deprecated Scripts (Replaced by Main Entry Points)

| Archived script | Use instead |
|-----------------|-------------|
| `pressure_switch_test.py` | `python scripts/hardware.py switch` |
| `pressure_switch_sweep_test.py` | `python scripts/hardware.py switch-sweep` |
| `test_solenoids.py` | `python scripts/hardware.py solenoids` |
| `labjack_discovery.py` | `python scripts/hardware.py discover` |
| `alicat_dual_test.py` | `python scripts/hardware.py alicat-dual` |
| `alicat_units_test.py` | (niche; restore from here if needed) |
| `run_comprehensive_suite.py` | `python scripts/suite.py` |
| `transducer_alicat_correlation_test.py` | `python scripts/calibrate.py collect` / `scripts/comprehensive_correlation_test.py` |
| `labjack_dio_scan.py` | `python scripts/hardware.py discover` |

## Legacy Experiments (Niche Use Cases)

| Archived script | Notes |
|-----------------|-------|
| `grid_offset_surface_test.py` | (niche; restore from here if needed) |
| `response_filter_test.py` | (niche; restore from here if needed) |
| `raw_data_test.py` | (niche; restore from here if needed) |
| `torr_streaming_test.py` | (niche; restore from here if needed) |
| `sensor_sweep_test.py` | (niche; restore from here if needed) |
| `switch_sweep_test.py` | (niche; restore from here if needed) |
| `labjack_ain_rate_test.py` | (niche; restore from here if needed) |
| `debug_alicat.py` | (diagnostics; restore from here if needed) |
| `serial_diagnostics.py` | (diagnostics; restore from here if needed) |
| `test_vacuum_port_b.py` | (port-specific; restore from here if needed) |

## One-Off Utility Scripts

These scripts were created for specific one-time tasks or debugging sessions:

| Archived script | Purpose |
|-----------------|---------|
| `find_work_order.py` | Query recent work orders with matching PTP parameters |
| `find_matching_ptp.py` | Find PTP records matching bench switch characteristics |
| `find_23psia_part.py` | Find parts with specific pressure characteristics |
| `find_port_a_20psi.py` | Find port A parts with 20 PSI setpoint |
| `find_port_a_setpoint.py` | Find port A setpoint queries |
| `find_wo_for_20psi.py` | Find work orders for 20 PSI parts |
| `test_display_conversion.py` | Test display pressure conversion logic |
| `test_in_spec_pressure_ref.py` | Test in-spec pressure reference logic |
| `test_in_spec_units.py` | Test in-spec units logic |
| `test_pressure_ref_fix.py` | Test pressure reference fix |
| `test_cycle_estimate_display.py` | Test cycle estimate display |
| `check_15xxx_parts.py` | One-off check for specific part numbers |
| `ptp_query.py` | Query PTP parameters for a work order |

**Primary entry points:**
- **Calibration:** `python scripts/calibrate.py` (collect / analyze / full)
- **Full suite:** `python scripts/suite.py`
- **Hardware:** `python scripts/hardware.py` (discover / switch / switch-sweep / solenoids / alicat-dual)
