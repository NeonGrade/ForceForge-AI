"""Finite-difference, local log-sensitivity of robust performance metrics."""
from dataclasses import dataclass
import pandas as pd
from .robust import Requirements, evaluate


def elasticities(topology: str, height_m: float, area_mm2: float,
                 req: Requirements, *, fractional_step: float = .01) -> pd.DataFrame:
    if not 0 < fractional_step < .1:
        raise ValueError("fractional_step must lie between 0 and 0.1")
    outputs = ["mass_kg", "worst_stress_util", "worst_displacement_util", "worst_buckling_util"]
    base = evaluate(topology, height_m, area_mm2, req)
    rows = []
    for variable in ("height_m", "area_mm2"):
        lo = {"height_m": height_m, "area_mm2": area_mm2}
        hi = lo.copy()
        lo[variable] *= 1.0-fractional_step
        hi[variable] *= 1.0+fractional_step
        ylo = evaluate(topology, lo["height_m"], lo["area_mm2"], req)
        yhi = evaluate(topology, hi["height_m"], hi["area_mm2"], req)
        for metric in outputs:
            denom = base[metric]
            slope = ((yhi[metric] - ylo[metric]) / (2*fractional_step*denom)
                     if denom != 0 else float("nan"))
            rows.append({"Parameter": variable, "Output": metric,
                         "Local elasticity": float(slope)})
    return pd.DataFrame(rows)
