"""Four-anchor wall-mount statics from explicit external loads, NOT wall FEA."""
from __future__ import annotations
from dataclasses import asdict
import json
import streamlit as st
import plotly.graph_objects as go
from forceforge.wall_mount import (
    WallMountInputs,analyze_wall_mount,parse_openfoam_pressure_patch_csv
)

st.set_page_config(
    page_title="ForceForge X | Wall Mount Load Transfer",page_icon="🔩",layout="wide"
)
st.title("Wall-Mounted Fan · Four-Anchor Load Transfer")
st.caption("Real 6-DOF rigid-body force and moment equilibrium · SI units · independently specified inputs")
st.warning(
    "This computes an ideal FOUR-ANCHOR FREE-BODY model, not deformation of "
    "actual wall/plate/anchors and not automatically integrated pressure from "
    "the current OpenFOAM reference-room case. The anchor strengths and "
    "wall contact are NOT assessed. User-supplied thrust is not a CFD result."
)

with st.expander("Optional · integrate uploaded OpenFOAM rotor surface pressure CSV"):
    st.caption(
        "For a single actual solver time, supply face centroids and outward "
        "normals from the SAME rotor geometry as the pressure field. "
        "Expected CSV columns: time_s, x_m, y_m, z_m, nx, ny, nz, "
        "area_m2, p_kinematic_m2_s2. No invented CFD fields."
    )
    pressure_csv=st.file_uploader(
        "Wetted rotor face pressures (CSV, 4 MB max)",
        type=["csv"],key="wall_pressure_patch_csv"
    )
    density=st.number_input(
        "Measured/assumed air density (kg/m³)",
        min_value=.1,max_value=20.,value=1.225,step=.025
    )
    if pressure_csv is not None:
        st.warning(
            "Uploaded pressure faces are user-provided and their OpenFOAM "
            "job/mesh identity has NOT been independently verified. "
            "Pressure forces exclude viscous shear and are not full fan thrust."
        )

with st.form("wall_anchor_load_input"):
    st.markdown("### Specify actual mechanical loads and mounting geometry")
    a,b,c=st.columns(3)
    with a:
        mass=st.number_input("Fan + mount total mass (kg)",min_value=.01,max_value=100.,value=2.5,step=.1)
        eccentricity=st.number_input("Center of mass from wall (mm)",min_value=0.,max_value=1000.,value=130.,step=10.)
        thrust=st.number_input("Signed axial thrust (N, + outward)",min_value=-10000.,max_value=10000.,value=0.,step=1.)
    with b:
        sx=st.number_input("Horizontal anchor pitch (mm)",min_value=20.,max_value=600.,value=140.,step=10.)
        sy=st.number_input("Vertical anchor pitch (mm)",min_value=20.,max_value=600.,value=110.,step=10.)
        torque=st.number_input("Reaction torque about wall normal (N·m)",min_value=-1000.,max_value=1000.,value=0.,step=.5)
    with c:
        fx=st.number_input("Other side force X (N)",min_value=-10000.,max_value=10000.,value=0.,step=1.)
        fy=st.number_input("Other vertical force Y (N)",min_value=-10000.,max_value=10000.,value=0.,step=1.)
        provenance=st.selectbox("Source of aerodynamic force inputs",(
            "unverified_example","user_supplied_or_measured","externally_integrated_cfd"
        ),format_func=lambda x:{
            "unverified_example":"Unverified demonstration numbers",
            "user_supplied_or_measured":"Measured or user-provided loads",
            "externally_integrated_cfd":"Independently integrated CFD surface loads",
        }[x])
    st.caption(
        "A real OpenFOAM solution only becomes rotor thrust when pressure/viscous "
        "tractions are integrated over a matching physical rotor surface at a "
        "specified time. The currently sampled U/p point cloud cannot do this."
    )
    calculate=st.form_submit_button("Calculate actual 4-anchor static reactions",type="primary")
if calculate:
    try:
        patch=(
            parse_openfoam_pressure_patch_csv(
                pressure_csv.getvalue(),air_density_kg_m3=float(density)
            )
            if pressure_csv is not None else None
        )
        pf=patch.force_xyz_n if patch is not None else (0.,0.,0.)
        pm=patch.moment_xyz_nm if patch is not None else (0.,0.,0.)
        spec=WallMountInputs(
            mass_kg=mass,center_offset_mm=eccentricity,
            anchor_spacing_x_mm=sx,anchor_spacing_y_mm=sy,
            axial_thrust_n=thrust+pf[2],
            motor_reaction_torque_nm=torque+pm[2],
            lateral_force_x_n=fx+pf[0],lateral_force_y_n=fy+pf[1],
            aerodynamic_moment_x_nm=pm[0],
            aerodynamic_moment_y_nm=pm[1],
            thrust_source=("uploaded_patch_csv_pressure_only" if patch is not None
                           else provenance),
        )
        result=analyze_wall_mount(spec)
        st.session_state["wall_mount_load_result"]=result
        st.session_state["wall_mount_pressure_patch_evidence"]=patch
    except (ValueError,TypeError,ArithmeticError) as exc:
        st.session_state.pop("wall_mount_load_result",None)
        st.session_state.pop("wall_mount_pressure_patch_evidence",None)
        st.error(str(exc))

result=st.session_state.get("wall_mount_load_result")
if result is not None:
    st.success("6-degree-of-freedom force and moment equilibrium verified")
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Maximum anchor tension",f"{result.max_anchor_tension_n:.2f} N")
    c2.metric("Maximum anchor shear",f"{result.max_anchor_shear_n:.2f} N")
    c3.metric("Force balance error",f"{result.force_balance_error_n:.2e} N")
    c4.metric("Moment balance error",f"{result.moment_balance_error_nm:.2e} N·m")
    st.markdown("### Per-anchor reactions")
    table=[asdict(p) for p in result.anchors]
    st.dataframe(table,width="stretch",hide_index=True)
    fig=go.Figure()
    fig.add_trace(go.Bar(x=[f"A{i+1}" for i in range(4)],
                         y=[x.tension_demand_n for x in result.anchors],
                         name="Axial tension demand (N)"))
    fig.add_trace(go.Bar(x=[f"A{i+1}" for i in range(4)],
                         y=[x.shear_demand_n for x in result.anchors],
                         name="In-plane shear demand (N)"))
    fig.update_layout(
        barmode="group",template="plotly_white",height=370,
        xaxis_title="Four physical anchor coordinates (see table)",
        yaxis_title="Reaction magnitude (N)",
    )
    st.plotly_chart(fig,width="stretch")
    st.caption(result.numerical_scope)
    patch=st.session_state.get("wall_mount_pressure_patch_evidence")
    if patch is not None:
        st.info(
            f"Integrated supplied pressure patches at t={patch.solver_time_s:.5f} s · "
            f"{patch.face_count} wetted faces · source SHA-256: {patch.source_sha256}. "
            "This is a real numerical pressure surface integral of uploaded data, "
            "not independently verified OpenFOAM job evidence or wall FEA."
        )
    if result.inputs.thrust_source=="unverified_example":
        st.warning("Demonstration inputs: DO NOT present these forces as measured or OpenFOAM-derived.")
    st.download_button(
        "Download statics load-transfer evidence (JSON)",
        json.dumps({
            "anchor_statics":result.as_dict(),
            "pressure_patch":(
                patch.as_dict() if patch is not None else None
            ),
        },indent=2),
        file_name="forceforge_wall_anchor_rigid_statics.json",
        mime="application/json",
    )
st.divider()
st.markdown("[Return to mechanical CAD models](./Natural_Language_Engineering)")
st.markdown("[Inspect actual OpenFOAM solved flow fields](./Transient_Rotating_CFD)")
