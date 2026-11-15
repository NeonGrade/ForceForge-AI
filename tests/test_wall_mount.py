"""Rigid-body mounting loads, force/moment conservation, and CFD traction units."""
import numpy as np
import pytest

from forceforge.wall_mount import (
    WallMountInputs,analyze_wall_mount,integrate_pressure_traction
)


def test_gravity_produces_shear_and_top_row_tension_with_exact_equilibrium():
    result=analyze_wall_mount(WallMountInputs(
        mass_kg=2.,center_offset_mm=100.,
        anchor_spacing_x_mm=100.,anchor_spacing_y_mm=100.,
        axial_thrust_n=0.,
    ))
    w=2*9.80665
    assert result.applied_force_xyz_n==(0.,-w,0.)
    assert result.applied_moment_xyz_nm==(w*.1,0.,0.)
    assert result.max_anchor_shear_n==pytest.approx(w/4)
    assert result.max_anchor_tension_n==pytest.approx(w*.1/(2*.1))
    assert result.force_balance_error_n<1e-10
    assert result.moment_balance_error_nm<1e-10
    assert sum(a.reaction_y_n for a in result.anchors)==pytest.approx(w)
    assert sum(a.reaction_z_n for a in result.anchors)==pytest.approx(0)


def test_nonzero_thrust_torque_and_sideforce_still_close_all_six_equilibrium_components():
    result=analyze_wall_mount(WallMountInputs(
        mass_kg=5.,center_offset_mm=250.,
        anchor_spacing_x_mm=170.,anchor_spacing_y_mm=110.,
        axial_thrust_n=35.,motor_reaction_torque_nm=4.,
        lateral_force_x_n=11.,lateral_force_y_n=-3.,
        thrust_source="externally_integrated_cfd",
    ))
    positions=np.asarray([(a.x_mm/1000,a.y_mm/1000,0.) for a in result.anchors])
    reaction=np.asarray([(a.reaction_x_n,a.reaction_y_n,a.reaction_z_n) for a in result.anchors])
    assert np.linalg.norm(reaction.sum(axis=0)+result.applied_force_xyz_n)<1e-10
    assert np.linalg.norm(np.cross(positions,reaction).sum(axis=0)
                          +result.applied_moment_xyz_nm)<1e-10
    assert result.max_anchor_shear_n>0
    assert result.max_anchor_tension_n>0


@pytest.mark.parametrize("change",[
    {"mass_kg":-1},{"anchor_spacing_x_mm":0},
    {"center_offset_mm":-5},{"axial_thrust_n":float("nan")},
    {"thrust_source":"hidden_simulator"}
])
def test_invalid_wall_load_inputs_rejected(change):
    args=dict(mass_kg=2.,center_offset_mm=100.,
              anchor_spacing_x_mm=100.,anchor_spacing_y_mm=100.,
              axial_thrust_n=10.)
    args.update(change)
    with pytest.raises(ValueError):
        WallMountInputs(**args)


def test_kinematic_pressure_face_integration_returns_real_si_force_and_moment():
    # 4 m² flat wetted face with 5 m²/s² kinematic pressure at rho=1.2:
    # physical force magnitude is 24 N along negative face normal.
    force,moment=integrate_pressure_traction(
        np.asarray([[0.,0.,.2]]),np.asarray([[0.,0.,1.]]),
        np.asarray([4.]),np.asarray([5.]),air_density_kg_m3=1.2
    )
    assert force.tolist()==pytest.approx([0.,0.,-24.])
    assert moment.tolist()==pytest.approx([0.,0.,0.])
    with pytest.raises(ValueError,match="unit vectors"):
        integrate_pressure_traction(
            np.asarray([[0.,0.,.2]]),np.asarray([[0.,0.,1.1]]),
            np.asarray([4.]),np.asarray([5.]),air_density_kg_m3=1.2
        )


def test_derived_cfd_force_requires_actual_surface_not_discrete_scatter_samples():
    with pytest.raises(ValueError,match="invalid geometry"):
        integrate_pressure_traction(
            np.zeros((500,3)),np.zeros((500,3)),
            np.ones(499),np.ones(500),air_density_kg_m3=1.2
        )



def test_user_supplied_real_patch_csv_pressure_integrates_into_anchor_statics():
    from forceforge.wall_mount import parse_openfoam_pressure_patch_csv
    source=(
        "time_s,x_m,y_m,z_m,nx,ny,nz,area_m2,p_kinematic_m2_s2\n"
        "0.04,0.1,0,0.2,0,0,1,0.2,10\n"
    ).encode("utf-8")
    patch=parse_openfoam_pressure_patch_csv(
        source,air_density_kg_m3=1.2
    )
    assert patch.face_count==1
    assert patch.solver_time_s==pytest.approx(.04)
    assert patch.pressure_only
    assert len(patch.source_sha256)==64
    assert patch.force_xyz_n==pytest.approx((0.,0.,-2.4))
    assert patch.moment_xyz_nm==pytest.approx((0.,.24,0.))
    # The physical surface load, including the face-offset yaw moment,
    # must survive the pressure -> anchor force transfer intact.
    case=WallMountInputs(
        mass_kg=2,center_offset_mm=100.,
        anchor_spacing_x_mm=100.,anchor_spacing_y_mm=100.,
        axial_thrust_n=patch.force_xyz_n[2],
        aerodynamic_moment_y_nm=patch.moment_xyz_nm[1],
        thrust_source="uploaded_patch_csv_pressure_only",
    )
    result=analyze_wall_mount(case)
    assert result.force_balance_error_n<1e-10
    assert result.moment_balance_error_nm<1e-10


def test_pressure_patch_csv_requires_same_physical_solver_time_and_all_columns():
    from forceforge.wall_mount import parse_openfoam_pressure_patch_csv
    bad=(
        "time_s,x_m,y_m,z_m,nx,ny,nz,area_m2,p_kinematic_m2_s2\n"
        "0.04,0,0,0,0,0,1,0.2,10\n"
        "0.05,0,0,0,0,0,1,0.2,10\n"
    ).encode("utf-8")
    with pytest.raises(ValueError,match="SAME solver time"):
        parse_openfoam_pressure_patch_csv(bad,air_density_kg_m3=1.2)
    with pytest.raises(ValueError,match="missing mandatory"):
        parse_openfoam_pressure_patch_csv(b"x,y\n0,1\n",air_density_kg_m3=1.2)
