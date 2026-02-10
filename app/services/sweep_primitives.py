"""Small reusable primitives for sweep and edge-detection flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SweepResult:
    activation_psi: float
    deactivation_psi: float


@dataclass(frozen=True)
class EdgeDetection:
    pressure_psi: float
    activated: bool


@dataclass(frozen=True)
class DebounceState:
    last_state: Optional[bool] = None
    pending_state: Optional[bool] = None
    pending_count: int = 0
    last_edge_time: float = 0.0
    pending_pressure: Optional[float] = None


def resolve_sweep_result(
    edge_out: EdgeDetection,
    edge_back: EdgeDetection,
) -> Optional[SweepResult]:
    activation = (
        edge_out.pressure_psi
        if edge_out.activated
        else edge_back.pressure_psi
        if edge_back.activated
        else None
    )
    deactivation = (
        edge_out.pressure_psi
        if not edge_out.activated
        else edge_back.pressure_psi
        if not edge_back.activated
        else None
    )
    if activation is None or deactivation is None:
        return None
    return SweepResult(activation_psi=activation, deactivation_psi=deactivation)


def observe_debounced_transition(
    state: DebounceState,
    current_state: bool,
    stable_count: int,
    min_edge_interval_s: float,
    now_s: float,
    *,
    track_last_sample: bool,
    update_edge_time_on_reject: bool,
    current_pressure: Optional[float] = None,
) -> tuple[DebounceState, Optional[bool], Optional[float]]:
    """Update edge debounce state and optionally emit a committed edge state.

    Returns:
        A tuple of (new_state, committed_edge, committed_pressure).
        ``committed_pressure`` is the pressure recorded at the *first*
        detection of the pending state change, which is more accurate than
        the pressure at commit time during fast ramp rates.
    """
    if state.last_state is None:
        return (
            DebounceState(
                last_state=current_state,
                pending_state=state.pending_state,
                pending_count=state.pending_count,
                last_edge_time=state.last_edge_time,
                pending_pressure=state.pending_pressure,
            ),
            None,
            None,
        )

    pending_state = state.pending_state
    pending_count = state.pending_count
    last_state = state.last_state
    last_edge_time = state.last_edge_time
    pending_pressure = state.pending_pressure

    if pending_state is None:
        if current_state != last_state:
            pending_state = current_state
            pending_count = 1
            # Capture the pressure at first detection of the state change
            pending_pressure = current_pressure
    else:
        if current_state == pending_state:
            pending_count += 1
        else:
            pending_state = current_state
            pending_count = 1
            # Reset pressure to current on direction change
            pending_pressure = current_pressure

    committed_edge: Optional[bool] = None
    committed_pressure: Optional[float] = None
    if pending_state is not None and pending_count >= stable_count:
        if now_s - last_edge_time >= min_edge_interval_s:
            committed_edge = pending_state
            committed_pressure = pending_pressure
            last_state = pending_state
            pending_state = None
            pending_count = 0
            pending_pressure = None
            last_edge_time = now_s
        elif update_edge_time_on_reject:
            last_edge_time = now_s

    if track_last_sample:
        last_state = current_state

    return (
        DebounceState(
            last_state=last_state,
            pending_state=pending_state,
            pending_count=pending_count,
            last_edge_time=last_edge_time,
            pending_pressure=pending_pressure,
        ),
        committed_edge,
        committed_pressure,
    )
