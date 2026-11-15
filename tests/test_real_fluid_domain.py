"""Real Gmsh 3D fluid-domain mesh roundtrip for a natural-language fan.

This test is *not* a CFD velocity/pressure validation. It independently
imports the real Gmsh MSH v2.2 to verify 3D tetrahedra, physical surfaces
and two conforming air cell zones, plus source CAD provenance.
"""
from pathlib import Path
import tempfile

import pytest

pytest.importorskip("gmsh")

from forceforge.engineering_schema import approve_demo_assumptions, interpret_text
from forceforge.engineering_pipeline import (
    TaskState, mesh_registered_fluid_domain, run_engineering,
)
from forceforge.step_mesh import _require_gmsh, _gmsh_session


def test_real_fan_step_to_tagged_air_tetrahedra_not_fake_flow():
    req=approve_demo_assumptions(interpret_text(
        "做一个直径30厘米、转速1500 RPM的壁挂风扇，"
        "希望分析空气流场和墙体支架受力"
    ).request)
    original=run_engineering(req)
    assert original.cad.solid_parts>=2
    assert original.fluid_domain is None
    assert original.plan.task("fluid_mesh").status==TaskState.READY
    result=mesh_registered_fluid_domain(req,original)
    assert result is original
    air=result.fluid_domain
    assert air is not None
    assert air.cad_source_sha256==original.cad.sha256
    assert air.tetrahedra>100
    assert air.tetrahedra<=90000
    assert air.nodes>50
    assert 0<=air.relative_volume_error<.08
    assert air.volumes_mm3["rotor_source_zone"]>0
    assert air.volumes_mm3["ambient_air_zone"]>air.volumes_mm3["rotor_source_zone"]
    assert air.preview_faces is not None
    assert len(air.preview_faces)>0
    assert air.mesh_bytes.startswith(b"$MeshFormat")
    assert b"rotor_source_zone" in air.mesh_bytes
    assert b"rotor_interface" in air.mesh_bytes
    assert b"upstream_open" in air.mesh_bytes
    assert b"downstream_open" in air.mesh_bytes
    assert b"lateral_farfield" in air.mesh_bytes
    assert air.as_dict()["solver_status"]=="NOT_RUN_NO_CFD_VELOCITIES_OR_PRESSURES"
    assert result.evidence()["fluid_cfd"] is None
    assert result.evidence()["structural_fea"] is None
    assert any(t.name=="fluid_mesh" and t.status==TaskState.COMPLETED
               for t in result.stage_results)
    assert any(t.name=="fluid_cfd" and t.status==TaskState.BLOCKED
               for t in result.stage_results)

    # Open the exported mesh in an independent Gmsh model, rather than
    # trusting the original worker's internal tagging metadata alone.
    gmsh=_require_gmsh()
    with tempfile.TemporaryDirectory(prefix="ff_air_verify_") as temp:
        path=Path(temp)/"real_air.msh"
        path.write_bytes(air.mesh_bytes)
        with _gmsh_session(gmsh):
            gmsh.option.setNumber("General.Terminal",0)
            gmsh.open(str(path))
            actual={
                gmsh.model.getPhysicalName(dim,tag):dim
                for dim,tag in gmsh.model.getPhysicalGroups()
            }
            for name in ("upstream_open","downstream_open",
                         "lateral_farfield","rotor_interface"):
                assert actual[name]==2
            assert actual["rotor_source_zone"]==3
            assert actual["ambient_air_zone"]==3
            types,tags,_=gmsh.model.mesh.getElements(3)
            independently_count=sum(
                len(ids) for t,ids in zip(types,tags) if int(t)==4
            )
            assert independently_count==air.tetrahedra
