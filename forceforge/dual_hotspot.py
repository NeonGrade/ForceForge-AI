"""Second-stage v1.1 evidence: *simultaneously* refine two competing 3D stress sites.

A moving global maximum can hop between two different physical CAD features.
After the existing single-hotspot 3-mesh audit has found two such XYZ sites,
this module does TWO MORE independently meshed and solved tetra10 FE studies.
EACH of the new meshes uses both hotspot centers through Gmsh's Min-of-Box
size fields. The fixed 7 mm physical spheres are compared across both.

All outcomes are PRELIMINARY NUMERICAL screens, never a fatigue, contact,
material-yield, experiment correlation, or structural approval.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Callable
import math

import numpy as np

from .isolated_cad import MAX_INTERACTIVE_TETS
from .mesh_verification import _fractional_difference
from .stress_probe import probe_physical_hotspot, probe_stress


@dataclass(frozen=True)
class DualMeshStep:
    label: str
    mesh_tetra_count: int
    size_factor: float
    tip_mm: float
    global_peak_mpa: float
    peak_xyz_mm: tuple[float, float, float]
    relative_reaction_residual: float
    volume_error_percent: float

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DualSiteEvidence:
    source_sha256: str
    physical_centers_xyz_mm: tuple[tuple[float,float,float], ...]
    radius_mm: float
    steps: tuple[DualMeshStep, ...]
    site_rows: tuple[dict, ...]
    maximum_site_mean_change_percent: float | None
    maximum_site_p90_change_percent: float | None
    global_peak_change_percent: float | None
    global_peak_movement_mm: float
    global_peak_status: str
    status: str
    explanation: str
    limitations: str

    def as_dict(self):
        return asdict(self)


def _validated_centers(centers_m) -> np.ndarray:
    centers = np.asarray(centers_m, dtype=float)
    if centers.shape != (2, 3) or not np.isfinite(centers).all():
        raise ValueError("Exactly two finite physical hotspot centers (XYZ, metres) are required")
    if np.linalg.norm(centers[0] - centers[1]) < 1e-6:
        raise ValueError("Competing physical hotspots are not distinct")
    return centers


def assess_dual_hotspot_study(baseline, refined_a, refined_b, *,
                              source_hash: str, centers_m) -> DualSiteEvidence:
    """Compare only fixed XYZ regions after *both* locations were refined.

    Evidence requires the same source SHA, load, centers and finite Gauss
    quadrature data on two independent new meshes; a changing maximum cannot
    silently be substituted for either fixed physical ROI.
    """
    centers = _validated_centers(centers_m)
    models = (baseline, refined_a, refined_b)
    if any(x.mesh.source_sha256 != source_hash for x in models):
        raise ValueError("Dual hotspot STEP source SHA mismatch")
    if any(x.load != baseline.load for x in models):
        raise ValueError("Dual hotspot material/force/fixture differs from baseline")
    if any(x.mesh.num_tets > MAX_INTERACTIVE_TETS for x in models):
        raise ValueError("Dual hotspot mesh exceeds 1,400 tetrahedra")
    if any(x.relative_reaction_residual > 1e-5 or
           x.mesh.relative_volume_difference > .20 or
           x.mesh.min_shape_quality <= 0 for x in models):
        raise ValueError("Dual hotspot FEA violates equilibrium, CAD volume or mesh quality gates")
    for model in (refined_a, refined_b):
        settings = model.mesh.local_refinement or {}
        recorded_centers = np.asarray(settings.get("centers_m", []), dtype=float)
        if recorded_centers.shape != (2, 3) or not np.allclose(
            recorded_centers, centers, atol=1e-10, rtol=0
        ):
            raise ValueError("Both new FE meshes must use both of the exact same physical hotspot centers")

    probes = (probe_stress(refined_a), probe_stress(refined_b))
    records = tuple(
        DualMeshStep(
            label=label,
            mesh_tetra_count=int(model.mesh.num_tets),
            size_factor=float(model.mesh.local_refinement["size_factor"]),
            tip_mm=float(model.tip_mm),
            global_peak_mpa=float(model.peak_von_mises_mpa),
            peak_xyz_mm=tuple(float(v) for v in probe.global_peak_location_mm),
            relative_reaction_residual=float(model.relative_reaction_residual),
            volume_error_percent=100*float(model.mesh.relative_volume_difference),
        )
        for label, model, probe in zip(
            ("Dual-centre mesh A", "Dual-centre mesh B"),
            (refined_a, refined_b), probes,
        )
    )
    actual_growth = (
        records[0].mesh_tetra_count >= 1.1 * baseline.mesh.num_tets
        and records[1].mesh_tetra_count >= 1.1 * records[0].mesh_tetra_count
        and records[1].size_factor < records[0].size_factor
    )

    site_rows = []
    site_error = None
    for idx, center in enumerate(centers):
        try:
            a = probe_physical_hotspot(refined_a, center, radius_mm=7.)
            b = probe_physical_hotspot(refined_b, center, radius_mm=7.)
            site_rows.append({
                "site": "Fixed physical hotspot " + str(idx+1),
                "center_xyz_mm": a.center_mm,
                "radius_mm": 7.,
                "mesh_A_gauss_samples": a.gauss_samples,
                "mesh_B_gauss_samples": b.gauss_samples,
                "mesh_A_weighted_mean_mpa": a.weighted_mean_mpa,
                "mesh_B_weighted_mean_mpa": b.weighted_mean_mpa,
                "mean_change_percent": _fractional_difference(
                    b.weighted_mean_mpa, a.weighted_mean_mpa
                ),
                "mesh_A_weighted_p90_mpa": a.weighted_p90_mpa,
                "mesh_B_weighted_p90_mpa": b.weighted_p90_mpa,
                "p90_change_percent": _fractional_difference(
                    b.weighted_p90_mpa, a.weighted_p90_mpa
                ),
            })
        except ValueError as exc:
            site_error = str(exc)
            break
    complete = len(site_rows) == 2
    max_mean = (max(row["mean_change_percent"] for row in site_rows)
                if complete and all(row["mean_change_percent"] is not None for row in site_rows)
                else None)
    max_p90 = (max(row["p90_change_percent"] for row in site_rows)
               if complete and all(row["p90_change_percent"] is not None for row in site_rows)
               else None)

    delta_peak = _fractional_difference(
        records[1].global_peak_mpa, records[0].global_peak_mpa
    )
    drift = float(np.linalg.norm(
        np.asarray(records[1].peak_xyz_mm)-np.asarray(records[0].peak_xyz_mm)
    ))
    axis = baseline.load.boundary_axis
    span = float((baseline.mesh.bbox_m[1,axis] -
                  baseline.mesh.bbox_m[0,axis]) * 1000)
    if span <= 0 or not math.isfinite(span):
        raise ValueError("Invalid STEP support-to-tip CAD span")
    near_clamp = any(
        p.global_peak_support_distance_fraction <= .05 for p in probes
    )
    peak_preliminary = (
        delta_peak is not None and delta_peak <= 5
        and drift <= .08 * span and not near_clamp
    )
    peak_status = (
        "PRELIMINARY_NUMERICAL_PEAK_SCREEN_NOT_CERTIFIED"
        if peak_preliminary else "PEAK_STRESS_UNRESOLVED"
    )

    if not actual_growth:
        status = "INSUFFICIENT_DUAL_SITE_REFINEMENT"
        explanation = (
            "Actual 3D tetrahedra did not increase by at least 10% in "
            "both steps. No dual-site mesh convergence can be inferred."
        )
    elif near_clamp:
        status = "SUPPORT_SINGULARITY_RISK"
        explanation = (
            "A sampled global maximum lies within 5% of the ideal fully "
            "clamped boundary. Numerical stress extrema may be singular."
        )
    elif not complete or max_mean is None or max_p90 is None:
        status = "DUAL_SITE_PROBES_UNRESOLVED"
        explanation = (
            "Both identical fixed XYZ spheres could not be sampled "
            "on both independently remeshed tetra10 FE solutions. "
            + (site_error or "Missing reliable sample statistics.")
        )
    elif max_mean > 5 or max_p90 > 5:
        status = "DUAL_SITE_STRESS_NOT_STABLE"
        explanation = (
            "At least one of the two fixed 7 mm XYZ regions changed "
            "by more than 5% in Gauss-volume weighted mean or P90 stress."
        )
    else:
        status = "PRELIMINARY_DUAL_SITE_NUMERICAL_STABILITY"
        explanation = (
            "Two fresh 3D volume meshes refined BOTH fixed stress regions "
            "simultaneously, with >=10% tetra growth and <=5% changes in "
            "each site's Gauss-volume weighted mean and P90. "
            "This is a heuristic finite-region numerical check ONLY. "
            "The moving global stress peak is judged separately: "
            + peak_status + "."
        )

    return DualSiteEvidence(
        source_sha256=source_hash,
        physical_centers_xyz_mm=tuple(
            tuple(float(x*1000) for x in c) for c in centers
        ),
        radius_mm=7.,
        steps=records,
        site_rows=tuple(site_rows),
        maximum_site_mean_change_percent=max_mean,
        maximum_site_p90_change_percent=max_p90,
        global_peak_change_percent=delta_peak,
        global_peak_movement_mm=drift,
        global_peak_status=peak_status,
        status=status,
        explanation=explanation,
        limitations=(
            "Two fixed finite physical spheres are NOT a mathematical "
            "convergence proof of the moving maximum. Single-solid STEP, "
            "linear elastic tetra10, idealized fixed support and applied "
            "load, faceted geometry; no joint contact, measured fixture "
            "loads, plasticity, fatigue, independent experiment or safety "
            "certification. Both Gmsh meshes must be reviewed for volume, "
            "quality, force equilibrium and physical load-path validity."
        )
    )


def run_dual_hotspot_study(original_step: bytes, baseline, previous_study, *,
                           source_label: str, unit: str,
                           solve_at: Callable) -> DualSiteEvidence:
    """Explicit continuation of the *same* v1.1 L-bracket / imported STEP.

    The two centers are frozen from the PREVIOUS single-hotspot study.
    Nothing is selected after seeing the two new FE outcomes.
    """
    source_hash = sha256(original_step).hexdigest()
    if baseline.mesh.source_sha256 != source_hash:
        raise ValueError("Baseline source differs from original STEP bytes")
    if previous_study.source_sha256 != source_hash:
        raise ValueError("Earlier local stress study has a different STEP source")
    if len(previous_study.matched_physical_hotspot_regions) != 2:
        raise ValueError(
            "Two competing physical hotspots have not been identified. "
            "Run the original local stress refinement first."
        )
    centers = _validated_centers([
        np.asarray(row["center_xyz_mm"], dtype=float) / 1000
        for row in previous_study.matched_physical_hotspot_regions
    ])
    results = []
    for factor in (.80, .65):
        result = solve_at(
            original_step, source_label=source_label,
            mesh_size_mm=float(baseline.mesh.mesh_size_mm),
            unit=unit, load=baseline.load,
            local_refinement={
                "centers_m": centers.tolist(),
                "size_factor": factor,
                "radius_fraction": .18,
            },
        )
        results.append(result)
    return assess_dual_hotspot_study(
        baseline, results[0], results[1],
        source_hash=source_hash, centers_m=centers,
    )
