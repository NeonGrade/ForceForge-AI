"""ForceForge X mission control: one user goal, three scenario-specific FEM models."""
from __future__ import annotations
from dataclasses import asdict, replace
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.decision import MISSIONS, demo_case, recommend_design, failure_explanation, plain_failure_name
from forceforge.industry import run_industry_case

st.set_page_config(
    page_title="ForceForge X | Engineering Decision Studio",
    page_icon="🛠️", layout="wide", initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.block-container {max-width: 1220px; padding-top: 1.8rem; padding-bottom: 3rem;}
[data-testid="stSidebar"] {background: #f7f8fb;}
.ff-eyebrow {font-size:.80rem; letter-spacing:.15em; font-weight:700; color:#57717d; margin-bottom:.4rem;}
.ff-hero {font-size:2.65rem; line-height:1.12; font-weight:800; color:#152f3d; margin:.1rem 0 .6rem;}
.ff-sub {font-size:1.10rem; color:#526b79; line-height:1.55; max-width:850px;}
.ff-panel {border:1px solid #dce5ea; border-radius:12px; padding:16px 18px; margin:10px 0 16px;}
.ff-kicker {font-size:0.8rem; color:#5c6e79; font-weight:650; text-transform:uppercase; letter-spacing:.06em;}
.ff-narrative {font-size:1.05rem; line-height:1.55;}
.ff-caption {font-size:.82rem; color:#60737c; line-height:1.45;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ForceForge X")
    st.caption("Engineering Decision Studio · Demo v0.3")
    st.markdown("**Your mission**")
    st.write("1. Pick an engineering problem")
    st.write("2. Increase the operating load")
    st.write("3. Ask the solver to improve the design")
    st.divider()
    st.markdown("**Engineering workspace**")
    st.markdown("[Detailed FEA scenario reports](/Cross_Industry_Platform)")
    st.markdown("[Frame, thermal and fatigue](/Advanced_Structural_Lab)")
    st.markdown("[Truss optimization and ML lab](/Engineering_Workbench)")
    st.caption("Earlier computational capabilities remain in the engineering workspace.")

st.markdown('[← Back to measured laboratory benchmark](/)')
st.markdown('<div class="ff-eyebrow">FORCEFORGE X · SIMPLIFIED INDUSTRY APPLICATIONS</div>',
            unsafe_allow_html=True)
st.markdown('<div class="ff-hero">What happens when a design faces a tougher day?</div>',
            unsafe_allow_html=True)
st.markdown(
    '<div class="ff-sub">Choose an engineering use case, challenge its operating '
    'conditions, and compare a redesigned option. Every numerical proposal '
    'is rechecked with the finite-element solver.</div>',
    unsafe_allow_html=True
)
st.caption("Three illustrative numerical cases; not measured products, engineering code approval or certification.")
st.divider()

st.subheader("1 · Choose the engineering problem")
LABELS = {"Building":"Roof truss", "Industrial":"Machine mounting bracket",
          "Automotive":"Suspension link"}
sector = st.radio("Engineering application", list(MISSIONS),
                  format_func=lambda key: LABELS[key],
                  horizontal=True, label_visibility="collapsed", key="ff_sector")
mission = MISSIONS[sector]
st.markdown(
    f'<div class="ff-panel"><div class="ff-kicker">{mission.headline}</div>'
    f'<div class="ff-narrative"><b>{mission.question}</b></div>'
    f'<div class="ff-caption">{mission.use_case}</div></div>',
    unsafe_allow_html=True,
)

st.subheader("2 · Change the operating conditions")
LOAD_CASES = {
    "Normal load": 1.0,
    "Heavier load (+60%)": 1.6,
    "Extreme example (+120%)": 2.2,
}
scenario = st.radio("Applied operating load", list(LOAD_CASES),
                    index=1, horizontal=True, key="ff_severity")
with st.expander("Advanced assumptions · optional for engineers"):
    st.caption("Simplified parameter values; actual materials and joints have not been measured.")
    temperature = st.slider(
        "Temperature change (K)",-20,150,
        0 if sector == "Automotive" else 50,5,
        key=f"ff_temperature_{sector}",disabled=sector=="Building")
    joint_log = st.slider(
        "log10 joint rotational stiffness (N·m/rad)",3.0,8.0,5.3,.1,
        key=f"ff_joint_{sector}",disabled=sector=="Building")
    cycles = st.slider(
        "Illustrative load cycles",10_000,1_000_000,200_000,10_000,
        key=f"ff_cycles_{sector}",disabled=sector=="Building")

current_case=replace(
    demo_case(sector,load_scale=LOAD_CASES[scenario]),
    temperature_change_k=float(temperature),
    joint_stiffness_nm_rad=float(10**joint_log),
    service_cycles=int(cycles)
)
if "ff_history" not in st.session_state:
    st.session_state["ff_history"]={}

if st.button("Analyze the current design",type="primary",use_container_width=True):
    try:
        with st.spinner("Solving three modeled loading scenarios..."):
            outcome=run_industry_case(current_case)
        st.session_state["ff_history"][sector] = {
            "case":current_case,"report":outcome,"improvement":None
        }
    except (ArithmeticError, ValueError, OverflowError) as error:
        st.error(f"The model could not evaluate the selected condition: {error}")

record=st.session_state["ff_history"].get(sector)
if record is None:
    st.info("Click **Analyze the current design** to begin. Results are retained when you switch industries.")
else:
    analysed=record["case"]
    report=record["report"]
    if analysed != current_case:
        st.warning("Inputs changed. Results below still refer to the previous analysis; click Analyze to update them.")
    st.divider()
    st.subheader("3 · See the limitation, then improve the design")
    util=float(report.governing["max_utilization"])
    reason=report.governing["controlling_check"]
    if util > 1.0:
        st.error(f"**Modeled constraint exceeded.** {failure_explanation(report)}")
        st.write("Can a larger section or a stiffer modeled connection improve this design?")
    else:
        st.success(f"**Within the modeled numerical bounds.** {failure_explanation(report)}")
        st.write("Can this design be made lighter while retaining the same modeled limits?")
    a,b,c=st.columns(3)
    a.metric("Modeled-limit use",f"{util*100:.1f}%")
    b.metric("Modeled member mass",f"{report.figures['mass_kg']:.2f} kg")
    c.metric("Applied load",f"{analysed.load_scale:.1f}× baseline")
    st.caption("100% is an illustrative constraint bound, not proof of actual structural safety.")
    st.markdown(f"**What matters:** {plain_failure_name(reason)}. This result identifies a modeled constraint, not an actual damaged component.")

    if st.button("Find an FEA-verified improvement",type="primary",
                 use_container_width=True):
        try:
            with st.spinner("Testing and re-solving alternative sections and joint assumptions..."):
                record["improvement"]=recommend_design(analysed)
        except (ArithmeticError,ValueError,OverflowError) as error:
            st.error(f"Design search could not complete: {error}")

    proposal=record.get("improvement")
    if proposal is not None:
        st.markdown("#### Original vs improved design")
        if proposal.redesigned is None:
            st.error("No tested candidate met all illustrative constraints.")
            st.write("Within this search space, sizing and joint-stiffness changes were insufficient. Geometry or boundary conditions would need further engineering review.")
        else:
            revised=proposal.redesigned
            revision=proposal.design_inputs
            left,right=st.columns(2)
            with left:
                st.markdown("**Original**")
                st.metric("Member mass",f"{report.figures['mass_kg']:.2f} kg")
                st.metric("Constraint utilization",f"{util*100:.1f}%")
                st.caption("Exceeds bound" if util>1.0 else "Within bound")
            with right:
                st.markdown("**Improved**")
                st.metric("Member mass",f"{revised.figures['mass_kg']:.2f} kg",
                          delta=f"{proposal.mass_delta_percent:+.1f}% vs original",
                          delta_color="inverse")
                st.metric("Constraint utilization",f"{revised.governing['max_utilization']*100:.1f}%")
                st.caption(
                    f"Member radius {revision.section_scale:.2f}×; "
                    f"joint stiffness {revision.joint_stiffness_nm_rad/analysed.joint_stiffness_nm_rad:.1f}×"
                )
            figure=go.Figure()
            figure.add_bar(x=["Original","Improved"],
                           y=[util,float(revised.governing["max_utilization"])],
                           marker_color=["#d16b48","#2a8e85"])
            figure.add_hline(y=1.0,line_dash="dash",line_color="#b7534f",
                             annotation_text="Illustrative model bound")
            figure.update_layout(showlegend=False,height=300,
                                 margin=dict(l=10,r=10,t=5,b=15),
                                 yaxis_title="Share of illustrative limit")
            st.plotly_chart(figure,use_container_width=True)
            explanation=f"**What changed:** Section radius {revision.section_scale:.2f}× the original."
            if revision.joint_stiffness_nm_rad>analysed.joint_stiffness_nm_rad:
                explanation+=(
                    f" The solver assumed {revision.joint_stiffness_nm_rad/analysed.joint_stiffness_nm_rad:.1f}× higher rotational connection stiffness."
                    " No bolt, weld, reinforcement material or cost is designed."
                )
            st.info(explanation+" All listed load cases were recomputed with FEA.")
        st.caption(
            f"Tested {proposal.alternatives_checked} combinations; {proposal.feasible_candidates} "
            "met illustrative model constraints. The objective is modeled member mass only, "
            "not global optimality, total cost or structural safety certification."
        )

    with st.expander("Engineering evidence · detailed results and unresolved requirements"):
        st.markdown("**Solver and fidelity**")
        st.write(report.solver)
        st.write(report.fidelity)
        st.markdown("**Modeled scenarios**")
        st.dataframe(pd.DataFrame(report.scenarios),hide_index=True,use_container_width=True)
        st.markdown("**Missing external qualification evidence**")
        st.dataframe(pd.DataFrame(report.verification),hide_index=True,use_container_width=True)
        st.write("Trace ID:",report.trace_id)
        payload={
            "analysed_inputs":asdict(analysed),
            "original":report.serializable(),
            "redesign":proposal.redesigned.serializable() if proposal and proposal.redesigned else None,
            "redesign_inputs":asdict(proposal.design_inputs) if proposal and proposal.design_inputs else None,
        }
        st.download_button(
            "Export traceable numerical run (JSON)",
            data=json.dumps(payload,indent=2),
            file_name=f"forceforge_{sector.lower()}_{report.trace_id}.json",
            mime="application/json"
        )
        st.caption("A trace hash is not a professional sign-off or independent validation.")

st.divider()
with st.expander("How it works · what the finite-element models do and do not prove"):
    st.markdown(
        "Building uses ideal 2D axial truss elements and simplified buckling. "
        "Industrial uses 2D beam-column mechanics, thermal loading and an equivalent rotational spring. "
        "Automotive uses a planar proxy, not a validated full suspension assembly."
    )
    st.markdown(
        "**Computed:** equilibrium, modeled stress/displacement, sampled redesigns and rechecks. "
        "**Not established:** actual code compliance, 3D joint contact, calibrated fatigue life, "
        "manufacturing costs, independent certification or approval."
    )
    st.markdown("[Detailed cross-industry cases](/Cross_Industry_Platform)")
    st.markdown("[Truss optimization and ML laboratory](/Engineering_Workbench)")
st.caption("ForceForge X · illustrative scenario-based engineering decisions · not approved for real service use.")
