"""Stochastic simulation algorithm engine translated from directMethod.m."""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Tuple

import numpy as np


PropensityFcn = Callable[[np.ndarray, object], np.ndarray]
OutputFcn = Optional[Callable[[float, np.ndarray], bool]]


def direct_method(
    stoich_matrix: np.ndarray,
    propensity_fcn: PropensityFcn,
    tspan: Iterable[float],
    x0: Iterable[float],
    params: object,
    output_fcn: OutputFcn = None,
    max_output_length: int = int(1e8),
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Discrete-time SSA loop that mirrors the MATLAB directMethod implementation."""

    t_start, t_stop = tuple(tspan)
    stoich_matrix = np.asarray(stoich_matrix, dtype=float)
    state = np.asarray(x0, dtype=float)
    time_points = [float(t_start)]
    state_history = [state.copy()]
    propensity_history = []

    while time_points[-1] < t_stop:
        a = np.asarray(propensity_fcn(state_history[-1], params), dtype=float)
        r = np.random.poisson(np.abs(a * params.dt)).astype(float)
        r[a < 0] *= -1
        next_state = state_history[-1] + r @ stoich_matrix
        next_state[next_state < 0] = 0

        if len(time_points) + 1 > max_output_length:
            break

        time_points.append(time_points[-1] + params.dt)
        state_history.append(next_state)
        propensity_history.append(a)

        if output_fcn is not None and output_fcn(time_points[-1], next_state.copy()):
            break

    t = np.asarray(time_points, dtype=float)
    x = np.asarray(state_history, dtype=float)
    b = np.asarray(propensity_history, dtype=float)
    return t, x, b
