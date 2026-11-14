"""Regression: true imported tetra geometry must reproduce existing verified solver.

No external CAD download or Gmsh dependency is needed for these tests.
The separate CAD-integration workflow checks Gmsh STEP import.
"""
from dataclasses import replace
from hashlib import sha256
import numpy as np
import pytest
from forceforge.solid3d import SolidCase, solve_solid, _solid_nodes_and_tets
from forceforge.step_mesh import CadMesh, _validate_step, mesh_step_bytes
from forceforge.cad_solid import CadLoad, solve_cad_mesh


def box_mesh(c):
    points,tet4=_solid_nodes_and_tets(c)
    volume=c.length_m*c.width_m*c.thickness_m
    return CadMesh(points,tet4,'test_sha','Numerical verification box',
                   4.,volume,volume,
                   np.vstack((points.min(axis=0),points.max(axis=0))),
                   0.,1.)


def test_cad_solver_reproduces_existing_verified_tetra10_benchmark():
    c=SolidCase(nx=2,ny=2,nz=8,force_n=100)
    original=solve_solid(c)
    loaded=CadLoad(force_n=100,force_axis=1,force_sign=-1,
                   boundary_axis=2,E_pa=c.E_pa,nu=c.nu,
                   density=c.density,yield_pa=c.yield_pa)
    imported=solve_cad_mesh(box_mesh(c),loaded)
    assert imported.tip_mm==pytest.approx(original.tip_displacement_mm,rel=1e-8)
    assert imported.peak_von_mises_mpa==pytest.approx(original.max_mises_mpa,rel=1e-8)
    assert imported.relative_reaction_residual<1e-7
    assert imported.mass_kg==pytest.approx(original.mass_kg,rel=1e-8)
    assert len(imported.tets10)==len(original.tets10)


def test_cad_solver_scales_stresses_and_displacement_linearly():
    case=SolidCase(nx=1,ny=1,nz=6)
    geometry=box_mesh(case)
    a=solve_cad_mesh(geometry,CadLoad(force_n=120,force_axis=1,force_sign=-1))
    b=solve_cad_mesh(geometry,CadLoad(force_n=240,force_axis=1,force_sign=-1))
    assert b.tip_mm==pytest.approx(2*a.tip_mm,rel=1e-8)
    assert b.peak_von_mises_mpa==pytest.approx(2*a.peak_von_mises_mpa,rel=1e-8)
    assert b.relative_reaction_residual<1e-7


def test_reject_invalid_boundary_and_material():
    with pytest.raises(ValueError):
        CadLoad(force_axis=2,boundary_axis=2)
    with pytest.raises(ValueError):
        CadLoad(nu=.50)
    with pytest.raises(ValueError):
        CadLoad(E_pa=-1)


def test_reject_wrong_source_and_units_before_optional_import():
    with pytest.raises(ValueError,match="STEP"):
        _validate_step(b'bad')
    with pytest.raises(ValueError,match="STEP"):
        mesh_step_bytes(b'not a STEP',unit='mm')
    valid=b'ISO-10303-21;'+b' '*300
    with pytest.raises(ValueError,match='Units'):
        mesh_step_bytes(valid,unit='inch')


def test_gmsh_import_error_preserves_actual_missing_module(monkeypatch):
    """ImportError may be native library load failure, not absent package."""
    import builtins
    from forceforge.step_mesh import _require_gmsh
    original=builtins.__import__

    def failed_import(name, *args, **kwargs):
        if name == "gmsh":
            raise ImportError("dlopen: Library not loaded: libgmsh.dylib")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failed_import)
    with pytest.raises(RuntimeError, match="libgmsh.dylib"):
        _require_gmsh()


def test_gmsh_not_installed_message_identifies_running_interpreter(monkeypatch):
    import builtins
    import sys
    from forceforge.step_mesh import _require_gmsh
    original=builtins.__import__

    def failed_import(name, *args, **kwargs):
        if name == "gmsh":
            raise ModuleNotFoundError("No module named 'gmsh'", name="gmsh")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failed_import)
    with pytest.raises(RuntimeError, match="not installed") as error:
        _require_gmsh()
    assert sys.executable in str(error.value)
