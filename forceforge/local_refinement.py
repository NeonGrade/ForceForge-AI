"""Independent mesh-local refinement around a measured FE hotspot.

Refinement modifies mesh *only*, not CAD BRep, material or load. Two
strictly bounded, crash-isolated tetra10 solves assess a spatially fixed
stress probe and movement of the Gauss-sampled maximum.

A sharp fully clamped edge can be a mathematically singular idealization.
It is not meaningful to promise convergence of its maximum stress;
this module reports UNRESOLVED instead of manufacturing a passing result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Callable
import math
import numpy as np

from .stress_probe import probe_stress
from .mesh_verification import _fractional_difference


@dataclass(frozen=True)
class RefinementStep:
    label: str
    mesh_tetra_count: int
    local_factor: float
    tip_mm: float
    global_peak_mpa: float
    region_mean_mpa: float
    region_p90_mpa: float
    peak_xyz_mm: tuple[float,float,float]
    reaction_residual: float
    volume_difference_pct: float

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class LocalRefinementEvidence:
    source_sha256: str
    focus_xyz_mm: tuple[float,float,float]
    region_start_fraction: float
    region_end_fraction: float
    steps: tuple[RefinementStep,...]
    peak_change_percent: float
    region_mean_change_percent: float
    region_p90_change_percent: float
    hotspot_move_mm: float
    peak_near_fixed_boundary: bool
    refinement_mono: bool
    status: str
    explanation: str
    limitations: str

    def as_dict(self):
        return asdict(self)


def assess_hotspot_refinement(original, refined1, refined2,
                              *, source_hash: str) -> LocalRefinementEvidence:
    models=(original,refined1,refined2)
    if any(x.mesh.source_sha256!=source_hash for x in models):
        raise ValueError("Imported STEP bytes differ between local refinement steps")
    if any(x.load!=original.load for x in models):
        raise ValueError("Material/force/support changed across local refinement")
    if any(x.mesh.num_tets>1400 for x in models):
        raise ValueError("Local refinement exceeds stable interactive tetra cap")
    if any(x.relative_reaction_residual>1e-5 or
           x.mesh.relative_volume_difference>.20 or
           x.mesh.min_shape_quality<=0 for x in models):
        raise ValueError("Refined mesh violates force, geometry or element-quality safeguards")
    probe=[probe_stress(x) for x in models]
    labels=("Original STEP mesh","Local refinement A","Local refinement B")
    settings=[1.0,.80,.60]
    records=tuple(
        RefinementStep(
            label=label,
            mesh_tetra_count=int(model.mesh.num_tets),
            local_factor=factor,
            tip_mm=model.tip_mm,
            global_peak_mpa=model.peak_von_mises_mpa,
            region_mean_mpa=p.mean_von_mises_mpa,
            region_p90_mpa=p.p90_von_mises_mpa,
            peak_xyz_mm=p.global_peak_location_mm,
            reaction_residual=model.relative_reaction_residual,
            volume_difference_pct=100*model.mesh.relative_volume_difference,
        ) for label,model,p,factor in zip(labels,models,probe,settings)
    )
    peak_change=_fractional_difference(records[-1].global_peak_mpa,
                                       records[-2].global_peak_mpa)
    mean_change=_fractional_difference(records[-1].region_mean_mpa,
                                       records[-2].region_mean_mpa)
    p90_change=_fractional_difference(records[-1].region_p90_mpa,
                                      records[-2].region_p90_mpa)
    moved=float(np.linalg.norm(
        np.asarray(records[-1].peak_xyz_mm) -
        np.asarray(records[-2].peak_xyz_mm)
    ))
    axis=original.load.boundary_axis
    extent_mm=float(1000*(original.mesh.bbox_m[1,axis]
                          -original.mesh.bbox_m[0,axis]))
    near_clamp=(
        probe[-1].global_peak_support_distance_fraction<=.05
        or probe[-2].global_peak_support_distance_fraction<=.05
    )
    monotone=(
        records[0].mesh_tetra_count<records[1].mesh_tetra_count<records[2].mesh_tetra_count
        and records[1].mesh_tetra_count>=1.1*records[0].mesh_tetra_count
        and records[2].mesh_tetra_count>=1.1*records[1].mesh_tetra_count
    )
    if not monotone:
        status="REFINEMENT_INSUFFICIENT"
        reason=(
            "Mesh-local refinement did not create two successive >=10% increases "
            "in actual tetra counts. Do not interpret stress changes as convergence."
        )
    elif near_clamp:
        status="SUPPORT_SINGULARITY_RISK"
        reason=(
            "Maximum sampled stress is at the idealized fully clamped boundary. "
            "A hard fixed face/corner may produce a nonconvergent stress maximum. "
            "Real attachment geometry/contact must be characterized and modeled."
        )
    elif peak_change>5. or mean_change>5. or p90_change>5. or moved>.08*extent_mm:
        status="LOCAL_STRESS_NOT_CONVERGED"
        reason=(
            "Under actual targeted tetra refinement, global peak / "
            "fixed-region stress / physical hotspot location changes too much. "
            "Additional physical fixture detail or refined numerical runs required."
        )
    else:
        status="PRELIMINARY_LOCAL_STRESS_SCREEN_MET"
        reason=(
            "Three mesh solutions pass a heuristic 5% sampled-stress "
            "sensitivity screen and location consistency. This is a "
            "preliminary numerical check, NOT a stress or safety certificate."
        )
    return LocalRefinementEvidence(
        source_sha256=source_hash,
        focus_xyz_mm=tuple(float(x*1000) for x in original.sampled_peak_location_m),
        region_start_fraction=probe[0].start_fraction,
        region_end_fraction=probe[0].end_fraction,
        steps=records,
        peak_change_percent=peak_change,
        region_mean_change_percent=mean_change,
        region_p90_change_percent=p90_change,
        hotspot_move_mm=moved,
        peak_near_fixed_boundary=near_clamp,
        refinement_mono=monotone,
        status=status,explanation=reason,
        limitations=(
            "Local refinement preserves identical original STEP/loads but "
            "does NOT replace actual bolt/contact model, material testing, "
            "independent stress measurements or formal mesh convergence. "
            "Global FEM uses linear elasticity with faceted tetra geometry. "
            "Peak stresses near ideal fixed support and geometrical corners "
            "may be singular regardless of how many tetrahedra are used."
        )
    )


def run_hotspot_refinement(original_step: bytes, baseline, *,
                           source_label: str, unit: str,
                           solve_at: Callable):
    """Do exactly two new isolated Gmsh real BRep meshing + tetra10 FE jobs."""
    src_hash=sha256(original_step).hexdigest()
    if baseline.mesh.source_sha256!=src_hash:
        raise ValueError("Original CAD source SHA-256 mismatch")
    center=np.asarray(baseline.sampled_peak_location_m,dtype=float)
    if center.shape!=(3,) or not np.isfinite(center).all():
        raise ValueError("No finite physical hotspot point to refine")
    solved=[baseline]
    for factor in (.80,.60):
        out=solve_at(
            original_step,source_label=source_label,
            mesh_size_mm=float(baseline.mesh.mesh_size_mm),
            unit=unit,load=baseline.load,
            local_refinement={
                "center_m":center.tolist(),
                "size_factor":factor,
                "radius_fraction":.20,
            },
        )
        solved.append(out)
    return assess_hotspot_refinement(*solved,source_hash=src_hash)
