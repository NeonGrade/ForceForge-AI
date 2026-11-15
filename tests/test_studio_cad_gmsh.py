"""Actual STEP -> Gmsh volume mesh -> tet10 UI adapter integration."""
import pytest

pytest.importorskip("gmsh")
import studio_cad_api as cad


def test_spatial_generated_bracket_true_step_mesh_and_fea():
    result=cad.analyze({
        "workspace":"cad",
        "source":"generated",
        "web_mm":8,
        "mesh_size_mm":12,
        "force_n":80,
        "direction":"+X",
        "boundary":"Z",
        "visual_scale":1,
    })
    assert result["workspace"]=="cad"
    assert result["mesh_count"]>10
    assert result["volume_difference_percent"]<20
    assert result["reaction_residual"]<1e-5
    assert result["tip_displacement_mm"]>0
    assert result["max_von_mises_mpa"]>0
    assert len(result["mesh"]["faces"])==len(result["mesh"]["scalar"])
    assert len(result["mesh"]["vertices"])>10
    assert result["cad_token"]==result["source_sha256"]


def test_spatial_cad_revision_really_changes_step_and_recomputes():
    result=cad.revise({
        "workspace":"cad",
        "source":"generated",
        "web_mm":8,
        "revision_web_mm":12,
        "mesh_size_mm":12,
        "force_n":80,
        "direction":"+X",
        "boundary":"Z",
        "visual_scale":1,
    })
    assert result["original"]["source_sha256"] != result["revision"]["source_sha256"]
    assert result["original"]["mesh_count"]>10
    assert result["revision"]["mesh_count"]>10
    assert result["original"]["mass_kg"] != result["revision"]["mass_kg"]
    assert result["original"]["reaction_residual"] <1e-5
    assert result["revision"]["reaction_residual"] <1e-5
