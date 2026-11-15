"""Contract tests for plain-language, unit-safe mechanical product specs."""
import pytest
from pydantic import ValidationError

from forceforge.engineering_schema import (
    EngineeringRequest, FanGeometry, ProductFamily,
    approve_demo_assumptions, interpret_text, preflight_missing,
)


def test_chinese_fan_extracts_literal_dimensions_and_physics_intents():
    parsed=interpret_text(
        "帮我做一个直径30厘米、转速1500 RPM的挂壁风扇，"
        "我想知道气流怎么走，墙壁怎么受力？"
    )
    assert parsed.request is not None, parsed.issues
    r=parsed.request
    assert r.family==ProductFamily.WALL_FAN
    assert isinstance(r.geometry,FanGeometry)
    assert r.geometry.diameter_mm==300.
    assert r.geometry.rpm==1500.
    assert r.analyses.fluid_cfd is True
    assert r.analyses.structural_fea is True
    assert set(preflight_missing(r))=={
        "blade_count","hub_diameter_mm","blade_pitch_deg"
    }
    assert r.loads.anchor_specification is None
    assert r.loads.force_n is None
    assert r.material.E_gpa is None
    assert not r.concept_assumptions_confirmed


def test_fan_geometry_assumptions_are_explicit_and_never_set_loads():
    r=interpret_text("设计直径300mm的挂壁风扇，展示CFD流场和墙壁受力。").request
    approved=approve_demo_assumptions(r)
    assert approved.concept_assumptions_confirmed
    assert approved.geometry.blade_count==5
    assert approved.geometry.hub_diameter_mm==75
    assert approved.geometry.blade_pitch_deg==20
    assert not preflight_missing(approved)
    assert len(approved.assumptions)>=4
    assert r.geometry.blade_count is None
    assert approved.loads.force_n is None
    assert approved.material.E_gpa is None


def test_bracket_simple_chinese_measures_units_and_load_without_hidden_defaults():
    out=interpret_text("做一个腹板厚度8毫米的L型支架，施加载荷250 N，求应力和变形。")
    assert out.request is not None, out.issues
    r=out.request
    assert r.family.value=="l_bracket"
    assert r.geometry.web_thickness_mm==8
    assert r.loads.force_n==250.
    assert r.material.E_gpa is None
    assert r.loads.support_axis is None
    assert r.analyses.structural_fea
    amended=approve_demo_assumptions(r)
    assert amended.material.E_gpa==200.
    assert amended.loads.support_axis=="Z"
    assert amended.loads.force_axis=="X"
    assert amended.loads.force_n==250.
    assert len(amended.assumptions)>=4


def test_bracket_rejects_unsupported_thickness_instead_of_mapping_it():
    result=interpret_text("10? no: 17mm thick L-bracket under 250 N load")
    assert result.request is None
    assert "17" in result.issues[0]


def test_unknown_product_family_does_not_fall_back_to_fake_fan():
    parsed=interpret_text("请设计一个汽车齿轮箱，计算噪声和润滑流场")
    assert parsed.request is None
    assert "Unregistered" in parsed.issues[0]


def test_extra_fields_and_mismatched_family_rejected():
    with pytest.raises(ValidationError):
        EngineeringRequest.model_validate({
            "prompt":"Build a fan",
            "family":"l_bracket",
            "geometry":{"family":"wall_fan","diameter_mm":300},
        })
    with pytest.raises(ValidationError):
        FanGeometry.model_validate({"family":"wall_fan","diameter_mm":300,"custom_script":"exec(...)"})


def test_invalid_geometry_never_silently_accepted():
    with pytest.raises(ValidationError):
        FanGeometry(diameter_mm=300,hub_diameter_mm=200)
    with pytest.raises(ValidationError):
        FanGeometry(diameter_mm=-300)


def test_versioned_schema_json_export_roundtrip():
    req=approve_demo_assumptions(
        interpret_text("Design a wall fan diameter 300 mm speed 1500 RPM and show airflow").request
    )
    copy=EngineeringRequest.model_validate_json(req.model_dump_json())
    assert copy==req
    assert copy.schema_version=="1.0"
    j=EngineeringRequest.model_json_schema()
    assert j["$defs"]["FanGeometry"]["properties"]["diameter_mm"]
