"""ForceForge AI 2.0: functional Streamlit engineering hackathon prototype."""
import json
import os
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
st.page_link("pages/6_Cross_Industry_Platform.py", label="Open ForceForge X: Unified Cross-Industry Platform", icon="🏗️")
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
        metrics_row(truss,result)
        st.dataframe(pd.DataFrame({"Member":range(len(truss.elements)),
                                   "Axial force (N)":result.force_n,
                                   "Stress (MPa)":result.stress_pa/1e6,
                                   "Euler Pcr (N)":result.buckling_critical_n}),
                     hide_index=True)
    with right:
        st.plotly_chart(draw_truss(truss,result),width="stretch")
        st.caption("Ideal pin-jointed rods. Orange=compression, teal=tension. Displacement in drawing is exaggerated.")
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
        c1,c2,c3=st.columns(3)
        c1.metric("Nominal displacement",f"{base.max_disp_m*1000:.4f} mm")
        c2.metric("Challenged displacement",f"{challenged.max_disp_m*1000:.4f} mm")
        c3.metric("Challenged maximum stress",f"{challenged.max_stress_pa/1e6:.3f} MPa")
        st.caption("Above are recomputed FEA results, not generated by a language model.")

with tab3:
    st.subheader("Train a surrogate from FEA results")
    st.caption("FEA generates labels → Random Forest learns approximate scenario utilization → candidates are FEA-verified again.")
    with st.spinner("Training and validating Random Forest surrogate..."):
        model,feature_cols,metrics=surrogate_cached(req)
    mdf=pd.DataFrame([{"Target":name,"MAE (utilization)":x["mae"],"Test R²":x["r2"]}
                      for name,x in metrics.items()])
    st.dataframe(mdf,hide_index=True)
    st.warning("Random split of FEA-generated design combinations. Test accuracy does not prove extrapolation to unseen topologies/materials. Always FEA-verify proposed designs.")
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
