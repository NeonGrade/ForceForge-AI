"""Spatial UI v0.2 source integrity, CAD bridge and existing solver regression.

The default CI does not require optional Gmsh. Real integration is exercised
by the dedicated Gmsh CI workflow on Linux and macOS.
"""
from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

import studio_cad_api as cad
import studio_server
from forceforge.cad_solid import CadLoad


def _valid_step(label=b""):
    return b"ISO-10303-21;\nHEADER;\n" + label + b"\n" + b"-"*150


def test_catalog_exposes_independent_versions_and_preserves_modules():
    c = studio_server.CATALOG
    assert c["ui_version"] == "0.2.1"
    assert c["engineering_version"] == "1.0"
    assert {"cad", "lab", "solid"} == {m["id"] for m in c["modules"]}


def test_step_source_registration_is_bounded_and_content_addressed():
    raw = _valid_step()
    stored = cad.store_step(raw, "test-part.step")
    assert stored["sha256"] == sha256(raw).hexdigest()
    again, name = cad.get_step(stored["token"])
    assert again == raw
    assert name == "test-part.step"
    with pytest.raises(ValueError, match="token"):
        cad.get_step("../something")
    with pytest.raises(ValueError, match="not in this local session"):
        cad.get_step("0"*64)
    with pytest.raises(ValueError, match="ISO-10303-21"):
        cad.store_step(b"Not a STEP file" + b"x"*200)


def test_cad_input_validation_without_gmsh():
    base = cad.options({})
    assert base["source"] == "generated"
    assert base["web_mm"] == 8
    for args in (
        {"web_mm": 9},
        {"mesh_size_mm": 40},
        {"direction": "+Z", "boundary": "Z"},
        {"force_n": "250"},
        {"E_gpa": float("inf")},
        {"source": "uploaded"},
        {"direction": "+X", "boundary": "X"},
    ):
        with pytest.raises(ValueError):
            cad.options(args)


def test_spatial_cad_bridge_uses_existing_solver_and_original_mesh(monkeypatch):
    mesh = SimpleNamespace(
        source_label="Generated demonstration bracket",
        source_sha256="a"*64,num_tets=18,
        mesh_volume_m3=2e-5,cad_volume_m3=2.01e-5,
        relative_volume_difference=.005,min_shape_quality=.1,
        bbox_m=np.array([[0,0,0],[.075,.04,.058]])
    )
    result = SimpleNamespace(
        mesh=mesh,load=CadLoad(force_n=250, force_sign=1, force_axis=0,
                               boundary_axis=2, yield_pa=900e6),
        tip_mm=.18,peak_von_mises_mpa=321.5,mass_kg=.15,
        relative_reaction_residual=1e-10,
        nodes_m=np.array([[0.,0.,0.],[0.,0.,.05],[.01,0,.05]]),
        displacements_m=np.zeros((3,3)),
        surface_faces=np.array([[0,1,2]]),
        surface_element_ids=np.array([0]),
        von_mises_pa=np.array([321.5e6]),
        max_displacement_m=.00018,strain_energy_j=.01,
    )
    mesh.mesh_size_mm=12
    monkeypatch.setattr(cad, "_solve", lambda args: (result,"a"*64))
    body=cad.analyze({"source":"generated"})
    assert body["workspace"]=="cad"
    assert body["model_title"]=="Generated demonstration bracket"
    assert body["mesh_count"]==18
    assert body["max_von_mises_mpa"]==321.5
    assert body["mesh"]["scalar"]==[321.5]
    assert body["source_sha256"]=="a"*64
    assert body["validation"].find("no independently measured static")>=0
    assert body["engineering_review"]["mesh_assessment"] == "NOT_EVALUATED"


def test_spatial_assets_and_original_specialist_pages_are_preserved():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    for path in (
        "app.py","pages/13_Real_STEP_Engineering.py",
        "pages/12_True_3D_Solid_FEA.py",
        "pages/9_Industry_Explorer.py",
        "forceforge/step_mesh.py","forceforge/cad_solid.py",
        "forceforge/modal_benchmark.py","forceforge/solid3d.py",
        "studio/index.html","studio/app.js","studio/viewport3d.js",
        "studio/adaptive.js","studio/adaptive.css","studio_cad_api.py",
        "CHANGELOG.txt",
    ):
        assert (root/path).exists(),path
    assert not (root/"docs/CHANGELOG.md").exists()
    html=(root/"studio/index.html").read_text()
    for anchor in (
        'data-workspace="cad"','id="cad-file"',
        'id="cad-run-revision"','id="cad-source-choice"',
        'id="cad-revision-file"','id="tools-toggle"',
        'id="compact-tools"'
    ):
        assert anchor in html
    script=(root/"studio/adaptive.js").read_text()
    assert "/api/cad/solve" in script
    assert "/api/cad/revise" in script
    assert "/api/cad/import" in script
    assert "ui.params.cad" in script
    log=(root/"CHANGELOG.txt").read_text()
    assert "UI VERSION 0.1.0" in log
    assert "UI VERSION 0.2.0" in log
    assert "ENGINEERING VERSION 0.7" in log
