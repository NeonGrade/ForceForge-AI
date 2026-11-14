"""Robust uncertainty challenge for the laboratory-derived 1D beam FEA.

All units follow beam_stress.py (N, m, Pa, kg). The assumed uncertainty
ranges are EXAMPLE design inputs, not confidence intervals inferred from
published measurements. No fatigue/service approval is implied.

For positive tip force on this linearly elastic statically determinate
cantilever, |tip displacement| increases monotonically with force and
decreases monotonically with E and section thickness. Maximum bending
stress similarly increases with force and decreases with section thickness.
Consequently the simultaneous worst upper-force, lower-E, lower-thickness
corner governs the specified box envelope. Other corners are independently
checked for the final selection.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from itertools import product

from .beam_stress import StaticCase, StaticResult, solve_static


@dataclass(frozen=True)
class UncertaintyBox:
    load_increase: float = .10
    modulus_reduction: float = .10
    thickness_reduction: float = .05

    def __post_init__(self) -> None:
        if not 0 <= self.load_increase <= 1.0:
            raise ValueError("load_increase must be in [0,1]")
        if not 0 <= self.modulus_reduction < .90:
            raise ValueError("modulus_reduction must be in [0,0.90)")
        if not 0 <= self.thickness_reduction < .35:
            raise ValueError("thickness_reduction must be in [0,0.35)")


@dataclass
class RobustCheck:
    nominal: StaticResult
    worst: StaticResult
    worst_displacement_utilization: float
    worst_stress_utilization: float
    worst_utilization: float
    passes: bool
    checked_corners: int


@dataclass
class RobustSearch:
    check: RobustCheck
    best: StaticResult | None
    best_worst: StaticResult | None
    tested: int
    feasible: int


DEFAULT_THICKNESS_RATIOS = (.70,.75,.80,.85,.90,.95,1.00,1.05,1.10,
                            1.15,1.20,1.25,1.30,1.35,1.40,1.50,1.60,1.70)


def worst_corner(case: StaticCase, box: UncertaintyBox) -> StaticResult:
    return solve_static(replace(
        case,
        force_n=case.force_n*(1.+box.load_increase),
        e_pa=case.e_pa*(1.-box.modulus_reduction),
        thickness_ratio=case.thickness_ratio*(1.-box.thickness_reduction)
    ))


def evaluate_robust(case: StaticCase, box: UncertaintyBox=UncertaintyBox(),
                    *, check_all: bool=True) -> RobustCheck:
    nominal=solve_static(case)
    worst=worst_corner(case,box)
    corners=[worst]
    if check_all:
        corners=[]
        for f,e,t in product((1.,1.+box.load_increase),
                             (1.,1.-box.modulus_reduction),
                             (1.,1.-box.thickness_reduction)):
            corners.append(solve_static(replace(
                case,force_n=case.force_n*f,e_pa=case.e_pa*e,
                thickness_ratio=case.thickness_ratio*t
            )))
    d=max(float(r.displacement_utilization) for r in corners)
    stress=max(float(r.stress_utilization) for r in corners)
    worst_util=max(d,stress)
    if check_all:
        if abs(worst.governing_utilization-worst_util)>1e-6:
            raise AssertionError("Corner monotonicity check failed")
    return RobustCheck(
        nominal=nominal,worst=worst,
        worst_displacement_utilization=d,worst_stress_utilization=stress,
        worst_utilization=worst_util,passes=worst_util<=1.+1e-10,
        checked_corners=len(corners)
    )


def search_robust(case: StaticCase, box: UncertaintyBox=UncertaintyBox(),
                  ratios: tuple[float,...]=DEFAULT_THICKNESS_RATIOS) -> RobustSearch:
    original=evaluate_robust(case,box,check_all=True)
    feasible=[]
    tested=0
    for ratio in ratios:
        # The underlying beam solver is validated only for thickness_ratio >= .65.
        if ratio*(1.-box.thickness_reduction)<.65:
            continue
        tested+=1
        c=replace(case,thickness_ratio=float(ratio))
        # Constant-section ratio and statically determinate beam ensure the
        # worst corner captures max stress and deflection over this box.
        worst=worst_corner(c,box)
        if worst.governing_utilization<=1.+1e-10:
            nominal=solve_static(c)
            feasible.append((nominal.mass_kg,ratio,nominal,worst))
    feasible.sort(key=lambda x:(x[0],x[1]))
    if not feasible:
        return RobustSearch(original,None,None,tested,0)
    _,_,best_nominal,best_worst=feasible[0]
    # Always independently recompute all 8 corners of the selected candidate.
    independent=evaluate_robust(best_nominal.case,box,check_all=True)
    if not independent.passes:
        raise AssertionError("Selected robust design was not confirmed by all corners")
    return RobustSearch(original,best_nominal,best_worst,tested,len(feasible))
