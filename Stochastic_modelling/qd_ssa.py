"""Exact Gillespie and corrected tau-leap engines for the QD laser model.

Both engines differ from the MATLAB port (direct_method.py) in two ways:
- stimulated emission and absorption are separate, non-negative channels
  (the MATLAB code uses one net channel whose sign flips below transparency,
  which underestimates the noise near threshold);
- populations are never clipped at zero (the MATLAB clipping creates
  particles: below threshold it adds photons to the cavity at ~13% of the
  out-coupled flux).

Initial values are rounded to integers.

``gillespie`` is Gillespie's exact direct method (one event at a time). The
state is sampled on a fixed grid with spacing ``dt`` so the output can be used
exactly like the tau-leap traces (FFT, g20 of photon counts per bin). It is
exact but slow: the ES<->GS exchange alone is ~1e17 events/s, so a 50 ns
trace is 1e9-1e10 events (minutes to tens of minutes).

``tau_leap`` is explicit tau-leaping on the same grid. A step that would make
any population negative is rejected and redone as two half steps.

Quiet pumping injects electrons regularly at rate eta*I/q: an exact
deterministic schedule in ``gillespie``, and a carried fractional remainder
in ``tau_leap`` (no rounding bias, unlike round(a*dt) in MATLAB).
"""

from __future__ import annotations

from typing import Iterable, Tuple

import numpy as np
from numba import njit, uint64

from qd_model import Params

#                   NRS NES NGS SGS OUT
STOICH = np.array(
    [
        [1, 0, 0, 0, 0],  # 0  pumping
        [1, -1, 0, 0, 0],  # 1  ES -> RS
        [-1, 1, 0, 0, 0],  # 2  RS -> ES
        [-1, 0, 0, 0, 0],  # 3  RS decay
        [0, 1, -1, 0, 0],  # 4  GS -> ES
        [0, -1, 1, 0, 0],  # 5  ES -> GS
        [0, -1, 0, 0, 0],  # 6  ES decay
        [0, 0, -1, 1, 0],  # 7  stimulated emission
        [0, 0, -1, 0, 0],  # 8  GS decay
        [0, 0, 0, -1, 0],  # 9  internal loss
        [0, 0, 0, -1, 1],  # 10 out-coupling
        [0, 0, 0, 1, 0],  # 11 spontaneous emission into the mode
        [0, 0, 1, -1, 0],  # 12 absorption
    ],
    dtype=np.int64,
)
N_RXN = STOICH.shape[0]


def rate_constants(p: Params) -> np.ndarray:
    """Pack the propensity constants (inverse lifetimes etc.) into a flat array for numba."""

    return np.array(
        [
            p.eta * p.I / p.q,
            1.0 / p.tau_ES_WL,
            1.0 / p.tau_WL_ES,
            1.0 / p.tau_WL_spon,
            1.0 / p.tau_GS_ES,
            1.0 / p.tau_ES_GS,
            1.0 / p.tau_ES_spon,
            p.Gamma * p.vg * p.Nb / p.V_QD * p.a_GS,
            1.0 / p.tau_GS_spon,
            p.kappa1 * p.vg,
            p.kappa2 * p.vg,
            p.Beta / p.tau_GS_spon,
            1.0 / p.Nb,
            p.xi / p.V_QD,
        ],
        dtype=float,
    )


@njit(cache=True)
def _propensities(x, k, a):
    NRS = x[0]
    NES = x[1]
    NGS = x[2]
    SGS = x[3]
    block_es = max(0.0, 1.0 - 0.25 * NES * k[12])
    rho_gs = 0.5 * NGS * k[12]
    stim = k[7] * SGS / (1.0 + k[13] * SGS)
    a[0] = k[0]
    a[1] = NES * k[1]
    a[2] = NRS * k[2] * block_es
    a[3] = NRS * k[3]
    a[4] = NGS * k[4] * block_es
    a[5] = NES * k[5] * max(0.0, 1.0 - rho_gs)
    a[6] = NES * k[6]
    a[7] = stim * rho_gs
    a[8] = NGS * k[8]
    a[9] = SGS * k[9]
    a[10] = SGS * k[10]
    a[11] = NGS * k[11]
    a[12] = stim * max(0.0, 1.0 - rho_gs)


@njit(cache=True, inline="always")
def _uniform(s):
    """xoshiro256+ uniform in [0, 1); about 4x faster than np.random inside numba."""
    result = s[0] + s[3]
    t = s[1] << uint64(17)
    s[2] ^= s[0]
    s[3] ^= s[1]
    s[1] ^= s[2]
    s[0] ^= s[3]
    s[2] ^= t
    s[3] = (s[3] << uint64(45)) | (s[3] >> uint64(19))
    return (result >> uint64(11)) * (1.0 / 9007199254740992.0)


@njit(cache=True)
def _gillespie_run(x0, k, stoich, n_steps, dt, quiet, rng):
    X = np.empty((n_steps + 1, x0.size))
    x = x0.copy()
    X[0] = x
    a = np.empty(stoich.shape[0])
    t = 0.0
    t_end = n_steps * dt
    grid = 1
    pump_period = 1.0 / k[0] if k[0] > 0 else np.inf
    t_pump = pump_period
    n_events = 0
    while grid <= n_steps:
        _propensities(x, k, a)
        if quiet:
            a[0] = 0.0
        a0 = 0.0
        for j in range(a.size):
            a0 += a[j]
        tau = -np.log(1.0 - _uniform(rng)) / a0 if a0 > 0 else np.inf
        t_next = t + tau
        # Quiet pump: a deterministic injection comes first. The exponential
        # waiting time is memoryless, so it is redrawn after the injection.
        pump_now = quiet and t_pump < t_next
        if pump_now:
            t_next = t_pump
        while grid <= n_steps and grid * dt <= t_next:
            X[grid] = x
            grid += 1
        if t_next >= t_end:
            break
        t = t_next
        if pump_now:
            x[0] += 1.0
            t_pump += pump_period
            continue
        target = _uniform(rng) * a0
        cum = 0.0
        mu = a.size - 1
        for j in range(a.size):
            cum += a[j]
            if cum > target:
                mu = j
                break
        for s in range(x.size):
            x[s] += stoich[mu, s]
        n_events += 1
    while grid <= n_steps:
        X[grid] = x
        grid += 1
    return X, n_events


@njit(cache=True)
def _tau_leap_run(x0, k, stoich, n_steps, dt, substeps, quiet, seed, max_depth):
    np.random.seed(seed)
    n_rxn = stoich.shape[0]
    n_sp = x0.size
    X = np.empty((n_steps + 1, n_sp))
    x = x0.copy()
    X[0] = x
    a = np.empty(n_rxn)
    dx = np.empty(n_sp)
    stack = np.empty(4 * max_depth + 8)
    h_leap = dt / substeps
    h_min = h_leap / 2.0**max_depth
    pump_acc = 0.0
    n_reject = 0
    n_clip = 0
    for step in range(1, n_steps * substeps + 1):
        stack[0] = h_leap
        top = 1
        while top > 0:
            top -= 1
            h = stack[top]
            _propensities(x, k, a)
            dx[:] = 0.0
            saved_acc = pump_acc
            if quiet:
                pump_acc += a[0] * h
                n0 = np.floor(pump_acc)
                pump_acc -= n0
            else:
                n0 = float(np.random.poisson(a[0] * h))
            for s in range(n_sp):
                dx[s] += n0 * stoich[0, s]
            for j in range(1, n_rxn):
                if a[j] > 0.0:
                    n = float(np.random.poisson(a[j] * h))
                    if n > 0.0:
                        for s in range(n_sp):
                            dx[s] += n * stoich[j, s]
            negative = False
            for s in range(n_sp):
                if x[s] + dx[s] < 0.0:
                    negative = True
                    break
            if negative and h > h_min:
                # Reject and redo the interval as two half steps.
                pump_acc = saved_acc
                stack[top] = 0.5 * h
                stack[top + 1] = 0.5 * h
                top += 2
                n_reject += 1
                continue
            for s in range(n_sp):
                x[s] += dx[s]
                if x[s] < 0.0:
                    x[s] = 0.0
                    n_clip += 1
        if step % substeps == 0:
            X[step // substeps] = x
    return X, n_reject, n_clip


def _prepare(tspan: Iterable[float], x0: Iterable[float], p: Params):
    t_start, t_stop = tuple(tspan)
    n_steps = int(round((t_stop - t_start) / p.dt))
    t = t_start + p.dt * np.arange(n_steps + 1)
    # Populations are particle counts. QD.m's initial values are not integers
    # (e.g. 0.48 photons); a fractional offset would persist forever here.
    return t, n_steps, np.rint(np.asarray(x0, dtype=float)), rate_constants(p)


def _seed(seed):
    return int(np.random.SeedSequence(seed).generate_state(1)[0] & 0x7FFFFFFF)


def gillespie(
    tspan: Iterable[float], x0: Iterable[float], p: Params, quiet: bool = False, seed=None
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Exact direct-method SSA, sampled every ``p.dt``. Returns ``t, x, info``."""

    t, n_steps, x0, k = _prepare(tspan, x0, p)
    rng = np.random.SeedSequence(seed).generate_state(4, np.uint64)
    x, n_events = _gillespie_run(x0, k, STOICH, n_steps, p.dt, quiet, rng)
    return t, x, {"events": int(n_events)}


def tau_leap(
    tspan: Iterable[float],
    x0: Iterable[float],
    p: Params,
    quiet: bool = False,
    seed=None,
    substeps: int = 1,
    max_depth: int = 30,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Fixed-step tau-leaping with step rejection. Returns ``t, x, info``.

    The leap step is ``p.dt / substeps``; the output is sampled every ``p.dt``.
    Tau-leaping needs the propensities to stay nearly constant over a step,
    which fails for the photon channels when only ~1 photon is in the cavity.
    At 2 mA (<S> ~ 0.4), substeps=1 overestimates <S> by ~12% and g20_out
    (2.1 vs 1.2 exact); substeps >= 25 agrees with ``gillespie``. Above
    threshold substeps=1 is fine. Check convergence when in doubt.

    ``info["rejected"]`` counts half-step subdivisions; ``info["clipped"]``
    counts populations clipped after ``max_depth`` halvings (should stay 0).
    """

    t, n_steps, x0, k = _prepare(tspan, x0, p)
    x, n_reject, n_clip = _tau_leap_run(x0, k, STOICH, n_steps, p.dt, int(substeps), quiet, _seed(seed), max_depth)
    return t, x, {"rejected": int(n_reject), "clipped": int(n_clip)}
