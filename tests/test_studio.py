"""Regression and API adapter checks for the standalone ForceForge X Studio.

Keep test assertions anchored to the existing independent numerical solvers.
No browser screenshots or real Safari acceptance are claimed by these tests.
"""
import json
import math
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import studio_server as studio
from forceforge.modal_benchmark import MEASURED_HZ
from forceforge.solid3d import SolidCase

ROOT = Path(__file__).resolve().parents[1]


def test_studio_assets_have_real_controls_and_single_log():
    assert (ROOT / "studio/index.html").exists()
    assert (ROOT / "studio/styles.css").exists()
    assert (ROOT / "studio/app.js").exists()
    assert (ROOT / "studio/viewport3d.js").exists()
    assert (ROOT / "CHANGELOG.txt").exists()
    assert not (ROOT / "docs/CHANGELOG.md").exists()
    html = (ROOT / "studio/index.html").read_text()
    for item in ("model-canvas", "pin-force", "pin-thickness", "pin-support",
                 "pin-mode", "pin-result", "spatial-editor", "editor-value",
                 "editor-range", "scene-selector", "quick-result",
                 "detail-panel", "settings-panel", "view-reset"):
        assert f'id="{item}"' in html
    assert "bottom-drawer" not in html
    assert "inspector" not in html
    assert html.index("viewport3d.js") < html.index("app.js")
    script = (ROOT / "studio/app.js").read_text()
    viewer = (ROOT / "studio/viewport3d.js").read_text()
    assert "window.ForgeViewport" in script
    assert "class ForgeViewport" in viewer
    assert "WebGL2" in viewer
    assert "layoutPins" in script
    assert "pinAnchors" in script
    assert "spatial engineering" in html.lower()
    assert studio.CATALOG["ui_version"].startswith("0.2")
    log = (ROOT / "CHANGELOG.txt").read_text()
    for version in ("VERSION 0.8.0", "VERSION 0.7", "VERSION 0.6",
                    "VERSION 0.5", "VERSION 0.4", "VERSION 0.3",
                    "VERSION 0.2", "VERSION 0.1", "UI VERSION 0.4"):
        assert version in log
    assert "SPATIAL ENGINEERING" in log


def test_javascript_source_parses_when_node_available():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed in this environment")
    for script in ("app.js", "viewport3d.js", "adaptive.js", "inspection.js"):
        subprocess.run([node, "--check", str(ROOT / "studio" / script)],
                       check=True, capture_output=True, text=True)


def test_invalid_solver_inputs_are_rejected():
    for value in ("200", None, True, float("nan"), float("inf"), -10):
        with pytest.raises(ValueError):
            studio.solid_analysis({"force_n": value})
    with pytest.raises(ValueError):
        studio.lab_analysis({"log10_k": 9})
    with pytest.raises(ValueError):
        studio.solid_analysis({"resolution": "impossibly-fine"})


def test_solid_mesh_results_stay_physically_computed():
    p = {"workspace": "solid", "force_n": 100, "thickness_mm": 12,
         "resolution": "fast", "visual_scale": 1}
    data = studio.solid_analysis(p)
    assert data["workspace"] == "solid"
    assert data["element_count"] > 0
    assert data["node_count"] > 0
    assert len(data["mesh"]["vertices"]) > 0
    assert len(data["mesh"]["faces"]) == len(data["mesh"]["scalar"])
    assert math.isfinite(data["tip_displacement_mm"])
    assert data["tip_displacement_mm"] > 0
    higher = studio.solid_analysis({**p, "force_n": 200})
    assert higher["tip_displacement_mm"] == pytest.approx(
        data["tip_displacement_mm"] * 2, rel=0.03
    )
    assert higher["max_von_mises_mpa"] > data["max_von_mises_mpa"]


def test_real_lab_source_frequency_and_stiffness_sensitivity():
    initial = studio.lab_analysis({"workspace": "lab", "elements": 16})
    assert initial["measured_hz"] == [1.569, 10.389, 29.619]
    assert initial["published_abaqus_hz"] == [1.698, 10.775, 30.590]
    assert len(initial["mesh"]["faces"]) > 0
    assert len(initial["sensors"]) == 5
    assert all("height_mm" in item for item in initial["sensors"])
    softer = studio.lab_analysis({
        "workspace": "lab", "elements": 16, "log10_k": 2.0
    })
    assert softer["frequencies_hz"][0] < initial["frequencies_hz"][0]


def test_modal_calibration_does_not_fit_held_out_modes():
    fitted = studio.lab_calibrate({
        "workspace": "lab", "elements": 16,
    })
    assert fitted["k_nm_rad"] > 0
    assert fitted["frequencies_hz"][0] == pytest.approx(MEASURED_HZ[0], abs=1e-4)
    assert len(fitted["frequencies_hz"]) == 3
    assert fitted["holdout_mape_percent"] >= 0
    assert "Mode 1" in fitted["method"]
    assert "Modes 2/3" in fitted["method"]


def test_redesign_rechecks_3d_volume_mesh_candidates(monkeypatch):
    calls = []
    original = studio._cached_solid

    def count_calls(case):
        calls.append(case.thickness_m)
        return original(case)

    monkeypatch.setattr(studio, "_cached_solid", count_calls)
    out = studio.solid_redesign({
        "workspace": "solid", "resolution": "fast",
        "force_n": 100, "allowed_mm": 0.3, "thickness_mm": 12,
    })
    assert out["tested_count"] == 9
    assert len(out["candidates"]) == 9
    assert len({round(t, 6) for t in calls}) >= 9
    assert out["best"] is not None
    assert out["best"]["passes_assumed_limit"] is True

def test_lab_static_mode_is_explicitly_computed_not_measured():
    baseline = studio.lab_analysis({"workspace": "lab", "elements": 16,
                                    "view": "static", "tip_force_n": 0.2})
    changed = studio.lab_analysis({"workspace": "lab", "elements": 16,
                                   "view": "static", "tip_force_n": 0.4})
    assert baseline["view"] == "static"
    assert baseline["static_force_n"] == pytest.approx(0.2)
    assert baseline["static_tip_mm"] is not None
    assert changed["static_tip_mm"] == pytest.approx(
        baseline["static_tip_mm"] * 2, rel=1e-5
    )
    assert baseline["measured_hz"] == [1.569, 10.389, 29.619]
    modal = studio.lab_analysis({"workspace": "lab", "elements": 16,
                                 "view": "modes"})
    assert modal["static_tip_mm"] is None

def test_surface_probe_preserves_reference_mesh_and_actual_fea_displacements():
    p={"workspace":"solid","force_n":100,"thickness_mm":12,
       "resolution":"fast","visual_scale":70}
    data=studio.solid_analysis(p)
    mesh=data["mesh"]
    assert len(mesh["vertices"])==len(mesh["reference_vertices"])
    assert len(mesh["vertices"])==len(mesh["displacements_mm"])
    assert len(mesh["scalar"])==len(mesh["faces"])
    ref=mesh["reference_vertices"]
    displayed=mesh["vertices"]
    actual=mesh["displacements_mm"]
    assert any(sum(abs(x) for x in u)>1e-8 for u in actual)
    for a,b,u in zip(ref,displayed,actual):
        for i in range(3):
            assert b[i]-a[i]==pytest.approx(70*u[i],abs=2e-5)


def test_real_lab_hover_does_not_fabricate_modal_local_motion():
    modal=studio.lab_analysis({"workspace":"lab","elements":16,"view":"modes"})
    mesh=modal["mesh"]
    assert len(mesh["reference_vertices"])==len(mesh["vertices"])
    assert "displacements_mm" not in mesh
    static=studio.lab_analysis({"workspace":"lab","elements":16,"view":"static"})
    assert len(static["mesh"]["displacements_mm"])==len(static["mesh"]["vertices"])


def test_probe_assets_and_data_attribution_are_available():
    html=(ROOT/"studio/index.html").read_text()
    js=(ROOT/"studio/inspection.js").read_text()
    assert 'src="/studio/inspection.js"' in html
    for phrase in ("SURFACE · FEM", "face sample", "REFERENCE", "barycentric",
                   "displacements_mm", "probeAt", "axisIndicator"):
        assert phrase.lower() in js.lower()
    assert "UI VERSION 0.2.1" in (ROOT/"CHANGELOG.txt").read_text()
