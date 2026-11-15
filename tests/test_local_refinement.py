"""Definitive numerical gates for local stress (never a fake safety pass)."""
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest
from forceforge.cad_solid import CadLoad
from forceforge.local_refinement import assess_hotspot_refinement

SOURCE=sha256(b"original STEP geometry").hexdigest()
LOAD=CadLoad(force_n=250,force_axis=0,boundary_axis=2)
VOLUME=.075*.04*.058


def model(tets,peak,*,peak_fraction=.30,
          source=SOURCE,load=LOAD,peak_y=.020,
          dual_sites=False):
    xyz=np.zeros((4*tets,3))
    xyz[:,0]=.010
    if dual_sites:
        xyz[:,1]=np.where(np.arange(len(xyz))%2==0,.012,.032)
    else:
        xyz[:,1]=.020
    xyz[:,2]=np.linspace(.001,.057,len(xyz))
    p=np.array([.010,peak_y,.058*peak_fraction])
    # The max sample is a physical location, independent of mesh id.
    return SimpleNamespace(
        mesh=SimpleNamespace(
            source_sha256=source,
            num_tets=tets,
            mesh_volume_m3=VOLUME,
            bbox_m=np.array([[0.,0.,0.],[.075,.04,.058]]),
            relative_volume_difference=.005,
            min_shape_quality=.03,
            mesh_size_mm=12.,
        ),
        load=load,
        relative_reaction_residual=1e-10,
        tip_mm=.035,
        peak_von_mises_mpa=float(peak),
        sampled_peak_location_m=p,
        gauss_points_m=xyz,
        gauss_von_mises_pa=np.full(len(xyz),peak*1e6),
        gauss_weights_m3=np.full(len(xyz),VOLUME/len(xyz)),
    )


def test_hard_fixture_never_passes_even_if_global_peak_is_stable():
    a=model(450,20.,peak_fraction=.02)
    b=model(650,20.1,peak_fraction=.02)
    c=model(950,20.1,peak_fraction=.02)
    result=assess_hotspot_refinement(a,b,c,source_hash=SOURCE)
    assert result.refinement_mono
    assert result.peak_near_fixed_boundary
    assert result.status=="SUPPORT_SINGULARITY_RISK"
    assert "attachment geometry/contact" in result.explanation


def test_local_peak_17_percent_change_is_not_converged():
    a=model(450,19.2361)
    b=model(650,18.6683)
    c=model(950,22.6327)
    result=assess_hotspot_refinement(a,b,c,source_hash=SOURCE)
    assert result.peak_change_percent==pytest.approx(17.51625,abs=.002)
    assert result.status=="LOCAL_STRESS_NOT_CONVERGED"


def test_smooth_off_fixture_stress_can_only_pass_preliminary_numeric_screen():
    a=model(450,20.)
    b=model(650,20.2)
    c=model(950,20.3)
    result=assess_hotspot_refinement(a,b,c,source_hash=SOURCE)
    assert result.status=="PRELIMINARY_LOCAL_STRESS_SCREEN_MET"
    assert "not" in result.explanation.lower()
    assert "does NOT" in result.limitations


def test_insufficient_true_tetra_count_is_rejected():
    r=assess_hotspot_refinement(
        model(500,20),model(510,20),model(520,20),source_hash=SOURCE
    )
    assert r.status=="REFINEMENT_INSUFFICIENT"


def test_mixed_cad_or_material_rejected_before_validity_report():
    with pytest.raises(ValueError,match="STEP bytes"):
        assess_hotspot_refinement(model(500,20),model(700,21),
                                  model(900,22,source="different"),
                                  source_hash=SOURCE)
    with pytest.raises(ValueError,match="Material/force/support"):
        assess_hotspot_refinement(
            model(500,20),model(700,21),
            model(900,22,load=CadLoad(force_n=999,force_axis=0,boundary_axis=2)),
            source_hash=SOURCE
        )


def test_two_competing_physical_hotspots_are_compared_at_same_xyz_locations():
    first=model(450,20.0,peak_y=.012,dual_sites=True)
    second=model(650,20.2,peak_y=.012,dual_sites=True)
    third=model(950,20.3,peak_y=.032,dual_sites=True)
    out=assess_hotspot_refinement(first,second,third,source_hash=SOURCE)
    assert out.refinement_mono
    assert out.hotspot_move_mm==pytest.approx(20)
    assert out.status=="PRELIMINARY_COMPETING_HOTSPOT_STABILITY"
    assert len(out.matched_physical_hotspot_regions)==2
    for region in out.matched_physical_hotspot_regions:
        assert region["mesh_A_gauss_samples"]>=12
        assert region["mesh_B_gauss_samples"]>=12
        assert region["mean_change_percent"]<5
        assert region["p90_change_percent"]<5
    assert "NOT an approval" in out.explanation


def test_two_competing_hotspots_do_not_fake_stability_if_fixed_region_changes():
    first=model(450,20.,peak_y=.012,dual_sites=True)
    second=model(650,20.,peak_y=.012,dual_sites=True)
    third=model(950,21.0,peak_y=.032,dual_sites=True)
    # Global finite-band mean stays at 20 MPa and its P90 changes only
    # 4.76%, so the broad screen passes. Yet the fixed *left* physical
    # hotspot changes 20 -> 19 MPa (5.26% using the fine denominator)
    # and therefore MUST fail the dual-site fixed-ROI requirement.
    third.gauss_von_mises_pa=np.where(
        third.gauss_points_m[:,1]<.020, 19e6, 21e6
    )
    out=assess_hotspot_refinement(first,second,third,source_hash=SOURCE)
    assert out.status=="MULTIPLE_HOTSPOTS_NOT_CORRELATED"
    assert len(out.matched_physical_hotspot_regions)==2
    assert out.maximum_fixed_site_p90_change_percent>5
