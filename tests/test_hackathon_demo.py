"""Smoke-test the judge-facing entrypoint (must not launch OpenFOAM)."""
from pathlib import Path
from streamlit.testing.v1 import AppTest

def test_hackathon_homepage_opens_without_docker():
    page=Path(__file__).resolve().parents[1]/"hackathon_app.py"
    app=AppTest.from_file(str(page),default_timeout=45).run()
    assert not app.exception, str(app.exception)
    assert any("Your engineering workflow" in h.value for h in app.subheader)
    assert not [x for x in app.button if "Run genuine OpenFOAM" in x.label]
