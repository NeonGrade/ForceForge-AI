"""Streamlit stability acceptance: click-to-run, actual STEP, no stale FEM.

This entire test module runs on the optional Gmsh integration CI job.
"""
import pytest
pytest.importorskip("gmsh")
from streamlit.testing.v1 import AppTest


def button(app, label):
    return next(x for x in app.button if x.label == label)


def test_default_page_opens_without_automatically_meshing_or_solving():
    app = AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py", default_timeout=140
    ).run()
    assert not app.exception
    # Loading/reloading a page must never automatically invoke Gmsh or FEM.
    assert not any(x.label == "3D tetrahedra" for x in app.metric)
    assert button(app, "Run CAD import + 3D FEA")
    assert "stable_initial" not in app.session_state


def test_user_click_runs_real_step_tetra10_and_revised_cad_job():
    app = AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py", default_timeout=160
    ).run()
    assert not app.exception
    button(app, "Run CAD import + 3D FEA").click().run()
    assert not app.exception
    initial = app.session_state["stable_initial"]
    assert initial["result"].mesh.num_tets > 20
    assert initial["result"].relative_reaction_residual < 1e-6
    labels = {x.label for x in app.metric}
    assert "3D tetrahedra" in labels
    assert "Sampled peak von Mises" in labels
    button(app, "Re-mesh revised CAD and re-run 3D FEA").click().run()
    assert not app.exception
    other = app.session_state["stable_revised"]
    assert other["result"].relative_reaction_residual < 1e-6
    assert other["result"].mesh.source_sha256 != initial["result"].mesh.source_sha256
    assert other["result"].mesh.cad_volume_m3 != initial["result"].mesh.cad_volume_m3


def test_changed_force_hides_old_fe_results_until_explicit_rerun():
    app = AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py", default_timeout=160
    ).run()
    button(app, "Run CAD import + 3D FEA").click().run()
    assert not app.exception
    first_hash = app.session_state["stable_initial"]["result"].mesh.source_sha256
    next(x for x in app.sidebar.slider if x.label == "Transverse force (N)").set_value(300).run()
    assert not app.exception
    assert not any(x.label == "3D tetrahedra" for x in app.metric)
    # The snapshot is preserved for diagnostics, but cannot be shown as new FEA.
    assert app.session_state["stable_initial"]["result"].mesh.source_sha256 == first_hash


def test_mesh_evidence_is_opt_in_and_has_three_actual_fea_levels():
    app = AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py", default_timeout=220
    ).run()
    assert not app.exception
    assert "stable_mesh_evidence" not in app.session_state
    button(app, "Run CAD import + 3D FEA").click().run()
    assert not app.exception
    assert "stable_mesh_evidence" not in app.session_state
    button(app, "Run mesh-sensitivity study (2 additional FE solves)").click().run()
    assert not app.exception
    verified = app.session_state["stable_mesh_evidence"]
    assert len(verified["study"].ordered_rows) == 3
    assert all(r.reaction_residual < 1e-5
               for r in verified["study"].ordered_rows)
