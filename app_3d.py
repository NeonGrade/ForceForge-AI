"""Legacy Streamlit 3D view (crash-isolated native worker).

Prefer the unified HTTP /solid3d workspace for reliable interactive demos.
This page remains available for compatibility, but it never imports Gmsh.
"""
import base64

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from solid3d_service import run_study

st.set_page_config(page_title="ForceForge | 3D Solid FEA", layout="wide")
st.title("ForceForge | 3D Solid FEA")
st.caption(
    "Experimental 3D solid mechanics, computed by a separate crash-isolated "
    "Gmsh/FEA process. For the stable no-WebSocket UI, run "
    "`python web_server.py` and open http://127.0.0.1:8000/solid3d."
)
st.warning(
    "Research/education prototype. First-order tetrahedra, isotropic "
    "linear elasticity, idealized nodal loading. No assembly contact, "
    "fatigue, CFD, plasticity, mesh convergence or certification."
)

with st.form("solid3d_study"):
    source = st.radio(
        "Geometry",
        ["Built-in rectangular solid", "Upload STEP solid geometry (experimental)"],
        horizontal=True,
    )
    mesh_size_mm = st.slider("Target tetrahedral size (mm)", 2., 25., 8., 1.)
    if source == "Built-in rectangular solid":
        length = st.number_input("Length (mm)", 20., 500., 100.)
        width = st.number_input("Width (mm)", 5., 150., 20.)
        height = st.number_input("Height (mm)", 5., 150., 20.)
        upload = None
        units = "mm"
    else:
        upload = st.file_uploader(
            "STEP solid (.step / .stp), maximum 4 MB", type=["step", "stp"]
        )
        units = st.selectbox("STEP coordinate unit", ["mm", "m", "inch"])
        length = width = height = None
    c1, c2, c3 = st.columns(3)
    E_gpa = c1.number_input("Young's modulus (GPa)", 0.001, 500., 200.)
    nu = c2.number_input("Poisson ratio", -.90, .49, .30, .01)
    force = c3.number_input("Signed face force along axis (N)", -100000., 100000., 1000.)
    axis = st.selectbox("Fix min / load max face along", ["X", "Y", "Z"])
    submitted = st.form_submit_button("Generate mesh and solve 3D FEA", type="primary")

amplification = st.slider("Deformation display amplification", 0, 300, 100)

if submitted:
    st.session_state.pop("solid3d_result", None)
    if upload is None and source.startswith("Upload"):
        st.error("Upload a STEP solid file first.")
    else:
        config = {
            "geometry": "step" if upload is not None else "box",
            "mesh_size_mm": mesh_size_mm,
            "E_gpa": E_gpa, "poisson": nu,
            "force_n": force, "axis": axis,
        }
        if upload is not None:
            raw = upload.getvalue()
            if not 0 < len(raw) <= 4_000_000:
                st.error("STEP file must be nonempty and at most 4 MB.")
                st.stop()
            config.update(
                step_base64=base64.b64encode(raw).decode("ascii"),
                cad_unit=units,
            )
        else:
            config.update(length_mm=length, width_mm=width, height_mm=height)
        try:
            with st.spinner("3D meshing and FEA in a separate worker..."):
                st.session_state["solid3d_result"] = run_study(config)
        except Exception as exc:
            st.error(f"3D solve failed: {exc}")

if "solid3d_result" in st.session_state:
    r = st.session_state["solid3d_result"]
    mesh = r["mesh"]
    metrics = r["metrics"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Nodes", str(mesh["node_count"]))
    c2.metric("Tetrahedra", str(mesh["tetrahedra"]))
    c3.metric("Max von Mises (MPa)", f'{metrics["max_von_mises_mpa"]:.3f}')
    st.metric("Max nodal displacement (mm)", f'{metrics["max_displacement_mm"]:.6f}')
    points = np.array(r["vertices_mm"]) + amplification * np.array(r["displacements_mm"])
    faces = np.array(r["boundary_faces"], dtype=int)
    stress = np.array(r["nodal_von_mises_mpa"])
    fig = go.Figure(go.Mesh3d(
        x=points[:, 0], y=points[:, 1], z=points[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        intensity=stress, intensitymode="vertex",
        colorscale="Turbo",
        colorbar=dict(title="von Mises MPa"),
        flatshading=False,
    ))
    fig.update_layout(
        scene=dict(aspectmode="data"),
        height=610,
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Deformation amplified {amplification}x. "
        "Color values are nodal averages and can be below peak element stress."
    )
    st.caption(
        "Force balance residual: "
        f'{metrics["equilibrium_residual_n"]:.3e} N'
    )
    st.info(r["assumptions"])
