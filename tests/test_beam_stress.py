import numpy as np
import pytest
from forceforge.beam_stress import StaticCase, LENGTH_M, WIDTH_M, solve_static, displacement_at, redesign, axial_stress_at


def test_uniform_3d_surface_bending_matches_cantilever_analytical():
    # Disable the thickness step by selecting a case? The published gauge regions
    # remain in actual geometry, so compare with a high-res numerical quadrature
    # using the exact moment-curvature expression for the piecewise section.
    case=StaticCase(force_n=.1,n_nominal_elements=130)
    ans=solve_static(case)
    z=np.linspace(0,LENGTH_M,100001)
    from forceforge.beam_stress import thickness_at
    t=thickness_at(z)
    EI=case.e_pa*WIDTH_M*t**3/12
    expected=np.trapezoid(case.force_n*(LENGTH_M-z)**2/EI,z)*1000
    assert ans.tip_mm == pytest.approx(expected,rel=2e-4)
    assert ans.support_reaction_n==pytest.approx(-case.force_n,abs=1e-6)
    assert ans.support_reaction_nm==pytest.approx(-case.force_n*LENGTH_M,abs=1e-6)
    assert ans.relative_equilibrium_residual<1e-5


def test_thickness_increase_reduces_stress_and_deflection():
    a=solve_static(StaticCase(force_n=.12,thickness_ratio=1.))
    b=solve_static(StaticCase(force_n=.12,thickness_ratio=1.2))
    assert b.mass_kg==pytest.approx(a.mass_kg*1.2)
    assert b.tip_mm==pytest.approx(a.tip_mm/(1.2**3),rel=1e-4)
    assert b.stress_max_mpa==pytest.approx(a.stress_max_mpa/(1.2**2),rel=1e-5)


def test_tip_load_scales_response():
    a=solve_static(StaticCase(force_n=.10))
    b=solve_static(StaticCase(force_n=.16))
    assert b.tip_mm/a.tip_mm==pytest.approx(1.6,rel=1e-9)
    assert b.stress_max_mpa/a.stress_max_mpa==pytest.approx(1.6)
    assert displacement_at(b,LENGTH_M)*1000==pytest.approx(b.tip_mm)


def test_stress_antisymmetric_and_zero_at_neutral_axis():
    r=solve_static(StaticCase(force_n=.1))
    zz=np.array([.20,.50,1.2]);x=np.array([.002,.002,.002])
    a=axial_stress_at(r,zz,x)
    b=axial_stress_at(r,zz,-x)
    assert np.allclose(a,-b)
    assert np.allclose(axial_stress_at(r,zz,0*x),0)


def test_design_reopt_is_rechecked_by_solvers():
    c=StaticCase(force_n=.18,displacement_limit_mm=2.0)
    original=solve_static(c)
    opt,all_results=redesign(c)
    assert opt is not None
    assert opt.governing_utilization<=1.0
    assert opt.mass_kg>0
    assert all(x.governing_utilization<=1.0 for x in all_results if x.mass_kg>=opt.mass_kg and x.case.thickness_ratio>=opt.case.thickness_ratio)
    assert original.governing_utilization>1.0


def test_surface_actual_fe_stress_and_color_range():
    r=solve_static(StaticCase(force_n=.08))
    from forceforge.beam_stress import plotly_surface
    fig=plotly_surface(r)
    assert len(fig.data)==2
    assert len(fig.data[1].intensity)>100
    assert max(fig.data[1].intensity)==pytest.approx(r.stress_max_mpa,rel=.03)
