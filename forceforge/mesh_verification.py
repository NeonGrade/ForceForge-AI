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

from .cad_solid import CADFEAResult, CadLoad


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
        ) for x in ordered
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
