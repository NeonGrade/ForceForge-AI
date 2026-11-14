import pytest
import numpy as np

from forceforge.industry import CaseInputs, SECTORS, run_industry_case, platform_summary


@pytest.mark.parametrize("sector", SECTORS)
def test_sector_runs_and_has_reproducible_audit_trace(sector):
    report=run_industry_case(CaseInputs(sector))
    repeated=run_industry_case(CaseInputs(sector))
    assert report.trace_id == repeated.trace_id
    assert report.trace_id.startswith("FFX-")
    assert len(report.scenarios)>=3
    assert all(np.isfinite(s["max_utilization"]) for s in report.scenarios)
    assert report.figures["mass_kg"]>0
    assert all(np.isfinite(np.array(report.figures["displaced"]).ravel()))
    assert report.certification_status.startswith("NOT CERTIFIED")
    assert len(report.gaps)>=4
    assert all(s["numerical_screen"] in {
        "WITHIN ILLUSTRATIVE LIMITS","EXCEEDS ILLUSTRATIVE LIMITS"
    } for s in report.scenarios)


@pytest.mark.parametrize("sector", SECTORS)
def test_load_increase_changes_response_and_trace(sector):
    standard=run_industry_case(CaseInputs(sector,load_scale=1.0))
    increased=run_industry_case(CaseInputs(sector,load_scale=1.4))
    assert increased.governing["peak_stress_mpa"]>standard.governing["peak_stress_mpa"]
    assert increased.trace_id!=standard.trace_id
    assert increased.governing["max_displacement_mm"]>standard.governing["max_displacement_mm"]


def test_cross_industry_platform_summary_no_false_certification():
    rows=platform_summary(CaseInputs("Building"))
    assert [r["sector"] for r in rows]==list(SECTORS)
    assert all(r["formal_approval"]=="NOT CERTIFIED" for r in rows)
    assert all(r["scenario_count"]==3 for r in rows)


def test_bad_inputs_rejected():
    with pytest.raises(ValueError):
        CaseInputs("Building",load_scale=-1)
    with pytest.raises(ValueError):
        CaseInputs("Building",service_cycles=0)
    with pytest.raises(ValueError):
        CaseInputs("Marine")
