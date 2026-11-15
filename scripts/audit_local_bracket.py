"""Reproduce the hackathon L-bracket stress-sensitive case with real STEP/FE.

Run in CI on macOS Python 3.13 and Linux with Gmsh installed.
A log/JSON artifact contains actual pre/post mesh counts, exact FE stress
statistics, source SHA and engineering verdicts, not simulated test numbers.
"""
from __future__ import annotations
from pathlib import Path
import json
from forceforge.cad_solid import CadLoad
from forceforge.isolated_cad import generate_bracket_safely,analyze_step_safely
from forceforge.mesh_verification import run_mesh_evidence
from forceforge.local_refinement import run_hotspot_refinement

def main():
    source=generate_bracket_safely(8.)
    load=CadLoad(force_n=250.,force_axis=0,boundary_axis=2)
    baseline=analyze_step_safely(
        source,source_label="CAD 8mm L bracket",mesh_size_mm=12.,
        unit="mm",load=load
    )
    global_study=run_mesh_evidence(
        source,baseline,source_label="CAD 8mm L bracket",
        unit="mm",solve_at=analyze_step_safely
    )
    local_study=run_hotspot_refinement(
        source,baseline,source_label="CAD 8mm L bracket",
        unit="mm",solve_at=analyze_step_safely
    )
    result={
        "scenario":"Actual Gmsh STEP L-bracket 8 mm web, 250 N transverse X, ideal Z-min clamp",
        "source_sha256":baseline.mesh.source_sha256,
        "gauss_sample_count":len(baseline.gauss_points_m),
        "global_mesh_evidence":global_study.as_dict(),
        "targeted_hotspot_evidence":local_study.as_dict(),
        "physical_validation":"No matched static experiment or actual fixture qualification"
    }
    Path("forceforge_v11_real_stress_audit.json").write_text(
        json.dumps(result,indent=2)
    )
    print(json.dumps({
        "base_tetra":baseline.mesh.num_tets,
        "global_tetra_counts":[r.tetrahedra for r in global_study.ordered_rows],
        "global_displacement_status":global_study.decision,
        "global_peak_status":global_study.local_peak_status,
        "global_peak_difference_percent":global_study.fine_vs_medium_stress_percent,
        "fixed_region_stress_difference_percent":global_study.fine_medium_probe_mean_percent,
        "peak_xyz_mm":(baseline.sampled_peak_location_m*1000).tolist(),
        "local_refinement_tetra":[r.mesh_tetra_count for r in local_study.steps],
        "local_refinement_status":local_study.status,
        "local_last_peak_percent":local_study.peak_change_percent,
        "local_last_probe_mean_percent":local_study.region_mean_change_percent,
        "local_last_probe_p90_percent":local_study.region_p90_change_percent,
        "local_hotspot_movement_mm":local_study.hotspot_move_mm,
        "local_peak_near_ideal_support":local_study.peak_near_fixed_boundary,
        "local_refinement_monotone":local_study.refinement_mono,
        "local_verdict_explanation":local_study.explanation,
        "local_peak_coordinates_mm":[r.peak_xyz_mm for r in local_study.steps],
        "local_sampled_stresses_mpa":[r.global_peak_mpa for r in local_study.steps],
        "local_probe_mean_mpa":[r.region_mean_mpa for r in local_study.steps],
        "local_probe_p90_mpa":[r.region_p90_mpa for r in local_study.steps],
    },indent=2))
    # Do not claim targeted refinement when actual tetra counts fail to grow.
    if not local_study.refinement_mono:
        raise SystemExit(
            "Local Gmsh hotspot refinement failed to increase actual "
            "tetra counts by at least 10% in both steps; tune local size "
            "field instead of claiming an improvement."
        )

if __name__=="__main__":
    main()
