"""ForceForge V3: an engineering-first, FEA-verified truss design studio.

Run with: python -m streamlit run app_ui_v3.py
The existing physics, optimization, and ML modules remain authoritative.
"""

from dataclasses import replace
import os

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from forceforge.agent import interpret
from forceforge.design import TOPOLOGIES, make_truss
from forceforge.physics import solve
from forceforge.robust import Requirements, best_feasible, evaluate, grid_search, pareto_front
from forceforge.sensitivity import elasticities
from forceforge.surrogate import propose_and_verify, train


NAVIGATION = ("Overview", "Structure Analysis", "Optimization", "AI Assistant")
LIMITS = (
    ("Yield", "worst_stress_util"),
    ("Displacement", "worst_displacement_util"),
    ("Ideal buckling", "worst_buckling_util"),
)
COLORS = {
    "blue": "#72a9ff", "teal": "#55d6d0", "orange": "#ffaf70",
    "red": "#ff738a", "muted": "#899db7", "grid": "#27334a",
    "paper": "rgba(0,0,0,0)", "plot": "#111b2b",
}
MATERIALS = {
    "Steel (nominal)": (200e9, 7850.0, 250e6),
    "Aluminum (nominal)": (70e9, 2700.0, 150e6),
}

st.set_page_config(
    page_title="ForceForge | Engineering Studio",
    page_icon=":triangular_ruler:", layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .stApp { background: radial-gradient(circle at 75% -15%, #1a2a44 0%, #0b1120 54%); color: #ecf3ff; }
  .block-container { max-width: 1680px; padding-top: 1.2rem; padding-bottom: 1.4rem; }
  [data-testid="stHeader"] { background: transparent; }
  [data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(18, 27, 43, 0.92); border: 1px solid #2a3951;
    border-radius: 15px; }
  [data-testid="stMetric"] {
    background: #151f30; border: 1px solid #2a3951;
    padding: .75rem .9rem; border-radius: 11px; }
  [data-testid="stMetricValue"] { color: #f1f7ff; font-size: 1.45rem; }
  [data-testid="stMetricLabel"] { color: #a3b5cb; }
  button[data-baseweb="tab"] { font-weight: 650; }
  .stButton button[kind="primary"] { background: #487ff1; color: white; border: 0; }
  .stButton button { border-radius: 10px; }
  div[data-testid="stProgress"] { padding-bottom: .15rem; }
  .ff-brand { font-size: 1.65rem; font-weight: 850; letter-spacing: -.06em; }
  .ff-brand span { color: #78abff; }
  .ff-subhead { font-size: .87rem; color: #9caec7; margin: .14rem 0 .9rem; }
  .ff-kicker { font-size: .70rem; letter-spacing: .13em; text-transform: uppercase;
    font-weight: 800; color: #8fb0e4; margin-bottom: .7rem; }
  .ff-status { border-radius: 12px; padding: .85rem 1rem; margin-bottom: .7rem;
    font-size: .92rem; font-weight: 700; }
  .ff-pass { color: #93efd0; background: #13342f; border: 1px solid #296358; }
  .ff-fail { color: #ffb4c0; background: #3e202e; border: 1px solid #74405a; }
  .ff-note { color: #9fb1c7; font-size: .75rem; line-height: 1.55; }
  .ff-tag { display: inline-block; padding: .2rem .6rem; border-radius: 99px;
    border: 1px solid #39506f; color: #bacff0; font-size: .66rem; letter-spacing: .07em; }
  .ff-divider { border-top: 1px solid #2b3c53; margin: .6rem 0 .8rem; }
  @media (max-width: 850px) {
    .ff-brand { font-size: 1.35rem; }
    .block-container { padding-top: .55rem; }
  }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_search(req: Requirements) -> pd.DataFrame:
    return grid_search(req)


@st.cache_resource(show_spinner=False)
def cached_model(req: Requirements):
    return train(cached_search(req))


def style_figure(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor=COLORS["paper"], plot_bgcolor=COLORS["plot"],
        font=dict(color="#b7c9df", size=11), margin=dict(l=12, r=12, t=24, b=26),
        hoverlabel=dict(bgcolor="#1c2c42", font_color="white"),
        legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    fig.update_yaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    return fig


def governing_constraint(check: dict) -> tuple[str, float]:
    name, key = max(LIMITS, key=lambda pair: float(check[pair[1]]))
    return name, float(check[key])


def limit_chart(check: dict) -> go.Figure:
    rows = [{"Constraint": name, "Utilization": float(check[key])} for name, key in LIMITS]
    values = [row["Utilization"] for row in rows]
    fig = go.Figure(go.Bar(
        x=values, y=[row["Constraint"] for row in rows], orientation="h",
        marker_color=[COLORS["red"] if value > 1 + 1e-10 else COLORS["teal"] for value in values],
        text=[f"{value:.2f}" for value in values], textposition="outside",
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=1.0, line_dash="dash", line_color=COLORS["orange"])
    fig.update_xaxes(range=[0, max(1.22, max(values) * 1.25)], title="Utilization / 1.0 limit")
    fig.update_yaxes(autorange="reversed")
    return style_figure(fig, 230)


def truss_plot(truss, result, show_deformation: bool = True) -> tuple[go.Figure, float]:
    xy = truss.nodes_m
    max_movement = max(float(np.max(np.linalg.norm(result.disp_m, axis=1))), 1e-12)
    scale = min(400.0, 0.07 * max(float(np.ptp(xy[:, 0])), 1.0) / max_movement)
    shown = xy + result.disp_m * scale if show_deformation else xy
    fig = go.Figure()
    if show_deformation:
        for i, (a, b) in enumerate(truss.elements):
            fig.add_trace(go.Scatter(
                x=xy[[a, b], 0], y=xy[[a, b], 1], mode="lines",
                line=dict(color="#50627d", width=2, dash="dot"),
                name="Undeformed", showlegend=i == 0, hoverinfo="skip",
            ))
    for i, (a, b) in enumerate(truss.elements):
        tension = float(result.force_n[i]) >= 0
        fig.add_trace(go.Scatter(
            x=shown[[a, b], 0], y=shown[[a, b], 1], mode="lines+markers",
            line=dict(width=6, color=COLORS["teal"] if tension else COLORS["orange"]),
            marker=dict(size=7, color="#eef6ff"), showlegend=False,
            hovertemplate=(
                f"Member {i}<br>{'Tension' if tension else 'Compression'}"
                f"<br>Axial force: {result.force_n[i]:,.1f} N"
                f"<br>Axial stress: {result.stress_pa[i] / 1e6:.3f} MPa<extra></extra>"
            ),
        ))
    fig.add_trace(go.Scatter(
        x=shown[:, 0], y=shown[:, 1], mode="markers+text",
        text=[str(i) for i in range(len(shown))], textposition="top center",
        marker=dict(size=6, color="#deebff"), showlegend=False,
        hovertemplate="Node %{text}<extra></extra>",
    ))
    for i, fixed_x, fixed_y in truss.supports:
        fig.add_trace(go.Scatter(
            x=[xy[i, 0]], y=[xy[i, 1]], mode="markers",
            marker=dict(size=18, symbol="triangle-up" if fixed_x else "triangle-down",
                        color=COLORS["blue"], line=dict(width=2, color="#e3efff")),
            showlegend=False, hovertemplate=f"Support at node {i}<extra></extra>",
        ))
    load_node = int(np.argmax(np.linalg.norm(truss.forces_n, axis=1)))
    force = float(np.linalg.norm(truss.forces_n[load_node]))
    if force > 0:
        fig.add_annotation(
            x=xy[load_node, 0], y=xy[load_node, 1], ax=0, ay=-65,
            text=f"LOAD {force:,.0f} N", showarrow=True, arrowhead=3,
            arrowcolor="#ffcf72", arrowwidth=2.6,
            font=dict(color="#ffcf72", size=11),
            bgcolor="rgba(11,17,31,.85)",
        )
    style_figure(fig, 410)
    fig.update_layout(showlegend=show_deformation)
    fig.update_xaxes(title="Span (m)", range=[-0.14 * np.ptp(xy[:, 0]), 1.14 * np.max(xy[:, 0])])
    fig.update_yaxes(title="Height (m)", scaleanchor="x", scaleratio=1)
    return fig, scale


def stress_chart(result, req: Requirements) -> go.Figure:
    stress = result.stress_pa / 1e6
    fig = go.Figure(go.Bar(
        x=[f"M{i}" for i in range(len(stress))], y=stress,
        marker_color=[COLORS["teal"] if val >= 0 else COLORS["orange"] for val in stress],
        hovertemplate="%{x}: %{y:.3f} MPa<extra></extra>",
    ))
    allowable = req.yield_pa / req.yield_safety_factor / 1e6
    fig.add_hline(y=allowable, line_color=COLORS["red"], line_dash="dash")
    fig.add_hline(y=-allowable, line_color=COLORS["red"], line_dash="dash")
    fig.update_yaxes(title="Signed axial stress (MPa)")
    return style_figure(fig)


def node_displacement_chart(result, req: Requirements) -> go.Figure:
    values = np.linalg.norm(result.disp_m, axis=1) * 1000
    fig = go.Figure(go.Bar(
        x=[f"N{i}" for i in range(len(values))], y=values,
        marker_color=COLORS["blue"],
        hovertemplate="%{x}: %{y:.5f} mm<extra></extra>",
    ))
    fig.add_hline(y=req.max_displacement_mm, line_dash="dash", line_color=COLORS["red"])
    fig.update_yaxes(title="Nodal displacement magnitude (mm)")
    return style_figure(fig)


def buckling_chart(result, req: Requirements) -> go.Figure:
    forces = np.asarray(result.force_n, dtype=float)
    use = np.where(
        forces < 0, np.abs(forces) * req.buckling_safety_factor /
        np.maximum(result.buckling_critical_n, 1e-15), 0.0,
    )
    fig = go.Figure(go.Bar(
        x=[f"M{i}" for i in range(len(use))], y=use,
        marker_color=[COLORS["red"] if v > 1 else COLORS["orange"] for v in use],
        hovertemplate="%{x}: %{y:.3f}<extra></extra>",
    ))
    fig.add_hline(y=1.0, line_dash="dash", line_color=COLORS["red"])
    fig.update_yaxes(title="Nominal ideal buckling utilization")
    return style_figure(fig)


def reactions_chart(truss, result) -> go.Figure:
    labels = [f"N{node}" for node, _, _ in truss.supports]
    rx = [float(result.reactions_n[node, 0]) if fix_x else 0.0
          for node, fix_x, fix_y in truss.supports]
    ry = [float(result.reactions_n[node, 1]) if fix_y else 0.0
          for node, fix_x, fix_y in truss.supports]
    fig = go.Figure()
    for name, values, color in (("Horizontal", rx, COLORS["blue"]),
                                ("Vertical", ry, COLORS["teal"])):
        fig.add_trace(go.Bar(x=labels, y=values, name=name,
                             marker_color=color,
                             hovertemplate="%{x}: %{y:.2f} N<extra></extra>"))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title="Support reaction (N)")
    return style_figure(fig)


def pareto_chart(df: pd.DataFrame) -> go.Figure:
    data = df.dropna(subset=["mass_kg", "worst_utilization"]).copy()
    fig = px.scatter(
        data, x="mass_kg", y="worst_utilization", color="topology", symbol="feasible",
        color_discrete_map={"Triangle": COLORS["blue"], "Fan": COLORS["teal"],
                            "Warren-2": COLORS["orange"]},
        hover_data=["height_m", "area_mm2", "worst_buckling_util"],
        labels={"mass_kg": "Nominal mass (kg)", "worst_utilization": "Worst-case utilization"},
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=COLORS["red"])
    front = pareto_front(df, x="mass_kg", y="worst_utilization")
    if not front.empty:
        fig.add_trace(go.Scatter(
            x=front.mass_kg, y=front.worst_utilization,
            mode="lines+markers", name="Feasible Pareto frontier",
            line=dict(color="#e5f0ff", width=2, dash="dot"),
            marker=dict(size=7, color="#ffffff"),
        ))
    return style_figure(fig, 375)


def topology_chart(df: pd.DataFrame) -> go.Figure:
    rows = []
    for topology in TOPOLOGIES:
        sub = df[(df["topology"] == topology) & (df["feasible"] == True)]
        rows.append({"Topology": topology, "Feasible": len(sub),
                     "Best mass (kg)": float(sub["mass_kg"].min()) if len(sub) else 0.0,
                     "Available": bool(len(sub))})
    fig = go.Figure(go.Bar(
        x=[r["Topology"] for r in rows], y=[r["Best mass (kg)"] for r in rows],
        marker_color=[COLORS["blue"] if r["Available"] else "#4b5364" for r in rows],
        customdata=[r["Feasible"] for r in rows],
        hovertemplate="%{x}<br>Best feasible mass: %{y:.3f} kg<br>Feasible candidates: %{customdata}<extra></extra>",
    ))
    fig.update_yaxes(title="Lowest feasible mass (kg)")
    return style_figure(fig, 270)


def comparison_chart(current: float, recommended: float, title: str, units: str) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[current, recommended], y=["Current", "Recommended"], orientation="h",
        marker_color=[COLORS["muted"], COLORS["teal"]],
        text=[f"{current:.2f} {units}", f"{recommended:.2f} {units}"],
        textposition="outside", cliponaxis=False,
    ))
    fig.update_xaxes(range=[0, max(current, recommended, 1e-9) * 1.38], title=title)
    fig.update_yaxes(autorange="reversed")
    return style_figure(fig, 220)


def sensitivity_chart(df: pd.DataFrame, output: str) -> go.Figure:
    sub = df[df["Output"] == output].sort_values("Local elasticity")
    values = sub["Local elasticity"].tolist()
    fig = go.Figure(go.Bar(
        x=values, y=sub["Parameter"].tolist(), orientation="h",
        marker_color=[COLORS["orange"] if v < 0 else COLORS["teal"] for v in values],
        hovertemplate="%{y}: %{x:.3f}<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="#a5b7d0")
    fig.update_xaxes(title="Local elasticity")
    return style_figure(fig, 230)


def metric_tiles(result, check):
    cols = st.columns(4, gap="small")
    cols[0].metric("Mass", f"{result.mass_kg:.2f} kg")
    cols[1].metric("Max displacement", f"{result.max_disp_m * 1000:.3f} mm")
    cols[2].metric("Max axial stress", f"{result.max_stress_pa / 1e6:.2f} MPa")
    cols[3].metric("Worst utilization", f"{float(check['worst_utilization']):.3f} / 1.0")


def status_box(check):
    governing, util = governing_constraint(check)
    status = "PASS" if check["feasible"] else "FAIL"
    phrase = "All modeled scenario constraints pass." if check["feasible"] else "At least one modeled constraint is exceeded."
    css = "ff-pass" if check["feasible"] else "ff-fail"
    st.markdown(
        f'<div class="ff-status {css}">{status} — {phrase} '
        f'Governing check: {governing} ({util:.2f}).</div>', unsafe_allow_html=True,
    )


def plot_truss_in_panel(truss, result, key: str):
    show = st.toggle("Show deformed geometry", value=True, key=key)
    fig, scale = truss_plot(truss, result, show)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    st.caption(
        "Teal = tension | Orange = compression | Light-blue triangles = supports. "
        + (f"Deformation magnified {scale:.0f}x." if show else "Undeformed geometry displayed.")
    )


# ---- App header and navigation ----
st.markdown(
    '<div class="ff-brand"><span>◭</span> ForceForge <span style="color:#9eb5d6;font-weight:450">/ Studio</span></div>'
    '<div class="ff-subhead">Design, visualize, challenge, and validate lightweight trusses using physics-backed computation.</div>',
    unsafe_allow_html=True,
)
page = st.radio("Workspace", NAVIGATION, horizontal=True, label_visibility="collapsed", key="ff_page")
# Apply values on the next script pass, before the sliders are instantiated.
pending_inputs = st.session_state.pop("ff_pending_inputs", None)
if pending_inputs is not None:
    st.session_state.update(pending_inputs)
st.write("")

# All pages share inputs and the same FEA reference state.
left, center, right = st.columns([1.02, 2.45, 1.10], gap="medium")
with left:
    with st.container(border=True):
        st.markdown('<div class="ff-kicker">Design parameters</div>', unsafe_allow_html=True)
        topology = st.selectbox("Topology", TOPOLOGIES, key="ff_topology")
        material = st.selectbox("Material", list(MATERIALS), key="ff_material")
        E, density, sy = MATERIALS[material]
        span = st.slider("Span (m)", 0.5, 4.0, 2.0, 0.1, key="ff_span")
        ratio = st.slider("Height / span", 0.20, 1.25, 0.50, 0.05, key="ff_height_ratio")
        height = span * ratio
        area = st.slider("Member area (mm²)", 60.0, 800.0, 180.0, 10.0, key="ff_area")
        force = st.slider("Central load (N)", 100, 3000, 1000, 100, key="ff_force")
        with st.expander("Limits and uncertainty"):
            max_disp = st.slider("Allowable movement (mm)", .25, 12.0, 2.0, .25, key="ff_limit")
            safety_y = st.slider("Yield safety factor", 1.0, 4.0, 2.0, .25, key="ff_yield_sf")
            safety_b = st.slider("Buckling safety factor", 1.0, 4.0, 2.0, .25, key="ff_buckle_sf")
            load_unc = st.slider("Load increase (%)", 0, 50, 20, 5, key="ff_load_unc") / 100
            e_unc = st.slider("Stiffness reduction (%)", 0, 35, 10, 5, key="ff_e_unc") / 100
            area_unc = st.slider("Area reduction (%)", 0, 25, 10, 5, key="ff_area_unc") / 100
        st.caption(f"Truss height: {height:.2f} m · Fixed idealized center-load topology")

req = Requirements(
    span_m=span, base_load_n=force, material_E_pa=E,
    density_kg_m3=density, yield_pa=sy, max_displacement_mm=max_disp,
    yield_safety_factor=safety_y, buckling_safety_factor=safety_b,
    load_uncertainty=load_unc, e_uncertainty=e_unc, area_uncertainty=area_unc,
)
if st.session_state.get("ff_req_signature") != req:
    for key in ("ff_search", "ff_ml_metrics", "ff_ml_results", "ff_redesign"):
        st.session_state.pop(key, None)
    st.session_state["ff_req_signature"] = req

try:
    truss = make_truss(topology, span, height, area, force, req.material)
    result = solve(truss)
    check = evaluate(topology, height, area, req)
except (ValueError, np.linalg.LinAlgError) as exc:
    st.error(f"Unable to solve this design: {exc}")
    st.stop()

# Prominent quick readout is above the detailed page content.
with right:
    with st.container(border=True):
        st.markdown('<div class="ff-kicker">Live engineering inspector</div>', unsafe_allow_html=True)
        status_box(check)
        controlling, controlling_value = governing_constraint(check)
        st.metric("Governing utilization", f"{controlling_value:.3f}")
        st.caption(f"Constraint: {controlling}")
        st.plotly_chart(limit_chart(check), use_container_width=True,
                        config={"displayModeBar": False}, key="ff_inspector_limits")
        st.markdown('<div class="ff-divider"></div>', unsafe_allow_html=True)
        st.metric("Nominal mass", f"{result.mass_kg:.2f} kg")
        st.metric("Max displacement", f"{result.max_disp_m * 1000:.3f} mm")
        st.metric("Max stress", f"{result.max_stress_pa / 1e6:.2f} MPa")
        st.caption("FEA scenario screening; not structural certification.")

with center:
    if page == "Overview":
        st.markdown('<div class="ff-kicker">01 / Project overview</div>', unsafe_allow_html=True)
        status_box(check)
        metric_tiles(result, check)
        with st.container(border=True):
            st.markdown("**Structural viewport**")
            plot_truss_in_panel(truss, result, "ff_overview_show")
        st.info(
            "Next: inspect individual members in Structure Analysis, or run a robust design search "
            "to compare feasible alternatives in Optimization."
        )

    elif page == "Structure Analysis":
        st.markdown('<div class="ff-kicker">02 / Structural analysis</div>', unsafe_allow_html=True)
        status_box(check)
        with st.container(border=True):
            st.markdown("**Geometry and force directions**")
            plot_truss_in_panel(truss, result, "ff_analysis_show")
        st.markdown("**Explore model responses**")
        stress_tab, displacement_tab, buckling_tab, support_tab = st.tabs(
            ["Member stress", "Node movement", "Buckling check", "Support reactions"]
        )
        with stress_tab:
            st.plotly_chart(stress_chart(result, req), use_container_width=True)
            st.caption("Signed nominal axial stress. Dashed limits represent nominal yield-strength screening.")
        with displacement_tab:
            st.plotly_chart(node_displacement_chart(result, req), use_container_width=True)
            st.caption("Resultant nominal nodal movement; dashed line is the allowed displacement.")
        with buckling_tab:
            st.plotly_chart(buckling_chart(result, req), use_container_width=True)
            st.caption("Nominal Euler buckling screen for ideal pinned round bars; tension members display zero.")
        with support_tab:
            st.plotly_chart(reactions_chart(truss, result), use_container_width=True)
            net_residual = np.linalg.norm(np.sum(result.reactions_n + truss.forces_n, axis=0))
            st.caption(f"Global equilibrium residual: {net_residual:.3e} N.")
        with st.expander("Detailed member, displacement, and reaction data"):
            member_rows = pd.DataFrame({
                "Member": [f"M{i}" for i in range(len(truss.elements))],
                "Force (N)": result.force_n,
                "Stress (MPa)": result.stress_pa / 1e6,
                "Ideal buckling Pcr (N)": result.buckling_critical_n,
            })
            movement_rows = pd.DataFrame({
                "Node": [f"N{i}" for i in range(len(truss.nodes_m))],
                "Ux (mm)": result.disp_m[:, 0] * 1000,
                "Uy (mm)": result.disp_m[:, 1] * 1000,
            })
            support_rows = pd.DataFrame([
                {"Support node": f"N{i}",
                 "Rx (N)": result.reactions_n[i, 0] if fx else None,
                 "Ry (N)": result.reactions_n[i, 1] if fy else None}
                for i, fx, fy in truss.supports
            ])
            st.dataframe(member_rows.round(5), use_container_width=True, hide_index=True)
            st.dataframe(movement_rows.round(5), use_container_width=True, hide_index=True)
            st.dataframe(support_rows.round(5), use_container_width=True, hide_index=True)

    elif page == "Optimization":
        st.markdown('<div class="ff-kicker">03 / Robust optimization</div>', unsafe_allow_html=True)
        search_tab, challenge_tab = st.tabs(["Design search", "Challenge and redesign"])
        with search_tab:
            st.write("Search 144 candidates across the three available topologies and eight uncertainty scenarios.")
            if st.button("Run physics-verified optimization", type="primary", key="ff_run_search"):
                with st.spinner("Evaluating engineering constraints across the design grid..."):
                    st.session_state["ff_search"] = cached_search(req)
            designs = st.session_state.get("ff_search")
            if designs is not None:
                best = best_feasible(designs)
                cols = st.columns(3)
                cols[0].metric("Candidates screened", str(len(designs)))
                cols[1].metric("Feasible candidates", str(int(designs.feasible.sum())))
                cols[2].metric("Best feasible mass", f"{best['mass_kg']:.2f} kg" if best else "None")
                if best is None:
                    st.error("No candidate passes all scenario constraints in the current search space.")
                else:
                    improvement = 100 * (1 - float(best["mass_kg"]) / result.mass_kg)
                    direction = "lighter" if improvement >= 0 else "heavier"
                    st.success(
                        f"Lowest-mass feasible option: {best['topology']} · "
                        f"{best['height_m']:.2f} m high · {best['area_mm2']:.0f} mm² section · "
                        f"{abs(improvement):.1f}% {direction} than the current design."
                    )
                st.markdown("**Design trade-off: mass versus worst-case utilization**")
                st.plotly_chart(pareto_chart(designs), use_container_width=True)
                st.markdown("**Compare topology families**")
                st.plotly_chart(topology_chart(designs), use_container_width=True)
                st.caption("A zero-height bar indicates no feasible candidate for that topology in this grid.")
                if best is not None:
                    st.markdown("**Current design versus best feasible candidate**")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.plotly_chart(comparison_chart(
                            result.mass_kg, float(best["mass_kg"]), "Mass (kg)", "kg"
                        ), use_container_width=True)
                    with c2:
                        st.plotly_chart(comparison_chart(
                            float(check["worst_utilization"]), float(best["worst_utilization"]),
                            "Worst-case utilization", ""
                        ), use_container_width=True)
                    with st.expander("Local sensitivity of the recommended design"):
                        output = st.selectbox("Output to explain", [
                            "mass_kg", "worst_stress_util", "worst_displacement_util",
                            "worst_buckling_util",
                        ], key="ff_sens_output")
                        local = elasticities(str(best["topology"]),
                                             float(best["height_m"]),
                                             float(best["area_mm2"]), req)
                        st.plotly_chart(sensitivity_chart(local, output), use_container_width=True)
                        st.caption("Finite-difference local elasticity; not a global sensitivity or causal claim.")
                with st.expander("Explore full candidate data and export"):
                    st.dataframe(designs.round(4), use_container_width=True, hide_index=True)
                    st.download_button("Download candidate results (CSV)", designs.to_csv(index=False),
                                       "forceforge_fea_candidates.csv", mime="text/csv")
            else:
                st.info("Run optimization to compare FEA-screened designs. No optimization results are preloaded.")
        with challenge_tab:
            st.write("Apply a larger load envelope to the current design and rerun all constraint checks.")
            challenge = st.slider("Load multiplier", 1.0, 1.6, 1.2, .05, key="ff_challenge")
            expanded = replace(req, load_uncertainty=max(req.load_uncertainty, challenge - 1.0))
            challenged = evaluate(topology, height, area, expanded)
            c1, c2 = st.columns(2)
            c1.metric("Current envelope", f"{float(check['worst_utilization']):.3f}")
            c2.metric("Expanded envelope", f"{float(challenged['worst_utilization']):.3f}")
            status_box(challenged)
            st.plotly_chart(limit_chart(challenged), use_container_width=True)
            if st.button("Find FEA-verified redesign", type="primary", key="ff_run_redesign"):
                with st.spinner("Re-optimizing across the expanded load envelope..."):
                    st.session_state["ff_redesign"] = (expanded, best_feasible(cached_search(expanded)))
            record = st.session_state.get("ff_redesign")
            if record is not None and record[0] == expanded:
                redesign = record[1]
                if redesign is None:
                    st.warning("No feasible redesign found in the fixed search grid.")
                else:
                    change = 100 * (float(redesign["mass_kg"]) / result.mass_kg - 1)
                    st.success(
                        f"FEA-screened redesign: {redesign['topology']}, "
                        f"{redesign['height_m']:.2f} m high, {redesign['area_mm2']:.0f} mm² section. "
                        f"Mass: {redesign['mass_kg']:.2f} kg ({change:+.1f}% vs current design)."
                    )
                    replacement = make_truss(str(redesign["topology"]), span,
                                             float(redesign["height_m"]),
                                             float(redesign["area_mm2"]), force, req.material)
                    replacement_result = solve(replacement)
                    st.plotly_chart(truss_plot(replacement, replacement_result)[0],
                                    use_container_width=True)
                    st.caption("The displayed redesigned geometry is evaluated at nominal load.")

    else:
        st.markdown('<div class="ff-kicker">04 / AI assistant and ML verification</div>', unsafe_allow_html=True)
        agent_tab, ml_tab = st.tabs(["Interpret design brief", "ML surrogate + FEA"])
        with agent_tab:
            st.write("Describe engineering requirements in English. Review parsed values before applying them.")
            brief = st.text_area(
                "Design brief", key="ff_brief", height=115,
                value="Design a lightweight 2 m truss under 1000 N with a 2 mm displacement limit.",
            )
            use_api = st.checkbox("Use optional OpenAI parsing when an API key is available", key="ff_use_api")
            if st.button("Interpret requirements", type="primary", key="ff_parse"):
                try:
                    st.session_state["ff_parsed"] = (brief, use_api, interpret(brief, use_api=use_api))
                except Exception as exc:
                    st.session_state.pop("ff_parsed", None)
                    st.error(f"Unable to interpret requirements: {exc}")
            parsed_record = st.session_state.get("ff_parsed")
            parsed = (parsed_record[2] if parsed_record is not None and
                      parsed_record[:2] == (brief, use_api) else None)
            if parsed is not None:
                cols = st.columns(3)
                cols[0].metric("Span", f"{parsed.span_m:.2f} m")
                cols[1].metric("Load", f"{parsed.load_n:.0f} N")
                cols[2].metric("Movement limit", f"{parsed.max_displacement_mm:.2f} mm")
                st.caption(parsed.rationale)
                in_range = (
                    0.5 <= parsed.span_m <= 4.0 and
                    100 <= parsed.load_n <= 3000 and
                    0.25 <= parsed.max_displacement_mm <= 12.0
                )
                load_step_ok = abs(parsed.load_n / 100 - round(parsed.load_n / 100)) < 1e-8
                span_step_ok = abs(parsed.span_m * 10 - round(parsed.span_m * 10)) < 1e-8
                limit_step_ok = abs(parsed.max_displacement_mm * 4 - round(parsed.max_displacement_mm * 4)) < 1e-8
                if not (in_range and load_step_ok and span_step_ok and limit_step_ok):
                    st.warning("Values must match the available slider ranges and steps before applying them. Edit the brief or use the left-side controls.")
                else:
                    if st.button("Apply values to design inputs", key="ff_apply"):
                        st.session_state["ff_pending_inputs"] = {
                            "ff_span": float(parsed.span_m),
                            "ff_force": int(parsed.load_n),
                            "ff_limit": float(parsed.max_displacement_mm),
                        }
                        st.session_state.pop("ff_parsed", None)
                        st.rerun()
            if not os.getenv("OPENAI_API_KEY"):
                st.caption("No API key configured. The local deterministic parser still works offline.")
        with ml_tab:
            st.write("Fit a surrogate on FEA outcomes, inspect held-out errors, then re-evaluate its proposals with FEA.")
            if st.button("Train and assess surrogate", type="primary", key="ff_train_ml"):
                with st.spinner("Training Random Forest and validating on held-out design rows..."):
                    model, columns, metrics = cached_model(req)
                    st.session_state["ff_ml_metrics"] = metrics
            metrics = st.session_state.get("ff_ml_metrics")
            if metrics is not None:
                records = [
                    {"Output": key.replace("worst_", "").replace("_util", ""),
                     "MAE": values["mae"], "Mean baseline MAE": values["baseline_mae"],
                     "Test R²": values["r2"]}
                    for key, values in metrics.items()
                ]
                display = pd.DataFrame(records)
                fig = go.Figure()
                fig.add_trace(go.Bar(x=display["Output"], y=display["MAE"],
                                     name="Random Forest", marker_color=COLORS["blue"]))
                fig.add_trace(go.Bar(x=display["Output"], y=display["Mean baseline MAE"],
                                     name="Mean baseline", marker_color=COLORS["muted"]))
                fig.update_layout(barmode="group")
                fig.update_yaxes(title="Held-out MAE (utilization)")
                st.plotly_chart(style_figure(fig, 300), use_container_width=True)
                st.dataframe(display.round(4), use_container_width=True, hide_index=True)
                st.caption("Grouped design holdout estimates interpolation error only, not unseen topology generalization.")
                if st.button("Propose and recheck candidates with FEA", key="ff_propose"):
                    with st.spinner("Ranking ML proposals and repeating the structural FEA checks..."):
                        model, columns, _ = cached_model(req)
                        st.session_state["ff_ml_results"] = propose_and_verify(model, columns, req, n=300)
            verified = st.session_state.get("ff_ml_results")
            if verified is not None:
                good = verified[verified["feasible"] == True]
                st.metric("FEA-verified proposals", f"{len(good)} / {len(verified)}")
                if good.empty:
                    st.warning("The proposed candidates did not satisfy all screened constraints.")
                else:
                    row = good.sort_values("mass_kg").iloc[0]
                    st.success(f"Lightest verified proposal: {row['topology']}, {row['mass_kg']:.2f} kg; worst utilization {row['worst_utilization']:.3f}.")
                with st.expander("FEA-verified proposal details"):
                    st.dataframe(verified.round(4), use_container_width=True, hide_index=True)
            st.info("ML recommends candidates; FEA determines whether modeled constraints pass.")

st.divider()
st.caption(
    "ForceForge AI 2.0 · Hack the Nest 2026 · Simplified ideal pin-jointed 2D linear-elastic trusses. "
    "No joint, fatigue, local buckling, imperfection, or structural-certification checks are performed."
)
