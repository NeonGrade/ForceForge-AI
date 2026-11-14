"""Real STEP OCC meshing integration tests, executed only when gmsh is available."""
from pathlib import Path
import tempfile
import numpy as np
import pytest

gmsh=pytest.importorskip("gmsh")
from forceforge.step_mesh import generated_bracket_step, mesh_step_bytes
from forceforge.cad_solid import CadLoad,solve_cad_mesh


def test_gmsh_generated_box_step_round_trip_and_real_volume_solve():
    with tempfile.TemporaryDirectory() as d:
        f=Path(d)/'box.step'
        gmsh.initialize()
        try:
            gmsh.option.setNumber('General.Terminal',0)
            gmsh.model.add('Verification STEP box')
            gmsh.model.occ.addBox(0,0,0,30,12,80)
            gmsh.model.occ.synchronize()
            gmsh.write(str(f))
        finally:
            gmsh.finalize()
        blob=f.read_bytes()
    mesh=mesh_step_bytes(blob,source_label='Test STEP box',mesh_size_mm=16,max_tets=5000)
    assert mesh.num_tets>20
    assert mesh.relative_volume_difference<.06
    assert np.allclose((mesh.bbox_m[1]-mesh.bbox_m[0])*1000,[30,12,80],atol=.1)
    r=solve_cad_mesh(mesh,CadLoad(force_n=60,force_axis=1,force_sign=-1))
    assert r.relative_reaction_residual<1e-7
    assert r.tip_mm>0
    assert r.peak_von_mises_mpa>0


def test_parametric_bracket_export_changes_real_cad_volume():
    a=generated_bracket_step(web_mm=8.)
    b=generated_bracket_step(web_mm=12.)
    assert a!=b
    first=mesh_step_bytes(a,source_label='Editable CAD web8',mesh_size_mm=12,max_tets=5000)
    second=mesh_step_bytes(b,source_label='Editable CAD web12',mesh_size_mm=12,max_tets=5000)
    assert second.cad_volume_m3>first.cad_volume_m3
    assert second.source_sha256!=first.source_sha256
    assert first.relative_volume_difference<.20
    assert second.relative_volume_difference<.20
