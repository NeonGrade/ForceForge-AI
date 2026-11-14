"""Golden-case tests: prevent regressions when expanding the UI and models."""
from pathlib import Path
import ast
import pytest
from forceforge.decision import demo_case, recommend_design
from forceforge.industry import run_industry_case

@pytest.mark.parametrize("sector,initial_u,improved_u,member_mass,change_pct",[
    ("Building",0.4907,0.9401,119.104125,-27.75),
    ("Industrial",1.793,0.9946,32.227651246,21.0),
    ("Automotive",0.1100,0.2158,2.499411948,-51.0),
])
def test_judge_facing_baseline_and_redesign_regression(sector,initial_u,improved_u,member_mass,change_pct):
    result=recommend_design(demo_case(sector,load_scale=1.6))
    assert result.baseline.governing["max_utilization"]==pytest.approx(initial_u,abs=2e-4)
    assert result.redesigned.governing["max_utilization"]==pytest.approx(improved_u,abs=2e-4)
    assert result.redesigned.figures["mass_kg"]==pytest.approx(member_mass,rel=1e-6)
    assert result.mass_delta_percent==pytest.approx(change_pct,abs=.01)

def test_numerical_trace_is_not_approval():
    for sector in ("Building","Industrial","Automotive"):
        report=run_industry_case(demo_case(sector))
        assert "NOT CERTIFIED" in report.certification_status
        assert "MISSING" in {row["status"] for row in report.verification}

def test_ui_sources_still_parse():
    root=Path(__file__).resolve().parents[1]
    for candidate in ["app.py","pages/5_Advanced_Structural_Lab.py",
                      "pages/6_Cross_Industry_Platform.py",
                      "pages/7_Engineering_Workbench.py"]:
        ast.parse((root/candidate).read_text())
