from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from forceforge.agent import ProposedRequirements, explain_design, interpret, parse_offline
from forceforge.robust import Requirements, evaluate, grid_search
from forceforge.surrogate import train, propose_and_verify


@pytest.fixture(scope="module")
def trained():
    req = Requirements()
    data = grid_search(req, heights=(.8, 1., 1.2), areas_mm2=(100., 180., 300., 550.))
    return req, data, train(pd.concat([data, data], ignore_index=True))


def test_duplicate_groups_do_not_leak(trained):
    _, _, (model, _, metrics) = trained
    info = model.forceforge_validation_
    assert set(info["train_groups"]).isdisjoint(info["test_groups"])
    assert info["train_rows"] + info["test_rows"] == 72
    assert all(np.isfinite(m["baseline_mae"]) for m in metrics.values())


def test_proposals_match_exact_solver_and_domain(trained):
    req, _, (model, cols, _) = trained
    verified = propose_and_verify(model, cols, req, n=300)
    assert len(verified) == 12
    assert verified.height_m.between(.8, 1.2).all()
    assert verified.area_mm2.between(100., 550.).all()
    for row in verified.to_dict("records"):
        exact = evaluate(row["topology"], row["height_m"], row["area_mm2"], req)
        assert row["feasible"] == exact["feasible"]
        assert row["worst_utilization"] == pytest.approx(exact["worst_utilization"])


@pytest.mark.parametrize("text", [
    "2 m bridge, 1 kN, displacement limit 2 mm",
    "跨度 2 米，载荷 1000 牛顿，位移 2 毫米",
    "200 cm bridge, 1000 N, 2 mm",
])
def test_parser_units(text):
    parsed = parse_offline(text)
    assert (parsed.span_m, parsed.load_n, parsed.max_displacement_mm) == (2., 1000., 2.)


@pytest.mark.parametrize("text", ["-2 m 1000 N", "2 m -1000 N", "2 m 3 m", "6 m"])
def test_parser_rejects_invalid_or_ambiguous(text):
    with pytest.raises(ValueError):
        parse_offline(text)


def test_api_failure_falls_back(monkeypatch):
    import openai
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    client = Mock()
    client.responses.parse.side_effect = RuntimeError("simulated offline")
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: client)
    parsed = interpret("2 m 1000 N 2 mm", use_api=True)
    assert parsed.load_n == 1000
    assert "API unavailable" in parsed.rationale


def test_schema_rejects_nan():
    with pytest.raises(ValueError):
        ProposedRequirements(span_m=float("nan"), load_n=1000, max_displacement_mm=2, rationale="test")


def test_failed_candidate_is_not_described_as_passing():
    row = evaluate("Triangle", 1., 100., Requirements(base_load_n=5000))
    assert not row["feasible"]
    assert "FAIL" in explain_design(row)


def test_ui_invalidates_ml_results():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("../app.py", default_timeout=90).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Propose with ML and verify with FEA").click().run()
    assert not app.exception
    assert "ml_verified" in app.session_state
    app.sidebar.slider[1].set_value(1200).run()
    assert not app.exception
    assert "ml_verified" not in app.session_state
