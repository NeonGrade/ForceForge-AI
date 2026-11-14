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
    assert (ROOT / "CHANGELOG.txt").exists()
    assert not (ROOT / "docs/CHANGELOG.md").exists()
    html = (ROOT / "studio/index.html").read_text()
    for item in ("model-canvas", "solid-force", "lab-stiffness",
                 "primary-action", "bottom-drawer", "mode-comparisons"):
        assert f'id="{item}"' in html
    log = (ROOT / "CHANGELOG.txt").read_text()
    for version in ("VERSION 0.8.0", "VERSION 0.7", "VERSION 0.6",
                    "VERSION 0.5", "VERSION 0.4", "VERSION 0.3",
                    "VERSION 0.2", "VERSION 0.1", "UI VERSION 0.4"):
        assert version in log


def test_javascript_source_parses_when_node_available():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed in this environment")
    subprocess.run([node, "--check", str(ROOT / "studio/app.js")],
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
