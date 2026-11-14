"""Smoke tests for the v0.5 single-screen UI on the v0.4 laboratory solver.

The original v0.4 homepage remains untouched while the new interface is
reviewed. These tests validate real Streamlit widget behavior, not mock data.
"""
import pytest
from streamlit.testing.v1 import AppTest


def _studio():
    app = AppTest.from_file("../app_ui_v5.py", default_timeout=90).run()
    assert not app.exception
    return app


def test_initial_dashboard_preserves_measured_and_computed_metrics():
    app = _studio()
    labels = [metric.label for metric in app.metric]
    assert "Measured first frequency" in labels
    assert "Our FE first frequency" in labels
    assert "First-mode deviation" in labels
    assert any(slider.key == "lab_logk" for slider in app.sidebar.slider)
    assert any(button.label == "Calibrate using measured Mode 1"
               for button in app.button)


def test_views_switch_without_leaving_dashboard():
    app = _studio()
    tabs = next(radio for radio in app.radio if radio.key == "lab_section")
    tabs.set_value("Frequency Match").run()
    assert not app.exception
    tabs.set_value("Data & Sources").run()
    assert not app.exception
    tabs.set_value("Calibration").run()
    assert not app.exception


def test_one_parameter_calibration_shows_unseen_mode_checks():
    app = _studio()
    next(button for button in app.button
         if button.label == "Calibrate using measured Mode 1").click().run()
    assert not app.exception
    assert app.session_state["lab_fitted"] is True
    assert app.session_state["lab_logk"] == pytest.approx(2.673, abs=.02)
    labels = [metric.label for metric in app.metric]
    assert "Mode 2 held-out error" in labels
    assert "Mode 3 held-out error" in labels


def test_solver_stiffness_control_changes_live_fe_readout():
    app = _studio()
    before = next(metric.value for metric in app.metric
                  if metric.label == "Our FE first frequency")
    next(slider for slider in app.sidebar.slider
         if slider.key == "lab_logk").set_value(2.0).run()
    assert not app.exception
    after = next(metric.value for metric in app.metric
                 if metric.label == "Our FE first frequency")
    assert after != before
