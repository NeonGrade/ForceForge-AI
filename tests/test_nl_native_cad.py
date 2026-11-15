"""Native geometry smoke: real ISO-10303-21 STEP and connected structural FEA."""
import pytest

pytest.importorskip("gmsh")

from forceforge.engineering_schema import (
    approve_demo_assumptions, interpret_text,
)
from forceforge.engineering_pipeline import run_engineering, TaskState
from forceforge.step_mesh import _validate_step, _require_gmsh, _gmsh_session
from forceforge.product_cad import generate_product
from pathlib import Path
import tempfile


def test_wall_fan_real_multibody_step_is_not_a_fake_cfd_result():
    req=approve_demo_assumptions(
        interpret_text(
            "做一个直径30厘米，转速1500 RPM的壁挂风扇，"
            "分析风速气流和墙壁受力"
        ).request
    )
    output=run_engineering(req)
    _validate_step(output.cad.step_bytes)
    assert output.cad.concept_only
    assert output.cad.solid_parts>=2
    assert len(output.cad.step_bytes)>1000
    assert output.evidence()["fluid_cfd"] is None
    assert output.evidence()["structural_fea"] is None
    assert any(x.status==TaskState.AVAILABLE_EXTERNAL and x.name=="fluid_cfd"
               for x in output.stage_results)
    # Confirm OpenCASCADE independently imports true STEP volumes
    gmsh=_require_gmsh()
    with tempfile.TemporaryDirectory() as d:
        source=Path(d)/"actual_fan.step"
        source.write_bytes(output.cad.step_bytes)
        with _gmsh_session(gmsh):
            gmsh.option.setNumber("General.Terminal",0)
            gmsh.model.add("test actual exported fan geometry")
            gmsh.model.occ.importShapes(str(source))
            gmsh.model.occ.synchronize()
            assert len(gmsh.model.getEntities(3))>=2


def test_native_bracket_natural_language_reuses_existing_real_tetra10_solver():
    req=approve_demo_assumptions(
        interpret_text(
            "做腹板厚度8毫米的L型支架，施加载荷250 N，计算应力和变形。"
        ).request
    )
    output=run_engineering(req)
    _validate_step(output.cad.step_bytes)
    assert not output.cad.concept_only
    assert output.structural_fea is not None
    fea=output.structural_fea
    assert fea.mesh.num_tets>100
    assert fea.mesh.num_tets<=1400
    assert fea.relative_reaction_residual<1e-5
    assert output.cad.sha256==fea.mesh.source_sha256
    assert 0<fea.tip_mm<1.
    assert 0<fea.peak_von_mises_mpa<500.
