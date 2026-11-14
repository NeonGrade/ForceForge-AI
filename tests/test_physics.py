import numpy as np
import pytest
from forceforge.design import make_truss, TOPOLOGIES
from forceforge.physics import solve


def test_triangle_analytic_reference():
    # Three-bar triangular truss, pin left / vertical roller right.
    # span=2 m, height=1 m, P=1000 N, E=200 GPa, A=100 mm^2.
    # Diagonals: -P*sqrt(2)/2 N, bottom chord: +P/2 N.
    truss = make_truss("Triangle", 2.0, 1.0, 100.0, 1000.0)
    r = solve(truss)
    expected = -(1000 * (2 * np.sqrt(2) + 1)) / (2 * 200e9 * 100e-6)
    assert r.disp_m[2, 1] == pytest.approx(expected, rel=1e-10)
    assert r.force_n[0] == pytest.approx(500.0, rel=1e-10)
    assert r.force_n[1] == pytest.approx(-1000 / np.sqrt(2), rel=1e-10)
    assert r.force_n[2] == pytest.approx(-1000 / np.sqrt(2), rel=1e-10)
    assert r.reactions_n[0, 1] == pytest.approx(500.0, rel=1e-10)
    assert r.reactions_n[1, 1] == pytest.approx(500.0, rel=1e-10)
    assert abs(r.reactions_n[0, 0]) < 1e-6
    assert np.linalg.norm(r.reactions_n.sum(axis=0) + truss.forces_n.sum(axis=0)) < 1e-6


@pytest.mark.parametrize("topology", TOPOLOGIES)
def test_all_supported_trusses_stable_and_in_equilibrium(topology):
    truss = make_truss(topology)
    r = solve(truss)
    assert np.isfinite(r.disp_m).all()
    assert r.mass_kg > 0
    assert np.linalg.norm(r.reactions_n.sum(axis=0) + truss.forces_n.sum(axis=0)) < 1e-5


def test_linear_load_scaling():
    t = make_truss("Triangle")
    a = solve(t)
    b = solve(t, load_factor=1.2)
    assert b.disp_m[2,1] / a.disp_m[2,1] == pytest.approx(1.2)
