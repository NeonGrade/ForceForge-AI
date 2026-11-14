"""Numerical evidence is source-locked and does not overstate convergence."""
from hashlib import sha256
from types import SimpleNamespace
import pytest

from forceforge.cad_solid import CadLoad
from forceforge.mesh_verification import (
    assess_mesh_evidence, run_mesh_evidence, select_mesh_sizes,
)

ORIGINAL = b"ISO-10303-21;" + b"STEP-source-verification" * 20
DIGEST = sha256(ORIGINAL).hexdigest()
CASE = CadLoad(force_n=120, force_axis=0, boundary_axis=2)


def fake(size=12, tets=200, tip=0.1, stress=20.0, *,
         source_hash=DIGEST, load=CASE, nodes=300, volume_error=.015,
         residual=1e-10):
    mesh = SimpleNamespace(
        mesh_size_mm=float(size), num_tets=tets,
        source_sha256=source_hash,
        relative_volume_difference=volume_error,
        min_shape_quality=.025,
    )
    return SimpleNamespace(
        mesh=mesh, load=load, nodes_m=[0]*nodes,
        tip_mm=float(tip), peak_von_mises_mpa=float(stress),
        strain_energy_j=.001, relative_reaction_residual=residual,
    )


@pytest.mark.parametrize("baseline", [5,6,8,10,12,14,15])
def test_mesh_plan_has_three_distinct_sizes_and_reuses_baseline(baseline):
    selected = select_mesh_sizes(baseline)
    assert len(selected) == 3
    assert selected[0] > selected[1] > selected[2]
    assert baseline in selected
    assert all(5 <= x <= 15 for x in selected)


def test_sensitivity_screen_never_claims_peak_stress_converged():
    specimens = [
        fake(15, 100, .120, 17),
        fake(12, 180, .108, 40),
        fake(10, 320, .107, 70),
    ]
    evidence = assess_mesh_evidence(specimens, DIGEST, CASE)
    assert evidence.decision == "PRELIMINARY_GLOBAL_DISPLACEMENT_STABILITY"
    assert evidence.fine_vs_medium_displacement_percent < 1
    assert evidence.fine_vs_medium_stress_percent > 40
    assert "not an asymptotic convergence proof" in evidence.limitations
    assert evidence.as_dict()["source_sha256"] == DIGEST


def test_sensitivity_screen_rejects_unstable_global_displacements():
    specimens = [
        fake(15, 100, .120),
        fake(12, 180, .105),
        fake(10, 320, .088),
    ]
    evidence = assess_mesh_evidence(specimens, DIGEST, CASE)
    assert evidence.decision == "MESH_SENSITIVE"


def test_actual_element_count_not_target_size_controls_validity():
    specimens = [
        fake(15, 300, .120),
        fake(12, 250, .108),
        fake(10, 320, .107),
    ]
    evidence = assess_mesh_evidence(specimens, DIGEST, CASE)
    assert evidence.decision == "INCONCLUSIVE_REFINEMENT"


def test_detects_insufficient_mesh_refinement():
    specimens = [
        fake(15, 180, .120),
        fake(12, 185, .108),
        fake(10, 190, .107),
    ]
    evidence = assess_mesh_evidence(specimens, DIGEST, CASE)
    assert evidence.decision == "INSUFFICIENT_REFINEMENT"


def test_detects_equilibrium_and_geometry_quality_failure():
    specimens = [
        fake(15, 100, .120),
        fake(12, 180, .108, residual=.02),
        fake(10, 320, .107),
    ]
    evidence = assess_mesh_evidence(specimens, DIGEST, CASE)
    assert evidence.decision == "INVALID_MODEL_EVIDENCE"


def test_refuses_mixed_cad_sources_and_force_material_assumptions():
    specimens = [
        fake(15, 100, .120),
        fake(12, 180, .108),
        fake(10, 320, .107, source_hash="DIFFERENT_STEP"),
    ]
    with pytest.raises(ValueError, match="CAD hash mismatch"):
        assess_mesh_evidence(specimens, DIGEST, CASE)
    specimens[2] = fake(10, 320, .107,
                        load=CadLoad(force_n=150, force_axis=0, boundary_axis=2))
    with pytest.raises(ValueError, match="Load/material/constraint mismatch"):
        assess_mesh_evidence(specimens, DIGEST, CASE)


def test_run_uses_existing_solution_and_exactly_two_isolated_fea_calls():
    completed = fake(12, 180, .108, nodes=300)
    invoked = []

    def solve_step(source, *, source_label, mesh_size_mm, unit, load):
        assert source == ORIGINAL
        assert load == CASE
        assert unit == "mm"
        invoked.append(mesh_size_mm)
        if mesh_size_mm == 15:
            return fake(15, 100, .120)
        elif mesh_size_mm == 10:
            return fake(10, 320, .107)
        raise AssertionError("Unexpected redundant FE calculation")

    evidence = run_mesh_evidence(
        ORIGINAL, completed, source_label="Original STEP",
        unit="mm", solve_at=solve_step,
    )
    assert set(invoked) == {15,10}
    assert len(invoked) == 2
    assert len(evidence.ordered_rows) == 3
    assert evidence.source_sha256 == DIGEST


def test_baseline_hash_must_match_original_bytes_before_any_solve():
    completed = fake(source_hash="DIFFERENT_STEP")
    with pytest.raises(ValueError, match="Baseline STEP"):
        run_mesh_evidence(
            ORIGINAL, completed, source_label="BAD SOURCE",
            unit="mm", solve_at=lambda *a, **kw: None,
        )
