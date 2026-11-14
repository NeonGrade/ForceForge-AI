"""ForceForge X v0.5 UI — a single-screen workstation for the real lab benchmark.

Launch:
    python -m streamlit run app_ui_v5.py

This interface is deliberately additive: it reuses the v0.4 modal solver,
measurements and reconstructed CAD without changing any physics or test data.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.modal_benchmark import (
    LENGTH_M, WIDTH_M, THICKNESS_M, SENSOR_HEIGHTS_M,
    MEASURED_HZ, PUBLISHED_FE_HZ, solve_modes, solve_static,
    fit_base_stiffness, frequency_comparison, holdout_mape,
    prism_surface, read_abaqus_inp,
)

ROOT = Path(__file__).resolve().parent
STEP = ROOT / "assets/benchmark/hannover_steel_beam_reconstructed.step"
STL = ROOT / "assets/benchmark/hannover_steel_beam_reconstructed_ascii.stl"
SOURCE_DATA = "https://data.uni-hannover.de/en/dataset/a-benchmark-structure-for-virtual-sensing-on-tower-structures"
SOURCE_PAPER = "https://wes.copernicus.org/articles/11/3359/2026/index.html"
PLOT_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": True}
COLORS = {
    "bg": "#09131f", "panel": "#102033", "border": "#294059",
    "aqua": "#5de1c9", "cyan": "#64baff", "amber": "#ffc17a",
    "muted": "#a0b4cb", "white": "#eff7ff",
}

st.set_page_config(
    page_title="ForceForge X | Real Lab Workstation",
    page_icon="🔬", layout="wide", initial_sidebar_state="expanded",
)

st.markdown("""
<style>
:root { --ff-bg:#09131f; --ff-line:#294059; --ff-text:#eff7ff; }
.stApp { background: radial-gradient(ellipse at 65% -10%, #182b45 0%, #09131f 58%); color: #eff7ff; }
[data-testid="stHeader"] { background:transparent; height:0!important; }
[data-testid="stDecoration"], #MainMenu, footer { display:none!important; }
[data-testid="stSidebar"] { background:#0d1b2b; border-right:1px solid #294059; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:.36rem; }
.block-container { max-width:1760px; padding: .85rem 1.15rem .45rem; }
[data-testid="stVerticalBlock"] { gap:.48rem; }
[data-testid="stHorizontalBlock"] { gap:.72rem; }
[data-testid="stMetric"] {
  background:rgba(19,36,56,.94); border:1px solid #294059;
  border-radius:12px; padding:.55rem .85rem; min-width:0;
}
[data-testid="stMetricLabel"] p { font-size:.73rem!important; color:#9fb4ce!important; }
[data-testid="stMetricValue"] { font-size:1.42rem!important; color:#f1f7ff!important; }
[data-testid="stMetricDelta"] { font-size:.75rem; }
[data-testid="stVerticalBlockBorderWrapper"] {
  background:rgba(16,32,51,.94);
  border:1px solid #2b4059!important; border-radius:14px!important;
}
[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stVerticalBlock"] { gap:.35rem; }
[data-testid="stWidgetLabel"] p { color:#a8c0d6!important; font-size:.76rem!important; }
[data-testid="stRadio"] label p { font-size:.83rem; }
[data-testid="stRadio"] div[role="radiogroup"] { gap:.45rem .75rem; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
  border-radius:9px; min-height:2.2rem; font-size:.81rem; font-weight:650;
}
[data-testid="stButton"] button[kind="primary"] { background:#43c2b3; color:#061a26; border:0; }
[data-testid="stButton"] button[kind="primary"]:hover { background:#6ce7d1; }
[data-testid="stAlert"] { padding:.45rem .75rem; }
[data-testid="stAlert"] p { font-size:.77rem; }
[data-testid="stDataFrame"] { border-radius:8px; }
.ff-brand { display:flex; align-items:center; gap:10px; font-size:1.55rem;
  font-weight:850; letter-spacing:-.045em; line-height:1.06; color:#f6fbff; }
.ff-brand-mark { width:34px; height:34px; border:1px solid #4b988f;
  display:inline-flex; align-items:center; justify-content:center;
  background:#183b44; color:#5de1c9; border-radius:10px; font-size:1.1rem; }
.ff-kicker { color:#5de1c9; font-size:.66rem; font-weight:800;
  letter-spacing:.16em; text-transform:uppercase; margin-bottom:.19rem; }
.ff-sub { color:#a0b4cb; font-size:.79rem; line-height:1.4; margin-top:.2rem; }
.ff-stage-title { color:#eaf5ff; font-size:.98rem; font-weight:760;
  letter-spacing:-.01em; margin:0 0 .1rem; }
.ff-note { color:#97aec6; font-size:.70rem; line-height:1.48; }
.ff-chip { display:inline-block; background:#173b40; border:1px solid #2c736d;
  color:#8ce2d2; border-radius:6px; padding:3px 7px; font-size:.65rem;
  font-weight:800; letter-spacing:.06em; }
.ff-statline { display:flex; justify-content:space-between; gap:6px;
  border-bottom:1px solid #294059; padding:.57rem 0;
  font-size:.79rem; color:#a8bdd3; }
.ff-statline b { color:#f5fbff; font-variant-numeric:tabular-nums; }
.ff-empty { margin:.8rem 0; border:1px dashed #39536b; border-radius:9px;
  padding:13px; font-size:.8rem; color:#a8bdd3; }
.ff-evidence { color:#9fb9ce; font-size:.74rem; padding:.65rem .8rem;
  background:rgba(14,34,49,.96); border:1px solid #2b445c;
  border-radius:10px; line-height:1.5; }
.ff-evidence strong {color:#9ce5d5;}
.ff-hero-foot { color:#90a7c0; font-size:.68rem; line-height:1.35; margin-top:.18rem; }
@media (min-width:1120px) and (min-height:735px) {
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    height:100dvh!important; overflow:hidden!important;
  }
  .block-container { height:100dvh!important; overflow:hidden!important; }
}
@media (max-width:1119px), (max-height:734px) {
  [data-testid="stMain"] { overflow:auto!important; }
}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _solve(log_k: float, young_gpa: float, density: float, elements: int, gauges: bool):
    return solve_modes(
        base_stiffness_nm_rad=10**log_k,
        E_pa=young_gpa * 1e9, rho_kg_m3=density,
        n_elements=elements, reduce_gauges=gauges,
    )


@st.cache_data(show_spinner=False)
def _fit(young_gpa: float, density: float, elements: int, gauges: bool):
    return fit_base_stiffness(
        E_pa=young_gpa * 1e9, rho_kg_m3=density,
        n_elements=elements, reduce_gauges=gauges,
    )


def _invalidate_fit():
    st.session_state["lab_fitted"] = False
    st.session_state["lab_cal_error"] = ""


def _calibrate():
    try:
        k, _ = _fit(
            st.session_state["lab_E"], st.session_state["lab_rho"],
            st.session_state["lab_n"], st.session_state["lab_gauges"],
        )
        value = float(np.log10(k))
        if not 0.0 <= value <= 6.0:
            raise ValueError("The fitted support stiffness is outside the displayed slider range.")
        st.session_state["lab_logk"] = value
        st.session_state["lab_fitted"] = True
        st.session_state["lab_cal_error"] = ""
    except (ValueError, np.linalg.LinAlgError) as exc:
        st.session_state["lab_fitted"] = False
        st.session_state["lab_cal_error"] = str(exc)


def _plot_style(fig: go.Figure, height: int = 355):
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#11253a",
        font={"color": "#bdd0e3", "size": 11},
        margin={"l": 8, "r": 8, "t": 16, "b": 25},
        hoverlabel={"bgcolor": "#223d52", "font_color": "#ffffff"},
        legend={"orientation": "h", "y": 1.09, "x": 0, "bgcolor": "rgba(0,0,0,0)"},
    )
    fig.update_xaxes(gridcolor="#294059", zerolinecolor="#294059")
    fig.update_yaxes(gridcolor="#294059", zerolinecolor="#294059")
    return fig


def _beam_figure(heights, offsets, mode_label, gauges):
    nodes, faces, colors = prism_surface(
        heights, offsets, include_gauge_areas=gauges,
    )
    fig = go.Figure()
    fig.add_trace(go.Mesh3d(
        x=nodes[:, 0]*1e3, y=nodes[:, 1]*1e3, z=nodes[:, 2]*1e3,
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        intensity=colors, colorscale=[[0, "#4c99b0"], [1, "#f8b36e"]],
        flatshading=False, opacity=.98, showscale=False,
        lighting={"ambient": .65, "diffuse": .7, "specular": .35},
        name="Reconstructed specimen",
        hovertemplate="Height: %{z:.0f} mm<extra>Reconstructed surface</extra>",
    ))
    fig.add_trace(go.Scatter3d(
        x=np.zeros(len(heights)), y=np.zeros(len(heights)), z=heights*1e3,
        mode="lines", line={"color": "#718ba4", "dash": "dash", "width": 4},
        name="Undeformed axis",
    ))
    fig.add_trace(go.Scatter3d(
        x=offsets*1e3, y=np.zeros(len(heights)), z=heights*1e3,
        mode="lines", line={"color": COLORS["amber"], "width": 7},
        name=mode_label,
    ))
    sensor_z = np.array(list(SENSOR_HEIGHTS_M.values()))
    sensor_x = np.interp(sensor_z, heights, offsets)*1e3
    fig.add_trace(go.Scatter3d(
        x=sensor_x, y=np.full(len(sensor_z), 25.0), z=sensor_z*1e3,
        text=list(SENSOR_HEIGHTS_M), textposition="middle right",
        mode="markers+text",
        textfont={"size": 10, "color": "#e9f9ff"},
        marker={"size": 5, "color": COLORS["aqua"]},
        name="Published sensor positions",
        hovertemplate="%{text}: %{z:.0f} mm<extra>Published sensor height</extra>",
    ))
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=365,
        paper_bgcolor="rgba(0,0,0,0)",
        font={"size": 10, "color": "#b7cede"},
        scene={
            "bgcolor": "#102033",
            "xaxis": {"title": "Lateral (mm)", "range": [-95, 95],
                      "showbackground": False, "gridcolor": "#294059"},
            "yaxis": {"title": "Width (mm)", "range": [-35, 40],
                      "showbackground": False, "gridcolor": "#294059"},
            "zaxis": {"title": "Height (mm)", "range": [-60, 1575],
                      "showbackground": False, "gridcolor": "#294059"},
            "aspectmode": "manual",
            "aspectratio": {"x": .72, "y": .42, "z": 2.55},
            "camera": {"eye": {"x": 1.65, "y": 1.45, "z": .75}},
        },
        showlegend=False,
    )
    return fig


def _frequency_figure(computed):
    labels = ["B1x", "B2x", "B3x"]
    fig = go.Figure()
    for name, values, color in [
        ("Physical measurement", MEASURED_HZ, COLORS["aqua"]),
        ("Our reduced FEM", computed, COLORS["amber"]),
        ("Authors' Abaqus reference", PUBLISHED_FE_HZ, COLORS["cyan"]),
    ]:
        fig.add_bar(
            x=labels, y=values, name=name,
            marker_color=color,
            hovertemplate="%{x}: %{y:.3f} Hz<extra>" + name + "</extra>",
        )
    fig.update_layout(
        barmode="group", yaxis_title="Natural frequency (Hz)",
        bargap=.26,
    )
    return _plot_style(fig)


def _calibration_figure(current, calibrated):
    labels = ["B1x · fit target", "B2x · holdout", "B3x · holdout"]
    fig = go.Figure()
    for name, values, color in [
        ("Published measurement", MEASURED_HZ, COLORS["aqua"]),
        ("Current FEM", current, "#7187a2"),
        ("After one-parameter calibration", calibrated, COLORS["amber"]),
    ]:
        fig.add_bar(x=labels, y=values, name=name, marker_color=color)
    fig.update_layout(barmode="group", yaxis_title="Frequency (Hz)", bargap=.25)
    return _plot_style(fig)


def _row(label, value):
    st.markdown(
        f'<div class="ff-statline"><span>{label}</span><b>{value}</b></div>',
        unsafe_allow_html=True,
    )


def _caption(text):
    st.markdown(f'<div class="ff-note">{text}</div>', unsafe_allow_html=True)


for name, default in [
    ("lab_logk", 3.0), ("lab_E", 210.0), ("lab_rho", 7850.0),
    ("lab_n", 32), ("lab_gauges", True), ("lab_fitted", False),
    ("lab_cal_error", ""), ("lab_mode", 1),
]:
    if name not in st.session_state:
        st.session_state[name] = default

with st.sidebar:
    st.markdown(
        '<div class="ff-brand"><span class="ff-brand-mark">F</span> '
        'ForceForge X</div>', unsafe_allow_html=True,
    )
    st.caption("REAL EXPERIMENT WORKSTATION · v0.4")
    st.markdown('<div class="ff-kicker">PHYSICS CONTROLS</div>', unsafe_allow_html=True)
    st.radio(
        "Analysis type", ["Natural vibration", "Lateral loading"],
        key="lab_view", horizontal=True,
    )
    st.slider(
        "Base rotational stiffness, log10(N·m/rad)",
        min_value=0.0, max_value=6.0, step=.05,
        key="lab_logk", on_change=_invalidate_fit,
    )
    st.caption(f"Effective kθ = {10**st.session_state['lab_logk']:,.1f} N·m/rad")
    st.radio(
        "Vibration mode", [1, 2, 3],
        format_func=lambda value: f"Mode {value}",
        key="lab_mode", horizontal=True,
        disabled=st.session_state["lab_view"] != "Natural vibration",
    )
    with st.expander("Display and material assumptions"):
        st.slider(
            "Mode shape amplitude (mm)", 5, 65, 28, 1, key="lab_amp",
            disabled=st.session_state["lab_view"] != "Natural vibration",
        )
        st.slider(
            "Illustrative lateral load (N)", .05, 1.0, .30, .05, key="lab_force",
            disabled=st.session_state["lab_view"] != "Lateral loading",
        )
        st.slider(
            "Static visual exaggeration", 1, 30, 15, key="lab_exaggeration",
            disabled=st.session_state["lab_view"] != "Lateral loading",
        )
        st.number_input(
            "Assumed Young modulus (GPa)", 150.0, 240.0,
            step=5.0, key="lab_E", on_change=_invalidate_fit,
        )
        st.number_input(
            "Assumed density (kg/m³)", 6500.0, 8500.0,
            step=50.0, key="lab_rho", on_change=_invalidate_fit,
        )
        st.select_slider(
            "Beam finite elements", options=[16, 24, 32, 48, 64],
            key="lab_n", on_change=_invalidate_fit,
        )
        st.checkbox(
            "Include reduced gauge sections", key="lab_gauges",
            on_change=_invalidate_fit,
        )
    st.divider()
    st.markdown('<div class="ff-kicker">EXPLORE THE PLATFORM</div>', unsafe_allow_html=True)
    st.page_link(
        "pages/9_Industry_Explorer.py",
        label="Building / Industrial / Automotive", icon="🏗️",
    )
    st.page_link(
        "pages/7_Engineering_Workbench.py",
        label="Structural FEA, optimization & ML", icon="📈",
    )
    st.page_link(
        "pages/5_Advanced_Structural_Lab.py",
        label="Advanced frame mechanics", icon="⚙️",
    )
    st.caption("Engineering screening only. No certification or service-life claim.")

st.markdown(
    '<div class="ff-kicker">PUBLIC LABORATORY BENCHMARK · MEASURED DATA</div>'
    '<div class="ff-brand">A physical test. A model you can challenge.</div>'
    '<div class="ff-sub">Rotate the reconstructed steel specimen, adjust its '
    'support stiffness, and compare independent FE predictions with '
    'published measurements.</div>',
    unsafe_allow_html=True,
)

try:
    result = _solve(
        float(st.session_state["lab_logk"]), float(st.session_state["lab_E"]),
        float(st.session_state["lab_rho"]), int(st.session_state["lab_n"]),
        bool(st.session_state["lab_gauges"]),
    )
except (ValueError, np.linalg.LinAlgError) as exc:
    st.error(f"Modal finite-element calculation failed: {exc}")
    st.stop()

first_error = 100 * (result.frequencies_hz[0] / MEASURED_HZ[0] - 1)
m1, m2, m3, m4 = st.columns(4)
m1.metric("Measured specimen length", "1,524 mm")
m2.metric("Measured first frequency", f"{MEASURED_HZ[0]:.3f} Hz")
m3.metric("Our FE first frequency", f"{result.frequencies_hz[0]:.3f} Hz")
m4.metric("First-mode deviation", f"{first_error:+.2f}%")

sections = ["3D Specimen", "Frequency Match", "Calibration", "Data & Sources"]
section = st.radio(
    "Select a workspace view", sections, horizontal=True,
    label_visibility="collapsed", key="lab_section",
)

left, right = st.columns([1.75, 1.0], gap="medium")
with left:
    with st.container(height=440, border=True):
        if section == "3D Specimen":
            st.markdown(
                '<div class="ff-stage-title">3D specimen &amp; FE mode shape</div>'
                '<div class="ff-note">Drag to rotate · scroll to zoom · '
                'sensor heights from the published lab dataset</div>',
                unsafe_allow_html=True,
            )
            if st.session_state["lab_view"] == "Natural vibration":
                mode = int(st.session_state["lab_mode"])
                shape = result.transverse_shapes[:, mode-1] * st.session_state["lab_amp"] / 1000
                mode_label = f"Calculated mode B{mode}x (exaggerated)"
            else:
                try:
                    _, deflection, _, _, _ = solve_static(
                        tip_force_n=st.session_state["lab_force"],
                        n_elements=st.session_state["lab_n"],
                        E_pa=st.session_state["lab_E"]*1e9,
                        rho_kg_m3=st.session_state["lab_rho"],
                        base_stiffness_nm_rad=10**st.session_state["lab_logk"],
                        reduce_gauges=st.session_state["lab_gauges"],
                    )
                except (ValueError, np.linalg.LinAlgError) as exc:
                    st.error(f"Static FEM failed: {exc}")
                    st.stop()
                shape = deflection * st.session_state["lab_exaggeration"]
                mode_label = "Calculated static deflection (exaggerated)"
            st.plotly_chart(
                _beam_figure(result.heights_m, shape, mode_label,
                             st.session_state["lab_gauges"]),
                use_container_width=True, config=PLOT_CONFIG, key="lab_3d_plot",
            )
            _caption("Real dimensions; reconstructed CAD, not the authors' original mesh. "
                     "Mode shapes and static displacement are deliberately magnified.")

        elif section == "Frequency Match":
            st.markdown(
                '<div class="ff-stage-title">Measured vs independently predicted modes</div>',
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                _frequency_figure(result.frequencies_hz),
                use_container_width=True, config=PLOT_CONFIG, key="lab_frequency_plot",
            )
            _caption("Measured = published physical test. Our FEM = live calculation. "
                     "Abaqus = separate published author model.")

        elif section == "Calibration":
            st.markdown(
                '<div class="ff-stage-title">Fit one mode. Test the others.</div>'
                '<div class="ff-note">Only the measured first mode is used to estimate '
                'effective base stiffness; Modes 2 &amp; 3 are held out.</div>',
                unsafe_allow_html=True,
            )
            try:
                fitted_k, fitted_result = _fit(
                    st.session_state["lab_E"], st.session_state["lab_rho"],
                    st.session_state["lab_n"], st.session_state["lab_gauges"],
                )
                st.plotly_chart(
                    _calibration_figure(
                        result.frequencies_hz, fitted_result.frequencies_hz,
                    ),
                    use_container_width=True, config=PLOT_CONFIG,
                    key="lab_calibration_plot",
                )
                _caption("The orange bars are a one-parameter fitted model, not "
                         "independent data. Only Modes 2 and 3 test holdout agreement.")
            except (ValueError, np.linalg.LinAlgError) as exc:
                st.warning(f"Calibration unavailable for current assumptions: {exc}")

        else:
            st.markdown(
                '<div class="ff-stage-title">Physical specimen &amp; published sensors</div>',
                unsafe_allow_html=True,
            )
            measurements = pd.DataFrame(
                [{"Sensor": name, "Height (mm)": round(height*1000),
                  "Measurement type": (
                      "Accelerometer / laser" if name in ("MP1", "MP2", "MP3")
                      else "Strain gauge"
                  )}
                 for name, height in SENSOR_HEIGHTS_M.items()]
            )
            _row("Free beam length", "1,524 mm")
            _row("Rectangular section", "30 × 5.2 mm")
            _row("Sanded gauge section", "5.0 mm")
            _row("Sampling frequency", "600 Hz")
            st.dataframe(measurements, hide_index=True, use_container_width=True)
            _caption("Sensor and specimen dimensions are from the cited study. "
                     "Attached sensor/magnet masses and exact clamp geometry are not modeled.")

with right:
    with st.container(height=440, border=True):
        st.markdown(
            '<div class="ff-stage-title">Live engineering inspector</div>'
            '<span class="ff-chip">LIVE FEA · NO CERTIFICATION</span>',
            unsafe_allow_html=True,
        )

        if section == "3D Specimen":
            _row("Selected vibration", f"B{st.session_state['lab_mode']}x")
            _row("Our selected frequency",
                 f"{result.frequencies_hz[st.session_state['lab_mode']-1]:.3f} Hz")
            _row("Observed frequency",
                 f"{MEASURED_HZ[st.session_state['lab_mode']-1]:.3f} Hz")
            _row("Model beam mass", f"{result.mass_kg:.3f} kg")
            st.button(
                "Calibrate using measured Mode 1", type="primary",
                on_click=_calibrate, use_container_width=True,
            )
            if st.session_state["lab_cal_error"]:
                st.error(st.session_state["lab_cal_error"])
            if st.session_state["lab_fitted"]:
                st.metric(
                    "Mode 2 held-out error",
                    f"{100*(result.frequencies_hz[1]/MEASURED_HZ[1]-1):+.2f}%",
                )
                st.metric(
                    "Mode 3 held-out error",
                    f"{100*(result.frequencies_hz[2]/MEASURED_HZ[2]-1):+.2f}%",
                )
            else:
                _caption("One click fits effective support stiffness to the first "
                         "measured mode. The next two modes remain independent checks.")

        elif section == "Frequency Match":
            st.markdown('<div class="ff-kicker">THREE INDEPENDENT READOUTS</div>',
                        unsafe_allow_html=True)
            for item in frequency_comparison(result.frequencies_hz):
                _row(item["Mode"] + " · measured", f"{item['Measured (Hz)']:.3f} Hz")
                _row("Our reduced FEM",
                     f"{item['Our reduced FEM (Hz)']:.3f} Hz "
                     f"({item['Our error (%)']:+.2f}%)")
            csv_data = pd.DataFrame(
                frequency_comparison(result.frequencies_hz)
            ).to_csv(index=False)
            st.download_button(
                "Export frequency comparison CSV", csv_data,
                "forceforge_lab_frequency_comparison.csv",
                mime="text/csv", use_container_width=True,
            )
            _caption("The authors' updated Abaqus reference uses different "
                     "modeling assumptions. Do not interpret low frequency "
                     "error alone as full model validation.")

        elif section == "Calibration":
            st.button(
                "Calibrate using measured Mode 1", type="primary",
                on_click=_calibrate, use_container_width=True,
            )
            if st.session_state["lab_cal_error"]:
                st.error(st.session_state["lab_cal_error"])
            try:
                fitted_k, fitted_result = _fit(
                    st.session_state["lab_E"], st.session_state["lab_rho"],
                    st.session_state["lab_n"], st.session_state["lab_gauges"],
                )
                _row("Fitted effective kθ", f"{fitted_k:.1f} N·m/rad")
                is_fitted = st.session_state["lab_fitted"] and np.isclose(
                    10**st.session_state["lab_logk"], fitted_k, rtol=1e-4,
                )
                if is_fitted:
                    st.metric(
                        "Mode 2 held-out error",
                        f"{100*(result.frequencies_hz[1]/MEASURED_HZ[1]-1):+.2f}%",
                    )
                    st.metric(
                        "Mode 3 held-out error",
                        f"{100*(result.frequencies_hz[2]/MEASURED_HZ[2]-1):+.2f}%",
                    )
                    _row("Held-out MAPE", f"{holdout_mape(result):.2f}%")
                else:
                    _caption("Click Calibrate to apply this parameter to the live model.")
                _caption("Fitted support stiffness is an effective model parameter, "
                         "not a directly measured fixture property.")
            except (ValueError, np.linalg.LinAlgError) as exc:
                st.warning(str(exc))

        else:
            st.markdown('<div class="ff-kicker">REPRODUCIBLE DOWNLOADS</div>',
                        unsafe_allow_html=True)
            if STEP.exists():
                st.download_button(
                    "Download reconstructed STEP", STEP.read_bytes(),
                    file_name=STEP.name, mime="application/step",
                    use_container_width=True,
                )
            if STL.exists():
                st.download_button(
                    "Download reconstructed STL", STL.read_bytes(),
                    file_name=STL.name, mime="model/stl",
                    use_container_width=True,
                )
            st.link_button(
                "Original university dataset", SOURCE_DATA,
                use_container_width=True,
            )
            st.link_button(
                "Peer-reviewed article", SOURCE_PAPER,
                use_container_width=True,
            )
            _caption("Paper: CC BY 4.0 · raw dataset: CC BY 3.0. "
                     "STEP/STL are our documented reconstruction.")
            with st.popover("Inspect source .inp / .mat files"):
                st.caption("User-supplied source files only; no implicit channel mapping.")
                uploaded_inp = st.file_uploader(
                    "Original Abaqus .inp", type=["inp"], key="lab_upload_inp",
                )
                if uploaded_inp is not None:
                    try:
                        parsed = read_abaqus_inp(
                            uploaded_inp.getvalue().decode("utf-8", errors="replace")
                        )
                        st.write(
                            f"{parsed['node_count']:,} nodes, "
                            f"{parsed['element_count']:,} elements"
                        )
                        st.caption("Preview only: original assembly/BCs are not solved.")
                    except (ValueError, UnicodeError) as exc:
                        st.warning(f"Could not parse the Abaqus file: {exc}")
                uploaded_mat = st.file_uploader(
                    "Original MATLAB .mat", type=["mat"], key="lab_upload_mat",
                )
                if uploaded_mat is not None:
                    try:
                        from scipy.io import loadmat
                        raw = loadmat(
                            BytesIO(uploaded_mat.getvalue()),
                            squeeze_me=True, struct_as_record=False,
                        )
                        metadata = [
                            {"Variable": name, "Shape": str(np.shape(value))}
                            for name, value in raw.items() if not name.startswith("__")
                        ]
                        st.dataframe(pd.DataFrame(metadata), hide_index=True)
                        st.caption("No signals are automatically assigned physical units.")
                    except (ValueError, NotImplementedError, OSError) as exc:
                        st.warning(f"MAT file cannot be previewed: {exc}")

st.markdown(
    '<div class="ff-hero-foot">SOURCE · Thurn et al., Wind Energy Science '
    '(2026), DOI 10.5194/wes-11-3359-2026. Observed frequencies are real; '
    'E = 210 GPa and density = 7850 kg/m³ are assumptions. The 2D Euler–Bernoulli '
    'model omits sensor masses, shear and fixture details. '
    '<b>No structural safety certification is claimed.</b></div>',
    unsafe_allow_html=True,
)
