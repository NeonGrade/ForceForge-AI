"""Planner DAG and no-fake-physics execution checks without Gmsh required."""
from hashlib import sha256
from types import SimpleNamespace

import pytest

from forceforge.engineering_schema import (
    EngineeringRequest, approve_demo_assumptions, interpret_text,
)
from forceforge.engineering_pipeline import (
    TaskState, plan_engineering, run_engineering,
)
from forceforge.product_cad import CADProduct
import forceforge.engineering_pipeline as pipeline


FAN_TEXT="帮我设计一个直径30厘米、转速1500 RPM的挂壁风扇，观察流场和墙壁受力"
BRACKET_TEXT="设计腹板厚度8mm的L型支架，施加载荷250 N，检查应力和位移"


def _fan():
    return approve_demo_assumptions(interpret_text(FAN_TEXT).request)


def _bracket():
    return approve_demo_assumptions(interpret_text(BRACKET_TEXT).request)


def test_fan_plan_advertises_separate_real_openfoam_job_but_not_completed_cfd():
    p=plan_engineering(_fan())
    assert p.task("generate_cad").status==TaskState.READY
    assert p.task("solid_mesh").status==TaskState.BLOCKED
    assert p.task("structural_fea").status==TaskState.BLOCKED
    assert p.task("fluid_domain").status==TaskState.READY
    assert p.task("fluid_mesh").status==TaskState.READY
    assert p.task("fluid_cfd").status==TaskState.AVAILABLE_EXTERNAL
    assert "OpenFOAM" in p.task("fluid_cfd").reason
    assert "NO CFD solve occurs" in p.task("fluid_cfd").reason
    assert "wall" in p.task("structural_fea").reason.lower()


def test_unconfirmed_fan_without_blade_parameters_blocks_cad():
    request=interpret_text(FAN_TEXT).request
    p=plan_engineering(request)
    assert p.task("generate_cad").status==TaskState.BLOCKED
    assert "blade_count" in p.task("generate_cad").missing_inputs
    with pytest.raises(ValueError,match="blocked"):
        run_engineering(request)


def test_bracket_plan_needs_assumptions_before_genuine_fea():
    parsed=interpret_text(BRACKET_TEXT).request
    p=plan_engineering(parsed)
    assert p.task("generate_cad").status==TaskState.READY
    assert p.task("structural_fea").status==TaskState.BLOCKED
    assert "E_gpa" in p.task("structural_fea").missing_inputs
    approved=_bracket()
    p=plan_engineering(approved)
    assert p.task("structural_fea").status==TaskState.READY
    assert p.task("fluid_cfd").status==TaskState.NOT_REQUESTED


def test_mocked_fan_run_exports_real_cad_metadata_but_no_fake_sim(monkeypatch):
    spec=_fan()
    blob=b"ISO-10303-21;"+b"test"*60
    product=CADProduct("wall_fan",blob,sha256(blob).hexdigest(),
                       "concept multi-body model",True,3)
    monkeypatch.setattr(pipeline,"generate_product",lambda req:product)
    out=run_engineering(spec)
    meta=out.evidence()
    assert meta["cad"]["concept_only"]
    assert meta["fluid_cfd"] is None
    assert meta["fluid_domain"] is None
    assert out.plan.task("fluid_mesh").status==TaskState.READY
    assert meta["structural_fea"] is None
    assert any(s["name"]=="fluid_cfd" and s["status"]=="AVAILABLE_EXTERNAL"
               for s in meta["stages"])
    assert any(s["name"]=="generate_cad" and s["status"]=="COMPLETED"
               for s in meta["stages"])


def test_bracket_execution_reuses_real_fea_adapter_and_checks_hash(monkeypatch):
    spec=_bracket()
    blob=b"ISO-10303-21;"+b"mock"*60
    digest=sha256(blob).hexdigest()
    monkeypatch.setattr(
        pipeline,"generate_product",
        lambda req:CADProduct("l_bracket",blob,digest,"real STEP",False,1),
    )
    class FakeFEA:
        mesh=SimpleNamespace(
            source_sha256=digest,num_tets=583,
            relative_volume_difference=.002,min_shape_quality=.12
        )
        tip_mm=.0358
        peak_von_mises_mpa=18.7
        mass_kg=.322
        relative_reaction_residual=1e-10
    import forceforge.isolated_cad as isolated
    calls=[]
    def check_call(step,**params):
        assert step==blob
        assert params["load"].force_n==250
        assert params["load"].force_axis==0
        assert params["load"].boundary_axis==2
        calls.append(params)
        return FakeFEA()
    monkeypatch.setattr(isolated,"analyze_step_safely",check_call)
    out=run_engineering(spec)
    assert len(calls)==1
    assert out.evidence()["structural_fea"]["provenance_sha256"]==digest
    assert out.evidence()["structural_fea"]["sampled_von_mises_mpa"]==18.7
    assert out.evidence()["stages"][2]["status"]=="COMPLETED"


def test_reject_unmatched_step_hash_not_a_fake_pass(monkeypatch):
    spec=_bracket()
    blob=b"ISO-10303-21;"+b"mock"*60
    monkeypatch.setattr(
        pipeline,"generate_product",
        lambda req:CADProduct("l_bracket",blob,sha256(blob).hexdigest(),"source",False,1),
    )
    import forceforge.isolated_cad as isolated
    monkeypatch.setattr(
        isolated,"analyze_step_safely",
        lambda *a,**kw:SimpleNamespace(
            mesh=SimpleNamespace(
                source_sha256="wrong",num_tets=500,
                relative_volume_difference=0,min_shape_quality=.1),
            relative_reaction_residual=0),
    )
    with pytest.raises(ValueError,match="SHA mismatch"):
        run_engineering(spec)


def test_fluid_domain_requires_explicit_separate_click(monkeypatch):
    from forceforge.engineering_pipeline import mesh_registered_fluid_domain
    from forceforge.fluid_domain import FluidDomainEvidence
    import forceforge.fluid_domain as fluid
    req=_fan()
    blob=b"ISO-10303-21;"+b"mesh"*70
    digest=sha256(blob).hexdigest()
    cad=CADProduct("wall_fan",blob,digest,"concept multi-body model",True,3)
    monkeypatch.setattr(pipeline,"generate_product",lambda request:cad)
    execution=run_engineering(req)
    called=[]
    def fake_mesh(request,source):
        assert request==req and source==blob
        called.append(1)
        return FluidDomainEvidence(
            "CONCEPT_FAN_TWO_ZONE_ACTUATOR_DOMAIN_NOT_CFD",
            digest,"mesh-hash",b"mesh-data",300.,900.,300.,750.,
            150.,90.,{"rotor_source_zone":12.,"ambient_air_zone":200.},
            212.,.002,800,500,
            {"upstream_open":20,"downstream_open":20,
             "lateral_farfield":70,"rotor_interface":32},
            {"upstream_open":101,"downstream_open":102,
             "lateral_farfield":103,"rotor_interface":104,
             "rotor_source_zone":201,"ambient_air_zone":202},
        )
    monkeypatch.setattr(fluid,"generate_fan_air_domain_safely",fake_mesh)
    assert len(called)==0
    mesh_registered_fluid_domain(req,execution)
    assert len(called)==1
    report=execution.evidence()
    assert report["fluid_domain"]["tetrahedra"]==800
    assert report["fluid_cfd"] is None
    assert any(t.name=="fluid_mesh" and t.status==TaskState.COMPLETED
               for t in execution.stage_results)
    assert any(t.name=="fluid_cfd" and t.status==TaskState.AVAILABLE_EXTERNAL
               for t in execution.stage_results)


def test_air_mesh_cannot_be_created_after_bracket_or_unapproved_assumptions():
    from forceforge.fluid_domain import _bounded_settings
    fan_raw=interpret_text(FAN_TEXT).request
    fake=b"ISO-10303-21;"+b"x"*300
    with pytest.raises(ValueError,match="Explicit consent"):
        _bounded_settings(fan_raw,fake)
    with pytest.raises(ValueError,match="wall_fan"):
        _bounded_settings(_bracket(),fake)
