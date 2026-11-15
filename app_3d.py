"""Standalone 3D solid mechanics demonstrator (optional Gmsh dependency)."""
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from forceforge.solid3d import make_box, import_step, scale_mesh, solve, boundary_triangles

st.set_page_config(page_title="ForceForge | 3D Solid FEA", layout="wide")
st.title("ForceForge | 3D Solid FEA")
st.warning("Educational linear-elastic tetrahedral prototype. No contacts, thermal stress, fatigue or certification. Verify boundary conditions and mesh convergence.")
st.caption("STEP import uses Gmsh OpenCASCADE. CAD coordinate units must be selected explicitly.")
source = st.radio("Geometry", ["Built-in rectangular solid", "Upload STEP solid geometry (experimental)"], horizontal=True)
mesh_size_mm = st.slider("Target tetrahedral size (mm)", 2.0, 25.0, 8.0, 1.0)
if source == "Built-in rectangular solid":
    length = st.number_input("Length (mm)", 20., 500., 100.)
    width = st.number_input("Width (mm)", 5., 150., 20.)
    height = st.number_input("Height (mm)", 5., 150., 20.)
    geometry = ("box", length, width, height, mesh_size_mm)
else:
    upload = st.file_uploader("STEP solid (.step/.stp)", type=["step", "stp"])
    units = st.selectbox("STEP geometry coordinate unit", ["mm", "m", "inch"])
    geometry = ("step", upload.getvalue() if upload else None, units, mesh_size_mm)

c1, c2, c3 = st.columns(3)
E_gpa = c1.number_input("Young's modulus (GPa)", min_value=0.001, value=200.0)
nu = c2.number_input("Poisson ratio", min_value=-0.9, max_value=0.49, value=0.30, step=0.01)
force = c3.number_input("Signed face force along axis (N)", value=1000.0)
axis = st.selectbox("Fix min face / load max face in axis", ["X", "Y", "Z"])
amplification = st.slider("Deformation display amplification", 0, 300, 100)
run = st.button("Generate mesh and solve 3D FEA", type="primary")

if run:
    # Never display an old result if the new meshing/solve attempt fails.
    st.session_state.pop("solid3d_result", None)
    if geometry[0] == "step" and geometry[1] is None:
        st.error("Upload a STEP file first.")
        st.stop()
    try:
        with st.spinner("Meshing solid and assembling tetrahedral stiffness..."):
            if geometry[0] == "box":
                _, l, w, h, size = geometry
                mesh = make_box(l/1000, w/1000, h/1000, size/1000)
            else:
                _, raw, units, size = geometry
                # Mesh STEP in native units, then explicitly rescale coordinates to SI.
                scale = {"mm": 0.001, "m": 1.0, "inch": 0.0254}[units]
                mesh = scale_mesh(import_step(raw, mesh_size=size/1000/scale), scale)
            result = solve(mesh, E=E_gpa*1e9, poisson=nu, force_n=force,
                           axis=["X","Y","Z"].index(axis))
        st.session_state["solid3d_result"] = (mesh, result)
    except Exception as exc:
        st.error(f"3D solve failed: {exc}")
        st.stop()

if "solid3d_result" in st.session_state:
    mesh, r = st.session_state["solid3d_result"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Nodes", str(len(mesh.xyz)))
    c2.metric("Tetrahedra", str(len(mesh.tet)))
    c3.metric("Max von Mises (MPa)", f"{np.max(r.von_mises_tet)/1e6:.3f}")
    st.metric("Maximum nodal displacement (mm)", f"{r.max_displacement*1000:.6f}")
    faces = boundary_triangles(mesh.tet)
    points = (mesh.xyz + amplification*r.displacement)*1000
    fig = go.Figure(go.Mesh3d(x=points[:,0], y=points[:,1], z=points[:,2],
                  i=faces[:,0], j=faces[:,1], k=faces[:,2],
                  intensity=r.von_mises_node/1e6, intensitymode="vertex",
                  colorscale="Turbo", colorbar=dict(title="von Mises MPa"),
                  flatshading=False))
    fig.update_layout(scene=dict(aspectmode="data"), height=650,
                      margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Deformation amplified {amplification}x. Nodal colors are element-average extrapolation; peak element stress can differ.")
    st.write("Force balance (N), reaction sum + external sum:", np.round(r.reaction_sum+r.force_sum, 6))
    if np.linalg.norm(r.reaction_sum+r.force_sum) > 1e-5*max(1, abs(force)):
        st.warning("Unbalanced reactions: treat simulation as invalid.")
    st.info("For STEP assemblies, solids are meshed together but interfaces are not automatically tied. A disconnected/singular assembly will fail; this is not contact or assembly FEA.")
