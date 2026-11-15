"""Auditable mesh-sensitivity evidence for one unchanged imported CAD solid.

Three independently tetrahedralized versions of the *same STEP bytes* are
compared using the identical materials, force and constraints. This module
does not claim mathematical convergence of local stress or physical safety.
The full 3D solve remains in the crash-isolated v0.9 worker process.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Callable, Sequence
import math
import numpy as np

from .cad_solid import CADFEAResult, CadLoad
from .stress_probe import probe_stress


@dataclass(frozen=True)
class MeshEvidenceRow:
    target_size_mm: float
    tetrahedra: int
    quadratic_nodes: int
    volume_error_percent: float
    minimum_quality_proxy: float
    tip_mm: float
    peak_sampled_mises_mpa: float
    strain_energy_mj: float
    reaction_residual: float
    probe_weighted_mean_mpa: float
    probe_weighted_p90_mpa: float
    probe_gauss_samples: int
    probe_volume_percent: float
    hotspot_x_mm: float
    hotspot_y_mm: float
    hotspot_z_mm: float
    hotspot_support_fraction: float
    hotspot_zone: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MeshEvidence:
    source_sha256: str
    load: CadLoad
    ordered_rows: tuple[MeshEvidenceRow, ...]
    decision: str
    decision_reason: str
    fine_vs_medium_displacement_percent: float | None
    fine_vs_medium_stress_percent: float | None
    medium_vs_coarse_displacement_percent: float | None
    limitations: str
    local_peak_status: str
    physical_band_stress_status: str
    engineering_evidence_status: str
    fine_medium_probe_mean_percent: float
    fine_medium_probe_p90_percent: float
    fine_medium_hotspot_drift_mm: float

    def as_dict(self) -> dict:
        data = asdict(self)
        data["load"] = asdict(self.load)
        return data


def select_mesh_sizes(baseline_mm: float) -> tuple[float, float, float]:
    """Three descending target tetra sizes; baseline always included.

    Gmsh might NOT return strictly increasing element counts even if target
    sizes decrease; the evidence evaluation explicitly checks real counts.
    """
    base = round(float(baseline_mm), 5)
    if not math.isfinite(base) or not 5 <= base <= 15:
        raise ValueError("Baseline interactive CAD mesh size must be 5–15 mm")
    proposed = [min(15., base + 3.), base, max(5., base - 2.)]
    # Fill endpoint duplicates without changing the already-solved baseline.
    if len(set(proposed)) < 3:
        for candidate in (base + 1., base - 1., base + 2., base - 2.,
                          base + 3., base - 3., 11., 9., 7.):
            if 5 <= candidate <= 15 and candidate not in proposed:
                proposed.append(candidate)
            if len(set(proposed)) >= 3:
                break
    ordered = tuple(sorted(set(proposed), reverse=True)[:3])
    if len(ordered) != 3 or base not in ordered:
        raise AssertionError("Mesh planning must include the baseline exactly")
    return ordered


def _fractional_difference(new: float, old: float) -> float | None:
    if not all(math.isfinite(float(x)) for x in (new, old)):
        return None
    denom = max(abs(float(new)), 1e-12)
    return 100. * abs(float(new) - float(old)) / denom


def assess_mesh_evidence(results: Sequence[CADFEAResult],
                         source_sha256: str,
                         expected_load: CadLoad,
                         displacement_screen_percent: float = 3.) -> MeshEvidence:
    """Analyze mesh sensitivity WITHOUT labeling any local stress certified.

    This 3-mesh screen checks whether the two most refined global displacements
    are within a user-visible 3% heuristic and the latest refinement change is
    not larger than the preceding change. This is not proof of asymptotic
    convergence; especially clamp/holes can have stress singularities.
    """
    if len(results) != 3:
        raise ValueError("Exactly 3 distinct nominal mesh resolutions are required")
    if not 0 < displacement_screen_percent <= 10:
        raise ValueError("Displacement screen must be between 0 and 10%")
    sizes = [float(x.mesh.mesh_size_mm) for x in results]
    if len(set(sizes)) != 3:
        raise ValueError("Mesh evidence requires 3 distinct mesh targets")
    if any(x.mesh.source_sha256 != source_sha256 for x in results):
        raise ValueError("CAD hash mismatch: do not compare different STEP geometry")
    if any(x.load != expected_load for x in results):
        raise ValueError("Load/material/constraint mismatch between mesh solves")
    ordered = sorted(results, key=lambda x: x.mesh.mesh_size_mm, reverse=True)
    # A physically fixed 5–30% support-to-load band is sampled in
    # millimetre coordinates, independent of mesh node / element numbering.
    # Exact Gauss-volume weights make these finite-region integrals
    # meaningful even when mesh sizes differ.
    probes = [probe_stress(x) for x in ordered]
    rows = tuple(
        MeshEvidenceRow(
            target_size_mm=float(x.mesh.mesh_size_mm),
            tetrahedra=int(x.mesh.num_tets),
            quadratic_nodes=len(x.nodes_m),
            volume_error_percent=100 * x.mesh.relative_volume_difference,
            minimum_quality_proxy=x.mesh.min_shape_quality,
            tip_mm=x.tip_mm,
            peak_sampled_mises_mpa=x.peak_von_mises_mpa,
            strain_energy_mj=1000 * x.strain_energy_j,
            reaction_residual=x.relative_reaction_residual,
            probe_weighted_mean_mpa=p.mean_von_mises_mpa,
            probe_weighted_p90_mpa=p.p90_von_mises_mpa,
            probe_gauss_samples=p.gauss_samples,
            probe_volume_percent=p.volume_fraction_percent,
            hotspot_x_mm=p.global_peak_location_mm[0],
            hotspot_y_mm=p.global_peak_location_mm[1],
            hotspot_z_mm=p.global_peak_location_mm[2],
            hotspot_support_fraction=p.global_peak_support_distance_fraction,
            hotspot_zone=p.global_peak_zone,
        ) for x,p in zip(ordered,probes)
    )
    if any(
        not math.isfinite(value)
        for row in rows
        for value in (
            row.volume_error_percent, row.minimum_quality_proxy, row.tip_mm,
            row.peak_sampled_mises_mpa, row.strain_energy_mj,
            row.reaction_residual,
        )
    ):
        raise ValueError("FE solution contains non-finite mesh evidence")
    if any(
        row.reaction_residual > 1e-5
        or row.volume_error_percent > 20
        or row.minimum_quality_proxy <= 0
        or row.strain_energy_mj < -1e-9
        for row in rows
    ):
        decision, reason = (
            "INVALID_MODEL_EVIDENCE",
            "At least one mesh fails equilibrium, positive quality, "
            "elastic energy or CAD-to-mesh volume checks.",
        )
    elif not (rows[0].tetrahedra < rows[1].tetrahedra < rows[2].tetrahedra):
        decision, reason = (
            "INCONCLUSIVE_REFINEMENT",
            "Decreasing target sizes did not increase actual tetra counts "
            "at every level. Target edge length alone is not evidence.",
        )
    elif rows[1].tetrahedra < 1.1 * rows[0].tetrahedra or rows[2].tetrahedra < 1.1 * rows[1].tetrahedra:
        decision, reason = (
            "INSUFFICIENT_REFINEMENT",
            "Successive meshes contain fewer than 10% additional elements. "
            "Use more distinct mesh resolutions for a meaningful check.",
        )
    else:
        change_1 = abs(rows[1].tip_mm - rows[0].tip_mm)
        change_2 = abs(rows[2].tip_mm - rows[1].tip_mm)
        relative_2 = _fractional_difference(rows[2].tip_mm, rows[1].tip_mm)
        if relative_2 is not None and relative_2 <= displacement_screen_percent and change_2 <= 1.1 * change_1:
            decision, reason = (
                "PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY",
                "The last two global tip-displacement estimates differ by "
                f"no more than the {displacement_screen_percent:g}% demonstration "
                "screen, with no growing absolute refinement change. "
                "This is not a formal grid-convergence certificate.",
            )
        else:
            decision, reason = (
                "MESH_SENSITIVE",
                "Global tip displacement has not met the preliminary "
                "mesh-stability screen. Refine again or review discretization.",
            )
    # Separate the actual engineering quantities. A stable *global*
    # displacement never implies a stable local Gauss stress extremum.
    normal_refinement = (
        rows[0].tetrahedra < rows[1].tetrahedra < rows[2].tetrahedra
        and rows[1].tetrahedra >= 1.1 * rows[0].tetrahedra
        and rows[2].tetrahedra >= 1.1 * rows[1].tetrahedra
    )
    probe_mean_diff = _fractional_difference(
        rows[2].probe_weighted_mean_mpa, rows[1].probe_weighted_mean_mpa
    )
    probe_p90_diff = _fractional_difference(
        rows[2].probe_weighted_p90_mpa, rows[1].probe_weighted_p90_mpa
    )
    peak_difference = _fractional_difference(
        rows[2].peak_sampled_mises_mpa, rows[1].peak_sampled_mises_mpa
    )
    hotspot_drift_mm = float(np.linalg.norm(
        np.array(probes[2].global_peak_location_mm)
        - np.array(probes[1].global_peak_location_mm)
    ))
    span_mm=float(
        (ordered[2].mesh.bbox_m[1,expected_load.boundary_axis] -
         ordered[2].mesh.bbox_m[0,expected_load.boundary_axis])*1000
    )
    # This is an explicit conservative *screen*, not ASTM or code approval:
    # 5% differences, same physical neighbourhood, and no mesh-count
    # problems are necessary but are not sufficient for local stress proof.
    peak_wanders = hotspot_drift_mm > 0.08*span_mm
    near_ideal_fixture = (
        probes[1].global_peak_support_distance_fraction<=.05
        or probes[2].global_peak_support_distance_fraction<=.05
    )
    if not normal_refinement or decision=="INVALID_MODEL_EVIDENCE":
        peak_status="UNVERIFIED_MESH_REFINEMENT"
        probe_status="UNVERIFIED_MESH_REFINEMENT"
    else:
        finite_stable = (
            probe_mean_diff is not None and probe_mean_diff<=5.
            and probe_p90_diff is not None and probe_p90_diff<=5.
        )
        peak_stable = (
            peak_difference is not None and peak_difference<=5.
            and not peak_wanders and not near_ideal_fixture
        )
        probe_status = (
            "PRELIMINARY_FINITE_REGION_STRESS_STABILITY"
            if finite_stable else "FINITE_REGION_STRESS_UNRESOLVED"
        )
        peak_status = (
            "PRELIMINARY_PEAK_STRESS_STABILITY"
            if peak_stable else "PEAK_STRESS_UNRESOLVED"
        )
    if (decision=="PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY"
            and peak_status=="PRELIMINARY_PEAK_STRESS_STABILITY"
            and probe_status=="PRELIMINARY_FINITE_REGION_STRESS_STABILITY"):
        overall="PRELIMINARY_NUMERICAL_SCREENS_MET_NOT_CERTIFIED"
    elif decision=="INVALID_MODEL_EVIDENCE":
        overall="INVALID_NUMERICAL_EVIDENCE"
    elif decision=="PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY":
        overall="GLOBAL_DISPLACEMENT_STABLE_LOCAL_STRESS_UNVERIFIED"
    else:
        overall="MESH_DEPENDENT_OR_INSUFFICIENT_EVIDENCE"
    return MeshEvidence(
        source_sha256=source_sha256,
        load=expected_load,
        ordered_rows=rows,
        decision=decision,
        decision_reason=reason,
        fine_vs_medium_displacement_percent=_fractional_difference(rows[2].tip_mm, rows[1].tip_mm),
        fine_vs_medium_stress_percent=_fractional_difference(
            rows[2].peak_sampled_mises_mpa, rows[1].peak_sampled_mises_mpa
        ),
        medium_vs_coarse_displacement_percent=_fractional_difference(rows[1].tip_mm, rows[0].tip_mm),
        local_peak_status=peak_status,
        physical_band_stress_status=probe_status,
        engineering_evidence_status=overall,
        fine_medium_probe_mean_percent=float(probe_mean_diff),
        fine_medium_probe_p90_percent=float(probe_p90_diff),
        fine_medium_hotspot_drift_mm=hotspot_drift_mm,
        limitations=(
            "Three grid sizes are a preliminary sensitivity SCREEN, not an "
            "asymptotic convergence proof. Peak sampled von Mises near "
            "clamped edges, hole walls and corners may be nonconvergent; "
            "do not use this screen to certify safety. STEP curvature is "
            "faceted by straight tetra geometry and all static loads, "
            "fixture/material inputs remain assumed until physically validated."
        ),
    )


def run_mesh_evidence(
    original_step: bytes,
    baseline: CADFEAResult,
    *,
    source_label: str,
    unit: str,
    solve_at: Callable[..., CADFEAResult],
) -> MeshEvidence:
    """Reuses completed baseline and invokes two *fresh* isolated FE solves."""
    exact_hash = sha256(original_step).hexdigest()
    if exact_hash != baseline.mesh.source_sha256:
        raise ValueError("Baseline STEP SHA-256 mismatch")
    sizes = select_mesh_sizes(baseline.mesh.mesh_size_mm)
    results = []
    for target_size in sizes:
        if target_size == baseline.mesh.mesh_size_mm:
            results.append(baseline)
        else:
            results.append(
                solve_at(
                    original_step,
                    source_label=source_label,
                    mesh_size_mm=target_size,
                    unit=unit,
                    load=baseline.load,
                )
            )
    return assess_mesh_evidence(results, exact_hash, baseline.load)
