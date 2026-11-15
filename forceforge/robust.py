"""Scenario-based, deterministic robust truss sizing/geometry search.

Engineering limitations: no geometric/material nonlinearities, no joints,
no fatigue, no out-of-plane instability; member Euler buckling idealized.
"""
from dataclasses import dataclass
from itertools import product
import numpy as np
import pandas as pd

from .design import make_truss, TOPOLOGIES
from .physics import Material, solve
from .provenance import truss_context


@dataclass(frozen=True)
class Requirements:
    span_m: float = 2.0
    base_load_n: float = 1000.0
    material_E_pa: float = 200e9
    density_kg_m3: float = 7850.0
    yield_pa: float = 250e6
    max_displacement_mm: float = 2.0
    yield_safety_factor: float = 2.0
    buckling_safety_factor: float = 2.0
    load_uncertainty: float = 0.20
    e_uncertainty: float = 0.10
    area_uncertainty: float = 0.10

    @property
    def material(self) -> Material:
        return Material(self.material_E_pa, self.density_kg_m3, self.yield_pa)

    def validate(self):
        if any(x <= 0 for x in [self.span_m, self.base_load_n, self.material_E_pa,
                                self.density_kg_m3, self.yield_pa, self.max_displacement_mm,
                                self.yield_safety_factor, self.buckling_safety_factor]):
            raise ValueError("Dimensions, load, properties and safety factors must be positive")
        if any(not 0 <= x < 1 for x in [self.load_uncertainty, self.e_uncertainty,
                                         self.area_uncertainty]):
            raise ValueError("Uncertainty fractions must be in [0, 1)")


def scenarios(req: Requirements) -> list[tuple[float,float,float]]:
    req.validate()
    return list(product((1., 1.+req.load_uncertainty),
                        (1., 1.-req.e_uncertainty),
                        (1., 1.-req.area_uncertainty)))


def evaluate(topology: str, height_m: float, area_mm2: float,
             req: Requirements) -> dict:
    """Report scenario worst-case utilization; feasible only if all <= 1."""
    truss = make_truss(topology, req.span_m, height_m, area_mm2,
                       req.base_load_n, req.material)
    base = solve(truss)
    worst_stress = 0.
    worst_disp = 0.
    worst_buckling = 0.
    critical = {}
    for load_factor, e_factor, area_factor in scenarios(req):
        result = solve(truss, load_factor=load_factor, e_factor=e_factor,
                       area_factor=area_factor)
        u_stress = result.max_stress_pa * req.yield_safety_factor / req.yield_pa
        u_disp = result.max_disp_m * 1000 / req.max_displacement_mm
        compressed = result.force_n < -1e-10
        u_buckling = (float(np.max(np.abs(result.force_n[compressed])
                                   * req.buckling_safety_factor
                                   / result.buckling_critical_n[compressed]))
                      if np.any(compressed) else 0.)
        if u_stress > worst_stress:
            worst_stress = u_stress
        if u_disp > worst_disp:
            worst_disp = u_disp
        if u_buckling > worst_buckling:
            worst_buckling = u_buckling
        critical[(load_factor, e_factor, area_factor)] = max(u_stress, u_disp, u_buckling)
    worst_util = max(worst_stress, worst_disp, worst_buckling)
    limiting = max(critical, key=critical.get)
    return {
        "topology": topology,
        "height_m": float(height_m),
        "area_mm2": float(area_mm2),
        "mass_kg": base.mass_kg,
        "baseline_disp_mm": base.max_disp_m * 1000,
        "worst_stress_util": worst_stress,
        "worst_displacement_util": worst_disp,
        "worst_buckling_util": worst_buckling,
        "worst_utilization": worst_util,
        "feasible": bool(worst_util <= 1.0 + 1e-10),
        "limiting_scenario": str(tuple(round(x, 3) for x in limiting)),
    }


def grid_search(req: Requirements, *, heights: tuple | None = None,
                areas_mm2: tuple | None = None,
                topologies: tuple = TOPOLOGIES) -> pd.DataFrame:
    req.validate()
    if heights is None:
        heights = tuple(np.linspace(0.4*req.span_m, 0.8*req.span_m, 6))
    if areas_mm2 is None:
        areas_mm2 = (100., 140., 180., 230., 300., 400., 550., 700.)
    rows = []
    for topology, height_m, area in product(topologies, heights, areas_mm2):
        try:
            rows.append(evaluate(topology, float(height_m), float(area), req))
        except (ValueError, np.linalg.LinAlgError) as err:
            rows.append({"topology": topology, "height_m": float(height_m),
                         "area_mm2": float(area), "feasible": False,
                         "reason": str(err)})
    df = pd.DataFrame(rows)
    df = df.sort_values(["feasible", "mass_kg"], ascending=[False,True],
                        na_position="last").reset_index(drop=True)
    df.attrs["forceforge_context"] = truss_context(req)
    return df


def pareto_front(df: pd.DataFrame, *, x: str = "mass_kg",
                 y: str = "worst_displacement_util") -> pd.DataFrame:
    valid = df[df["feasible"]].dropna(subset=[x, y]).copy()
    if valid.empty:
        return valid
    order = valid.sort_values([x,y])
    keep, lowest_y = [], float("inf")
    for idx, row in order.iterrows():
        if float(row[y]) < lowest_y - 1e-12:
            keep.append(idx)
            lowest_y = float(row[y])
    return valid.loc[keep].sort_values(x).reset_index(drop=True)


def best_feasible(df: pd.DataFrame) -> dict | None:
    feasible = df[df["feasible"]].dropna(subset=["mass_kg"])
    if feasible.empty:
        return None
    return feasible.sort_values("mass_kg").iloc[0].to_dict()
