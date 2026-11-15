"""Second-stage v1.1 checks: two physical hotspots on BOTH real FE meshes."""
from hashlib import sha256
from types import SimpleNamespace
import numpy as np
import pytest

from forceforge.cad_solid import CadLoad
from forceforge.dual_hotspot import (
    assess_dual_hotspot_study, run_dual_hotspot_study,
)

SOURCE_BYTES = b"Identical source STEP bytes for a deterministic unit test"
SOURCE_SHA = sha256(SOURCE_BYTES).hexdigest()
LOAD = CadLoad(force_n=250, force_axis=0, boundary_axis=2)
VOLUME = .075*.04*.058
CENTERS = np.array([[.010,.012,.020],[.010,.032,.020]])


def model(n, peak=20., *, source=SOURCE_SHA, load=LOAD,
          factor=None, centers=CENTERS, peak_y=.012):
    # Real Gauss sample locations/volumes are exercised by stress_probe.
    pos=np.zeros((4*n, 3))
    pos[:,0]=.010
    pos[:,1]=np.where(np.arange(len(pos)) % 2 == 0, .012, .032)
    pos[:,2]=np.linspace(.001,.057,len(pos))
    settings=(
        {"centers_m":np.asarray(centers).tolist(),
         "size_factor":float(factor),"radius_fraction":.18}
        if factor is not None else None
    )
    return SimpleNamespace(
        mesh=SimpleNamespace(
            source_sha256=source,
            num_tets=n,
            mesh_size_mm=12.,
            local_refinement=settings,
            mesh_volume_m3=VOLUME,
            bbox_m=np.array([[0,0,0],[.075,.040,.058]]),
            relative_volume_difference=.005,
            min_shape_quality=.04,
        ),
        load=load,
        relative_reaction_residual=1e-9,
        tip_mm=.0356,
        peak_von_mises_mpa=peak,
        sampled_peak_location_m=np.array([.010,peak_y,.020]),
        gauss_points_m=pos,
        gauss_von_mises_pa=np.full(len(pos),peak*1e6),
        gauss_weights_m3=np.full(len(pos),VOLUME/len(pos)),
    )


def test_two_centres_stable_without_claiming_peak_convergence():
    baseline=model(583)
    a=model(770,20.,factor=.80,peak_y=.012)
    b=model(1010,20.2,factor=.65,peak_y=.032)
    evidence=assess_dual_hotspot_study(
        baseline,a,b,source_hash=SOURCE_SHA,centers_m=CENTERS
    )
    assert evidence.status=="PRELIMINARY_DUAL_SITE_NUMERICAL_STABILITY"
    assert evidence.global_peak_status=="PEAK_STRESS_UNRESOLVED"
    assert evidence.global_peak_movement_mm==pytest.approx(20.)
    assert len(evidence.site_rows)==2
    assert evidence.maximum_site_mean_change_percent<5.
    assert evidence.maximum_site_p90_change_percent<5.
    assert "NOT" in evidence.limitations


def test_one_fixed_site_changed_must_not_pass():
    baseline=model(583)
    a=model(770,20.,factor=.80)
    b=model(1010,20.,factor=.65)
    b.gauss_von_mises_pa=np.where(
        b.gauss_points_m[:,1]<.020, 24e6, 20e6
    )
    evidence=assess_dual_hotspot_study(
        baseline,a,b,source_hash=SOURCE_SHA,centers_m=CENTERS
    )
    assert evidence.status=="DUAL_SITE_STRESS_NOT_STABLE"
    assert evidence.maximum_site_p90_change_percent>5


def test_identical_source_material_and_centres_required():
    baseline=model(583)
    a=model(770,factor=.80)
    b=model(1010,factor=.65)
    with pytest.raises(ValueError,match="source SHA"):
        assess_dual_hotspot_study(
            baseline,a,model(1010,source="not-same",factor=.65),
            source_hash=SOURCE_SHA,centers_m=CENTERS
        )
    with pytest.raises(ValueError,match="material/force/fixture"):
        assess_dual_hotspot_study(
            baseline,a,model(1010,load=CadLoad(force_n=600),factor=.65),
            source_hash=SOURCE_SHA,centers_m=CENTERS
        )
    with pytest.raises(ValueError,match="exact same physical hotspot centers"):
        assess_dual_hotspot_study(
            baseline,a,model(1010,factor=.65,centers=np.array([[.01,.014,.02],[.01,.032,.02]])),
            source_hash=SOURCE_SHA,centers_m=CENTERS
        )
    with pytest.raises(ValueError,match="two finite"):
        assess_dual_hotspot_study(
            baseline,a,b,source_hash=SOURCE_SHA,centers_m=[[0,0,0]]
        )


def test_fake_refinement_without_actual_tetra_growth_is_inconclusive():
    out=assess_dual_hotspot_study(
        model(583),model(610,factor=.80),model(640,factor=.65),
        source_hash=SOURCE_SHA,centers_m=CENTERS
    )
    assert out.status=="INSUFFICIENT_DUAL_SITE_REFINEMENT"


def test_clamp_singularity_cannot_be_certified():
    baseline=model(583)
    a=model(770,factor=.80)
    b=model(1010,factor=.65)
    a.sampled_peak_location_m=np.array([.01,.012,.0009])
    result=assess_dual_hotspot_study(
        baseline,a,b,source_hash=SOURCE_SHA,centers_m=CENTERS
    )
    assert result.status=="SUPPORT_SINGULARITY_RISK"


def test_runner_uses_same_two_fixed_sites_in_both_new_gmsh_jobs():
    baseline=model(583)
    prior=SimpleNamespace(
        source_sha256=SOURCE_SHA,
        matched_physical_hotspot_regions=(
            {"center_xyz_mm":(10.,12.,20.)},
            {"center_xyz_mm":(10.,32.,20.)},
        )
    )
    calls=[]
    def solve_at(blob,**params):
        assert blob==SOURCE_BYTES
        assert params["load"]==LOAD
        settings=params["local_refinement"]
        assert np.allclose(settings["centers_m"],CENTERS)
        calls.append(settings["size_factor"])
        return model(
            770 if len(calls)==1 else 1010, 20., factor=settings["size_factor"]
        )
    result=run_dual_hotspot_study(
        SOURCE_BYTES,baseline,prior,source_label="original STEP",
        unit="mm",solve_at=solve_at,
    )
    assert calls==[.65,.45]
    assert len(result.steps)==2
    assert result.status=="PRELIMINARY_DUAL_SITE_NUMERICAL_STABILITY"
