"""Truthful NL product catalog: actual OCC STEP geometry and physics gates."""
import math
from pathlib import Path
import tempfile

import pytest

from forceforge.engineering_schema import (
    HollowShaftGeometry,MountingPlateGeometry,interpret_text,preflight_missing,
)
from forceforge.engineering_pipeline import TaskState,plan_engineering,run_engineering
from forceforge.step_mesh import _validate_step


SHAFT_ZH="设计一个空心轴，外径60mm，内径30mm，长度120mm。"
PLATE_ZH="做一个矩形安装板，长度150mm，宽度100mm，厚度8mm，开4个孔，孔径6mm，孔中心距边缘15mm。"


def test_natural_language_hollow_shaft_dimensions_are_literal():
    parsed=interpret_text(SHAFT_ZH)
    assert parsed.request is not None, parsed.issues
    g=parsed.request.geometry
    assert isinstance(g,HollowShaftGeometry)
    assert (g.outer_diameter_mm,g.inner_diameter_mm,g.length_mm)==(60,30,120)
    assert not preflight_missing(parsed.request)
    assert parsed.request.family.value=="hollow_shaft"
    assert not parsed.request.concept_assumptions_confirmed


def test_plate_chinese_and_english_holes_are_not_invented():
    expected=[(150,100,8,4,6,15), (150,100,8,4,6,15)]
    samples=[
        PLATE_ZH,
        "Create mounting plate length 150 mm width 100 mm thickness 8 mm with 4 holes, hole diameter 6 mm hole edge offset 15 mm",
    ]
    for text,want in zip(samples,expected):
        parsed=interpret_text(text)
        assert parsed.request is not None, parsed.issues
        g=parsed.request.geometry
        assert isinstance(g,MountingPlateGeometry)
        assert (g.length_mm,g.width_mm,g.thickness_mm,g.hole_count,
                g.hole_diameter_mm,g.hole_edge_margin_mm)==want
        assert not preflight_missing(parsed.request)


def test_new_product_missing_parameters_block_cad_and_real_physics():
    shaft=interpret_text("Create a hollow shaft outer diameter 60 mm and calculate stress")
    assert shaft.request is not None
    assert preflight_missing(shaft.request)==("inner_diameter_mm","length_mm")
    tasks=plan_engineering(shaft.request)
    assert tasks.task("generate_cad").status==TaskState.BLOCKED
    assert tasks.task("structural_fea").status==TaskState.BLOCKED
    plate=interpret_text("Make a mounting plate length 150 mm width 100 mm thickness 8 mm with 4 holes")
    assert plate.request is not None
    assert preflight_missing(plate.request)==("hole_diameter_mm","hole_edge_margin_mm")
    with pytest.raises(ValueError,match="blocked"):
        run_engineering(plate.request)


def test_invalid_holes_or_nonregistered_products_cannot_change_geometry():
    unsupported=interpret_text(
        "Make a mounting plate length 150 mm width 100 mm thickness 8 mm with 2 holes"
    )
    assert unsupported.request is None
    assert "4-hole" in unsupported.issues[0]
    shaft=interpret_text("Make a hollow shaft outer diameter 30 mm inner diameter 29 mm length 60 mm")
    assert shaft.request is None
    assert "Hollow shaft" in shaft.issues[0]
    unknown=interpret_text("请设计变速箱齿轮并且自动进行CFD计算")
    assert unknown.request is None


def test_unparameterized_parametric_fea_and_cfd_remain_blocked():
    text=SHAFT_ZH+"分析应力、流场和散热。"
    req=interpret_text(text).request
    assert req is not None
    plan=plan_engineering(req)
    assert plan.task("generate_cad").status==TaskState.READY
    assert plan.task("solid_mesh").status==TaskState.READY
    assert plan.task("structural_fea").status==TaskState.BLOCKED
    assert plan.task("fluid_cfd").status==TaskState.BLOCKED
    assert plan.task("thermal").status==TaskState.BLOCKED


@pytest.mark.parametrize("prompt,expect_volume",[
    (SHAFT_ZH,math.pi/4*(60**2-30**2)*120),
    (PLATE_ZH,150*100*8-4*math.pi*(6/2)**2*8),
])
def test_real_open_cascade_step_reimports_and_matches_true_volume(
    prompt,expect_volume
):
    gmsh=pytest.importorskip("gmsh")
    from forceforge.step_mesh import _gmsh_session
    req=interpret_text(prompt).request
    assert req is not None
    result=run_engineering(req)
    assert result.cad.solid_parts==1
    assert len(result.cad.step_bytes)>1000
    assert result.cad.concept_only
    assert result.structural_fea is None
    assert result.evidence()["fluid_cfd"] is None
    assert result.evidence()["thermal"] is None
    assert len(result.cad.sha256)==64
    _validate_step(result.cad.step_bytes)
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"reimport.step"
        path.write_bytes(result.cad.step_bytes)
        with _gmsh_session(gmsh):
            gmsh.option.setNumber("General.Terminal",0)
            gmsh.model.add("Independently imported NL parametric product")
            gmsh.model.occ.importShapes(str(path))
            gmsh.model.occ.synchronize()
            solids=gmsh.model.getEntities(3)
            assert len(solids)==1
            volume=gmsh.model.occ.getMass(*solids[0])
            assert volume==pytest.approx(expect_volume,rel=.002)



@pytest.mark.parametrize("prompt",[
    SHAFT_ZH+"请分析结构应力。",
    "做一个矩形安装板，长度80mm，宽度60mm，厚度12mm，分析受力和应力。"
])
def test_explicitly_approved_material_support_and_traction_unlock_real_fea(prompt):
    from forceforge.engineering_schema import approve_demo_assumptions
    parsed=interpret_text(prompt)
    assert parsed.request is not None, parsed.issues
    original=parsed.request
    before=plan_engineering(original)
    assert before.task("structural_fea").status==TaskState.BLOCKED
    assert before.task("solid_mesh").status==TaskState.READY
    approved=approve_demo_assumptions(original)
    assert original.material.E_gpa is None
    assert approved.material.E_gpa==70.
    assert approved.loads.force_n==200.
    after=plan_engineering(approved)
    assert after.task("structural_fea").status==TaskState.READY
    assert after.task("fluid_cfd").status==TaskState.NOT_REQUESTED
    assert approved.assumptions
    assert any("fixed minimum-Z" in x for x in approved.assumptions)


@pytest.mark.parametrize("prompt",[
    "做一个空心轴，外径30mm，内径10mm，长度60mm，分析结构应力。",
    "做一个矩形安装板，长度60mm，宽度50mm，厚度12mm，分析结构受力。",
])
def test_real_parametric_step_to_independent_tetra10_fea(prompt):
    pytest.importorskip("gmsh")
    from forceforge.engineering_schema import approve_demo_assumptions
    request=approve_demo_assumptions(interpret_text(prompt).request)
    result=run_engineering(request)
    assert result.cad.solid_parts==1
    assert result.structural_fea is not None
    fea=result.structural_fea
    assert fea.mesh.source_sha256==result.cad.sha256
    assert fea.mesh.num_tets>30
    assert fea.relative_reaction_residual<1e-5
    assert fea.peak_von_mises_mpa>0
    assert fea.mass_kg>0
    assert fea.tip_mm>0
    assert result.evidence()["structural_fea"]["solver"].startswith("existing")
    assert result.evidence()["fluid_cfd"] is None
    assert result.plan.task("structural_fea").status==TaskState.READY



def test_real_four_hole_plate_tetra10_fea_and_typed_boundary_assumptions():
    """Real four-hole geometry is more demanding than a rectangular block.

    If the mesh cap or independent solver rejects the geometry, the job
    must fail loudly rather than present plausible but fabricated stress.
    """
    pytest.importorskip("gmsh")
    from forceforge.engineering_schema import approve_demo_assumptions
    spec=interpret_text(
        "做一个矩形安装板，长度60mm，宽度50mm，厚度12mm，"
        "开4个孔，孔径4mm，孔中心距边缘12mm，分析应力"
    ).request
    assert spec is not None
    assert spec.geometry.hole_count==4
    assert spec.geometry.hole_diameter_mm==4
    assert spec.geometry.hole_edge_margin_mm==12
    ready=approve_demo_assumptions(spec)
    ready.mesh_size_mm=15.
    assert plan_engineering(ready).task("structural_fea").status==TaskState.READY
    out=run_engineering(ready)
    assert out.structural_fea is not None
    assert out.cad.solid_parts==1
    assert out.structural_fea.mesh.source_sha256==out.cad.sha256
    assert out.structural_fea.relative_reaction_residual<1e-5
    assert out.structural_fea.peak_von_mises_mpa>0
