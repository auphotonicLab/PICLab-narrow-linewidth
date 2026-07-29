"""Quiet variant of the SSA engine translated from directMethod_quiet.m."""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Tuple

import numpy as np

from Squeezing_python.direct_method import PropensityFcn, OutputFcn


def direct_method_quiet(
    stoich_matrix: np.ndarray,
    propensity_fcn: PropensityFcn,
    tspan: Iterable[float],
    x0: Iterable[float],
    params: object,
    output_fcn: OutputFcn = None,
    max_output_length: int = int(1e8),
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """SSA loop where the first reaction channel is rounded deterministically."""

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
        r[0] = np.rint(a[0] * params.dt)
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
