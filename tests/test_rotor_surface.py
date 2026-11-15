"""Actual 300 mm STEP to watertight rotating blade STL provenance test.

Gmsh OpenCASCADE is required. The reference room placement is separate from
the wall-mount scenario; no fluid solution is assumed.
"""
from hashlib import sha256

import numpy as np
import pytest

pytest.importorskip("gmsh")

from forceforge.engineering_schema import approve_demo_assumptions, interpret_text
from forceforge.product_cad import generate_product
from forceforge.rotor_surface import extract_rotor_from_step


def test_actual_concept_step_rotor_stl_in_si_units():
    request=approve_demo_assumptions(interpret_text(
        "帮我建模直径30厘米、1500 RPM的壁挂风扇，分析气流"
    ).request)
    model=generate_product(request)
    rotor=extract_rotor_from_step(request,model.step_bytes)
    assert rotor.cad_source_sha256==model.sha256
    assert rotor.stl_sha256==sha256(rotor.stl_bytes).hexdigest()
    assert rotor.triangles>100
    assert len(rotor.stl_bytes)>10000
    assert rotor.stl_bytes.startswith(b"solid fan")
    assert rotor.stl_bytes.rstrip().endswith(b"endsolid fan")
    assert rotor.reference_room_centre_m==(-3.,2.,2.6)
    assert rotor.source_bbox_mm[3]-rotor.source_bbox_mm[0]<315
    assert rotor.as_dict()["geometry_scope"].startswith("USER_ROTOR")


def test_unconfirmed_assumptions_cannot_be_used_for_rotating_blades():
    source=approve_demo_assumptions(interpret_text(
        "设计直径300mm的壁挂风扇，求风速"
    ).request)
    model=generate_product(source)
    original=interpret_text(
        "设计直径300mm的壁挂风扇，求风速"
    ).request
    with pytest.raises(ValueError,match="approval"):
        extract_rotor_from_step(original,model.step_bytes)
