# State Machine (Stinger)

This document defines the per-port state machine for Stinger test execution.

## Design Approach

Each port runs an **independent state machine**. The hardware layer manages N ports dynamically (currently 2, but designed for N-port scalability).

States are organized in a **hierarchical** structure:
- **Top-level states** represent major workflow phases
- **Substates** represent detailed steps within each phase

## Top-Level States

| State | Description |
|-------|-------------|
| `INIT` | System initialization, hardware connection |
| `IDLE` | Ready for operator action, no test in progress |
| `PRESSURIZING` | Ramping to initial pressure (well past setpoint) |
| `MANUAL_ADJUST` | QAL 15 only: waiting for operator SEI adjustment |
| `CYCLING` | Running proof cycles (3 cycles) |
| `PRECISION_TEST` | Slow sweep for edge detection |
| `REVIEW` | Test complete, awaiting operator decision |
| `ERROR` | Fault condition, requires reset |
| `END` | Work order complete, returning to login |

## State Diagram (Simplified)

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    ▼                                         │
┌──────┐    ┌──────┐    ┌─────────────┐    ┌─────────────┐   │
│ INIT │───▶│ IDLE │───▶│PRESSURIZING │───▶│MANUAL_ADJUST│───┼──┐
└──────┘    └──────┘    └─────────────┘    └─────────────┘   │  │
               ▲                                  │          │  │
               │                                  │ (QAL15)  │  │
               │                                  ▼          │  │
               │        ┌─────────────────────────┘          │  │
               │        │                                    │  │
               │        ▼                                    │  │
               │    ┌────────┐    ┌───────────────┐    ┌────────┐
               │    │CYCLING │───▶│PRECISION_TEST │───▶│ REVIEW │
               │    └────────┘    └───────────────┘    └────────┘
               │                                           │
               │        ┌──────────────────────────────────┘
               │        │ (Record/Retest/Next)
               │        ▼
               │    ┌────────┐
               └────│  IDLE  │
                    └────────┘
                        │
                        │ (End Work Order)
                        ▼
                    ┌────────┐
                    │  END   │
                    └────────┘

    Any State ──(error)──▶ ERROR ──(reset)──▶ IDLE
```

## Substates by Phase

### INIT Substates
| Substate | Description |
|----------|-------------|
| `INIT.CONNECTING_DAQ` | Establishing DAQ connection |
| `INIT.CONNECTING_ALICAT` | Establishing Alicat connection |
| `INIT.VERIFYING_DB` | Testing database connectivity |
| `INIT.READY` | All systems ready, transition to IDLE |

### PRESSURIZING Substates
| Substate | Description |
|----------|-------------|
| `PRESSURIZING.START` | Begin pressure ramp |
| `PRESSURIZING.RAMPING` | Actively ramping (setpoint → target) |
| `PRESSURIZING.HOLD` | At target, holding stable |
| `PRESSURIZING.VENT` | Operator cancelled, venting to atmosphere |

### MANUAL_ADJUST Substates (QAL 15 only)
| Substate | Description |
|----------|-------------|
| `MANUAL_ADJUST.WAITING_SWITCH` | Switch has not changed state yet |
| `MANUAL_ADJUST.SWITCH_DETECTED` | Switch changed, Test button enabled |

### CYCLING Substates
| Substate | Description |
|----------|-------------|
| `CYCLING.START` | Begin cycle sequence |
| `CYCLING.SETPOINT` | Driving to far setpoint (fast) |
| `CYCLING.RETURN` | Returning toward atmosphere |
| `CYCLING.NEXT` | Preparing for next cycle |
| `CYCLING.STOP` | Operator cancelled or complete |

### PRECISION_TEST Substates
| Substate | Description |
|----------|-------------|
| `PRECISION.START` | Begin precision sweep |
| `PRECISION.FAST_APPROACH` | Fast ramp to near first expected edge |
| `PRECISION.SLOW_SWEEP_1` | Slow sweep toward first edge (5 Torr/sec) |
| `PRECISION.EDGE_1_DETECTED` | First edge captured |
| `PRECISION.OVERSHOOT` | Going slightly past first edge |
| `PRECISION.SLOW_SWEEP_2` | Slow sweep toward second edge |
| `PRECISION.EDGE_2_DETECTED` | Second edge captured |
| `PRECISION.EXHAUST` | Returning to atmosphere |
| `PRECISION.STOP` | Operator cancelled or complete |

### REVIEW Substates
| Substate | Description |
|----------|-------------|
| `REVIEW.EVALUATING` | Computing pass/fail |
| `REVIEW.SHOWING_RESULT` | Displaying result to operator |
| `REVIEW.WAITING_DECISION` | Awaiting Record/Retest tap |
| `REVIEW.RECORDING` | Writing to database |

### ERROR Substates
| Substate | Description |
|----------|-------------|
| `ERROR.HARDWARE_FAULT` | DAQ/Alicat communication issue |
| `ERROR.EDGE_NOT_FOUND` | No edge within expected range |
| `ERROR.WIRING_FAULT` | Impossible DI state detected |
| `ERROR.DB_WRITE_FAILED` | Database write error |

## State Transitions

### From IDLE
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `pressurize` | Work order loaded, parameters valid | `PRESSURIZING` | Command Alicat to target |
| `end_work_order` | — | `END` | Cleanup, return to login |
| `error` | Hardware fault | `ERROR` | Log error, show message |

### From PRESSURIZING
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `target_reached` | At target pressure, stable | `MANUAL_ADJUST` (QAL15) or `CYCLING` (QAL16/17) | — |
| `vent` | Operator pressed Vent | `IDLE` | Vent to atmosphere |
| `error` | Hardware fault | `ERROR` | Safe stop |

### From MANUAL_ADJUST
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `switch_changed` | DI state flipped | (stay, enable Test) | — |
| `test` | Switch has changed, operator pressed Test | `CYCLING` | — |
| `vent` | Operator pressed Vent | `IDLE` | Vent to atmosphere |

### From CYCLING
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `cycles_complete` | 3 cycles done | `PRECISION_TEST` | Begin slow sweep |
| `cancel` | Operator pressed Cancel | `IDLE` | Vent to atmosphere |
| `error` | Edge not found during cycle | `ERROR` | Log, show message |

### From PRECISION_TEST
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `both_edges_captured` | Activation + deactivation recorded | `REVIEW` | Evaluate |
| `edge_not_found` | 10% past limit, no edge | `ERROR` | — |
| `cancel` | Operator pressed Cancel | `IDLE` | Vent to atmosphere |

### From REVIEW
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `record_success` | PASS, operator confirmed | `IDLE` | Write to DB, advance serial |
| `record_failure` | FAIL, operator confirmed | `IDLE` | Write to DB, advance serial |
| `retest` | Operator chose Retest | `PRESSURIZING` (QAL15) or `CYCLING` (QAL16/17) | Increment attempt |

### From ERROR
| Trigger | Condition | Destination | Action |
|---------|-----------|-------------|--------|
| `reset` | Operator acknowledged | `IDLE` | Clear error state |

## Threading Model

```
┌─────────────────────────────────────────────────────────────┐
│                       Main Thread (UI)                       │
│  - PyQt event loop                                          │
│  - Receives signals from hardware thread                    │
│  - Emits user actions to state machines                     │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ PyQt Signals
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hardware Thread                           │
│  - Polling loop (DAQ + Alicat)                              │
│  - Per-port state machine execution                         │
│  - Edge detection logic                                      │
│  - Emits state changes + data to UI                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hardware Abstraction                      │
│  - DAQ controller (N devices)                               │
│  - Alicat controller (N addresses)                          │
│  - Designed for 1 to N ports                                │
└─────────────────────────────────────────────────────────────┘
```

### Thread Safety

- **Serial number allocation**: Use a thread-safe counter with lock
- **Hardware access**: Each port owns its DAQ device (no contention for LeftDAQ vs RightDAQ)
- **Alicat access**: Single COM port, use lock for command/response pairs
- **State machine**: Each port's state machine runs on the hardware thread; state changes emitted via signals

### N-Port Scalability

The design supports dynamic port count:
```python
# Config-driven port initialization
ports = []
for port_config in config['hardware']['daq'].values():
    if port_config.get('device_name'):
        ports.append(Port(port_config))
```

Hardware layer abstractions:
- `DAQDevice` - wraps a single NI DAQ
- `AlicatDevice` - wraps a single Alicat address
- `Port` - combines DAQ + Alicat + state machine for one test port
- `HardwareManager` - manages N ports, runs polling loop
