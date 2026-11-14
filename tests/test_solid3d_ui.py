"""Streamlit acceptance tests for genuine 3D solid tetrahedral FEA."""
from streamlit.testing.v1 import AppTest


def test_true_3d_solid_page_solves_and_displays_volume_element_results():
    app=AppTest.from_file("../pages/12_True_3D_Solid_FEA.py",
                          default_timeout=90).run()
    assert not app.exception
    labels={x.label for x in app.metric}
    assert "3D FE tip movement" in labels
    assert "Peak element von Mises" in labels
    assert "Volume tetra10 elements" in labels
    assert any(b.label=="Find lighter feasible solid thickness (3D FEA)"
               for b in app.button)


def test_solids_are_really_resolved_after_thickness_change():
    app=AppTest.from_file("../pages/12_True_3D_Solid_FEA.py",
                          default_timeout=90).run()
    assert not app.exception
    next(b for b in app.button
         if b.label=="Find lighter feasible solid thickness (3D FEA)").click().run()
    assert not app.exception
    result=app.session_state["solid_redesign"]
    assert len(result["options"])==9
    assert result["selected"] is not None
    _,best=result["selected"]
    assert len(best.tets10)>0
    assert best.tip_displacement_mm<=.12+1e-8
