"""Judge-flow smoke tests in a real Streamlit test runner.

New product UX and legacy specialist UI are tested separately, so a product
landing-page change cannot silently delete previously verified ML controls.
"""
from streamlit.testing.v1 import AppTest


def _button(app, label):
    return next(widget for widget in app.button if widget.label == label)


def _radio(app, key):
    return next(widget for widget in app.radio if widget.key == key)


def test_new_landing_explains_a_real_eng_problem_without_exposing_solver_first():
    app=AppTest.from_file("../app.py",default_timeout=90).run()
    assert not app.exception
    assert _button(app,"Analyze the current design")
    assert _radio(app,"ff_sector")
    assert _radio(app,"ff_severity")


def test_judge_scenario_and_redesign_survive_industry_switch():
    app=AppTest.from_file("../app.py",default_timeout=90).run()
    assert not app.exception

    _radio(app,"ff_sector").set_value("Industrial").run()
    assert not app.exception
    _button(app,"Analyze the current design").click().run()
    assert not app.exception
    original=app.session_state["ff_history"]["Industrial"]["report"]
    assert original.governing["max_utilization"]>1.0

    _button(app,"Find an FEA-verified improvement").click().run()
    assert not app.exception
    saved=app.session_state["ff_history"]["Industrial"]
    assert saved["improvement"].redesigned is not None
    assert saved["improvement"].redesigned.governing["max_utilization"]<=1

    _radio(app,"ff_sector").set_value("Building").run()
    assert not app.exception
    _radio(app,"ff_sector").set_value("Industrial").run()
    assert not app.exception
    recovered=app.session_state["ff_history"]["Industrial"]
    assert recovered["report"].trace_id==saved["report"].trace_id
    assert recovered["improvement"].redesigned.trace_id==saved["improvement"].redesigned.trace_id
