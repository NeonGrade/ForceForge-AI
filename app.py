"""ForceForge AI 2.0: functional Streamlit engineering hackathon prototype."""
import json
import os
from dataclasses import replace
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from forceforge.design import make_truss, TOPOLOGIES
from forceforge.physics import solve
from forceforge.robust import Requirements, evaluate, grid_search, best_feasible, pareto_front
from forceforge.surrogate import train, propose_and_verify
from forceforge.agent import interpret, explain_design
from forceforge.sensitivity import elasticities

st.set_page_config(page_title="ForceForge AI 2.0", page_icon="⚙️", layout="wide")
st.title("ForceForge AI 2.0")
st.caption("Physics-verified generative truss design · uncertainty challenge · ML-assisted search")
st.warning("Research / education prototype only. Ideal pin-jointed 2D truss, small strain, linear elastic. No joint, fatigue or full structural safety certification.")

@st.cache_data(show_spinner=False)
def search_cached(req: Requirements):
    return grid_search(req)

@st.cache_resource(show_spinner=False)
def surrogate_cached(req: Requirements):
    return train(grid_search(req))

with st.sidebar:
    st.header("Design requirements")
    material_name = st.selectbox("Material", ["Steel (nominal)", "Aluminum (nominal)"])
    material_values = {"Steel (nominal)": (200e9, 7850., 250e6),
                       "Aluminum (nominal)": (70e9, 2700., 150e6)}
    E, density, sy = material_values[material_name]
    span = st.slider("Span (m)", 0.5, 4.0, 2.0, 0.1)
    force = st.slider("Nominal central force (N)", 100, 3000, 1000, 100)
    max_disp = st.slider("Maximum displacement (mm)", .25, 12., 2., .25)
    safety_y = st.slider("Yield safety factor", 1.0, 4.0, 2.0, .25)
    safety_b = st.slider("Buckling screening factor", 1.0, 4.0, 2.0, .25)
    load_unc = st.slider("Load increase considered (%)", 0, 50, 20, 5) / 100.
    e_unc = st.slider("E reduction considered (%)", 0, 35, 10, 5) / 100.
    area_unc = st.slider("Area reduction considered (%)", 0, 25, 10, 5) / 100.

req = Requirements(span_m=span, base_load_n=force, material_E_pa=E,
                   density_kg_m3=density, yield_pa=sy, max_displacement_mm=max_disp,
                   yield_safety_factor=safety_y, buckling_safety_factor=safety_b,
                   load_uncertainty=load_unc, e_uncertainty=e_unc,
                   area_uncertainty=area_unc)

if st.session_state.get("ml_requirements") != req:
    st.session_state.pop("ml_verified", None)
    st.session_state["ml_requirements"] = req


def draw_truss(t, r, exaggeration: float = 250.0):
    nodes = t.nodes_m
    displayed = nodes + r.disp_m * exaggeration
    fig = go.Figure()
    for idx,(a,b) in enumerate(t.elements):
        sign = "Tension" if r.force_n[idx]>=0 else "Compression"
        color = "#257f91" if sign == "Tension" else "#cf7840"
        fig.add_trace(go.Scatter(x=nodes[[a,b],0], y=nodes[[a,b],1],
                                 mode="lines", line=dict(color="#a6a6a6",width=2,dash="dot"),
                                 showlegend=idx==0, name="Undeformed", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=displayed[[a,b],0], y=displayed[[a,b],1],
                                 mode="lines", line=dict(color=color,width=5),
                                 name=sign, showlegend=False,
                                 hovertext=f"Member {idx} | {sign} | N={r.force_n[idx]:.1f} N | stress={r.stress_pa[idx]/1e6:.3f} MPa",
                                 hoverinfo="text"))
    fig.add_trace(go.Scatter(x=displayed[:,0],y=displayed[:,1],mode="markers+text",
                             text=[str(i) for i in range(len(nodes))],
                             textposition="top center",name="Nodes",
                             marker=dict(color="#2c7181",size=10)))
    fig.update_yaxes(scaleanchor="x",scaleratio=1)
    fig.update_layout(height=370, margin=dict(l=5,r=5,t=35,b=5),
                      title=f"{t.topology} | displayed deformation exaggerated {exaggeration:.0f}×")
    return fig


def metrics_row(t, r):
    a,b,c=st.columns(3)
    a.metric("Nominal mass",f"{r.mass_kg:.3f} kg")
    b.metric("Maximum nodal displacement",f"{r.max_disp_m*1000:.4f} mm")
    c.metric("Maximum axial stress",f"{r.max_stress_pa/1e6:.3f} MPa")


tab1,tab2,tab3,tab4=st.tabs(["1 · Physics FEA", "2 · Robust Optimization", "3 · ML Surrogate", "4 · Engineering AI Agent"])

with tab1:
    left,right=st.columns([1,2])
    with left:
        topology=st.selectbox("Topology",TOPOLOGIES)
        height=st.slider("Structure height (m)",.2*span,1.25*span,.5*span,.05*span)
        area=st.slider("Uniform solid round-bar area (mm²)",60.,800.,180.,10.)
        truss=make_truss(topology,span,height,area,force,req.material)
        result=solve(truss)
    with right:
        st.plotly_chart(draw_truss(truss,result),width="stretch")
        st.caption("Ideal pin-jointed rods. Orange=compression, teal=tension. Displacement in drawing is exaggerated.")

    # Keep engineering metrics in the full-width section. In the narrow input
    # column their values were clipped on a standard Mac laptop display.
    st.subheader("FEA results | nominal load")
    metrics_row(truss,result)

    member_table = pd.DataFrame({
        "Member": range(len(truss.elements)),
        "Axial force (N)": result.force_n,
        "Stress (MPa)": result.stress_pa / 1e6,
        "Euler Pcr (N)": result.buckling_critical_n,
    })
    reaction_table = pd.DataFrame([
        {
            "Support node": int(node),
            "Rx (N)": float(result.reactions_n[node, 0]) if fix_x else None,
            "Ry (N)": float(result.reactions_n[node, 1]) if fix_y else None,
        }
        for node, fix_x, fix_y in truss.supports
    ])
    members_col, reactions_col = st.columns([3, 2])
    with members_col:
        st.markdown("**Member forces and ideal buckling loads**")
        st.dataframe(member_table.round(4), hide_index=True, width="stretch")
    with reactions_col:
        st.markdown("**Support reactions**")
        st.dataframe(reaction_table.round(4), hide_index=True, width="stretch")
        residual_n = np.linalg.norm(
            np.sum(result.reactions_n, axis=0) + np.sum(truss.forces_n, axis=0)
        )
        st.caption(f"Global force equilibrium residual: {residual_n:.3e} N")
    st.write("Current design across all uncertainty scenarios:")
    st.json(evaluate(topology,height,area,req))

with tab2:
    st.subheader("Robust design screening")
    st.caption("All candidates checked by full FEA over 8 corner scenarios, including load increase, E decrease, and section reduction.")
    with st.spinner("FEA-evaluating candidate structures..."):
        designs=search_cached(req)
    n_feasible=int(designs.feasible.sum())
    st.metric("FEA-verified feasible candidates",f"{n_feasible} / {len(designs)}")
    best=best_feasible(designs)
    if best is not None:
        st.success(explain_design(best))
    else:
        st.error("No feasible candidate in current design space. Try different load/limits.")
    fig=px.scatter(designs.dropna(subset=["mass_kg","worst_displacement_util"]),
                   x="mass_kg",y="worst_displacement_util",color="topology",
                   symbol="feasible", hover_data=["area_mm2","height_m","worst_buckling_util"])
    fig.update_layout(height=390, xaxis_title="Mass (kg)",yaxis_title="Worst-case displacement utilization")
    st.plotly_chart(fig,width="stretch")
    st.write("**Non-dominated feasible alternatives: mass vs worst-case displacement utilization**")
    st.dataframe(pareto_front(designs).round(4),hide_index=True)
    if best is not None:
        with st.expander("Local engineering sensitivity (finite differences)"):
            st.dataframe(elasticities(str(best["topology"]),float(best["height_m"]),
                                          float(best["area_mm2"]),req).round(3),hide_index=True)
            st.caption("Log-derivative about the selected design; valid locally only. Governing constraint may switch.")
    st.download_button("Download candidate database CSV",designs.to_csv(index=False),
                       "forceforge_fea_designs.csv","text/csv")
    st.subheader("Challenge My Design")
    challenge=st.slider("Challenge load multiplier",1.,1.6,1.2,.05)
    if best is not None:
        built=make_truss(str(best["topology"]),span,float(best["height_m"]),float(best["area_mm2"]),
                         force,req.material)
        base=solve(built)
        challenged=solve(built,load_factor=challenge,e_factor=1.-e_unc,area_factor=1.-area_unc)

        # The original robust search only protects against the sidebar's
        # maximum load increase. A larger challenge needs a NEW feasibility
        # assessment including stress, displacement AND Euler buckling.
        challenge_envelope=replace(
            req,load_uncertainty=max(req.load_uncertainty,challenge-1.0)
        )
        challenged_check=evaluate(str(best["topology"]),float(best["height_m"]),
                                  float(best["area_mm2"]),challenge_envelope)
        st.caption(
            f"Original robustness envelope: up to {1.+req.load_uncertainty:.2f}× load. "
            f"Now checking up to {1.+challenge_envelope.load_uncertainty:.2f}× load, "
            f"with E reduced {100.*e_unc:.0f}% and area reduced {100.*area_unc:.0f}%."
        )
        c1,c2,c3=st.columns(3)
        c1.metric("Nominal displacement",f"{base.max_disp_m*1000:.4f} mm")
        c2.metric("Challenged displacement",f"{challenged.max_disp_m*1000:.4f} mm")
        c3.metric("Challenged maximum stress",f"{challenged.max_stress_pa/1e6:.3f} MPa")

        check_rows=[
            ("Axial yield",challenged_check["worst_stress_util"]),
            ("Nodal displacement",challenged_check["worst_displacement_util"]),
            ("Ideal member buckling",challenged_check["worst_buckling_util"]),
        ]
        st.markdown("**Recomputed worst-case constraint checks (utilization ≤ 1.0 required)**")
        st.dataframe(pd.DataFrame([
            {"Constraint":name,"Utilization":round(float(util),4),
             "Status":"PASS" if util<=1.0+1e-10 else "FAIL"}
            for name,util in check_rows
        ]),hide_index=True,width="stretch")
        if challenged_check["feasible"]:
            st.success(
                f"PASS — the originally selected design remains feasible over the "
                f"expanded scenario grid (maximum utilization "
                f"{challenged_check['worst_utilization']:.3f})."
            )
        else:
            limiting=max(check_rows,key=lambda entry:entry[1])
            st.error(
                f"FAIL — the original design violates {limiting[0]} "
                f"(utilization {limiting[1]:.3f} > 1.0). "
                "The previously optimized design was not qualified for this higher load."
            )
        st.caption("These values are recomputed from the idealized FEA model, not generated by an LLM.")

        if st.button("Find FEA-verified redesign for this challenge",type="primary"):
            with st.spinner("Re-optimizing every candidate over the expanded scenario grid..."):
                expanded_designs=search_cached(challenge_envelope)
                updated_best=best_feasible(expanded_designs)
            st.write(
                f"**Expanded search:** {int(expanded_designs.feasible.sum())} / "
                f"{len(expanded_designs)} candidates satisfy the updated constraints."
            )
            if updated_best is None:
                st.warning(
                    "No feasible candidate in the current topology, height and "
                    "section grid. Consider enlarging the search space or relaxing constraints."
                )
            else:
                old_mass=float(best["mass_kg"])
                new_mass=float(updated_best["mass_kg"])
                change_pct=(new_mass/old_mass-1.0)*100.
                st.success(
                    f"Recomputed robust solution: {updated_best['topology']} | "
                    f"height {updated_best['height_m']:.2f} m | "
                    f"area {updated_best['area_mm2']:.0f} mm² | "
                    f"mass {new_mass:.3f} kg | "
                    f"worst utilization {updated_best['worst_utilization']:.3f}."
                )
                p1,p2,p3=st.columns(3)
                p1.metric("Original mass",f"{old_mass:.3f} kg")
                p2.metric("Redesigned mass",f"{new_mass:.3f} kg",delta=f"{change_pct:+.1f}%")
                p3.metric("Redesign worst utilization",
                          f"{updated_best['worst_utilization']:.3f} / 1.000")
                updated_truss=make_truss(
                    str(updated_best["topology"]),span,
                    float(updated_best["height_m"]),float(updated_best["area_mm2"]),
                    force,req.material
                )
                updated_result=solve(updated_truss)
                st.plotly_chart(draw_truss(updated_truss,updated_result),width="stretch")
                st.caption(
                    "Shown geometry is the FEA-verified redesign within the searched "
                    "discrete candidate grid; deformation visualized at nominal load. "
                    "No physical prototype or connection-strength verification."
                )

with tab3:
    st.subheader("Train a surrogate from FEA results")
    st.caption("FEA generates labels → Random Forest learns approximate scenario utilization → candidates are FEA-verified again.")
    with st.spinner("Training and validating Random Forest surrogate..."):
        model,feature_cols,metrics=surrogate_cached(req)
    mdf=pd.DataFrame([{"Target":name,"MAE (utilization)":x["mae"],"Test R²":x["r2"],
                       "Mean baseline MAE": x["baseline_mae"]}
                      for name,x in metrics.items()])
    st.dataframe(mdf,hide_index=True)
    st.caption(model.forceforge_validation_["method"])
    st.warning("Duplicate design combinations stay in the same split. Metrics estimate interpolation under current requirements, not generalization to new topologies or materials. Proposals stay within sampled feature bounds and are FEA-verified.")
    if st.button("Propose with ML and verify with FEA"):
        with st.spinner("Screening random candidates, then verifying shortlisted designs..."):
            vdf=propose_and_verify(model,feature_cols,req,n=300)
        st.dataframe(vdf.round(4),hide_index=True)
        st.session_state["ml_verified"] = vdf
    elif "ml_verified" in st.session_state:
        st.dataframe(st.session_state["ml_verified"].round(4),hide_index=True)

with tab4:
    st.subheader("Natural-language requirements (optional OpenAI API)")
    text=st.text_area("Write a design brief",value="Design a lightweight 2 m truss bridge under 1000 N, with displacement limit 2 mm.")
    use_api=st.checkbox("Use OpenAI Structured Outputs if API key available",value=False)
    if st.button("Interpret engineering requirements"):
        try:
            parsed=interpret(text,use_api=use_api)
            st.json(parsed.model_dump())
            st.info("Review extracted values, then enter them using the sidebar controls. The LLM never computes FEA results.")
        except Exception as exc:
            st.error(f"Requirement interpretation failed: {exc}")
    if not os.getenv("OPENAI_API_KEY"):
        st.caption("No OPENAI_API_KEY set. Offline deterministic parser works without payment or network access.")
    st.markdown("**Agent design boundary:** proposed inputs → schema validation → engineer approval → FEA → optimizer → design critique. Never accept an AI-generated stress value as evidence.")

st.divider()
st.caption("ForceForge AI 2.0 | Hack the Nest 2026 prototype | Not intended for real-world structural safety decisions")

