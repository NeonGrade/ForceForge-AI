"""AI is allowed to propose bounded STEP parameter values; FEM judges everything."""
from types import SimpleNamespace
from dataclasses import replace

import pytest

from forceforge.cad_copilot import (
    THICKNESSES_MM, DesignLimits, LLMProposal, propose_designs,
    evaluate_candidate, pick_lightest_feasible,
)
from forceforge.cad_solid import CadLoad
import forceforge.cad_copilot as copilot


LIMITS = DesignLimits(.015, 16, 40)
LOAD = CadLoad(force_n=250, force_axis=0, boundary_axis=2)


def fake_result(tag, mass, tip, stress, *, loading=LOAD, quality=.05,
                volume_error=.004, equilibrium=1e-10):
    return SimpleNamespace(
        mesh=SimpleNamespace(
            source_sha256=tag, num_tets=600,
            relative_volume_difference=volume_error,
            min_shape_quality=quality,
        ),
        load=loading,
        mass_kg=float(mass),
        tip_mm=float(tip),
        peak_von_mises_mpa=float(stress),
        relative_reaction_residual=equilibrium,
    )


BASE = fake_result("original", 1.0, .0358, 18.7)
C10 = fake_result("step-10", 1.09, .018, 17.0)
C12 = fake_result("step-12", 1.20, .0116, 11.7)
C14 = fake_result("step-14", 1.30, .008, 9.5)


def test_offline_plan_evaluates_all_three_real_alternatives():
    plan = propose_designs(
        brief="minimize mass, keep displacement below the stated limit",
        original_thickness_mm=8, baseline=BASE,
        limits=LIMITS,
    )
    assert plan.mode == "RULE_BASED_FULL_SEARCH"
    assert plan.candidates_mm == (10,12,14)
    assert plan.llm_priorities_mm == ()
    assert not plan.model_name
    assert "No AI API" in plan.message


def test_missing_api_key_is_not_mislabeled_ai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    plan=propose_designs(
        brief="lighter bracket", original_thickness_mm=8,
        baseline=BASE, limits=LIMITS, use_api=True,
    )
    assert plan.mode=="RULE_BASED_FULL_SEARCH"
    assert "no api key" in plan.message.lower()


def test_valid_llm_only_changes_priority_not_eval_coverage(monkeypatch):
    monkeypatch.setattr(
        copilot, "_llm_proposal", lambda **kw: LLMProposal(
            candidate_thickness_mm=[14, 12],
            rationale="Increase section stiffness first; FEA still decides."
        ),
    )
    plan = propose_designs(
        brief="bracket should be stiffer", original_thickness_mm=8,
        baseline=BASE, limits=LIMITS, use_api=True, api_key="test-only",
    )
    assert plan.mode=="LLM_PRIORITIZED_WITH_REAL_FEA"
    assert plan.llm_priorities_mm == (14,12)
    assert plan.candidates_mm == (14,12,10)


def test_invalid_hallucinated_llm_dimension_triggers_labeled_fallback(monkeypatch):
    monkeypatch.setattr(
        copilot, "_llm_proposal", lambda **kw: LLMProposal(
            candidate_thickness_mm=[999,12],
            rationale="unsupported hallucinated size"
        ),
    )
    plan=propose_designs(
        brief="test", original_thickness_mm=8,
        baseline=BASE,limits=LIMITS,use_api=True,api_key="test-only",
    )
    assert plan.mode=="RULE_BASED_FULL_SEARCH"
    assert 999 not in plan.candidates_mm
    assert "AI unavailable or invalid" in plan.message


def test_real_fea_results_determine_lightest_feasible_design():
    rows=[
        evaluate_candidate(original=BASE,candidate=can,thickness_mm=t,limits=LIMITS)
        for t,can in ((10,C10),(12,C12),(14,C14))
    ]
    assert rows[0].constraints_pass is False
    assert set(rows[0].failure_reasons)=={
        "Displacement exceeds illustrative limit",
        "Sampled stress exceeds illustrative limit",
    }
    assert rows[1].constraints_pass is True
    assert rows[2].constraints_pass is True
    assert pick_lightest_feasible(rows)==12
    assert rows[1].tetrahedra == 600
    assert rows[1].source_sha256 == "step-12"


def test_no_design_passed_is_reported_not_fabricated():
    strict=DesignLimits(.001,1,0)
    rows=[
        evaluate_candidate(original=BASE,candidate=can,thickness_mm=t,limits=strict)
        for t,can in ((10,C10),(12,C12),(14,C14))
    ]
    assert all(not row.constraints_pass for row in rows)
    assert pick_lightest_feasible(rows) is None


def test_material_change_stale_sha_and_solver_quality_are_rejected():
    with pytest.raises(ValueError,match="identical"):
        evaluate_candidate(
            original=BASE,candidate=fake_result("original",1.2,.01,10),
            thickness_mm=12,limits=LIMITS,
        )
    with pytest.raises(ValueError,match="material/force/support"):
        evaluate_candidate(
            original=BASE,candidate=fake_result(
                "changed",1.2,.01,10,loading=CadLoad(force_n=350)
            ),
            thickness_mm=12,limits=LIMITS,
        )
    bad=fake_result("changed",1.2,.01,10,quality=0)
    row=evaluate_candidate(original=BASE,candidate=bad,thickness_mm=12,limits=LIMITS)
    assert not row.constraints_pass
    assert not row.numerical_qa_pass


def test_limits_and_intent_are_bounded():
    for x in [float("inf"),float("nan"),0,-1,500]:
        with pytest.raises(ValueError):
            DesignLimits(x,16,40)
    with pytest.raises(ValueError,match="500 characters"):
        propose_designs(
            brief="a"*501, original_thickness_mm=8,
            baseline=BASE, limits=LIMITS,
        )
    with pytest.raises(ValueError):
        propose_designs(
            brief="test",original_thickness_mm=99,
            baseline=BASE,limits=LIMITS,
        )
