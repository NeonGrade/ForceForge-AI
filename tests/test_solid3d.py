"""3D SOLID FEA verification: patch strain, force balance and mesh convergence."""
from dataclasses import replace
import numpy as np
import pytest

from forceforge.solid3d import (
    SolidCase, solve_solid, surface_figure, _solid_nodes_and_tets,
    _quadratic_connectivity, _B, _D,
)


def test_tet10_affine_strain_patch_recovers_exact_3d_strain():
    case=SolidCase(nx=1,ny=1,nz=4)
    corners,tet4=_solid_nodes_and_tets(case)
    points,ten,_=_quadratic_connectivity(corners,tet4)
    nodes=points[ten[0]]
    strain=.0012
    displacement=np.zeros((10,3))
    displacement[:,2]=strain*nodes[:,2]
    B,volume=_B(nodes[:4],np.array([.25]*4))
    eps=B@displacement.ravel()
    assert np.allclose(eps,[0,0,strain,0,0,0],atol=1e-12)
    sigma=_D(case.E_pa,case.nu)@eps
    assert sigma[2]>sigma[0]>0
    assert volume>0


def test_true_solid_fem_force_balance_and_positive_tetra_volumes():
    case=SolidCase(force_n=100,nx=2,ny=2,nz=8)
    r=solve_solid(case)
    assert r.relative_reaction_residual<1e-7
    assert r.support_reaction_n[1]==pytest.approx(100,rel=1e-8)
    assert r.tip_displacement_m<0
    assert len(r.von_mises_pa)==len(r.tets10)>0
    assert np.all(r.element_volumes_m3>0)
    assert r.mass_kg==pytest.approx(case.density*case.length_m*case.width_m*case.thickness_m)
    assert r.max_mises_mpa>0


def test_3d_quadratic_tetra_mesh_converges_towards_beam_bending_reference():
    coarse=solve_solid(SolidCase(nx=1,ny=1,nz=4))
    fine=solve_solid(SolidCase(nx=2,ny=2,nz=12))
    reference=fine.beam_reference_tip_mm
    err_coarse=abs(coarse.tip_displacement_mm-reference)/reference
    err_fine=abs(fine.tip_displacement_mm-reference)/reference
    assert err_fine<err_coarse
    assert err_fine<.04


def test_linear_elastic_3d_force_scaling():
    a=solve_solid(SolidCase(force_n=100,nx=1,ny=1,nz=6))
    b=solve_solid(SolidCase(force_n=200,nx=1,ny=1,nz=6))
    assert b.tip_displacement_mm==pytest.approx(2*a.tip_displacement_mm,rel=1e-8)
    assert b.max_mises_mpa==pytest.approx(2*a.max_mises_mpa,rel=1e-8)
    assert a.mass_kg==pytest.approx(b.mass_kg)


def test_true_volume_element_stress_visualization():
    r=solve_solid(SolidCase(nx=1,ny=1,nz=4))
    fig=surface_figure(r,deformation_scale=50)
    assert len(fig.data)==1
    assert len(fig.data[0].intensity)==3*len(r.surface_faces)
    assert float(max(fig.data[0].intensity))<=r.max_mises_mpa+1e-8
    assert "3D tetra10 SOLID FEA" in fig.layout.title.text
    with pytest.raises(ValueError):
        surface_figure(r,stress_cmax_mpa=r.max_mises_mpa/2)


def test_invalid_mesh_material_and_poisson_rejected():
    with pytest.raises(ValueError):
        SolidCase(E_pa=-1)
    with pytest.raises(ValueError):
        SolidCase(nu=.50)
    with pytest.raises(ValueError):
        SolidCase(nx=-1)
