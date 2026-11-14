"""True 3D C3D10-style tetrahedral solid FEA demonstration.

This page is kept separate from the licensed real modal specimen. Its
dimensions and static load are an original verification benchmark, not a
measured vehicle, industrial bracket or building component.
"""
from dataclasses import replace,asdict
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.solid3d import SolidCase,solve_solid,surface_figure

st.set_page_config(page_title="ForceForge X | True 3D Solid FEA",
                   page_icon="🔩",layout="wide")
st.markdown("[← Return to published laboratory benchmark](/)")
st.title("True 3D Solid FEA — Volume Elements, Not Surface Coloring")
st.markdown(
    "The structural solver now assembles a **3D linear-elastic model with "
    "10-node quadratic tetrahedral elements**. Each node has 3 displacement "
    "degrees of freedom, loads are integrated over the end face, and stresses "
    "are recovered from volumetric elements."
)
st.caption(
    "Geometry: an original 120 × 30 × 12 mm solid cantilever verification "
    "specimen. It is not a source CAD model of a real manufactured bracket "
    "or a physically validated static test."
)

with st.sidebar:
    st.subheader("Solid specimen")
    st.caption("3D dimensions are regenerated before every new FEA run.")
    thickness_mm=st.slider("Thickness (mm)",8,20,12,1)
    force_n=st.slider("Distributed transverse end load (N)",50,500,200,10)
    allowed=st.slider("Illustrative tip movement limit (mm)",.04,.30,.12,.01)
    mesh_quality=st.selectbox(
        "Tetrahedral resolution",
        ["Fast · 2×2×8","Refined · 2×2×12","Higher resolution · 3×3×12"],
        index=1
    )
    exaggeration=st.slider("Visual-only deformation multiplier",1,120,60,5)
    st.caption("Fixed base face, uniformly distributed tip traction, "
               "isotropic steel E=210 GPa, nu=0.30. These properties are assumptions.")
    st.divider()
    st.markdown("[Published real laboratory modal validation](/)")
    st.markdown("[Previous 1D stress / robust redesign](/3D_CAD_Simulation)")

resolutions={
    "Fast · 2×2×8":(2,2,8),
    "Refined · 2×2×12":(2,2,12),
    "Higher resolution · 3×3×12":(3,3,12),
}
nx,ny,nz=resolutions[mesh_quality]
case=SolidCase(
    length_m=.120,width_m=.030,thickness_m=thickness_mm/1000,
    force_n=force_n,nx=nx,ny=ny,nz=nz
)


@st.cache_data(show_spinner=False)
def calculate(c: SolidCase):
    return solve_solid(c)


with st.spinner("Assembling 3D tetrahedral elasticity and solving sparse FEM system..."):
    result=calculate(case)

p1,p2,p3,p4=st.columns(4)
p1.metric("3D FE tip movement",f"{result.tip_displacement_mm:.4f} mm")
p2.metric("Max Gauss-point von Mises",f"{result.max_mises_mpa:.2f} MPa")
p3.metric("Solid mass",f"{result.mass_kg:.3f} kg")
p4.metric("Volume tetra10 elements",f"{len(result.tets10):,}")

if result.tip_displacement_mm>allowed:
    st.error("Modeled displacement exceeds the selected illustrative limit. "
             "Modify thickness or load and re-solve.")
else:
    st.success("Model displacement is within the selected illustrative "
               "limit. This is a numerical check, not a safety certification.")

st.plotly_chart(
    surface_figure(result,deformation_scale=exaggeration),
    key="solid_fea_surface",width="stretch"
)
st.caption(
    "The color shows the largest sampled von Mises stress among four "
    "integration points in each quadratic tetrahedron, mapped to external "
    "element faces. The actual interior field can vary within each element. "
    "Displacement is exaggerated for viewing; clamped-edge peaks are "
    "sensitive to mesh resolution."
)

st.subheader("Independent numerical verification")
q1,q2,q3=st.columns(3)
q1.metric("3D volume force-balance residual",
          f"{result.relative_reaction_residual:.2e}")
q2.metric("Euler–Bernoulli reference displacement",
          f"{result.beam_reference_tip_mm:.4f} mm")
q3.metric("3D vs beam reference difference",
          f"{result.beam_reference_error_pct:+.2f}%")
st.caption(
    "The beam formula is a separate theoretical reference, not measured "
    "deflection. A 3D stress tensor and quadratic volume elements are "
    "being solved; the agreement is checked, not assumed."
)

with st.expander("Inspect mesh and material assumptions"):
    st.write(
        f"{len(result.nodes_m):,} solid nodes with three displacement DOFs "
        f"each, {len(result.tets10):,} curved-order quadratic tetrahedra "
        "(straight-edged geometry), 4-point volume integration."
    )
    st.write("Minimum tetrahedral volume (m³):",
             float(np.min(result.element_volumes_m3)))
    st.write("Support reaction vector (N):",
             result.support_reaction_n.tolist())
    st.write("This prototype generates a structured tetrahedral volume mesh "
             "from parametric solid dimensions; arbitrary STEP file import "
             "and CAD assembly topology are not implemented here.")
    st.write("Yield strength 250 MPa is an assumed illustrative limit. "
             "Peak FEA stress near a fully fixed clamp depends on mesh "
             "refinement and boundary representation.")

st.divider()
st.subheader("Modify the real 3D mesh and re-solve")
st.write(
    "Choose a manufacturable thickness candidate. This regenerates the "
    "**actual 3D volume mesh**, not just a colored surface, and re-solves "
    "all 3D degrees of freedom."
)
if st.button("Find lighter feasible solid thickness (3D FEA)",type="primary"):
    options=[]
    with st.spinner("Rebuilding 3D meshes and running volume FEA for each candidate..."):
        for t in (8,10,11,12,13,14,16,18,20):
            candidate=replace(case,thickness_m=t/1000)
            r=calculate(candidate)
            options.append((t,r))
    feasible=[(t,r) for t,r in options
              if r.tip_displacement_mm <= allowed and
                 r.max_mises_mpa <= 250]
    best=min(feasible,key=lambda pair:pair[1].mass_kg) if feasible else None
    st.session_state["solid_redesign"]={
        "inputs":(case,allowed),"options":options,"selected":best
    }
stored=st.session_state.get("solid_redesign")
if stored is not None and stored["inputs"]!=(case,allowed):
    st.warning("FE geometry, force, mesh or limit changed. Previous redesign "
               "is hidden until the 3D solid analysis is rerun.")
    stored=None
if stored is not None:
    st.write(f"Re-solved {len(stored['options'])} independent 3D solid FE meshes.")
    if stored["selected"] is None:
        st.error("No thickness candidate meets the assumed displacement and "
                 "250 MPa von Mises limits.")
    else:
        thick,best=stored["selected"]
        a,b,c=st.columns(3)
        a.metric("Selected 3D solid thickness",f"{thick} mm")
        b.metric("3D FEA displacement",f"{best.tip_displacement_mm:.4f} mm")
        c.metric("Solid mass change",f"{(best.mass_kg/result.mass_kg-1)*100:+.1f}%")
        shared_stress=1.01*max(best.max_mises_mpa,result.max_mises_mpa)
        st.caption(
            f"Both charts use the same 0–{shared_stress:.2f} MPa stress scale. "
            "Every candidate is a new SOLID volume FE solution."
        )
        left,right=st.columns(2)
        with left:
            st.markdown("**Current solid**")
            st.plotly_chart(surface_figure(
                result,deformation_scale=exaggeration,
                stress_cmax_mpa=shared_stress
            ),key="solid_before",width="stretch")
        with right:
            st.markdown("**Revised solid**")
            st.plotly_chart(surface_figure(
                best,deformation_scale=exaggeration,
                stress_cmax_mpa=shared_stress
            ),key="solid_after",width="stretch")
        st.dataframe(pd.DataFrame([
            {"Metric":"Thickness (mm)","Before":thickness_mm,"After":thick},
            {"Metric":"Tip displacement (mm)",
             "Before":result.tip_displacement_mm,
             "After":best.tip_displacement_mm},
            {"Metric":"Peak von Mises (MPa)",
             "Before":result.max_mises_mpa,"After":best.max_mises_mpa},
            {"Metric":"Solid mass (kg)",
             "Before":result.mass_kg,"After":best.mass_kg}
        ]),hide_index=True,width="stretch")
        payload={
            "description":"Original parametric cantilever; not an experimentally validated component",
            "solver":"3D 10-node quadratic tetrahedra, 4-point integration",
            "initial":{**asdict(case),
                       "tip_mm":result.tip_displacement_mm,
                       "von_mises_mpa":result.max_mises_mpa},
            "revised":{**asdict(best.case),
                       "tip_mm":best.tip_displacement_mm,
                       "von_mises_mpa":best.max_mises_mpa},
            "limit_mm":allowed,
            "independent_reference":"Euler-Bernoulli theoretical deflection",
        }
        st.download_button("Export 3D solid FEA evidence (JSON)",
                           json.dumps(payload,indent=2),
                           file_name="forceforge_3d_solid_fem.json",
                           mime="application/json")
st.caption(
    "Engineering research only. Missing actual CAD provenance, material tests, "
    "joint stress concentration verification, code compliance and sign-off. "
    "The experimental Hannover modal benchmark remains available separately."
)
