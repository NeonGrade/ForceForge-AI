"""Real laboratory homepage and CAD/measurement provenance tests."""
from pathlib import Path
import csv
import pytest


def test_documented_3d_cad_files_are_present_and_not_empty():
    root=Path(__file__).resolve().parents[1]
    step=root/"assets/benchmark/hannover_steel_beam_reconstructed.step"
    stl=root/"assets/benchmark/hannover_steel_beam_reconstructed_ascii.stl"
    assert step.exists() and step.stat().st_size>1000
    assert "ISO-10303-21" in step.read_text()[:100]
    assert stl.exists() and stl.stat().st_size>1000
    assert stl.read_text().startswith("solid")
    assert (root/"docs/BENCHMARK_CAD_PROVENANCE.md").exists()


def test_published_lab_mode_table_is_not_synthetic():
    root=Path(__file__).resolve().parents[1]
    with (root/"data/benchmark/real_modal_modes.csv").open() as stream:
        values=list(csv.DictReader(stream))
    assert len(values)==3
    assert [float(x["measured_frequency_hz"]) for x in values]==[1.569,10.389,29.619]
    assert [float(x["published_updated_abaqus_frequency_hz"]) for x in values]==[1.698,10.775,30.59]


def test_home_page_uses_real_lab_measurements_and_3d_interactivity():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file("../app.py",default_timeout=90).run()
    assert not app.exception
    labels=[x.label for x in app.metric]
    assert "Measured first frequency" in labels
    assert "Our FE first frequency" in labels
    assert any(b.label=="Calibrate using measured Mode 1" for b in app.button)
    assert any(s.key=="lab_logk" for s in app.sidebar.slider)


def test_click_calibration_updates_support_parameter_and_preserves_readout():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file("../app.py",default_timeout=90).run()
    assert not app.exception
    next(b for b in app.button if b.label=="Calibrate using measured Mode 1").click().run()
    assert not app.exception
    assert float(app.session_state["lab_logk"])==pytest.approx(2.673,abs=.02)
    assert app.session_state["lab_fitted"] is True
    assert any(x.label=="Mode 2 held-out error" for x in app.metric)
