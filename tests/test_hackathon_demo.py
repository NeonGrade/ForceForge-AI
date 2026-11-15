"""Judge cockpit smoke must not start Docker, create fake U/p, or use API keys."""
import ast
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import pytest
from streamlit.testing.v1 import AppTest


def test_hackathon_homepage_opens_without_docker():
    page=Path(__file__).resolve().parents[1]/"hackathon_app.py"
    app=AppTest.from_file(str(page),default_timeout=45).run()
    assert not app.exception, str(app.exception)
    assert any("Your engineering workflow" in h.value for h in app.subheader)
    assert not [x for x in app.button if "Run genuine OpenFOAM" in x.label]
    links=[x.label for x in app.page_link]
    assert "Open Natural Language CAD" in links
    assert "Open Structural FEA" in links
    assert "Open Transient CFD" in links
    assert "Open Wall Load Transfer" in links
    assert "forceforge_reference_cfd_job" not in app.session_state


def _load_visual_function():
    """Isolate just the verified-array renderer; homepage itself has side effects."""
    src=Path(__file__).resolve().parents[1]/"hackathon_app.py"
    tree=ast.parse(src.read_text(encoding="utf-8"))
    node=next(x for x in tree.body
              if isinstance(x,ast.FunctionDef) and x.name=="_sourced_velocity_plot")
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    namespace={"np":np,"go":go}
    exec(compile(module,str(src),"exec"),namespace)
    return namespace["_sourced_velocity_plot"]


def test_sourced_velocity_plot_uses_only_actual_input_arrays():
    render=_load_visual_function()
    # Synthetic fixtures are TESTS ONLY; never shown in the product UI.
    xyz=np.array([
        [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]],
        [[0.,0.,.1],[1.,0.,.1],[0.,1.,.1]]
    ])
    vel=np.array([
        [[0.,0.,0.],[1.,0.,0.],[0.,0.,2.]],
        [[0.,0.,0.],[2.,0.,0.],[0.,3.,0.]]
    ])
    fig=render({"sample_points":xyz,"velocity_m_s":vel})
    assert fig.data[0].type=="scatter3d"
    assert list(fig.data[0].marker.color)==pytest.approx([0.,2.,3.])
    assert len(fig.data[0].x)==3
    with pytest.raises(ValueError,match="No finite"):
        render({
            "sample_points":np.full((2,3,3),np.nan),
            "velocity_m_s":np.zeros((2,3,3))
        })
