"""Core quantum-dot laser parameters and propensity function."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import pi

import numpy as np


@dataclass
class Params:
    q: float = 1.602e-19
    c: float = 2.9979e10
    Kb: float = 8.617e-5
    meff: float = 2.07e-32
    hba: float = 6.582e-16
    T: float = 293.0
    E_WL: float = 1.25
    E_ES: float = 1.03
    E_GS: float = 0.95
    nr: float = 3.5
    eta: float = 0.18
    L: float = 7.5e-2
    W: float = 2e-4
    h_QD: float = 5e-7
    n_layer: float = 8
    ND: float = 5.9e10
    Gamma: float = 0.06
    a_GS: float = 5e-15
    Beta: float = 1e-4
    tau_WL_spon: float = 500e-12
    tau_ES_spon: float = 500e-12
    tau_GS_spon: float = 1200e-12
    tau_WL_ES: float = 0.25 * 25.1e-12
    tau_ES_GS: float = 0.25 * 11.6e-12
    kappa1: float = 0.0
    kappa2: float = 23.72
    I: float = 0.002
    dt: float = 5e-13
    vg: float = field(init=False)
    S: float = field(init=False)
    Nb: float = field(init=False)
    V_QD: float = field(init=False)
    rho_WL_o: float = field(init=False)
    rho_WL: float = field(init=False)
    tau_GS_ES: float = field(init=False)
    tau_ES_WL: float = field(init=False)

    def __post_init__(self) -> None:
        self.vg = self.c / self.nr
        self.S = self.L * self.W
        self.Nb = self.ND * self.S * self.n_layer
        self.V_QD = self.S * self.h_QD * self.n_layer
        self.rho_WL_o = self.meff * self.Kb * self.T * self.S / (pi * (self.hba**2))
        self.rho_WL = self.rho_WL_o * 1e-4 / self.q
        self.tau_GS_ES = 0.5 * self.tau_ES_GS * np.exp((self.E_ES - self.E_GS) / (self.Kb * self.T))
        self.tau_ES_WL = (
            4 * self.tau_WL_ES * np.exp((self.E_WL - self.E_ES) / (self.Kb * self.T)) * self.Nb / self.rho_WL
        )


def qdlaser(x: np.ndarray, p: Params) -> np.ndarray:
    """Return the 12 propensities used by the MATLAB QDlaser function."""

    NRS = x[0]
    NES = x[1]
    NGS = x[2]
    SGS = x[3]
    gGS = p.Nb / p.V_QD * p.a_GS * (2 * NGS / (2 * p.Nb) - 1)
    return np.array(
        [
            p.eta * p.I / p.q,
            NES / p.tau_ES_WL,
            NRS / p.tau_WL_ES * (1 - NES / (4 * p.Nb)),
            NRS / p.tau_WL_spon,
            NGS / p.tau_GS_ES * (1 - NES / (4 * p.Nb)),
            NES / p.tau_ES_GS * (1 - NGS / (2 * p.Nb)),
            NES / p.tau_ES_spon,
            p.Gamma * p.vg * gGS * SGS,
            NGS / p.tau_GS_spon,
            SGS * p.kappa1 * p.vg,
            SGS * p.kappa2 * p.vg,
            p.Beta * NGS / p.tau_GS_spon,
        ],
        dtype=float,
    )
