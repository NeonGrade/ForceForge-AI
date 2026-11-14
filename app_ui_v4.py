"""ForceForge AI V4 - viewport-first, click-to-switch engineering workspace.

Run from the ForceForge-AI repository root:
    python3 -m streamlit run app_ui_v4.py

Uses the repository's physics / robust / ML modules unchanged. Desktop-first,
with a safe scroll fallback for smaller browser viewports.
"""

from dataclasses import replace
import os
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from forceforge.agent import interpret
from forceforge.design import TOPOLOGIES, make_truss
from forceforge.physics import solve
from forceforge.robust import Requirements, evaluate, grid_search, best_feasible, pareto_front
from forceforge.surrogate import train, propose_and_verify


COLORS = {
    "bg": "#0A1020", "panel": "#121F32", "cyan": "#52D9CC",
    "blue": "#72AAFF", "amber": "#FFB978", "red": "#FF7E95",
    "muted": "#93A8C1", "grid": "#26354A", "white": "#F4F8FF",
}
MATERIALS = {
    "Steel (nominal)": (200e9, 7850.0, 250e6),
    "Aluminum (nominal)": (70e9, 2700.0, 150e6),
}
LIMITS = (
    ("Stress / Yield", "worst_stress_util"),
    ("Displacement", "worst_displacement_util"),
    ("Ideal buckling", "worst_buckling_util"),
)
PLOT_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": False}

st.set_page_config(
    page_title="ForceForge AI | Engineering Workstation",
    page_icon=":triangular_ruler:",
    layout="wide", initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
:root { --ff-cyan:#52d9cc; --ff-edge:#283d58; }
.stApp { background: radial-gradient(ellipse at 65% -15%, #192a46, #0a1020 62%); color: #eff7ff; }
[data-testid="stHeader"] { background: transparent; height: 0 !important; }
[data-testid="stDecoration"] { display:none; }
.block-container { padding: .65rem 1.05rem .4rem; max-width: 1760px; }
[data-testid="stVerticalBlock"] { gap: .52rem; }
[data-testid="stHorizontalBlock"] { gap: .75rem; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(16,27,44,.94); border: 1px solid #293b55;
  border-radius: 15px; padding: .1rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap:.40rem; }
[data-testid="stWidgetLabel"] { margin-bottom:-.24rem; }
[data-testid="stWidgetLabel"] p { font-size:.77rem !important; color:#a9bad1 !important; }
[data-testid="stNumberInput"] input { padding: .3rem .5rem !important; height: 2rem; }
[data-testid="stSelectbox"] [data-baseweb="select"] > div { min-height:2.05rem; }
[data-testid="stRadio"] div[role="radiogroup"] { gap:.4rem 1rem; }
[data-testid="stRadio"] label p { font-size:.79rem; }
[data-testid="stTextArea"] textarea { min-height:5rem !important; }
.stButton button, [data-testid="stPopover"] button { border-radius:9px; min-height:2.05rem; }
.stButton button[kind="primary"] { background:#397de7; color:#fff; border:none; }
[data-testid="stAlert"] { padding:.35rem .75rem; }
[data-testid="stAlert"] p { font-size:.8rem; }
[data-testid="stDataFrame"] { border:1px solid #273c53; border-radius:8px; }
.ff-head { display:flex;align-items:center;gap:.55rem;font-size:1.46rem;
  font-weight:850;letter-spacing:-.055em;white-space:nowrap;color:#f0f8ff; }
.ff-icon { color:#55d8ce; font-size:1.65rem; }
.ff-tagline { color:#8ea9c6;font-size:.71rem;margin-top:-.35rem; }
.ff-kicker { font-size:.67rem;color:#8eb0d9;letter-spacing:.12em;
  font-weight:800;text-transform:uppercase; margin:0 0 .2rem; }
.ff-sectionhead { font-size:.91rem;color:#f3f8ff;font-weight:750; }
.ff-brief { font-size:.78rem;color:#9fb4ce;line-height:1.55; }
.ff-status {padding:.55rem .7rem;border:1px solid #275d55;background:#11382f;
  color:#a9f0de;border-radius:9px;font-size:.80rem;font-weight:740;}
.ff-status.fail { border-color:#78455b;background:#422432;color:#ffbdc8; }
.ff-status small { display:block;font-weight:450;line-height:1.35;margin-top:.12rem; }
.ff-kpis { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.55rem; }
.ff-kpi { background:#142238;border:1px solid #283b56;padding:.55rem .65rem;border-radius:10px;min-width:0; }
.ff-kpi label {display:block;font-size:.69rem;color:#9bafc9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.ff-kpi strong {font-size:1.23rem;letter-spacing:-.03em;color:#f5f9ff;}
.ff-kpi small {margin-left:.2rem;color:#8eabc8;font-size:.7rem;}
.ff-slimbox {border:1px solid #293d58;background:#142338;padding:.65rem .75rem;border-radius:10px;}
.ff-constraint {margin:.52rem 0 .82rem;}
.ff-constraint-top {display:flex;justify-content:space-between;align-items:center;
  font-size:.77rem;color:#b6c8dd;margin-bottom:.26rem;}
.ff-bar {width:100%;height:8px;border-radius:99px;background:#24374e;overflow:hidden;}
.ff-fill {height:100%;border-radius:99px;}
.ff-rule {border-top:1px solid #293b53;margin:.7rem 0;}
.ff-hint {font-size:.72rem;color:#8fa5c1;line-height:1.6;}
.ff-action {font-size:.78rem;color:#bbd3ed;margin-top:.25rem;}
@media (min-width:1180px) and (min-height:700px) {
  html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"] {
    height:100dvh !important; overflow:hidden !important;
  }
  .block-container {height:100dvh !important;overflow:hidden !important;}
}
@media (max-width:1179px), (max-height:699px) {
  [data-testid="stMain"] {overflow:auto !important;}
  .ff-kpis {grid-template-columns:repeat(2,minmax(0,1fr));}
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_search(req: Requirements) -> pd.DataFrame:
    return grid_search(req)


@st.cache_resource(show_spinner=False)
def cached_model(req: Requirements):
    return train(cached_search(req))


def figure_style(fig: go.Figure, height: int = 326) -> go.Figure:
    fig.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#111e31",
        font=dict(color="#aac1da", size=11),
        margin=dict(l=12, r=10, t=24, b=32),
        hoverlabel=dict(bgcolor="#21354e", font_color="white"),
        legend=dict(orientation="h", y=1.14, x=0, bgcolor="rgba(0,0,0,0)"),
        autosize=True,
    )
    fig.update_xaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    fig.update_yaxes(gridcolor=COLORS["grid"], zerolinecolor=COLORS["grid"])
    return fig


def show_plot(fig: go.Figure, key: str):
    st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG, key=key)


def truss_figure(truss, res, show_deform=True) -> go.Figure:
    points = truss.nodes_m
    movement = float(np.linalg.norm(res.disp_m, axis=1).max())
    scale = min(400., .08 * max(np.ptp(points[:, 0]), 1.) / max(movement, 1e-12))
    moved = points + res.disp_m * scale if show_deform else points
    fig = go.Figure()
    for i, (a, b) in enumerate(truss.elements):
        if show_deform:
            fig.add_trace(go.Scatter(
                x=points[[a,b],0], y=points[[a,b],1], mode="lines",
                line=dict(color="#4d6280", width=2, dash="dot"),
                name="Original geometry", showlegend=(i == 0), hoverinfo="skip",
            ))
        tension = res.force_n[i] >= 0
        fig.add_trace(go.Scatter(
            x=moved[[a,b],0], y=moved[[a,b],1], mode="lines+markers",
            line=dict(color=COLORS["cyan"] if tension else COLORS["amber"], width=5),
            marker=dict(size=6, color="#eff7ff"), showlegend=False,
            hovertemplate=(
                f"Member M{i} | {'Tension' if tension else 'Compression'}"
                f"<br>Force: {res.force_n[i]:,.1f} N"
                f"<br>Stress: {res.stress_pa[i] / 1e6:.3f} MPa<extra></extra>"
            ),
        ))
    for i, (x, y) in enumerate(moved):
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text", text=[f"N{i}"], textposition="top center",
            marker=dict(size=7, color="#ecf5ff"), showlegend=False,
            hovertemplate=f"Node N{i}<extra></extra>",
        ))
    for node, fx, fy in truss.supports:
        fig.add_trace(go.Scatter(
            x=[points[node,0]], y=[points[node,1]], mode="markers",
            marker=dict(size=17, symbol="triangle-up" if fx else "triangle-down",
                        color=COLORS["blue"], line=dict(width=2, color="#dae9ff")),
            hovertemplate=f"Support at N{node}<extra></extra>", showlegend=False,
        ))
    load_node = int(np.argmax(np.linalg.norm(truss.forces_n, axis=1)))
    force = float(np.linalg.norm(truss.forces_n[load_node]))
    if force:
        fig.add_annotation(
            x=float(points[load_node,0]), y=float(points[load_node,1]),
            ax=0, ay=-57, text=f"{force:,.0f} N ↓", showarrow=True,
            arrowhead=3, arrowcolor="#ffc783", font=dict(color="#ffc783", size=11),
            bgcolor="rgba(12,18,32,.8)",
        )
    figure_style(fig, 351)
    fig.update_layout(showlegend=show_deform)
    fig.update_xaxes(title="Span (m)", range=[-0.14 * np.ptp(points[:,0]), 1.14 * float(points[:,0].max())])
    fig.update_yaxes(title="Height (m)", scaleanchor="x", scaleratio=1)
    return fig


def bar_figure(labels, values, title, units="", allowed=None, signed=False, colors=None) -> go.Figure:
    vals = [float(x) for x in values]
    fig = go.Figure(go.Bar(
        x=list(labels), y=vals,
        marker_color=colors or [COLORS["cyan"] if v >= 0 else COLORS["amber"] for v in vals],
        hovertemplate=f"%{{x}}: %{{y:.4f}} {units}<extra></extra>",
    ))
    if allowed is not None:
        fig.add_hline(y=float(allowed), line_color=COLORS["red"], line_dash="dash")
        if signed:
            fig.add_hline(y=-float(allowed), line_color=COLORS["red"], line_dash="dash")
    fig.update_yaxes(title=title)
    return figure_style(fig)


def analysis_figure(view, truss, res, req):
    if view == "Stress":
        return bar_figure([f"M{i}" for i in range(len(res.stress_pa))],
                          res.stress_pa / 1e6, "Axial stress (MPa)", "MPa",
                          req.yield_pa / req.yield_safety_factor / 1e6, True)
    if view == "Movement":
        return bar_figure([f"N{i}" for i in range(len(res.disp_m))],
                          np.linalg.norm(res.disp_m, axis=1) * 1000,
                          "Nodal movement (mm)", "mm", req.max_displacement_mm,
                          colors=[COLORS["blue"]] * len(res.disp_m))
    if view == "Buckling":
        forces = np.asarray(res.force_n, float)
        values = np.where(forces < 0, abs(forces) * req.buckling_safety_factor /
                          np.maximum(res.buckling_critical_n, 1e-12), 0.)
        return bar_figure([f"M{i}" for i in range(len(forces))],
                          values, "Nominal ideal buckling utilization", "", 1.0)
    if view == "Reactions":
        labels = [f"N{i}" for i, _, _ in truss.supports]
        rx = [float(res.reactions_n[i, 0]) if fx else 0. for i, fx, fy in truss.supports]
        ry = [float(res.reactions_n[i, 1]) if fy else 0. for i, fx, fy in truss.supports]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=labels, y=rx, name="Horizontal", marker_color=COLORS["blue"]))
        fig.add_trace(go.Bar(x=labels, y=ry, name="Vertical", marker_color=COLORS["cyan"]))
        fig.update_layout(barmode="group")
        fig.update_yaxes(title="Support reaction (N)")
        return figure_style(fig)
    raise ValueError(f"Unsupported view: {view}")


def tradeoff_figure(df):
    clean = df.dropna(subset=["mass_kg", "worst_utilization"])
    fig = px.scatter(
        clean, x="mass_kg", y="worst_utilization", color="topology", symbol="feasible",
        hover_data=["height_m", "area_mm2", "worst_buckling_util"],
        color_discrete_map={"Triangle":COLORS["blue"], "Fan":COLORS["cyan"],
                            "Warren-2":COLORS["amber"]},
        labels={"mass_kg":"Nominal mass (kg)", "worst_utilization":"Worst scenario utilization"},
    )
    front = pareto_front(df, x="mass_kg", y="worst_utilization")
    if len(front):
        fig.add_trace(go.Scatter(
            x=front.mass_kg, y=front.worst_utilization, mode="lines+markers",
            name="Feasible Pareto frontier", line=dict(color="#e7f3ff", dash="dot"),
        ))
    fig.add_hline(y=1., line_color=COLORS["red"], line_dash="dash")
    return figure_style(fig)


def topologies_figure(df):
    items = []
    for name in TOPOLOGIES:
        sub = df[(df.topology == name) & (df.feasible == True)]
        items.append((name, float(sub.mass_kg.min()) if len(sub) else None))
    names = [a for a, _ in items]
    values = [v or 0 for _, v in items]
    return bar_figure(names, values, "Best feasible mass (kg)", "kg",
                      colors=[COLORS["cyan"] if v is not None else "#536176" for _, v in items])


def compare_figure(old_mass, best_mass, old_util, best_util):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[old_mass, best_mass], y=["Current mass", "Best mass"],
                         orientation="h", marker_color=[COLORS["muted"], COLORS["cyan"]],
                         text=[f"{old_mass:.2f} kg", f"{best_mass:.2f} kg"], textposition="auto"))
    fig.update_layout(title=f"Current worst utilization: {old_util:.3f} | Recommended: {best_util:.3f}")
    fig.update_xaxes(title="Nominal mass (kg)")
    return figure_style(fig)


def limit_figure(check):
    values = [float(check[key]) for _, key in LIMITS]
    labels = [label for label, _ in LIMITS]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=[COLORS["red"] if v > 1 else COLORS["cyan"] for v in values],
        text=[f"{v:.3f}" for v in values], textposition="auto",
    ))
    fig.add_vline(x=1., line_color=COLORS["amber"], line_dash="dash")
    fig.update_xaxes(title="Utilization (1.0 = limit)", range=[0, max(1.20, max(values) * 1.13)])
    fig.update_yaxes(autorange="reversed")
    return figure_style(fig)


def kpi_cards(items):
    cards = "".join(
        '<div class="ff-kpi"><label>' + html.escape(str(label)) + '</label>'
        + '<strong>' + html.escape(str(value)) + '</strong>'
        + '<small>' + html.escape(str(unit)) + '</small></div>'
        for label, value, unit in items
    )
    st.markdown('<div class="ff-kpis">' + cards + '</div>', unsafe_allow_html=True)


def status_html(check):
    passed = bool(check["feasible"])
    status = "PASS · Screened constraints" if passed else "FAIL · Constraint exceeded"
    explanation = "All modeled scenarios satisfy the chosen limits." if passed else "At least one modeled limit is exceeded."
    css = "ff-status" if passed else "ff-status fail"
    st.markdown(f'<div class="{css}">{status}<small>{explanation}</small></div>', unsafe_allow_html=True)


def inspector(check, res, topology, span, height):
    st.markdown('<div class="ff-kicker">Live inspector</div>', unsafe_allow_html=True)
    status_html(check)
    st.markdown(
        f'<div class="ff-brief">{html.escape(topology)} · {span:.2f} m span '
        f'· {height:.2f} m height</div>', unsafe_allow_html=True,
    )
    bars = []
    for label, key in LIMITS:
        val = float(check[key])
        color = COLORS["red"] if val > 1.0000000001 else COLORS["cyan"]
        bars.append(
            f'<div class="ff-constraint"><div class="ff-constraint-top"><span>{html.escape(label)}</span>'
            f'<strong>{val:.3f} / 1.0</strong></div><div class="ff-bar">'
            f'<div class="ff-fill" style="background:{color};width:{min(100, val*100):.2f}%"></div>'
            '</div></div>'
        )
    st.markdown('<div class="ff-slimbox">'
                '<div class="ff-kicker">Worst-case constraint use</div>'
                + "".join(bars) + '</div>', unsafe_allow_html=True)
    st.markdown('<div class="ff-kicker">Nominal FEA readout</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ff-slimbox"><div class="ff-brief">Mass <b style="float:right;color:#f2f8ff">{res.mass_kg:.3f} kg</b></div>'
        f'<div class="ff-rule"></div><div class="ff-brief">Max movement <b style="float:right;color:#f2f8ff">{res.max_disp_m*1e3:.4f} mm</b></div>'
        f'<div class="ff-rule"></div><div class="ff-brief">Max axial stress <b style="float:right;color:#f2f8ff">{res.max_stress_pa/1e6:.3f} MPa</b></div></div>',
        unsafe_allow_html=True,
    )
    member = st.selectbox("Inspect an individual member", [f"M{i}" for i in range(len(res.force_n))],
                          key="ff4_member_inspector")
    i = int(member[1:])
    state = "Tension" if float(res.force_n[i]) >= 0 else "Compression"
    st.markdown(
        f'<div class="ff-hint"><b style="color:#deebff">{state}</b> · '
        f'Force {float(res.force_n[i]):,.1f} N · '
        f'Stress {float(res.stress_pa[i]) / 1e6:.3f} MPa</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="ff-hint">2D linear truss · ideal pin joints · Euler buckling screen. '
                'Not structural safety certification.</div>', unsafe_allow_html=True)


# Requirements parsed by the agent are applied only before controls are created.
pending = st.session_state.pop("ff4_pending", None)
if pending:
    st.session_state.update(pending)

# Header
logo, navigation, header_status = st.columns([1.32, 2.7, .85], gap="small")
with logo:
    st.markdown('<div class="ff-head"><span class="ff-icon">⬡</span> FORCEFORGE <span style="color:#55d8ce">AI</span></div>'
                '<div class="ff-tagline">STRUCTURAL DESIGN WORKSTATION</div>', unsafe_allow_html=True)
with navigation:
    page = st.radio("Workspace", ["Studio", "Analysis", "Optimization", "AI Assistant"],
                    horizontal=True, label_visibility="collapsed", key="ff4_page")
with header_status:
    st.markdown('<div class="ff-hint" style="text-align:right">● FEA SOLVER<br>LIVE ENGINEERING</div>',
                unsafe_allow_html=True)

left, middle, right = st.columns([1.04, 2.55, 1.12], gap="small")

with left:
    with st.container(border=True):
        st.markdown('<div class="ff-kicker">01 / Design inputs</div>', unsafe_allow_html=True)
        topology = st.selectbox("Topology", TOPOLOGIES, key="ff4_topology")
        material = st.selectbox("Material", tuple(MATERIALS), key="ff4_material")
        span = st.number_input("Span (m)", min_value=.5, max_value=4.0,
                               value=2.0, step=.1, format="%.2f", key="ff4_span")
        ratio = st.number_input("Height / span", min_value=.20, max_value=1.25,
                                value=.50, step=.05, format="%.2f", key="ff4_ratio")
        area = st.number_input("Member area (mm²)", min_value=60.0, max_value=800.0,
                               value=180.0, step=10.0, format="%.0f", key="ff4_area")
        force = st.number_input("Vertical load (N)", min_value=100, max_value=3000,
                                value=1000, step=100, key="ff4_force")
        with st.popover("⚙  Limits & uncertainty", use_container_width=True):
            max_disp = st.slider("Allowed movement (mm)", .25, 12., 2., .25, key="ff4_limit")
            safety_y = st.slider("Yield safety factor", 1., 4., 2., .25, key="ff4_ysf")
            safety_b = st.slider("Buckling safety factor", 1., 4., 2., .25, key="ff4_bsf")
            load_unc = st.slider("Load increase (%)", 0, 50, 20, 5, key="ff4_load_unc") / 100.
            e_unc = st.slider("E reduction (%)", 0, 35, 10, 5, key="ff4_e_unc") / 100.
            area_unc = st.slider("Area reduction (%)", 0, 25, 10, 5, key="ff4_area_unc") / 100.
        height = float(span * ratio)
        st.markdown(f'<div class="ff-hint">Height: <b>{height:.2f} m</b> · Uniform round-bar cross-sections</div>',
                    unsafe_allow_html=True)

E, density, sy = MATERIALS[material]
req = Requirements(span_m=span, base_load_n=force, material_E_pa=E,
                   density_kg_m3=density, yield_pa=sy, max_displacement_mm=max_disp,
                   yield_safety_factor=safety_y, buckling_safety_factor=safety_b,
                   load_uncertainty=load_unc, e_uncertainty=e_unc, area_uncertainty=area_unc)

if st.session_state.get("ff4_req") != req:
    for k in ("ff4_search", "ff4_redesign", "ff4_ml_metrics", "ff4_ml_verified"):
        st.session_state.pop(k, None)
    st.session_state["ff4_req"] = req

try:
    truss = make_truss(topology, span, height, area, force, req.material)
    res = solve(truss)
    check = evaluate(topology, height, area, req)
except (ValueError, np.linalg.LinAlgError) as exc:
    st.error(f"Could not solve this structure: {exc}")
    st.stop()

with middle:
    st.markdown('<div class="ff-kicker">02 / Interactive workspace</div>', unsafe_allow_html=True)
    kpi_cards([
        ("Nominal mass", f"{res.mass_kg:.2f}", "kg"),
        ("Max movement", f"{res.max_disp_m*1e3:.3f}", "mm"),
        ("Axial stress", f"{res.max_stress_pa/1e6:.2f}", "MPa"),
        ("Worst utilization", f"{check['worst_utilization']:.3f}", "/ 1"),
    ])

    if page == "Studio":
        c_title, c_toggle = st.columns([2, 1])
        with c_title:
            st.markdown('<div class="ff-sectionhead">Structure viewport</div>', unsafe_allow_html=True)
        with c_toggle:
            show_deform = st.toggle("Show deformation", value=True, key="ff4_deform")
        show_plot(truss_figure(truss, res, show_deform), "ff4_geometry")
        st.markdown('<div class="ff-hint">Hover a member for force and stress. Cyan = tension; '
                    'amber = compression; dotted lines = original geometry. '
                    'Deformation is exaggerated for visibility.</div>', unsafe_allow_html=True)

    elif page == "Analysis":
        mode = st.radio("Inspect", ["Stress", "Movement", "Buckling", "Reactions", "Data"],
                        horizontal=True, label_visibility="collapsed", key="ff4_analysis_mode")
        if mode == "Data":
            kind = st.radio("Table", ["Members", "Nodes", "Supports"],
                            horizontal=True, label_visibility="collapsed", key="ff4_table_mode")
            if kind == "Members":
                data = pd.DataFrame({"Member": [f"M{i}" for i in range(len(res.force_n))],
                                     "Axial force (N)": res.force_n,
                                     "Stress (MPa)": res.stress_pa/1e6,
                                     "Ideal Pcr (N)": res.buckling_critical_n})
            elif kind == "Nodes":
                data = pd.DataFrame({"Node": [f"N{i}" for i in range(len(truss.nodes_m))],
                                     "Ux (mm)": res.disp_m[:,0]*1e3,
                                     "Uy (mm)": res.disp_m[:,1]*1e3})
            else:
                data = pd.DataFrame([{
                    "Support node": f"N{i}",
                    "Rx (N)": float(res.reactions_n[i,0]) if fx else None,
                    "Ry (N)": float(res.reactions_n[i,1]) if fy else None,
                } for i, fx, fy in truss.supports])
            st.dataframe(data.round(5), height=320, use_container_width=True, hide_index=True)
            st.download_button("Export visible table (CSV)", data.to_csv(index=False),
                               file_name=f"forceforge_{kind.lower()}.csv", mime="text/csv")
        else:
            show_plot(analysis_figure(mode, truss, res, req), "ff4_analysis_chart")
            details = {
                "Stress": "Signed member stresses. Dashed lines are nominal yield-screen limits.",
                "Movement": "Resultant nodal movements at nominal load; dashed line is the chosen limit.",
                "Buckling": "Ideal Euler screening at nominal load, not a real-world stability certification.",
                "Reactions": "Support reactions at nominal load; compare with the applied load.",
            }
            st.markdown(f'<div class="ff-hint">{details[mode]}</div>', unsafe_allow_html=True)

    elif page == "Optimization":
        mode = st.radio("Optimize mode", ["Design search", "Load challenge"], horizontal=True,
                        label_visibility="collapsed", key="ff4_opt_mode")
        if mode == "Design search":
            btn, guide = st.columns([1, 2])
            with btn:
                launch = st.button("Run FEA search", type="primary", use_container_width=True)
            with guide:
                st.markdown('<div class="ff-hint">3 topologies · 144 candidates · 8 scenarios each</div>',
                            unsafe_allow_html=True)
            if launch:
                with st.spinner("Screening design candidates with FEA..."):
                    st.session_state["ff4_search"] = cached_search(req)
            designs = st.session_state.get("ff4_search")
            if designs is None:
                st.info("Click Run FEA search to reveal a verified design comparison.")
            else:
                best = best_feasible(designs)
                count = int(designs.feasible.sum())
                desc = (f"{len(designs)} candidates · {count} feasible · "
                        + (f"best {best['topology']} at {best['mass_kg']:.3f} kg" if best else "none feasible"))
                st.markdown(f'<div class="ff-action">{html.escape(desc)}</div>', unsafe_allow_html=True)
                views = ["Trade-off", "Topologies", "Candidates"]
                if best:
                    views.insert(2, "Compare")
                view = st.radio("Search result view", views, horizontal=True,
                                label_visibility="collapsed", key="ff4_search_view")
                if view == "Trade-off":
                    show_plot(tradeoff_figure(designs), "ff4_tradeoff")
                elif view == "Topologies":
                    show_plot(topologies_figure(designs), "ff4_topology")
                elif view == "Compare" and best:
                    show_plot(compare_figure(res.mass_kg, float(best['mass_kg']),
                                             float(check['worst_utilization']),
                                             float(best['worst_utilization'])), "ff4_compare")
                else:
                    st.dataframe(designs.round(4), height=280, use_container_width=True, hide_index=True)
                    st.download_button("Export all candidates (CSV)", designs.to_csv(index=False),
                                       file_name="forceforge_candidates.csv", mime="text/csv")
                if best:
                    delta = (float(best["mass_kg"]) / res.mass_kg - 1) * 100.
                    st.markdown(f'<div class="ff-hint">Recommended height {best["height_m"]:.2f} m · '
                                f'area {best["area_mm2"]:.0f} mm² · mass change {delta:+.1f}% vs current design. '
                                'A heavier optimum can be expected when the current design fails constraints.</div>',
                                unsafe_allow_html=True)
        else:
            multiplier = st.slider("Peak load multiplier", min_value=1.0, max_value=1.6,
                                   value=1.2, step=.05, key="ff4_challenge_mult")
            stressed_req = replace(req, load_uncertainty=max(req.load_uncertainty, multiplier - 1.0))
            stressed_check = evaluate(topology, height, area, stressed_req)
            st.markdown('<div class="ff-action">Worst utilization: '
                        f'{check["worst_utilization"]:.3f} → {stressed_check["worst_utilization"]:.3f} '
                        '(expanded scenario envelope)</div>', unsafe_allow_html=True)
            if st.button("Find verified redesign", type="primary"):
                with st.spinner("Finding a redesign within the expanded load envelope..."):
                    st.session_state["ff4_redesign"] = (stressed_req, best_feasible(cached_search(stressed_req)))
            record = st.session_state.get("ff4_redesign")
            redesign = record[1] if record is not None and record[0] == stressed_req else None
            if record is not None and record[0] == stressed_req and redesign is None:
                st.warning("No feasible redesigned candidate in the fixed search grid.")
            view = st.radio("Challenge view", ["Constraint checks", "Redesigned geometry"],
                            horizontal=True, label_visibility="collapsed", key="ff4_challenge_view")
            if view == "Redesigned geometry" and redesign:
                new_truss = make_truss(str(redesign["topology"]), span, float(redesign["height_m"]),
                                       float(redesign["area_mm2"]), force, req.material)
                show_plot(truss_figure(new_truss, solve(new_truss)), "ff4_redesign_truss")
            elif view == "Redesigned geometry":
                st.info("Run verified redesign first, then view the new structure here.")
            else:
                show_plot(limit_figure(stressed_check), "ff4_challenged_limits")
            if redesign:
                delta = 100 * (float(redesign["mass_kg"]) / res.mass_kg - 1)
                st.markdown(f'<div class="ff-hint">FEA-screened redesign: {redesign["topology"]} · '
                            f'{redesign["mass_kg"]:.2f} kg ({delta:+.1f}% vs current design).</div>',
                            unsafe_allow_html=True)

    else:  # AI Assistant
        mode = st.radio("AI mode", ["Design brief", "ML surrogate"], horizontal=True,
                        label_visibility="collapsed", key="ff4_ai_mode")
        if mode == "Design brief":
            brief = st.text_area("Describe your engineering requirement", height=92,
                                 value="Design a lightweight 2 m truss with 1000 N load and 2 mm movement limit.",
                                 key="ff4_brief")
            use_api = st.checkbox("Use OpenAI API when configured", value=False, key="ff4_use_api")
            if st.button("Interpret requirements", type="primary"):
                try:
                    st.session_state["ff4_parsed"] = (brief, use_api, interpret(brief, use_api=use_api))
                except Exception as exc:
                    st.session_state.pop("ff4_parsed", None)
                    st.error(f"Could not parse requirement: {exc}")
            stored = st.session_state.get("ff4_parsed")
            parsed = stored[2] if stored is not None and stored[:2] == (brief, use_api) else None
            if parsed:
                st.markdown(f'<div class="ff-action">Span {parsed.span_m:.2f} m · '
                            f'Load {parsed.load_n:.0f} N · Movement limit {parsed.max_displacement_mm:.2f} mm</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="ff-hint">{html.escape(parsed.rationale)}</div>', unsafe_allow_html=True)
                valid = (0.5 <= parsed.span_m <= 4.0 and 100 <= parsed.load_n <= 3000
                         and 0.25 <= parsed.max_displacement_mm <= 12.0
                         and abs(parsed.span_m * 10 - round(parsed.span_m * 10)) < 1e-8
                         and abs(parsed.load_n / 100 - round(parsed.load_n / 100)) < 1e-8
                         and abs(parsed.max_displacement_mm * 4 - round(parsed.max_displacement_mm * 4)) < 1e-8)
                if valid:
                    if st.button("Apply parsed values to the design"):
                        st.session_state["ff4_pending"] = {
                            "ff4_span": float(parsed.span_m),
                            "ff4_force": int(parsed.load_n),
                            "ff4_limit": float(parsed.max_displacement_mm),
                        }
                        st.session_state.pop("ff4_parsed", None)
                        st.rerun()
                else:
                    st.warning("Parsed values do not match current input ranges/steps. Edit and retry.")
            if not os.getenv("OPENAI_API_KEY"):
                st.markdown('<div class="ff-hint">No API key is required. Offline interpretation works.</div>',
                            unsafe_allow_html=True)
        else:
            launch = st.button("Train surrogate on FEA results", type="primary")
            if launch:
                with st.spinner("Training the model on FEA-labelled candidates..."):
                    _, _, metrics = cached_model(req)
                    st.session_state["ff4_ml_metrics"] = metrics
            metrics = st.session_state.get("ff4_ml_metrics")
            if metrics is None:
                st.info("Train the model to inspect holdout errors and FEA-verified proposals.")
            else:
                data = pd.DataFrame([{"Target": name.replace("worst_", "").replace("_util", ""),
                                      "Random forest MAE": float(d["mae"]),
                                      "Baseline MAE": float(d["baseline_mae"]),
                                      "R²": float(d["r2"])} for name, d in metrics.items()])
                mode2 = st.radio("ML view", ["Holdout error", "FEA proposals"], horizontal=True,
                                 label_visibility="collapsed", key="ff4_ml_view")
                if mode2 == "Holdout error":
                    fig = go.Figure()
                    fig.add_trace(go.Bar(x=data["Target"], y=data["Random forest MAE"],
                                         name="Random forest", marker_color=COLORS["cyan"]))
                    fig.add_trace(go.Bar(x=data["Target"], y=data["Baseline MAE"],
                                         name="Mean baseline", marker_color=COLORS["blue"]))
                    fig.update_layout(barmode="group")
                    fig.update_yaxes(title="Held-out MAE (utilization)")
                    show_plot(figure_style(fig), "ff4_ml_errors")
                else:
                    if st.button("Propose candidates and recheck with FEA"):
                        with st.spinner("Rechecking ML-selected candidates with FEA..."):
                            model, columns, _ = cached_model(req)
                            st.session_state["ff4_ml_verified"] = propose_and_verify(model, columns, req, n=300)
                    verified = st.session_state.get("ff4_ml_verified")
                    if verified is not None:
                        good = verified[verified.feasible == True]
                        st.markdown(f'<div class="ff-action">{len(good)} / {len(verified)} proposals pass FEA scenario screening.</div>',
                                    unsafe_allow_html=True)
                        st.dataframe(verified.round(4), height=260, use_container_width=True, hide_index=True)
                    else:
                        st.info("Click propose to inspect FEA-rechecked candidate designs.")
                st.markdown('<div class="ff-hint">Holdout error tests interpolation inside sampled structure families; '
                            'ML proposals are always checked with the physics solver.</div>', unsafe_allow_html=True)

with right:
    with st.container(border=True):
        inspector(check, res, topology, span, height)
