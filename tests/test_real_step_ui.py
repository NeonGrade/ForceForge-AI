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


def test_real_stress_screen_does_not_mark_unresolved_local_peak_safe():
    app=AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py",default_timeout=220
    ).run()
    assert not app.exception
    button(app,"Run CAD import + 3D FEA").click().run()
    assert not app.exception
    button(app,"Run mesh-sensitivity study (2 additional FE solves)").click().run()
    assert not app.exception
    evidence=app.session_state["stable_mesh_evidence"]["study"]
    assert evidence.local_peak_status in {
        "PEAK_STRESS_UNRESOLVED",
        "PRELIMINARY_PEAK_STRESS_STABILITY",
        "UNVERIFIED_MESH_REFINEMENT",
    }
    assert evidence.engineering_evidence_status
    assert evidence.fine_medium_probe_mean_percent>=0
    assert evidence.fine_medium_hotspot_drift_mm>=0
    assert len(evidence.ordered_rows)==3


def test_opt_in_hotspot_refinement_is_physical_and_survives_streamlit_rerun():
    app=AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py",default_timeout=240
    ).run()
    assert not app.exception
    button(app,"Run CAD import + 3D FEA").click().run()
    assert not app.exception
    assert "stable_hotspot_study" not in app.session_state
    button(app,"Run two local hotspot refinements").click().run()
    assert not app.exception
    study=app.session_state["stable_hotspot_study"]["study"]
    assert len(study.steps)==3
    assert study.source_sha256==app.session_state["stable_initial"]["result"].mesh.source_sha256
    assert all(r.reaction_residual<1e-5 for r in study.steps)


def test_dual_hotspot_ui_is_opt_in_and_keeps_previous_fea_results():
    """End-to-end Streamlit click through real STEP/Gmsh/tetra10 workers."""
    app=AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py",default_timeout=360
    ).run()
    assert not app.exception
    assert "stable_dual_hotspot" not in app.session_state
    button(app,"Run CAD import + 3D FEA").click().run()
    assert not app.exception
    assert "stable_dual_hotspot" not in app.session_state
    button(app,"Run two local hotspot refinements").click().run()
    assert not app.exception
    original=app.session_state["stable_initial"]
    first=app.session_state["stable_hotspot_study"]["study"]
    assert len(first.matched_physical_hotspot_regions)==2
    button(app,"Run dual-hotspot re-mesh + 2 independent 3D FEA solves").click().run()
    assert not app.exception
    evidence=app.session_state["stable_dual_hotspot"]["study"]
    assert len(evidence.steps)==2
    assert len(evidence.site_rows)==2
    assert evidence.source_sha256==original["result"].mesh.source_sha256
    assert "PEAK" in evidence.global_peak_status
    assert app.session_state["stable_hotspot_study"]["study"] is first
    # Changing a force should hide, rather than mislabel, stale dual-site data.
    next(x for x in app.sidebar.slider if x.label == "Transverse force (N)").set_value(310).run()
    assert not app.exception
    assert "stable_dual_hotspot" in app.session_state
    assert not any(x.label == "Largest fixed-site P90 difference" for x in app.metric)


def test_live_cad_copilot_uses_real_step_and_tetra10_not_mock_physics():
    """One explicit click builds 3 independently checked CAD variations."""
    app=AppTest.from_file(
        "../pages/13_Real_STEP_Engineering.py",default_timeout=360
    ).run()
    assert not app.exception
    assert "stable_cad_copilot" not in app.session_state
    button(app,"Run CAD import + 3D FEA").click().run()
    assert not app.exception
    assert "stable_cad_copilot" not in app.session_state
    button(app,"Generate CAD proposals + verify every candidate with real 3D FEA").click().run()
    assert not app.exception
    audit=app.session_state["stable_cad_copilot"]
    assert audit["proposal"].mode=="RULE_BASED_FULL_SEARCH"
    assert audit["proposal"].candidates_mm==(10,12,14)
    assert len(audit["rows"])==3
    assert not audit["failures"],audit["failures"]
    assert len(audit["sources"])==3
    assert len(audit["solutions"])==3
    hashes=set()
    base=app.session_state["stable_initial"]["result"]
    for row in audit["rows"]:
        assert row.source_sha256 not in hashes
        assert row.source_sha256 != base.mesh.source_sha256
        hashes.add(row.source_sha256)
        solved=audit["solutions"][row.thickness_mm]
        assert solved.mesh.num_tets==row.tetrahedra>20
        assert solved.relative_reaction_residual<1e-5
        assert solved.load==base.load
        assert solved.mesh.source_sha256==row.source_sha256
    assert audit["selected"] in (10,12,14)
    assert "stable_initial" in app.session_state
    # Changing constraints changes only the screening signature; no
    # previously computed FEM may be displayed as a new recommendation.
    next(x for x in app.number_input if x.label=="Target max tip displacement (mm)").set_value(.02).run()
    assert not app.exception
    assert "stable_cad_copilot" in app.session_state
    # Streamlit AppTest Warning exposes no .message attribute; the UI emits
    # a stale-result notice without rendering the old recommendation.
    assert len(app.warning) >= 1
