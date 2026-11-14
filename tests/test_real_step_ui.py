"""Browser-level interaction against the actual STEP mesher (Gmsh optional).

Run in the dedicated Gmsh CI job. The existing 3D, modal and ML test
suite continues in the standard Python jobs without gmsh.
"""
import pytest
pytest.importorskip('gmsh')
from streamlit.testing.v1 import AppTest


def _get_button(app,label):
    return next(b for b in app.button if b.label==label)


def test_real_step_studio_opens_with_drilled_parametric_cad_and_solved_volume():
    app=AppTest.from_file('../pages/13_Real_STEP_Engineering.py',
                          default_timeout=100).run()
    assert not app.exception
    labels={x.label for x in app.metric}
    assert 'Solid tetrahedra' in labels
    assert 'Sampled peak von Mises' in labels
    assert 'Reaction residual' in labels
    assert _get_button(app,'Re-mesh revised CAD and re-run 3D FEA')


def test_real_step_before_after_regenerates_cad_and_independently_solves():
    app=AppTest.from_file('../pages/13_Real_STEP_Engineering.py',
                          default_timeout=150).run()
    assert not app.exception
    _get_button(app,'Re-mesh revised CAD and re-run 3D FEA').click().run()
    assert not app.exception
    previous=app.session_state['real_cad_revision']
    assert previous['result'].mesh.num_tets>0
    assert previous['result'].relative_reaction_residual<1e-7
    assert previous['result'].mesh.source_sha256!=previous['inputs'][0]
