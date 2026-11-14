import numpy as np
import pytest
from forceforge.advanced_frame import FrameMember, FrameModel,FrameMaterial,solve_frame,circular_section,cantilever_demo
from forceforge.fatigue import SNModel, StressBlock,miner_damage


def test_cantilever_tip_deflection_and_rotation_vs_euler_bernoulli():
    P,L,E=1000.,2.,200e9
    m=cantilever_demo(length_m=L,tip_force_n=P)
    result=solve_frame(m)
    I=m.members[0].inertia_m4
    assert result.u[1,1] == pytest.approx(-P*L**3/(3*E*I), rel=1e-9)
    assert result.u[1,2] == pytest.approx(-P*L**2/(2*E*I), rel=1e-9)
    assert result.reactions[0,1] == pytest.approx(P,rel=1e-9)
    assert result.reactions[0,2] == pytest.approx(P*L,rel=1e-9)
    assert abs(result.member_axial_forces_n[0]) < 1e-5


def test_rotational_compliance_at_base_matches_closed_form():
    P,L,E=1200.,1.5,200e9
    k=25000.
    m=cantilever_demo(length_m=L,tip_force_n=P,rotational_spring_nm_rad=k)
    r=solve_frame(m)
    I=m.members[0].inertia_m4
    expected=-P*(L**3/(3*E*I)+L**2/k)
    assert r.u[1,1] == pytest.approx(expected,rel=1e-9)
    assert abs(r.u[0,2])>1e-8


def test_free_thermal_expansion_and_zero_axial_reaction():
    L,dT=2.5,65.
    m=cantilever_demo(length_m=L,tip_force_n=0.,temp_rise_k=dT)
    r=solve_frame(m)
    assert r.u[1,0] == pytest.approx(m.material.alpha_per_k*dT*L,rel=1e-10)
    assert abs(r.reactions[0,0])<1e-6


def test_thermal_stress_when_axially_restrained():
    m=cantilever_demo(length_m=2.,tip_force_n=0.,temp_rise_k=50.)
    m.supports.append((1,True,False,False))
    r=solve_frame(m)
    assert r.member_axial_forces_n[0] == pytest.approx(-m.material.E_pa*m.material.alpha_per_k*50*m.members[0].area_m2)
    assert r.u[1,0] == pytest.approx(0.)


def test_second_order_pdelta_increases_lateral_displacement_under_compression():
    # Vertical cantilever with compressive tip load P and transverse lateral force.
    E=200e9; A,I=circular_section(.035)
    f=FrameModel(
        nodes_m=np.array([[0.,0.],[0.,1.8]]),
        members=[FrameMember(0,1,A,I)],
        nodal_forces=np.array([[0.,0.,0.],[500.,-25000.,0.]]),
        supports=[(0,True,True,True)],
        material=FrameMaterial(E_pa=E))
    linear=solve_frame(f)
    nonlinear=solve_frame(f,second_order=True)
    assert nonlinear.converged
    assert abs(nonlinear.u[1,0])>abs(linear.u[1,0])
    assert nonlinear.iterations>=2


def test_zero_rotation_support_makes_single_cantilever_a_mechanism():
    m=cantilever_demo(rotational_spring_nm_rad=0.)
    with pytest.raises(ValueError, match='near-singular'):
        solve_frame(m)


def test_miner_damage_reference_sn_and_goodman_mean():
    sn=SNModel(reference_amplitude_pa=100e6, reference_cycles=1e6,
               slope_m=3, ultimate_strength_pa=400e6)
    r=miner_damage(sn,[StressBlock(50e6,0.,1e6)])
    assert r['miner_damage']==pytest.approx(.125)
    assert r['repetitions_until_unit_damage']==pytest.approx(8.)
    mean=miner_damage(sn,[StressBlock(50e6,100e6,1e6)])
    assert mean['miner_damage']==pytest.approx(1/3.375)
    assert mean['miner_damage']>r['miner_damage']


def test_bad_material_or_spectrum_rejected():
    with pytest.raises(ValueError):
        SNModel(0,1e6,3,400e6)
    with pytest.raises(ValueError):
        miner_damage(SNModel(100e6,1e6,3,400e6),[StressBlock(-20e6,0,1e5)])
