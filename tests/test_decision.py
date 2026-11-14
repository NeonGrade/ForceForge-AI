from dataclasses import replace
import pytest

from forceforge.industry import CaseInputs, run_industry_case, SECTORS
from forceforge.decision import MISSIONS, demo_case, recommend_design


@pytest.mark.parametrize("sector", SECTORS)
def test_demo_has_clear_problem_and_reproducible_default(sector):
    case = demo_case(sector, load_scale=1.6)
    assert MISSIONS[sector].headline
    a = run_industry_case(case)
    b = run_industry_case(case)
    assert a.trace_id == b.trace_id
    assert a.figures["mass_kg"] > 0
    assert a.certification_status.startswith("NOT CERTIFIED")


@pytest.mark.parametrize("sector", SECTORS)
def test_section_radius_controls_mass_physically(sector):
    standard = demo_case(sector)
    larger = replace(standard, section_scale=1.2)
    before = run_industry_case(standard)
    after = run_industry_case(larger)
    assert after.figures["mass_kg"]/before.figures["mass_kg"] == pytest.approx(1.2**2,rel=1e-9)
    assert after.trace_id != before.trace_id


@pytest.mark.parametrize("sector", SECTORS)
def test_feaverified_recommendation_never_claims_certification(sector):
    case = demo_case(sector, load_scale=1.6)
    result = recommend_design(case)
    assert result.alternatives_checked > 0
    assert result.feasible_candidates <= result.alternatives_checked
    if result.redesigned is not None:
        assert result.redesigned.governing["max_utilization"] <= 1.0+1e-10
        assert result.design_inputs is not None
        assert result.redesigned.trace_id == run_industry_case(result.design_inputs).trace_id
        assert result.redesigned.certification_status.startswith("NOT CERTIFIED")
        assert result.mass_delta_percent is not None


def test_industrial_resizing_alone_is_insufficient_and_joint_revision_helps():
    result = recommend_design(demo_case("Industrial", load_scale=1.6))
    assert result.baseline.governing["max_utilization"] > 1.0
    assert result.redesigned is not None
    assert result.design_inputs.joint_stiffness_nm_rad > 200_000
    assert result.redesigned.governing["max_utilization"] <= 1.0
    assert result.mass_delta_percent > 0


def test_building_can_reduce_member_mass_under_modeled_limits():
    result = recommend_design(demo_case("Building", load_scale=1.6))
    assert result.redesigned is not None
    assert result.mass_delta_percent < 0
    assert result.redesigned.governing["max_utilization"] <= 1


def test_invalid_member_radius_rejected():
    with pytest.raises(ValueError, match="radius"):
        CaseInputs("Building", section_scale=.2)


def test_empty_feasible_set_is_reported_honestly():
    result = recommend_design(demo_case("Industrial", load_scale=3.0),
                              radii=(.7,), joint_options=(1.0,))
    assert result.redesigned is None
    assert result.feasible_candidates == 0
