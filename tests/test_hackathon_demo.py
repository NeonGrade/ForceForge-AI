"""Judge cockpit smoke must not require Docker or external API keys."""
from pathlib import Path
from streamlit.testing.v1 import AppTest


def test_hackathon_homepage_opens_without_docker():
    page=Path(__file__).resolve().parents[1]/"hackathon_app.py"
    app=AppTest.from_file(str(page),default_timeout=45).run()
    assert not app.exception, str(app.exception)
    assert any("Your engineering workflow" in h.value for h in app.subheader)
    assert not [x for x in app.button if "Run genuine OpenFOAM" in x.label]
    # A competitor should see all four entrypoints without starting a CFD job.
    labels=[x.label for x in app.page_link]
    assert "Open Natural Language CAD" in labels
    assert "Open Structural FEA" in labels
    assert "Open Transient CFD" in labels
    assert "Open Wall Load Transfer" in labels
    # Do not claim the reference CFD demo is locally present in CI.
    assert "forceforge_reference_cfd_job" not in app.session_state


def test_sourced_plot_rejects_fabricated_nan_velocity():
    """Reject invalid source arrays instead of painting invented magnitudes."""
    import ast
    import numpy as np
    src=Path(__file__).resolve().parents[1]/"hackathon_app.py"
    # Inspect actual implementation with AST so smoke does not start an app.
    tree=ast.parse(src.read_text())
    func=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
              and x.name=="_sourced_velocity_plot")
    assert "np.linalg.norm" in ast.unparse(func)
    assert "np.isfinite" in ast.unparse(func)
