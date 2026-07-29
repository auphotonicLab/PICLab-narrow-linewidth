"""Analysis helpers for photon statistics and g20 metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

import numpy as np


@dataclass
class PhotonMetrics:
    mean_photon: float
    var_photon: float
    mean_nrs: float
    mean_nes: float
    mean_ngs: float
    mean_out: float
    var_out: float
    ans: float
    g20_out: float
    g20_in: float
    fano_out: float
    fano_in: float
    qm_out: float
    qm_in: float


def _clean(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array[np.isfinite(array)]


def g20(values: Iterable[float]) -> float:
    clean = _clean(values)
    if clean.size == 0:
        return float("nan")
    mean_value = clean.mean()
    if mean_value == 0:
        return float("nan")
    return float(np.mean(clean * (clean - 1)) / mean_value**2)


def photon_metrics(x: np.ndarray) -> PhotonMetrics:
    """Mirror the MATLAB post-processing for photon and output statistics."""

    photon = _clean(x[:, 3])
    nrs = _clean(x[:, 0])
    nes = _clean(x[:, 1])
    ngs = _clean(x[:, 2])

    output = x[:, 4]
    y = np.diff(output)
    if y.size > 0:
        y = y[:-1]

    mean_photon = float(np.mean(photon))
    var_photon = float(np.var(photon))
    mean_out = float(np.mean(y)) if y.size else float("nan")
    var_out = float(np.var(y)) if y.size else float("nan")
    ans = float(var_out - mean_out) if y.size else float("nan")
    g20_out = g20(y)
    g20_in = g20(photon)
    fano_out = float(var_out / mean_out) if y.size and mean_out != 0 else float("nan")
    fano_in = float(var_photon / mean_photon) if mean_photon != 0 else float("nan")
    qm_out = float(fano_out - 1) if np.isfinite(fano_out) else float("nan")
    qm_in = float(fano_in - 1) if np.isfinite(fano_in) else float("nan")

    return PhotonMetrics(
        mean_photon=mean_photon,
        var_photon=var_photon,
        mean_nrs=float(np.mean(nrs)),
        mean_nes=float(np.mean(nes)),
        mean_ngs=float(np.mean(ngs)),
        mean_out=mean_out,
        var_out=var_out,
        ans=ans,
        g20_out=g20_out,
        g20_in=g20_in,
        fano_out=fano_out,
        fano_in=fano_in,
        qm_out=qm_out,
        qm_in=qm_in,
    )
