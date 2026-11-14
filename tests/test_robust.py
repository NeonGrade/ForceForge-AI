from forceforge.robust import Requirements, scenarios, evaluate, grid_search, best_feasible, pareto_front
from forceforge.surrogate import train, propose_and_verify


def test_scenarios_include_design_and_challenge():
    req = Requirements()
    cases = scenarios(req)
    assert (1.,1.,1.) in cases
    assert (1.2, .9, .9) in cases
    assert len(cases) == 8


def test_mass_and_monotone_area_sensitivity():
    req = Requirements()
    light = evaluate("Triangle", 1.0, 150., req)
    heavy = evaluate("Triangle", 1.0, 300., req)
    assert heavy["mass_kg"] > light["mass_kg"]
    assert heavy["worst_displacement_util"] < light["worst_displacement_util"]
    assert heavy["worst_buckling_util"] < light["worst_buckling_util"]


def test_optimizer_and_surrogate_have_only_verified_outputs():
    req = Requirements()
    results = grid_search(req, heights=(.8,1.,1.2), areas_mm2=(100.,140.,180.,230.,300.,400.,550.,700.))
    assert len(results) == 3*3*8
    best = best_feasible(results)
    assert best is not None and best["worst_utilization"] <= 1.0+1e-10
    assert not pareto_front(results).empty
    model, cols, metrics = train(results)
    assert all(key in metrics for key in ("worst_stress_util","worst_displacement_util","worst_buckling_util"))
    verified = propose_and_verify(model, cols, req, n=40)
    assert len(verified) <= 12
    assert "worst_utilization" in verified


def test_local_section_area_elasticity():
    from forceforge.sensitivity import elasticities
    req = Requirements()
    s = elasticities("Triangle", 1., 200., req)
    get = lambda name: s[(s.Parameter=="area_mm2") & (s.Output==name)].iloc[0]["Local elasticity"]
    assert abs(get("mass_kg") - 1.) < .001
    assert abs(get("worst_displacement_util") + 1.) < .002
    assert abs(get("worst_buckling_util") + 2.) < .004


def test_challenge_60_percent_load_catches_member_buckling():
    """A +60% load is NOT covered by the original +20% robust design."""
    from dataclasses import replace

    original_req = Requirements()
    initial = evaluate("Triangle", .8, 180., original_req)
    assert initial["feasible"]
    assert initial["worst_buckling_util"] < 1.0

    challenged_req = replace(original_req, load_uncertainty=.60)
    reevaluated = evaluate("Triangle", .8, 180., challenged_req)
    assert not reevaluated["feasible"]
    assert reevaluated["worst_buckling_util"] > 1.0
    # At fixed E and area, axial force and utilization increase linearly with load.
    assert abs(reevaluated["worst_buckling_util"]
               / initial["worst_buckling_util"] - 1.60/1.20) < 1e-10


def test_expanded_challenge_reoptimization_stays_physics_verified():
    from dataclasses import replace

    original_req = Requirements()
    earlier = evaluate("Triangle", .8, 180., original_req)
    expanded_req = replace(original_req, load_uncertainty=.60)
    expanded_results = grid_search(expanded_req)
    new_best = best_feasible(expanded_results)
    assert new_best is not None
    assert new_best["feasible"]
    assert new_best["worst_utilization"] <= 1.0
    assert new_best["mass_kg"] > earlier["mass_kg"]
