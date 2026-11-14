"""ForceForge AI 2.0 - CAD-inspired structural engineering workbench.

This alternative interface keeps the existing physics, optimization, and
surrogate modules unchanged. It is designed for fast hackathon demonstrations.
"""

from dataclasses import replace
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from forceforge.design import TOPOLOGIES, make_truss
from forceforge.physics import solve
from forceforge.robust import (
    Requirements, evaluate, grid_search, best_feasible, pareto_front
)
from forceforge.surrogate import train, propose_and_verify
from forceforge.agent import interpret

st.set_page_config(
    page_title="ForceForge | Structural Design Studio",
    page_icon=":triangular_ruler:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      :root { --ff-bg: #090e19; --ff-panel: #121b2b; --ff-stroke: #29364d; }
      .stApp { background: radial-gradient(ellipse at 70% -20%, #172744 0%, #090e19 55%); color: #dce8fa; }
      .block-container { padding-top: 1.3rem; padding-bottom: 2rem; max-width: 1600px; }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stSidebar"] { background: #101827; }
      h1, h2, h3 { letter-spacing: -.025em; }
      h3 { font-size: 1.10rem; }
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(18,27,43,.70);
        border-color: #2a3b52;
        border-radius: 16px;
      }
      div[data-testid="stMetric"] {
        padding: .7rem .8rem; background: #151f30; border: 1px solid #29364d; border-radius: 12px;
      }
      [data-testid="stMetricLabel"] { color: #92a7bf; }
      [data-testid="stMetricValue"] { color: #ecf4ff; font-size: 1.35rem; }
      .stButton > button[kind="primary"] { background: #4c83f4; color: white; border-radius: 10px; border: 0; }
      .stButton > button { border-radius: 10px; border-color: #354762; }
      button[data-baseweb="tab"] { font-weight: 650; letter-spacing: .02em; }
      .ff-logo { display: inline-flex; align-items: center; gap: .65rem; color: #edf5ff; font-size: 1.5rem; font-weight: 800; letter-spacing: -.06em; }
      .ff-mark { display: inline-block; padding: .15rem .55rem; background: #4c83f4; border-radius: 8px; font-size: 1.35rem; }
      .ff-kicker { color: #7ea8f9; text-transform: uppercase; letter-spacing: .15em; font-size: .66rem; font-weight: 700; }
      .ff-subtitle { color: #8ea3bb; margin-top: .2rem; margin-bottom: .8rem; font-size: .93rem; }
      .ff-section { color: #93a8bf; font-size: .75rem; font-weight: 700; text-transform: uppercase; letter-spacing: .11em; margin: .3rem 0 .7rem; }
      .ff-note { font-size: .75rem; color: #8fa7c4; line-height: 1.5; }
      .ff-badge { display: inline-block; border: 1px solid #365270; border-radius: 99px; padding: .25rem .75rem; font-size: .75rem; color: #b3d1ef; }
      .ff-good { background: #12392d; color: #82e1b3; border: 1px solid #285e4b; padding: .65rem .8rem; border-radius: 10px; font-weight: 700; }
      .ff-bad { background: #3d2328; color: #ffb1af; border: 1px solid #6b343e; padding: .65rem .8rem; border-radius: 10px; font-weight: 700; }
      .ff-topline { border-top: 1px solid #27354b; padding-top: .65rem; margin-top: .5rem; }
      @media (max-width: 900px) { .ff-logo { font-size: 1.18rem; } .block-container { padding-top: .7rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(show_spinner=False)
def search_cached(req: Requirements):
    return grid_search(req)

@st.cache_resource(show_spinner=False)
def surrogate_cached(req: Requirements):
    return train(grid_search(req))


def truss_figure(truss, result, show_deformation=True):
    """Show the native geometry, member forces, supports and central load."""
    xy = truss.nodes_m
    max_disp = float(np.max(np.abs(result.disp_m)))
    scale = min(400.0, (0.07 * max(float(np.ptp(xy[:, 0])), 1.0)) / max(max_disp, 1e-12))
    deformed = xy + result.disp_m * scale if show_deformation else xy

    fig = go.Figure()
    for idx, (a, b) in enumerate(truss.elements):
        fig.add_trace(go.Scatter(
            x=xy[[a, b], 0], y=xy[[a, b], 1],
            mode="lines", line=dict(color="#41516b", width=2, dash="dash"),
            showlegend=(idx == 0), name="Original", hoverinfo="skip",
        ))
        tension = result.force_n[idx] >= 0
        fig.add_trace(go.Scatter(
            x=deformed[[a, b], 0], y=deformed[[a, b], 1],
            mode="lines+markers",
            line=dict(color="#41c8dc" if tension else "#fa946d", width=5),
            marker=dict(size=7, color="#dbe9ff"),
            showlegend=False,
            hovertemplate=(
                "Member " + str(idx) + "<br>" +
                ("Tension" if tension else "Compression") + "<br>" +
                "Axial force: " + f"{result.force_n[idx]:,.1f}" + " N<br>" +
                "Stress: " + f"{result.stress_pa[idx] / 1e6:.3f}" + " MPa<extra></extra>"
            ),
        ))
    for node_idx, fix_x, fix_y in truss.supports:
        fig.add_trace(go.Scatter(
            x=[xy[node_idx, 0]], y=[xy[node_idx, 1]],
            mode="markers", marker=dict(
                size=17, symbol="triangle-up", color="#82a6f1",
                line=dict(width=2, color="#d9e9ff"),
            ),
            name="Support", showlegend=False,
            hovertemplate="Support node " + str(node_idx) + "<extra></extra>",
        ))
    load_node = int(np.argmax(np.linalg.norm(truss.forces_n, axis=1)))
    force_mag = float(np.linalg.norm(truss.forces_n[load_node]))
    if force_mag > 0:
        fig.add_annotation(
            x=xy[load_node, 0], y=xy[load_node, 1],
            ax=0, ay=-60, text=f"LOAD {force_mag:,.0f} N",
            showarrow=True, arrowhead=3, arrowsize=1.2,
            arrowwidth=3, arrowcolor="#f5b84e",
            font=dict(color="#f5b84e", size=11),
            bgcolor="rgba(12,19,31,.80)",
        )
    fig.update_layout(
        height=470, paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0c1524", font=dict(color="#a7bad3", size=11),
        margin=dict(l=15, r=18, t=24, b=18),
        showlegend=True, legend=dict(orientation="h", x=.02, y=1.05),
        hoverlabel=dict(bgcolor="#18263b"),
    )
    fig.update_xaxes(
        showgrid=True, gridcolor="#233047", zeroline=False,
        title="Span (m)", range=[-0.13 * max(xy[:, 0]), 1.13 * max(xy[:, 0])],
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#233047", zeroline=False,
        scaleanchor="x", scaleratio=1, title="Height (m)",
    )
    return fig, scale


st.markdown(
    '<div class="ff-logo"><span class="ff-mark">F</span> ForceForge'
    '<span style="color:#7190bb;font-weight:400"> / Design Studio</span></div>'
    '<div class="ff-subtitle">Physics-verified generative truss design. '
    'Start with a structure, stress-test the assumptions, and compare lighter alternatives.</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<span class="ff-badge">2D LINEAR-ELASTIC FEA</span>&nbsp; '
    '<span class="ff-badge">ROBUST OPTIMIZATION</span>&nbsp; '
    '<span class="ff-badge">ML + FEA VERIFICATION</span>',
    unsafe_allow_html=True,
)
st.write("")

controls, workspace, inspector = st.columns([1.08, 2.35, 1.10], gap="medium")

with controls:
    with st.container(border=True):
        st.markdown('<div class="ff-section">01 / Design inputs</div>', unsafe_allow_html=True)
        topology = st.selectbox("Truss topology", TOPOLOGIES)
        material_name = st.selectbox("Material", ["Steel", "Aluminum"])
        material_values = {"Steel": (200e9, 7850.0, 250e6), "Aluminum": (70e9, 2700.0, 150e6)}
        E, density, sy = material_values[material_name]
        span = st.slider("Span / m", 0.5, 4.0, 2.0, 0.1)
        height = st.slider("Truss height / m", 0.2 * span, 1.25 * span, 0.5 * span, 0.05 * span)
        area = st.slider("Member area / mm2", 60.0, 800.0, 180.0, 10.0)
        force = st.slider("Vertical load / N", 100, 3000, 1000, 100)
        with st.expander("Advanced safety and uncertainty"):
            max_disp = st.slider("Displacement limit / mm", 0.25, 12.0, 2.0, 0.25)
            safety_y = st.slider("Yield safety factor", 1.0, 4.0, 2.0, 0.25)
            safety_b = st.slider("Buckling safety factor", 1.0, 4.0, 2.0, 0.25)
            load_unc = st.slider("Load increase / %", 0, 50, 20, 5) / 100.0
            e_unc = st.slider("Elastic modulus decrease / %", 0, 35, 10, 5) / 100.0
            area_unc = st.slider("Member area decrease / %", 0, 25, 10, 5) / 100.0

req = Requirements(
    span_m=span, base_load_n=force, material_E_pa=E,
    density_kg_m3=density, yield_pa=sy, max_displacement_mm=max_disp,
    yield_safety_factor=safety_y, buckling_safety_factor=safety_b,
    load_uncertainty=load_unc, e_uncertainty=e_unc, area_uncertainty=area_unc,
)
if st.session_state.get("active_requirements") != req:
    for key in ("optimized_designs", "ml_designs", "redesign", "ml_metrics"):
        st.session_state.pop(key, None)
    st.session_state["active_requirements"] = req

truss = make_truss(topology, span, height, area, force, req.material)
result = solve(truss)
check = evaluate(topology, height, area, req)

with workspace:
    with st.container(border=True):
        topbar_left, topbar_right = st.columns([2, 1])
        with topbar_left:
            st.markdown('<div class="ff-section">02 / Structural viewport</div>', unsafe_allow_html=True)
        with topbar_right:
            show_def = st.toggle("Show deformation", value=True)
        fig, scale = truss_figure(truss, result, show_deformation=show_def)
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        st.markdown(
            f'<div class="ff-note">TEAL: TENSION &nbsp;|&nbsp; CORAL: COMPRESSION'
            f' &nbsp;|&nbsp; GRAY: ORIGINAL GEOMETRY<br>'
            f'Deformation display factor: {scale:.0f}x. Geometry is an idealized truss model.</div>',
            unsafe_allow_html=True,
        )

with inspector:
    with st.container(border=True):
        st.markdown('<div class="ff-section">03 / Engineering checks</div>', unsafe_allow_html=True)
        if check["feasible"]:
            st.markdown('<div class="ff-good">SCREENING PASS</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="ff-bad">LIMIT EXCEEDED</div>', unsafe_allow_html=True)
        st.caption("Computed over the defined uncertainty envelope, not a safety certification.")
        st.metric("Nominal mass", f"{result.mass_kg:.2f} kg")
        st.metric("Maximum displacement", f"{result.max_disp_m * 1e3:.3f} mm")
        st.metric("Maximum axial stress", f"{result.max_stress_pa / 1e6:.2f} MPa")
        st.markdown('<div class="ff-section ff-topline">Worst-case utilization</div>', unsafe_allow_html=True)
        for label, key in [
            ("Yield", "worst_stress_util"),
            ("Deflection", "worst_displacement_util"),
            ("Ideal buckling", "worst_buckling_util"),
        ]:
            value = float(check[key])
            st.progress(max(0.0, min(1.0, value)), text=f"{label}: {value:.2f} / 1.00")
        st.caption("Values above 1.00 exceed a modeled constraint.")

st.write("")
st.markdown('<div class="ff-section">04 / Explore and validate</div>', unsafe_allow_html=True)
opt_tab, challenge_tab, ml_tab, agent_tab = st.tabs([
    "Optimize structure", "Challenge the design", "ML + FEA", "AI requirements"
])

with opt_tab:
    st.write("Find lower-mass designs that satisfy all eight model scenarios.")
    if st.button("Run robust optimization", type="primary", key="opt_run"):
        with st.spinner("Evaluating candidate trusses with FEA..."):
            st.session_state["optimized_designs"] = search_cached(req)
    designs = st.session_state.get("optimized_designs")
    if designs is not None:
        best = best_feasible(designs)
        a, b, c = st.columns(3)
        a.metric("Screened designs", str(len(designs)))
        b.metric("Feasible designs", str(int(designs.feasible.sum())))
        c.metric("Lightest feasible mass", f"{float(best['mass_kg']):.2f} kg" if best is not None else "None")
        if best is not None:
            st.success(
                f"Suggested: {best['topology']} | height {float(best['height_m']):.2f} m | "
                f"area {float(best['area_mm2']):.0f} mm2 | "
                f"worst utilization {float(best['worst_utilization']):.3f}."
            )
        chart_data = designs.dropna(subset=["mass_kg", "worst_displacement_util"])
        if not chart_data.empty:
            scatter = px.scatter(
                chart_data, x="mass_kg", y="worst_displacement_util",
                color="topology", symbol="feasible",
                hover_data=["height_m", "area_mm2", "worst_buckling_util"],
                labels={"mass_kg": "Mass / kg", "worst_displacement_util": "Worst deflection utilization"},
            )
            scatter.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0c1524",
                font=dict(color="#b0c2db"), height=340,
            )
            st.plotly_chart(scatter, use_container_width=True)
        with st.expander("Pareto candidates and export"):
            st.dataframe(pareto_front(designs).round(3), use_container_width=True)
            st.download_button("Export FEA candidate data (CSV)", designs.to_csv(index=False),
                               "forceforge_fea_candidates.csv", "text/csv")

with challenge_tab:
    st.write("Increase the design load and check whether the original structure still meets all constraints.")
    multiplier = st.slider("Challenge load multiplier", 1.0, 1.6, 1.2, 0.05)
    expanded = replace(req, load_uncertainty=max(req.load_uncertainty, multiplier - 1.0))
    challenged_check = evaluate(topology, height, area, expanded)
    c1, c2, c3 = st.columns(3)
    c1.metric("Original worst utilization", f"{float(check['worst_utilization']):.3f}")
    c2.metric("Challenge worst utilization", f"{float(challenged_check['worst_utilization']):.3f}")
    c3.metric("Challenge screening", "PASS" if challenged_check["feasible"] else "FAIL")
    if challenged_check["feasible"]:
        st.success("The current geometry passes the expanded model scenario grid.")
    else:
        st.error("The current geometry exceeds a modeled constraint under the challenge.")
    if st.button("Find a robust redesign", key="challenge_redesign"):
        with st.spinner("Searching the expanded uncertainty envelope..."):
            st.session_state["redesign"] = best_feasible(search_cached(expanded))
    if "redesign" in st.session_state:
        redesigned = st.session_state["redesign"]
        if redesigned is None:
            st.warning("No feasible redesign was found in the available candidate grid.")
        else:
            st.success(
                f"FEA-screened redesign: {redesigned['topology']} | "
                f"height {float(redesigned['height_m']):.2f} m | "
                f"area {float(redesigned['area_mm2']):.0f} mm2 | "
                f"mass {float(redesigned['mass_kg']):.2f} kg."
            )

with ml_tab:
    st.write("A Random Forest predicts candidate utilization; its proposals still require full FEA checks.")
    if st.button("Train and validate surrogate", key="ml_train"):
        with st.spinner("Training against simulated FEA labels..."):
            model, features, metrics = surrogate_cached(req)
            st.session_state["ml_metrics"] = metrics
    if "ml_metrics" in st.session_state:
        metric_rows = [
            {"Target": name, "MAE": value["mae"],
             "Test R2": value["r2"], "Baseline MAE": value["baseline_mae"]}
            for name, value in st.session_state["ml_metrics"].items()
        ]
        st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)
        if st.button("Propose candidates and verify with FEA", key="ml_propose"):
            with st.spinner("Re-solving the proposed candidates..."):
                model, features, _ = surrogate_cached(req)
                st.session_state["ml_designs"] = propose_and_verify(model, features, req, n=300)
    if "ml_designs" in st.session_state:
        st.dataframe(st.session_state["ml_designs"].round(4), use_container_width=True)
    st.info("ML metrics describe interpolation within sampled topologies and requirements, not general structural generalization.")

with agent_tab:
    st.write("Translate a plain-English design brief into bounded, reviewable engineering inputs.")
    prompt = st.text_area(
        "Design brief",
        "Design a lightweight 2 m steel truss under a 1000 N central load, with 2 mm maximum displacement.",
    )
    use_api = st.checkbox("Enable OpenAI structured interpretation when a key is configured")
    if st.button("Interpret requirements", key="agent_interpret"):
        try:
            parsed = interpret(prompt, use_api=use_api)
            st.json(parsed.model_dump())
            st.info("Review all extracted parameters before applying them. The language model does not solve FEA.")
        except Exception as exc:
            st.error(f"Unable to interpret the design brief: {exc}")
    if not os.getenv("OPENAI_API_KEY"):
        st.caption("No API key detected. Deterministic offline parsing is available.")

st.divider()
st.caption(
    "FORCEFORGE AI 2.0  |  HACK THE NEST 2026  |  "
    "Ideal pin-jointed 2D truss, linear elastic, small strain. "
    "Not validated for joint strength, fatigue, imperfections, or practical structural certification."
)
