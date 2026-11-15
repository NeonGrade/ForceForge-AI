"""Streamlit AppTest confirms the page never runs native CAD on mere redraw."""
from streamlit.testing.v1 import AppTest


PAGE="../pages/14_Natural_Language_Engineering.py"


def test_natural_language_ui_requires_explicit_confirmation_and_run():
    app=AppTest.from_file(PAGE,default_timeout=45).run()
    assert not app.exception
    assert "nl_result" not in app.session_state
    submit=next(x for x in app.button if x.label=="Interpret engineering requirements")
    submit.click().run()
    assert not app.exception
    assert app.session_state["nl_interpretation"].request.family.value=="wall_fan"
    assert "nl_result" not in app.session_state
    # No Gmsh, FEA, or fabricated CFD may run on rerender.
    app.run()
    assert not app.exception
    assert "nl_result" not in app.session_state


def test_nl_page_handles_unknown_product_without_invoking_cad():
    app=AppTest.from_file(PAGE,default_timeout=45).run()
    source=next(x for x in app.text_area
                if x.label=="What should ForceForge build and analyze?")
    # Form widget changes are committed together with the submit event.
    source.set_value("设计一个自动变速箱，计算油路和振动")
    button=next(x for x in app.button
                if x.label=="Interpret engineering requirements")
    button.click().run()
    assert not app.exception
    assert app.session_state["nl_interpretation"].request is None
    assert "nl_result" not in app.session_state
