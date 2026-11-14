"""Failure containment and SHA-verified subprocess CAD solver."""
from __future__ import annotations
from types import SimpleNamespace
import subprocess
import pytest

from forceforge.isolated_cad import (
    CadJobError, _invoke, generate_bracket_safely,
    analyze_step_safely, MAX_INTERACTIVE_TETS,
)
from forceforge.cad_solid import CadLoad


def test_worker_native_crash_is_reported_without_killing_parent(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=-11, stderr="", stdout="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(CadJobError, match="exited with code -11"):
        _invoke("generate", {"web_mm": 8}, None, 2)
    # Reaching here proves main Python/Streamlit process survived.


def test_worker_timeout_is_reported_without_killing_parent(monkeypatch):
    def fail_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="gmsh", timeout=1)
    monkeypatch.setattr(subprocess, "run", fail_run)
    with pytest.raises(CadJobError, match="exceeded 1 seconds"):
        _invoke("generate", {"web_mm": 8}, None, 1)


def test_analyzer_enforces_memory_bound_before_loading_cad():
    with pytest.raises(ValueError, match="tetra element cap"):
        analyze_step_safely(b"invalid cad", source_label="bad",
                            mesh_size_mm=10, unit="mm",
                            load=CadLoad(), max_tets=10000)


def test_automatic_fe_allocation_is_absent_from_page_source():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] /
           "pages/13_Real_STEP_Engineering.py").read_text()
    assert "Run CAD import + 3D FEA" in src
    assert "generate_bracket_safely" in src
    assert "analyze_step_safely" in src
    assert "@st.cache_data" not in src


def test_isolated_real_step_generation_and_full_tetra10_solve():
    pytest.importorskip("gmsh")
    original = generate_bracket_safely(8)
    changed = generate_bracket_safely(12)
    assert original != changed
    c = CadLoad(force_n=120, force_axis=0, boundary_axis=2)
    base = analyze_step_safely(original, source_label="8mm bracket",
                              mesh_size_mm=12, unit="mm", load=c)
    revision = analyze_step_safely(changed, source_label="12mm bracket",
                                  mesh_size_mm=12, unit="mm", load=c)
    assert base.mesh.num_tets <= MAX_INTERACTIVE_TETS
    assert revision.mesh.num_tets <= MAX_INTERACTIVE_TETS
    assert base.relative_reaction_residual < 1e-6
    assert revision.relative_reaction_residual < 1e-6
    assert revision.mesh.cad_volume_m3 > base.mesh.cad_volume_m3
    assert revision.mesh.source_sha256 != base.mesh.source_sha256
    assert base.peak_von_mises_mpa > 0
