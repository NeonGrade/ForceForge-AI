"""Wall-load page uses no solver until an explicit user click."""
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_wall_mount_starts_idle_and_has_explicit_load_source():
    page=Path(__file__).resolve().parents[1]/"pages/16_Wall_Mount_Loads.py"
    app=AppTest.from_file(str(page),default_timeout=35).run()
    assert not app.exception
    assert "wall_mount_load_result" not in app.session_state
    assert any("Calculate actual 4-anchor" in b.label for b in app.button)
    assert any("Source of aerodynamic force inputs" == s.label for s in app.selectbox)
    app.run()
    assert "wall_mount_load_result" not in app.session_state


def test_wall_mount_click_computes_real_balanced_anchors():
    page=Path(__file__).resolve().parents[1]/"pages/16_Wall_Mount_Loads.py"
    app=AppTest.from_file(str(page),default_timeout=35).run()
    next(b for b in app.button if "Calculate actual 4-anchor" in b.label).click().run()
    assert not app.exception
    result=app.session_state["wall_mount_load_result"]
    assert len(result.anchors)==4
    assert result.max_anchor_shear_n>0
    assert result.max_anchor_tension_n>0
    assert result.force_balance_error_n<1e-9
    assert result.moment_balance_error_nm<1e-9
