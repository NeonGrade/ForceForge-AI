"""Independent checks of tetrahedral strain/stiffness and a basic load case."""
import numpy as np
from forceforge.solid3d import Mesh, _tet_B, _elasticity, solve, boundary_triangles


def test_constant_strain_patch():
    xyz = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    B, volume = _tet_B(xyz)
    assert np.isclose(volume, 1/6)
    # u_x = 0.01*x, u_y = 0.02*y, u_z = -0.005*z
    u = np.column_stack((.01*xyz[:,0], .02*xyz[:,1], -.005*xyz[:,2])).ravel()
    strain = B@u
    assert np.allclose(strain, [.01,.02,-.005,0,0,0])
    D = _elasticity(200e9,.3)
    assert np.all(np.linalg.eigvalsh(D)>0)


def test_exterior_faces_single_tet():
    assert len(boundary_triangles(np.array([[0,1,2,3]]))) == 4


def test_solver_equilibrium():
    # A tetrahedron with x=0 support triangle, x=1 loaded corner.
    mesh = Mesh(np.array([[0.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]]),
                np.array([[0,1,2,3]]))
    out = solve(mesh, E=1e7, force_n=10)
    assert np.isfinite(out.von_mises_tet).all()
    assert np.isclose(out.force_sum[0], 10.)
    assert np.allclose(out.force_sum+out.reaction_sum, 0., atol=1e-7)
    assert out.max_displacement>0


def test_invalid_material():
    mesh=Mesh(np.array([[0.,0.,0.],[0.,1.,0.],[0.,0.,1.],[1.,0.,0.]]),
              np.array([[0,1,2,3]]))
    try:
        solve(mesh, E=1e7, poisson=.5)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid material rejection")
