"""Real STEP BRep localized mesh with an independently re-solved 3D stress field.

All tests use the original generated bracket STEP bytes, not recolored
surfaces or invented element data. Gmsh is optional outside integration CI.
"""
from hashlib import sha256
import numpy as np
import pytest

pytest.importorskip("gmsh")
from forceforge.cad_solid import CadLoad
from forceforge.isolated_cad import (
    generate_bracket_safely,analyze_step_safely,MAX_INTERACTIVE_TETS,
)
from forceforge.stress_probe import probe_stress
from forceforge.local_refinement import run_hotspot_refinement


@pytest.fixture(scope="module")
def cad_case():
    source=generate_bracket_safely(8)
    load=CadLoad(force_n=250,force_axis=0,boundary_axis=2)
    base=analyze_step_safely(source,source_label="actual 8mm bracket STEP",
                            mesh_size_mm=12,unit="mm",load=load)
    return source,load,base


def test_actual_tetra10_gauss_weights_and_peak_coordinates(cad_case):
    blob,load,solved=cad_case
    assert solved.mesh.source_sha256==sha256(blob).hexdigest()
    assert len(solved.gauss_points_m)==4*solved.mesh.num_tets
    assert len(solved.gauss_von_mises_pa)==4*solved.mesh.num_tets
    assert solved.gauss_points_m.shape[1]==3
    assert np.isclose(solved.gauss_weights_m3.sum(),
                      solved.mesh.mesh_volume_m3,rtol=1e-9)
    index=int(np.argmax(solved.gauss_von_mises_pa))
    np.testing.assert_allclose(
        solved.sampled_peak_location_m,solved.gauss_points_m[index])
    assert solved.peak_von_mises_mpa==pytest.approx(
        solved.gauss_von_mises_pa.max()/1e6,rel=1e-12)
    band=probe_stress(solved)
    assert band.gauss_samples>=12
    assert band.mean_von_mises_mpa>0
    assert 0<=band.global_peak_support_distance_fraction<=1


def test_actual_local_box_refines_same_step_without_changing_force(cad_case):
    blob,load,original=cad_case
    center=original.sampled_peak_location_m.tolist()
    out=analyze_step_safely(
        blob,source_label="real 8mm bracket targeted",
        mesh_size_mm=12,unit="mm",load=load,
        local_refinement={
            "center_m":center,
            "size_factor":.80,
            "radius_fraction":.20,
        },
    )
    assert out.mesh.local_refinement["size_factor"]==pytest.approx(.80)
    assert out.mesh.source_sha256==original.mesh.source_sha256
    assert out.load==original.load
    assert 0<out.mesh.num_tets<=MAX_INTERACTIVE_TETS
    assert out.relative_reaction_residual<1e-7
    assert out.mesh.relative_volume_difference<.20


def test_real_two_stage_hotspot_refinement_has_explicit_non_certifying_status(cad_case):
    blob,load,original=cad_case
    report=run_hotspot_refinement(
        blob,original,source_label="real 8mm bracket",unit="mm",
        solve_at=analyze_step_safely,
    )
    assert len(report.steps)==3
    assert report.refinement_mono, (
        "Actual STEP mesh counts did not increase by >=10% at each "
        f"local refinement: {[x.mesh_tetra_count for x in report.steps]}"
    )
    assert report.source_sha256==sha256(blob).hexdigest()
    assert all(r.reaction_residual<1e-5 for r in report.steps)
    assert report.status in {
        "REFINEMENT_INSUFFICIENT","SUPPORT_SINGULARITY_RISK",
        "LOCAL_STRESS_NOT_CONVERGED","PRELIMINARY_LOCAL_STRESS_SCREEN_MET",
    }
    assert "NOT" in report.limitations or "does NOT" in report.limitations
