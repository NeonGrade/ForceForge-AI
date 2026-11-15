"""Measured Gmsh-only mesh calibration on the original 8 mm drilled STEP.

No FEA computed in this diagnostic. Actual counts help choose TWO
independent dual-box field sizes that generate useful refinement while
respecting the existing 1,400-input-tet interactive limit.

Centers are frozen from the actual earlier FE audit (PR #16) and are only
valid for this identical L-bracket geometry. They must not be reused to
claim stress convergence on other imported STEP shapes.
"""
from __future__ import annotations
import json

from forceforge.step_mesh import generated_bracket_step, mesh_step_bytes

CENTERS_M = [
    [0.006894427190999917, 0.012383162794280898, 0.009155427371529477],
    [0.006894427190999917, 0.031651003722976732, 0.009109536468423034],
]


def main():
    data = generated_bracket_step(web_mm=8.)
    baseline=mesh_step_bytes(
        data, source_label="8 mm drilled L-bracket",mesh_size_mm=12,
        unit="mm",max_tets=1400,
    )
    designs=[
        (.20, (.70, .50)),
        (.22, (.68, .48)),
        (.24, (.65, .45)),
        (.26, (.70, .50)),
        (.28, (.72, .52)),
        (.30, (.75, .55)),
    ]
    print("BASE:", baseline.num_tets, "tetrahedra, source", baseline.source_sha256)
    results=[]
    for radius, factors in designs:
        counts=[]
        for factor in factors:
            try:
                m=mesh_step_bytes(
                    data,source_label="real 8mm L-bracket",
                    mesh_size_mm=12,unit="mm",max_tets=1400,
                    local_refinement={
                        "centers_m":CENTERS_M,
                        "size_factor":factor,
                        "radius_fraction":radius,
                    },
                )
                counts.append(m.num_tets)
            except ValueError as exc:
                counts.append(None)
                print("MESH REJECTED:",radius,factor,str(exc))
        growth=(
            round(100*(counts[1]/counts[0]-1),3)
            if all(c is not None for c in counts) else None
        )
        item={
            "radius_fraction":radius,"factors":factors,
            "counts":counts,"growth_pct":growth,
            "first_vs_baseline_growth_pct":(
                round(100*(counts[0]/baseline.num_tets-1),3)
                if counts[0] is not None else None
            ),
            "under_1400":all(c is not None for c in counts),
        }
        print("MESH RESULT:",json.dumps(item))
        results.append(item)
    suitable=[x for x in results if (
        x["under_1400"] and
        x["growth_pct"] is not None and x["growth_pct"]>=10 and
        x["first_vs_baseline_growth_pct"]>=10
    )]
    print("MESH-ONLY CANDIDATES (NO STRESS CLAIM):",json.dumps(suitable))
    if not suitable:
        raise SystemExit(
            "No dual-hotspot candidate meets actual mesh growth constraints; "
            "do not lower FE acceptance thresholds."
        )


if __name__=="__main__":
    main()
