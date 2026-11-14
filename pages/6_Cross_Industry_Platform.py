"""ForceForge X cross-industry engineering simulation and evidence dashboard.

This page does not provide any legally meaningful certification status.
All three sample workflows use physically computed, idealized FEA responses.
"""
import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.industry import CaseInputs, SECTORS, platform_summary, run_industry_case

st.set_page_config(page_title="ForceForge X | Industry Mission Control", page_icon="🏗️", layout="wide")

INDUSTRY_LABELS = {
    "Building": "Building · Michigan steel truss",
    "Industrial": "Industrial · Equipment support bracket",
    "Automotive": "Automotive · Suspension-link load path",
}

st.title("ForceForge X | Industry Mission Control")
st.caption("One engineering platform · three application domains · physics-driven simulations · auditable evidence gates")
st.warning(
    "All supplied load cases, dimensions, material properties, fatigue data, "
    "and illustrative screening limits are examples. This system does not "
    "perform full industry code checks, contact/3D qualification or formal certification."
)

with st.sidebar:
    st.header("Application")
    sector = st.radio(
        "Industry workflow", SECTORS, format_func=lambda x: INDUSTRY_LABELS[x]
    )
    st.header("Shared what-if parameters")
    load_scale = st.slider("Mechanical load multiplier", 0.5, 2.0, 1.0, 0.05)
    temperature_change_k = st.slider(
        "Uniform temperature difference (K)", -20, 150, 50, 5,
        disabled=sector == "Building",
        help="Used by the frame-based Industrial and Automotive examples only.",
    )
    joint_k = st.slider(
        "Joint rotational stiffness log10 (N m/rad)", 3.0, 8.0, 5.3, 0.1,
        disabled=sector == "Building",
        help="Equivalent support rotational spring; not a bolt/contact constitutive model.",
    )
    service_cycles = st.slider(
        "Hypothetical load cycles", 10_000, 1_000_000, 200_000, 10_000,
        disabled=sector == "Building",
        help="Used solely with unvalidated illustrative S-N input data.",
    )
    st.caption("Current status: engineering research prototype, not approved for service.")

inputs = CaseInputs(
    sector=sector,
    load_scale=load_scale,
    temperature_change_k=temperature_change_k,
    joint_stiffness_nm_rad=10.0**joint_k,
    service_cycles=service_cycles,
)


@st.cache_data(show_spinner=False)
def cached_case(value: CaseInputs):
    return run_industry_case(value)


@st.cache_data(show_spinner=False)
def cached_summary(value: CaseInputs):
    return platform_summary(value)


def make_model_figure(report, exaggeration: float):
    g = report.figures
    nodes = np.asarray(g["nodes"], dtype=float)
    moved = np.asarray(g["displaced"], dtype=float)
    display_nodes = nodes + (moved-nodes)*exaggeration
    stresses = np.asarray(g["member_values_mpa"], dtype=float)
    vmax = max(float(np.max(stresses)), 1e-12)
    fig = go.Figure()
    for i, (a, b) in enumerate(g["members"]):
        fig.add_trace(go.Scatter(
            x=nodes[[a,b],0], y=nodes[[a,b],1],
            mode="lines", line=dict(color="#96a4b0",width=2,dash="dot"),
            name="Original nodes" if i == 0 else None,
            legendgroup="baseline",showlegend=(i==0),hoverinfo="skip",
        ))
        relative = stresses[i] / vmax
        color = "#d85e51" if relative > 0.67 else "#d09a35" if relative > 0.34 else "#208a8b"
        fig.add_trace(go.Scatter(
            x=display_nodes[[a,b],0],y=display_nodes[[a,b],1],mode="lines",
            line=dict(color=color,width=5),showlegend=False,
            hovertext=f"Member {i} | nominal / modeled stress magnitude {stresses[i]:.3f} MPa",
            hoverinfo="text",
        ))
    fig.add_trace(go.Scatter(
        x=display_nodes[:,0],y=display_nodes[:,1],mode="markers+text",
        marker=dict(color="#1a5c87",size=9),
        text=[str(i) for i in range(len(nodes))],textposition="top center",
        name="Nodes",
    ))
    fig.update_yaxes(scaleanchor="x",scaleratio=1)
    fig.update_layout(height=400,margin=dict(l=10,r=10,t=20,b=10),
                      xaxis_title="X (m)",yaxis_title="Y (m)",
                      legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="right",x=1.0))
    return fig


try:
    report = cached_case(inputs)
except (ValueError, ArithmeticError) as exc:
    st.error(f"Solver rejected this input: {exc}")
    st.stop()

st.subheader(report.title)
st.caption(report.description)

max_util = float(report.governing["max_utilization"])
scenarios = report.scenarios
m1,m2,m3,m4 = st.columns(4)
m1.metric("Model mass",f"{report.figures['mass_kg']:.3f} kg")
m2.metric("Governing scenario stress",f"{report.governing['peak_stress_mpa']:.3f} MPa")
m3.metric("Worst scenario utilization",f"{max_util:.3f} / 1.000")
m4.metric("Evidence gaps",f"{len(report.gaps)} unresolved")
if max_util > 1.0:
    st.error("One or more illustrated numerical screening limits are exceeded. This is NOT a design-code failure verdict.")
else:
    st.info("Illustrative numerical limits are met for the modeled cases only. This does NOT imply structural safety or certification.")

st.caption(f"Solver: {report.solver} | fidelity: {report.fidelity}")

tab_sim,tab_physics,tab_evidence,tab_compare = st.tabs([
    "Simulation", "Failure modes & inputs", "Verification evidence", "Cross-industry overview"
])

with tab_sim:
    c_left,c_right=st.columns([7,5])
    with c_left:
        st.markdown("**Model-based deformed shape**")
        exaggeration=st.slider("Displacement visualization multiplier",1,500,120,10)
        st.plotly_chart(make_model_figure(report,exaggeration),use_container_width=True)
        st.caption(
            "The plot connects calculated nodal translations with straight segments. "
            "It does not visualize a continuous beam curvature, joint contact, local bolt stresses or 3D geometry."
        )
    with c_right:
        st.markdown("**Shared solver interface**")
        st.write("Domain",report.sector)
        st.write("FEA solver",report.solver)
        st.write("Physical scenario count",len(scenarios))
        st.write("Trace ID",report.trace_id)
        st.write("Authorization",report.certification_status)
        st.caption("The trace ID is a reproducible input/result hash, NOT a digital professional signature.")
    st.markdown("**Scenario matrix**")
    columns=["scenario","max_displacement_mm","peak_stress_mpa","max_utilization","controlling_check","numerical_screen"]
    df=pd.DataFrame(scenarios)[columns]
    st.dataframe(df,use_container_width=True,hide_index=True)
    fig=go.Figure()
    fig.add_trace(go.Bar(x=df["scenario"],y=df["max_utilization"],name="Scenario utilization"))
    fig.add_hline(y=1.0,line_dash="dash",line_color="#bd5439",
                  annotation_text="Illustrative threshold = 1.0")
    fig.update_layout(height=300,yaxis_title="Maximum model-screening utilization",
                      margin=dict(l=0,r=0,t=15,b=0))
    st.plotly_chart(fig,use_container_width=True)

with tab_physics:
    st.markdown("**Engineering assumptions and calculations**")
    st.json(report.design_inputs,expanded=True)
    st.markdown("**Governing scenario — constraint-by-constraint**")
    check_df=pd.DataFrame([
        {"Constraint": k, "Utilization": v,
         "Numerical result": "Within illustrative bound" if v<=1.0 else "Exceeds illustrative bound"}
        for k,v in report.governing["checks"].items()
    ])
    st.dataframe(check_df,use_container_width=True,hide_index=True)
    if "hypothetical_miner_damage" in report.governing:
        st.metric("Hypothetical S–N / Miner damage",f"{report.governing['hypothetical_miner_damage']:.6g}")
        st.warning("Fatigue is based on invented example S–N inputs and a simplified 0-to-peak load block. Do NOT use this as real suspension or bracket fatigue life.")
    st.markdown("**Sensitivity to applied load**")
    rows=[]
    for scale in (0.75,1.0,1.25,1.50):
        test=cached_case(CaseInputs(sector,inputs.load_scale*scale,
                                    inputs.temperature_change_k,
                                    inputs.joint_stiffness_nm_rad,inputs.service_cycles))
        rows.append({"Relative to chosen load":scale,
                     "Controlling stress (MPa)":test.governing["peak_stress_mpa"],
                     "Max numerical utilization":test.governing["max_utilization"]})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    st.caption("This load sensitivity uses actual FEA reruns under idealized inputs; it is not a probability-of-failure estimate.")

with tab_evidence:
    st.subheader("Audit-ready evidence inventory")
    st.caption(
        "Evidence statuses are recorded separately from numerical FEA results. "
        "No engineering approval is conferred by an uploaded calculation or a successful benchmark."
    )
    st.dataframe(pd.DataFrame(report.verification),use_container_width=True,hide_index=True)
    st.markdown("**Unresolved evidence and approvals**")
    for gap in report.gaps:
        st.write("• "+gap)
    st.download_button("Export model run + evidence (JSON)",
                       data=json.dumps(report.serializable(),indent=2),
                       file_name=f"forceforge_{sector.lower()}_{report.trace_id}.json",
                       mime="application/json")
    st.caption("Export includes model assumptions, all calculated scenarios and unresolved evidence gates; no third-party signature.")

with tab_compare:
    st.subheader("Three industries · one orchestration layer")
    st.caption("All cases share one typed input/router, a numerical FEA execution layer and an evidence-report schema. "
               "Absolute masses and utilizations are not directly comparable across these different structures.")
    try:
        overview=pd.DataFrame(cached_summary(inputs))
    except (ValueError, ArithmeticError) as exc:
        st.error(f"Unable to evaluate all cases under selected what-if factors: {exc}")
    else:
        st.dataframe(overview,use_container_width=True,hide_index=True)
    st.markdown("**Physics availability by domain**")
    caps=pd.DataFrame([
        {"Capability":"2D axial truss and ideal member buckling","Building":"Available","Industrial":"—","Automotive":"—"},
        {"Capability":"2D beam/frame bending","Building":"Future","Industrial":"Available","Automotive":"Available as planar surrogate"},
        {"Capability":"Semi-rigid equivalent joint and thermal expansion","Building":"Future","Industrial":"Available","Automotive":"Available as surrogate"},
        {"Capability":"Second-order elastic P–Δ","Building":"Future","Industrial":"Available","Automotive":"Available as surrogate"},
        {"Capability":"Illustrative S–N/Goodman/Miner screen","Building":"Future","Industrial":"Available (unvalidated)","Automotive":"Available (unvalidated)"},
        {"Capability":"3D solid / contact / elastoplasticity / FSI","Building":"Not implemented","Industrial":"Not implemented","Automotive":"Not implemented"},
        {"Capability":"Formal industry-code certification","Building":"Not implemented","Industrial":"Not implemented","Automotive":"Not implemented"},
    ])
    st.dataframe(caps,hide_index=True,use_container_width=True)

st.divider()
st.caption("ForceForge X cross-industry simulation platform · numerical screening and evidence management · no formal structural approval")
