"""Independent tests for the explicitly assumed robust design envelope."""
from dataclasses import replace
import pytest
from forceforge.beam_stress import StaticCase, solve_static
from forceforge.reliability import (
    UncertaintyBox, evaluate_robust, search_robust, worst_corner,
)


def test_user_screenshot_nominal_pass_can_fail_robust_load_challenge():
    case=StaticCase(force_n=.26,thickness_ratio=1.10,
                    displacement_limit_mm=3.25)
    check=evaluate_robust(case,UncertaintyBox(.10,.10,.05))
    assert check.nominal.tip_mm == pytest.approx(3.158,abs=.010)
    assert check.nominal.displacement_utilization<1
    assert check.checked_corners==8
    assert check.worst.tip_mm>3.25
    assert not check.passes
    assert check.worst_displacement_utilization>1.0


def test_robust_reoptimization_rechecks_actual_fea():
    case=StaticCase(force_n=.26,thickness_ratio=1.10,
                    displacement_limit_mm=3.25)
    box=UncertaintyBox(.10,.10,.05)
    result=search_robust(case,box)
    assert not result.check.passes
    assert result.best is not None
    assert result.best.case.thickness_ratio==pytest.approx(1.25)
    assert result.best_worst.tip_mm<=3.25
    confirm=evaluate_robust(result.best.case,box,check_all=True)
    assert confirm.passes
    assert confirm.checked_corners==8
    assert result.best.mass_kg>result.check.nominal.mass_kg


def test_robust_corner_check_is_monotonic_for_load_e_and_thickness():
    c=StaticCase(force_n=.21,thickness_ratio=1.20)
    box=UncertaintyBox(.20,.15,.05)
    chk=evaluate_robust(c,box)
    assert chk.worst.tip_mm>=chk.nominal.tip_mm
    assert chk.worst.stress_max_mpa>=chk.nominal.stress_max_mpa
    worst=worst_corner(c,box)
    assert chk.worst.tip_mm==pytest.approx(worst.tip_mm)


def test_uncertainty_rejects_impossible_decrements():
    with pytest.raises(ValueError):
        UncertaintyBox(thickness_reduction=.4)
    with pytest.raises(ValueError):
        UncertaintyBox(modulus_reduction=1.0)


def test_robust_search_never_accepts_section_outside_fea_domain():
    c=StaticCase(force_n=.10,thickness_ratio=.75,
                 displacement_limit_mm=5)
    run=search_robust(c,UncertaintyBox(.05,.05,.10))
    assert run.tested<18
    assert run.best is not None


def test_robust_zero_uncertainty_reduces_to_nominal_design():
    case=StaticCase(force_n=.22,thickness_ratio=1.0)
    check=evaluate_robust(case,UncertaintyBox(0,0,0))
    assert check.worst.tip_mm==pytest.approx(check.nominal.tip_mm)
    assert check.worst.stress_max_mpa==pytest.approx(check.nominal.stress_max_mpa)
