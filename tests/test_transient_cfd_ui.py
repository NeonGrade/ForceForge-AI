"""Transient CFD page never fabricates fields on load or without Docker."""
from streamlit.testing.v1 import AppTest


def test_reference_cfd_page_is_idle_without_explicit_solver_click():
    app=AppTest.from_file(
        "../pages/15_Transient_Rotating_CFD.py",default_timeout=45
    ).run()
    assert not app.exception
    assert "forceforge_reference_cfd_job" not in app.session_state
    assert all("velocity_m_s" not in str(x) for x in app.session_state)


def test_custom_cfd_mode_requires_actual_source_step_rotor_geometry():
    app=AppTest.from_file(
        "../pages/15_Transient_Rotating_CFD.py",default_timeout=45
    ).run()
    radio=next(x for x in app.radio if x.label=="Select provenance / geometry scope")
    radio.set_value("My STEP-derived rotor in the official OpenFOAM reference room").run()
    assert not app.exception
    assert "forceforge_reference_cfd_job" not in app.session_state
    assert not any("actual_openfoam_dynamic_animation" in str(k) for k in app.session_state)
