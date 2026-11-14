"""Keep the video-inspired FEA flow running in Streamlit regression tests."""
from streamlit.testing.v1 import AppTest


def test_new_cad_stress_page_has_verifiable_computed_metrics():
    app = AppTest.from_file("../pages/10_3D_CAD_Simulation.py", default_timeout=90).run()
    assert not app.exception
    labels = {x.label for x in app.metric}
    assert "Tip movement" in labels
    assert "Peak bending stress" in labels
    assert "Member mass" in labels
    assert any("Find the lightest design that meets the modeled limits" == b.label for b in app.button)


def test_redesign_keeps_solver_results_and_updates_comparison():
    app = AppTest.from_file("../pages/10_3D_CAD_Simulation.py", default_timeout=90).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Find the lightest design that meets the modeled limits").click().run()
    assert not app.exception
    assert "static_redesign" in app.session_state
    optimum, all_cases = app.session_state["static_redesign"]["output"]
    assert len(all_cases) > 0
    assert optimum is not None
    assert optimum.governing_utilization <= 1.0


def test_homepage_source_keeps_real_modal_benchmark_and_new_link():
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1]/"app.py").read_text()
    assert "3D stress / failure / redesign" in s
    assert "Measured first frequency" in s
    assert "Calibrate using measured Mode 1" in s


def test_changed_load_never_displays_outdated_redesign_as_current():
    app = AppTest.from_file("../pages/10_3D_CAD_Simulation.py", default_timeout=90).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Find the lightest design that meets the modeled limits").click().run()
    assert not app.exception
    assert any(x.label == "Redesigned thickness / reference" for x in app.metric)
    previous = dict(app.session_state["static_redesign"]["inputs"])
    load = next(x for x in app.sidebar.slider if x.label == "Tip side load (N)")
    load.set_value(.26).run()
    assert not app.exception
    assert app.session_state["static_redesign"]["inputs"] == previous
    assert not any(x.label == "Redesigned thickness / reference" for x in app.metric)
