"""Real generated STEP -> independent dual-box Gmsh meshes -> tetra10 FEA.

No fabricated stresses: five isolated FE solves from the same actual STEP
(three original local-refinement meshes, then two dual-site meshes).
The two center positions are frozen BEFORE the last two FE solutions.
"""
from hashlib import sha256

import numpy as np
import pytest

pytest.importorskip("gmsh")

from forceforge.cad_solid import CadLoad
from forceforge.dual_hotspot import run_dual_hotspot_study
from forceforge.isolated_cad import generate_bracket_safely, analyze_step_safely
from forceforge.local_refinement import run_hotspot_refinement


def test_real_drilled_step_both_competing_sites_are_remeshed_and_solved():
    step=generate_bracket_safely(8.)
    load=CadLoad(force_n=250,force_axis=0,boundary_axis=2)
    base=analyze_step_safely(
        step,source_label="real 8 mm L-bracket",
        mesh_size_mm=12,unit="mm",load=load,
    )
    prior=run_hotspot_refinement(
        step,base,source_label="real 8 mm L-bracket",
        unit="mm",solve_at=analyze_step_safely,
    )
    assert len(prior.matched_physical_hotspot_regions)==2, (
        "Expected the two competing physical hotspots recorded in "
        "v1.1. No synthetic sites may substitute for actual FE results."
    )
    dual=run_dual_hotspot_study(
        step,base,prior,source_label="real 8 mm L-bracket",
        unit="mm",solve_at=analyze_step_safely,
    )
    assert dual.source_sha256==sha256(step).hexdigest()
    assert len(dual.site_rows)==2, "Both physical sites need actual Gauss support"
    assert len(dual.steps)==2
    assert dual.steps[0].mesh_tetra_count>0
    assert dual.steps[1].mesh_tetra_count>0
    assert all(row["mesh_A_gauss_samples"]>=12 for row in dual.site_rows)
    assert all(row["mesh_B_gauss_samples"]>=12 for row in dual.site_rows)
    assert all(row["radius_mm"]==7 for row in dual.site_rows)
    assert np.isfinite(dual.global_peak_movement_mm)
    assert dual.global_peak_status in {
        "PEAK_STRESS_UNRESOLVED",
        "PRELIMINARY_NUMERICAL_PEAK_SCREEN_NOT_CERTIFIED",
    }
    assert dual.status in {
        "INSUFFICIENT_DUAL_SITE_REFINEMENT",
        "DUAL_SITE_PROBES_UNRESOLVED",
        "DUAL_SITE_STRESS_NOT_STABLE",
        "SUPPORT_SINGULARITY_RISK",
        "PRELIMINARY_DUAL_SITE_NUMERICAL_STABILITY",
    }
    assert "NOT" in dual.limitations
    print("ACTUAL DUAL HOTSPOT STUDY:",dual.as_dict())
