import numpy as np
import pytest
from modal_benchmark import (
    LENGTH_M, MEASURED_HZ, PUBLISHED_FE_HZ, SENSOR_HEIGHTS_M,
    build_matrices, solve_modes, solve_static, fit_base_stiffness,
    frequency_comparison,holdout_mape,section_properties,prism_surface,read_abaqus_inp)


def test_real_source_measurement_constants_have_correct_provenance():
    assert LENGTH_M == pytest.approx(1.524)
    assert MEASURED_HZ.tolist() == [1.569, 10.389, 29.619]
    assert PUBLISHED_FE_HZ.tolist() == [1.698, 10.775, 30.59]
    assert SENSOR_HEIGHTS_M['MP1'] == pytest.approx(1.462)


def test_mass_and_matrix_properties():
    z,K,M,free,mass=build_matrices()
    assert K.shape==(66,66)
    assert M.shape==(66,66)
    assert np.allclose(K,K.T,rtol=1e-12,atol=1e-6)
    assert np.allclose(M,M.T,rtol=1e-12,atol=1e-6)
    assert 1.5<mass<2.2
    assert 0 not in free
    assert 1 in free


def test_frequency_spectrum_positive_monotonic_and_base_stiffness_sensitivity():
    soft=solve_modes(base_stiffness_nm_rad=100.)
    stiff=solve_modes(base_stiffness_nm_rad=1000.)
    assert np.all(np.diff(stiff.frequencies_hz)>0)
    assert np.all(stiff.frequencies_hz>soft.frequencies_hz)


def test_clamped_cantilever_matches_analytical_eb_frequency():
    E,rho,L,b,h=210e9,7850.,1.524,.03,.0052
    I=b*h**3/12; A=b*h
    beta=1.875104068711961
    theoretical=beta**2/(2*np.pi*L**2)*np.sqrt(E*I/(rho*A))
    calculated=solve_modes(base_stiffness_nm_rad=None,reduce_gauges=False,n_elements=32)
    assert calculated.frequencies_hz[0] == pytest.approx(theoretical,rel=1e-6)


def test_fit_first_measured_frequency_then_hold_out_2_and_3():
    stiffness,result=fit_base_stiffness()
    assert 200<stiffness<1000
    assert result.frequencies_hz[0] == pytest.approx(MEASURED_HZ[0],rel=1e-4)
    assert holdout_mape(result)<2.0
    rows=frequency_comparison(result.frequencies_hz)
    assert len(rows)==3
    assert rows[0]['Measured (Hz)']==1.569


def test_static_work_conjugacy_and_linear_load_scaling():
    z,a,rot,reactions,m=solve_static(tip_force_n=.2,base_stiffness_nm_rad=450)
    _,b,_,_,_=solve_static(tip_force_n=.4,base_stiffness_nm_rad=450)
    assert a[-1]>0
    assert b[-1]==pytest.approx(2*a[-1],rel=1e-12)
    assert reactions[0]==pytest.approx(-.2,abs=1e-6)


def test_section_gauge_reductions():
    A0,I0=section_properties(0.1)
    A1,I1=section_properties(SENSOR_HEIGHTS_M['MP4'])
    assert A1<A0 and I1<I0


def test_prism_closed_shape():
    z=np.linspace(0,LENGTH_M,20)
    v,f,intensity=prism_surface(z,np.zeros_like(z))
    assert v.shape == (80,3)
    assert len(f)==4*(19)*2+4
    assert np.isfinite(v).all()


def test_abaqus_inp_reader_preserves_actual_node_coordinates():
    inp='''*Heading
** Comment
*Node
1, 0, 0, 0
2, 0, 0, 1.524
*Element, type=B31
1, 1, 2
*Boundary
1, 1, 6
'''
    out=read_abaqus_inp(inp)
    assert out['node_count']==2
    assert out['element_count']==1
    assert out['types']==['B31']
    assert out['nodes'][2][2] == pytest.approx(1.524)
