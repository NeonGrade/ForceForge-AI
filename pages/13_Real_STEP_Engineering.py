"""ForceForge X stable CAD Studio: explicit, crash-isolated engineering runs.

A Streamlit rerun never invokes Gmsh or volumetric FEA automatically.
All expensive work is user-triggered, dispatched to a separate Python
process with a timeout, and committed as one traceable session snapshot.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import time
import urllib.request

import numpy as np
import pandas as pd
import streamlit as st

from forceforge.cad_solid import CadLoad
from forceforge.isolated_cad import (
    CadJobError, MAX_INTERACTIVE_TETS,
    analyze_step_safely, generate_bracket_safely,
)
from forceforge.mesh_verification import run_mesh_evidence, select_mesh_sizes
from forceforge.local_refinement import run_hotspot_refinement
from forceforge.dual_hotspot import run_dual_hotspot_study
from forceforge.cad_copilot import (
    DesignLimits, evaluate_candidate, pick_lightest_feasible, propose_designs,
)
from forceforge.stress_probe import probe_stress
import plotly.graph_objects as go
from forceforge.solid3d import surface_figure
from forceforge.step_mesh import (
    MAX_CAD_BYTES, NIST_BRIDGE_URL, NIST_DATASET_DOI, NIST_PINNED_SHA256,
)

st.set_page_config(
    page_title="ForceForge X | Stable Real STEP Studio",
    page_icon="🧩", layout="wide",
)

st.title("Real CAD → 3D Solid FEA → CAD Revision")
st.caption(
    "Stable mode · CAD and FEA start only when you press Run · native "
    "Gmsh and sparse 3D FEM run in separate bounded worker processes."
)
st.write(
    "Import an actual STEP BRep, create a 3D tetrahedral volume mesh, "
    "solve a small-strain elastic FE problem, and independently re-mesh "
    "and re-solve a revised CAD geometry."
)
st.info(
    "This is an engineering analysis prototype. The NIST STEP represents "
    "real published geometry; mechanical loads, fixture assumptions and "
    "material parameters in this demo are not experimentally validated."
)

with st.sidebar:
    st.markdown("### 1 · CAD source")
    selection = st.radio(
        "Choose model",
        ["Editable 3D L-bracket", "NIST original bridge STEP", "Upload your STEP"],
    )
    web = None
    uploaded = None
    unit = "mm"
    if selection == "Editable 3D L-bracket":
        web = st.select_slider(
            "Current vertical web thickness (mm)",
            options=[8, 10, 12, 14], value=8,
        )
        st.caption("Original parametric CAD test bracket with drilled mounting holes.")
    elif selection == "Upload your STEP":
        uploaded = st.file_uploader(
            "Permission-cleared single-body STEP", type=["step", "stp"],
        )
        unit = st.selectbox(
            "Confirm actual STEP coordinate units", ["mm", "m"],
        )
    else:
        st.caption(
            "Published IN718 bridge specimen, NIST AMB2022-01, "
            "DOI 10.18434/mds2-2607."
        )
    mesh_size = st.slider(
        "Target tetra size (mm)", 5.0, 15.0, 12.0, 1.0,
        help="Coarser meshes reduce memory but do not validate peak stress. "
             "The default is chosen for reliable interactive use.",
    )
    st.caption(
        f"Safety cap: {MAX_INTERACTIVE_TETS:,} input tetrahedra. "
        "Too-fine meshes are rejected, never silently truncated."
    )
    st.divider()
    st.markdown("### 2 · Assumed static load")
    force = st.slider("Transverse force (N)", 20, 2000, 250, 10)
    direction = st.selectbox("Force direction", ["+X", "-X", "+Y", "-Y"])
    boundary = st.selectbox("Base-to-tip direction", ["Z", "X", "Y"])
    with st.expander("Material assumptions"):
        E = st.number_input(
            "Young modulus (GPa)", min_value=10.0,
            max_value=400.0, value=200.0, step=10.0,
        )
        nu = st.number_input(
            "Poisson ratio", min_value=.10,
            max_value=.45, value=.29, step=.01,
        )
        yield_mpa = st.number_input(
            "Illustrative yield stress (MPa)", min_value=10.0,
            max_value=1800.0, value=900.0, step=50.0,
        )
        rho = st.number_input(
            "Assumed density (kg/m³)", min_value=1000.0,
            max_value=20000.0, value=8190.0, step=100.0,
        )
    st.divider()
    st.caption(
        "Prior modules remain available. This page does not run CAD "
        "meshing or FEA just because you adjust a slider."
    )
    st.markdown("[Real measured modal validation](/)")
    st.markdown("[Earlier 3D tetra10 verification](/True_3D_Solid_FEA)")

case = CadLoad(
    force_n=float(force),
    force_axis={"X": 0, "Y": 1}[direction[-1]],
    force_sign=1 if direction[0] == "+" else -1,
    boundary_axis={"X": 0, "Y": 1, "Z": 2}[boundary],
    E_pa=E * 1e9,
    nu=nu,
    yield_pa=yield_mpa * 1e6,
    density=rho,
)

source_name = None
source_bytes = None
if selection == "Editable 3D L-bracket":
    source_name = f"Original parametric bracket ({web} mm web)"
    source_token = f"bracket:{web}"
elif selection == "Upload your STEP":
    if uploaded is not None:
        source_name = uploaded.name
        source_bytes = uploaded.getvalue()
        source_token = sha256(source_bytes).hexdigest()
    else:
        source_token = "no-upload"
else:
    st.markdown(
        f"[NIST original STEP]({NIST_BRIDGE_URL}) · "
        f"[Dataset DOI](https://doi.org/{NIST_DATASET_DOI})"
    )
    if st.button("Fetch official NIST STEP", type="secondary"):
        try:
            with st.spinner("Downloading the original published STEP..."):
                req = urllib.request.Request(
                    NIST_BRIDGE_URL,
                    headers={"User-Agent": "ForceForge-X-research/0.9"},
                )
                with urllib.request.urlopen(req, timeout=25) as response:
                    blob = response.read(MAX_CAD_BYTES + 1)
                if sha256(blob).hexdigest() != NIST_PINNED_SHA256:
                    raise ValueError(
                        "The NIST original STEP hash differs from the "
                        "independently verified original; do not substitute."
                    )
                st.session_state["stable_nist_blob"] = blob
                st.success("Original NIST STEP downloaded; ready to run.")
        except Exception as exc:
            st.error(
                f"NIST source unavailable: {type(exc).__name__}: {exc}. "
                "You can download it separately and choose Upload your STEP."
            )
    source_bytes = st.session_state.get("stable_nist_blob")
    source_name = "NIST AMB2022-01 official original STEP"
    source_token = (
        sha256(source_bytes).hexdigest()
        if source_bytes is not None else "nist-not-downloaded"
    )

# Every numerical snapshot binds to all physical controls and exact CAD.
signature = (
    selection, source_token, float(mesh_size), unit, case,
)

st.subheader("Step 1 · Explicitly run the CAD-to-FEA calculation")
if source_bytes is None and selection != "Editable 3D L-bracket":
    st.warning(
        "No STEP selected. Fetch the official NIST source or upload a STEP. "
        "No calculation will start until a source is available and you press Run."
    )
run_disabled = (
    selection != "Editable 3D L-bracket" and source_bytes is None
)
run_requested = st.button(
    "Run CAD import + 3D FEA",
    type="primary", disabled=run_disabled,
    key="stable_run_original",
)

if run_requested:
    # Immediately invalidate the previous solution and its comparison.
    st.session_state.pop("stable_initial", None)
    st.session_state.pop("stable_revised", None)
    st.session_state.pop("stable_mesh_evidence", None)
    st.session_state.pop("stable_hotspot_study", None)
    st.session_state.pop("stable_dual_hotspot", None)
    st.session_state.pop("stable_cad_copilot", None)
    t0 = time.monotonic()
    try:
        with st.spinner(
            "Isolated CAD process: STEP → tetra mesh → 3D FEA. "
            "The UI server stays separate."
        ):
            blob = (
                generate_bracket_safely(float(web))
                if selection == "Editable 3D L-bracket"
                else source_bytes
            )
            result = analyze_step_safely(
                blob, source_label=source_name,
                mesh_size_mm=float(mesh_size),
                unit=unit, load=case,
            )
        st.session_state["stable_initial"] = {
            "signature": signature,
            "source": blob,
            "source_name": source_name,
            "result": result,
            "seconds": time.monotonic() - t0,
        }
    except (CadJobError, RuntimeError, ValueError, OSError) as exc:
        st.error(
            f"Isolated CAD/FEA job failed safely: {exc}"
        )
        st.info(
            "Streamlit remains available. Try a coarser mesh, "
            "a smaller single-body STEP or check the Python environment. "
            "Do not present a failed solve as a physical result."
        )

saved = st.session_state.get("stable_initial")
if saved is not None and saved["signature"] != signature:
    st.warning(
        "The CAD geometry, mesh, material or load inputs changed. "
        "The previous result has been hidden; press Run to calculate the "
        "updated design. This prevents mixing different scenarios."
    )
    saved = None

if saved is None:
    st.caption(
        "Ready for a controlled solve. You can freely change sliders first. "
        "No Gmsh or 3D FEM job starts during an ordinary page refresh."
    )
    st.stop()

result = saved["result"]
mesh = result.mesh
st.success(
    f"FEA complete in {saved['seconds']:.1f} s. "
    "CAD provenance and results are fixed until you explicitly rerun."
)
st.caption(
    f"Source SHA-256: {mesh.source_sha256} · "
    f"{saved['source_name']}"
)
st.download_button(
    "Download analyzed STEP",
    data=saved["source"],
    file_name="forceforge_current.step",
    mime="application/step",
)

st.subheader("Step 2 · Review physical predictions and mesh quality")
m1, m2, m3, m4 = st.columns(4)
m1.metric("3D tetrahedra", f"{mesh.num_tets:,}")
m2.metric("Tip displacement", f"{result.tip_mm:.5f} mm")
m3.metric("Sampled peak von Mises", f"{result.peak_von_mises_mpa:.2f} MPa")
m4.metric("Reaction residual", f"{result.relative_reaction_residual:.2e}")
st.caption(
    f"CAD volume: {mesh.cad_volume_m3*1e9:,.2f} mm³ · "
    f"tetra mesh volume error: {mesh.relative_volume_difference*100:.2f}% · "
    f"mesh shape-quality proxy (minimum): {mesh.min_shape_quality:.5f}"
)
peak_pt = np.asarray(result.sampled_peak_location_m)*1000
st.caption(
    "Global peak Gauss sample (undeformed STEP XYZ) = "
    f"({peak_pt[0]:.2f}, {peak_pt[1]:.2f}, {peak_pt[2]:.2f}) mm. "
    "The peak location may move between meshes."
)
if result.peak_von_mises_mpa > yield_mpa:
    st.warning(
        "Computed elastic stress exceeds the *assumed* yield limit. "
        "This exceeds the linear-elastic model's validity."
    )
else:
    st.info(
        "Stress is a sampled integration-point result under assumed static "
        "loads, not an experimentally validated service stress."
    )

visual = st.slider(
    "Display-only deformation multiplier", 1, 150, 35, 5,
    key="stable_visual_scale",
)
st.plotly_chart(
    surface_figure(result, deformation_scale=visual),
    width="stretch", key="stable_original_surface",
)

with st.expander(
    "Mesh-sensitivity evidence · 3 independent volume meshes",
    expanded=False,
):
    planned = select_mesh_sizes(mesh.mesh_size_mm)
    st.write(
        "The same exact STEP file, load, support planes and material will be "
        "solved with target tetra edge sizes of "
        + ", ".join(f"{x:g} mm" for x in planned)
        + ". The current completed result is reused; two additional "
        "mesh/FEA jobs run in short-lived isolated subprocesses."
    )
    st.caption(
        "This screens numerical mesh dependence, particularly global "
        "tip displacement. Local peak stress around fixed edges and holes "
        "is separately reported and cannot be called converged."
    )
    if st.button(
        "Run mesh-sensitivity study (2 additional FE solves)",
        key="stable_run_mesh_verification",
    ):
        st.session_state.pop("stable_mesh_evidence", None)
        elapsed_start = time.monotonic()
        try:
            with st.spinner(
                "Checking 3 mesh resolutions · 2 isolated 3D FEA runs. "
                "The main web server remains separate."
            ):
                evidence = run_mesh_evidence(
                    saved["source"], result,
                    source_label=saved["source_name"],
                    unit=unit, solve_at=analyze_step_safely,
                )
            st.session_state["stable_mesh_evidence"] = {
                "signature": signature,
                "source_sha256": mesh.source_sha256,
                "study": evidence,
                "seconds": time.monotonic() - elapsed_start,
            }
        except (CadJobError, RuntimeError, ValueError, OSError) as exc:
            st.error(
                f"Mesh verification did not finish: {exc}. "
                "No convergence result has been asserted. "
                "Try a larger base tetra edge size or a simpler CAD solid."
            )
    record = st.session_state.get("stable_mesh_evidence")
    if record is not None and (
        record["signature"] != signature
        or record["source_sha256"] != mesh.source_sha256
    ):
        st.warning(
            "Geometry, loading, mesh or material inputs changed. "
            "Previous mesh evidence is stale and hidden."
        )
        record = None
    if record is not None:
        evidence = record["study"]
        if evidence.engineering_evidence_status == "GLOBAL_DISPLACEMENT_STABLE_LOCAL_STRESS_UNVERIFIED":
            st.error(
                "GLOBAL DISPLACEMENT STABLE; LOCAL STRESS NOT VERIFIED. "
                "A stable tip displacement does not validate the peak "
                "von Mises stress or authorize a safety decision."
            )
        elif evidence.engineering_evidence_status == "PRELIMINARY_NUMERICAL_SCREENS_MET_NOT_CERTIFIED":
            st.warning(
                "Preliminary numerical screens met. Real fixture/material "
                "verification and experimental correlation remain missing."
            )
        else:
            st.error(
                "Numerical evidence incomplete or mesh sensitive: "
                + evidence.engineering_evidence_status
            )
        st.write("**Global displacement screen:**",evidence.decision)
        st.write("**Peak local stress screen:**",evidence.local_peak_status)
        st.write("**Physical 5–30% span band:**",evidence.physical_band_stress_status)
        st.caption(evidence.decision_reason)
        rows = [r.as_dict() for r in evidence.ordered_rows]
        df = pd.DataFrame(rows).rename(columns={
            "target_size_mm": "Target edge (mm)",
            "tetrahedra": "3D tetrahedra",
            "quadratic_nodes": "Quadratic FE nodes",
            "volume_error_percent": "Volume discrepancy (%)",
            "minimum_quality_proxy": "Min shape-quality proxy",
            "tip_mm": "Tip displacement (mm)",
            "peak_sampled_mises_mpa": "Sampled peak von Mises (MPa)",
            "strain_energy_mj": "Strain energy (mJ)",
            "reaction_residual": "Relative equilibrium residual",
            "probe_weighted_mean_mpa": "Fixed-band mean stress (MPa)",
            "probe_weighted_p90_mpa": "Fixed-band weighted P90 (MPa)",
            "probe_gauss_samples": "Band Gauss samples",
            "probe_volume_percent": "Band volume fraction (%)",
            "hotspot_x_mm": "Hotspot X (mm)",
            "hotspot_y_mm": "Hotspot Y (mm)",
            "hotspot_z_mm": "Hotspot Z (mm)",
            "hotspot_support_fraction": "Peak support distance / span",
            "hotspot_zone": "Peak zone",
        })
        st.dataframe(df.round(6), hide_index=True, width="stretch")
        a, b, c = st.columns(3)
        a.metric(
            "Fine/medium tip difference",
            f"{evidence.fine_vs_medium_displacement_percent:.2f}%",
        )
        b.metric(
            "Fine/medium sampled stress difference",
            f"{evidence.fine_vs_medium_stress_percent:.2f}%",
        )
        c.metric(
            "Mesh count · coarse → fine",
            f"{rows[0]['tetrahedra']:,} → {rows[2]['tetrahedra']:,}",
        )
        st.caption(
            "Fine/medium stress difference = "
            "|fine stress − medium stress| / |fine stress| × 100 "
            "(using unrounded FEA values). "
            f"Fixed physical-band mean difference: "
            f"{evidence.fine_medium_probe_mean_percent:.2f}%; "
            f"physical-band P90 difference: "
            f"{evidence.fine_medium_probe_p90_percent:.2f}%; "
            f"global peak moved {evidence.fine_medium_hotspot_drift_mm:.2f} mm."
        )
        left_chart,right_chart=st.columns(2)
        with left_chart:
            fig=go.Figure(go.Scatter(
                x=[row.tetrahedra for row in evidence.ordered_rows],
                y=[row.tip_mm for row in evidence.ordered_rows],
                mode="lines+markers", name="Physical tip movement",
                line=dict(width=3),
            ))
            fig.update_layout(
                title="Global displacement convergence",
                xaxis_title="Actual tetrahedral elements",
                yaxis_title="Displacement (mm)",
                height=335,margin=dict(t=48,b=50,l=50,r=15),
            )
            st.plotly_chart(fig,width="stretch",key="mesh_disp_verified")
        with right_chart:
            fig=go.Figure()
            for label, attr in [
                ("Moving sampled maximum","peak_sampled_mises_mpa"),
                ("Fixed-band volume mean","probe_weighted_mean_mpa"),
                ("Fixed-band weighted P90","probe_weighted_p90_mpa"),
            ]:
                fig.add_trace(go.Scatter(
                    x=[row.tetrahedra for row in evidence.ordered_rows],
                    y=[getattr(row,attr) for row in evidence.ordered_rows],
                    mode="lines+markers",name=label,
                ))
            fig.update_layout(
                title="Local stress mesh sensitivity",
                xaxis_title="Actual tetrahedral elements",
                yaxis_title="von Mises (MPa)",
                legend=dict(orientation="h",y=-.40),
                height=335,margin=dict(t=48,b=80,l=50,r=15),
            )
            st.plotly_chart(fig,width="stretch",key="mesh_stress_verified")
        st.caption(evidence.limitations)
        st.download_button(
            "Download mesh-sensitivity evidence (JSON)",
            data=json.dumps(evidence.as_dict(), indent=2),
            file_name="forceforge_mesh_evidence.json",
            mime="application/json",
            key="download_mesh_evidence",
        )

st.subheader("Step 3 · Physically localized stress refinement")
with st.expander(
    "Refine around the actual 3D stress hotspot (explicit action)",
    expanded=False,
):
    physical_probe=probe_stress(result)
    st.write(
        "Highest sampled Gauss stress occurs at the undeformed CAD "
        "coordinate (X, Y, Z) = "
        + str(tuple(round(v,2) for v in physical_probe.global_peak_location_mm))
        + " mm. The solver will re-import the identical STEP and apply "
        "two locally refined 3D meshes (60% and 45% target size) "
        "around this physical location, preserving identical CAD, load and support."
    )
    if physical_probe.global_peak_zone=="NEAR_IDEALIZED_FIXED_FACE":
        st.warning(
            "The maximum is near the idealized clamped plane. Its maximum "
            "may be a mathematically mesh-sensitive support singularity. "
            "No real bolt/contact solution has been supplied; a realistic "
            "attachment model is necessary before engineering approval."
        )
    if st.button(
        "Run two local hotspot refinements",
        key="run_true_local_refinements",
    ):
        st.session_state.pop("stable_hotspot_study",None)
        st.session_state.pop("stable_dual_hotspot",None)
        try:
            with st.spinner(
                "Remeshing source STEP locally and running two isolated "
                "3D tetra10 FE solves..."
            ):
                refined=run_hotspot_refinement(
                    saved["source"],result,
                    source_label=saved["source_name"],unit=unit,
                    solve_at=analyze_step_safely,
                )
            st.session_state["stable_hotspot_study"]={
                "signature":signature,
                "study":refined,
            }
        except (CadJobError,RuntimeError,ValueError,OSError) as exc:
            st.error(
                "Local stress verification could not be completed: "
                + str(exc) + ". No stress-convergence claim has been made. "
                "The original completed 3D FE result is preserved."
            )
    targeted=st.session_state.get("stable_hotspot_study")
    if targeted is not None and targeted["signature"]!=signature:
        st.warning("Old hotspot verification is stale after input changes.")
        targeted=None
    if targeted is not None:
        details=targeted["study"]
        if details.status in (
            "PRELIMINARY_LOCAL_STRESS_SCREEN_MET",
            "PRELIMINARY_COMPETING_HOTSPOT_STABILITY",
        ):
            st.warning(
                "Preliminary NUMERICAL stress-region screening only; "
                "no actual fixture/contact verification, laboratory "
                "stress correlation, or structural safety approval."
            )
            if details.status=="PRELIMINARY_COMPETING_HOTSPOT_STABILITY":
                st.info(
                    "The highest sampled stress switched between multiple "
                    "physical locations. Two fixed XYZ hotspot regions "
                    "have been evaluated on BOTH refined 3D meshes. "
                    "Inspect each critical region separately."
                )
        else:
            st.error(
                "LOCAL STRESS UNRESOLVED — " + details.status
            )
        st.write(details.explanation)
        local_rows=pd.DataFrame([r.as_dict() for r in details.steps])
        local_rows=local_rows.rename(columns={
            "label":"FE solution",
            "mesh_tetra_count":"Real tetra elements",
            "local_factor":"Hotspot mesh factor",
            "tip_mm":"Tip movement (mm)",
            "global_peak_mpa":"Global sampled peak (MPa)",
            "region_mean_mpa":"Fixed-band mean (MPa)",
            "region_p90_mpa":"Fixed-band P90 (MPa)",
            "peak_xyz_mm":"Peak XYZ (mm)",
            "reaction_residual":"Reaction error",
            "volume_difference_pct":"CAD/mesh volume difference (%)",
        })
        st.dataframe(local_rows,hide_index=True,width="stretch")
        st.caption(
            f"Finer local meshes: moving maximum changed "
            f"{details.peak_change_percent:.2f}%, weighted band mean "
            f"{details.region_mean_change_percent:.2f}%, band P90 "
            f"{details.region_p90_change_percent:.2f}%, and hotspot "
            f"location moved {details.hotspot_move_mm:.2f} mm."
        )
        if details.matched_physical_hotspot_regions:
            st.markdown(
                "**Independent spatial stress probes · competing hotspots**"
            )
            st.caption(
                "Each row is one FIXED 7 mm physical XYZ sphere, "
                "queried on both 3D FE solutions; it is not a moving "
                "maximum element ID. Values are Gauss-volume weighted."
            )
            fixed_sites = pd.DataFrame(
                list(details.matched_physical_hotspot_regions)
            ).rename(columns={
                "center_xyz_mm": "Physical XYZ center (mm)",
                "radius_mm": "Sphere radius (mm)",
                "mesh_A_gauss_samples": "Mesh A samples",
                "mesh_B_gauss_samples": "Mesh B samples",
                "mesh_A_volume_weighted_mean_mpa": "Mesh A mean (MPa)",
                "mesh_B_volume_weighted_mean_mpa": "Mesh B mean (MPa)",
                "mean_change_percent": "Mean change (%)",
                "mesh_A_weighted_p90_mpa": "Mesh A P90 (MPa)",
                "mesh_B_weighted_p90_mpa": "Mesh B P90 (MPa)",
                "p90_change_percent": "P90 change (%)",
            })
            st.dataframe(fixed_sites,hide_index=True,width="stretch")
            st.caption(
                "Largest matched-site mean change: "
                f"{details.maximum_fixed_site_mean_change_percent:.2f}%; "
                "largest matched-site P90 change: "
                f"{details.maximum_fixed_site_p90_change_percent:.2f}%."
            )
        st.caption(details.limitations)
        st.download_button(
            "Download local stress-verification JSON",
            json.dumps(details.as_dict(),indent=2),
            file_name="forceforge_hotspot_stress_audit.json",
            mime="application/json",key="download_hotspot_stress",
        )

        # The second-stage study is only meaningful after two actual
        # competing physical hotspot positions have been found. Preserve
        # earlier CAD/FE results if the optional further two jobs fail.
        if len(details.matched_physical_hotspot_regions)==2:
            st.markdown("#### Step 3B · Refine BOTH competing hotspots")
            st.write(
                "The moving maximum occurred at two distinct physical "
                "sites. The next study freezes both exact XYZ coordinates "
                "BEFORE new calculations, re-imports the SAME STEP, and "
                "creates two independent tetra10 FE meshes with native "
                "Gmsh Box size fields around BOTH sites simultaneously. "
                "It requires two additional explicit solver runs. "
                "No global peak convergence or engineering safety "
                "will be assumed from stable finite-region averages."
            )
            selected_centers=tuple(
                tuple(float(v) for v in region["center_xyz_mm"])
                for region in details.matched_physical_hotspot_regions
            )
            st.caption(
                "Frozen physical centers (mm): "
                + str(tuple(tuple(round(x,3) for x in p) for p in selected_centers))
                + ". Fixed 7 mm spheres are compared on both new meshes."
            )
            if st.button(
                "Run dual-hotspot re-mesh + 2 independent 3D FEA solves",
                key="run_true_dual_hotspot",
            ):
                st.session_state.pop("stable_dual_hotspot",None)
                try:
                    with st.spinner(
                        "Locally refining BOTH true CAD hotspots in two "
                        "separate bounded Gmsh / tetra10 FE worker jobs..."
                    ):
                        dual=run_dual_hotspot_study(
                            saved["source"],result,details,
                            source_label=saved["source_name"],unit=unit,
                            solve_at=analyze_step_safely,
                        )
                    st.session_state["stable_dual_hotspot"]={
                        "signature":signature,
                        "source_sha256":mesh.source_sha256,
                        "centers":selected_centers,
                        "study":dual,
                    }
                except (CadJobError,RuntimeError,ValueError,OSError) as exc:
                    st.error(
                        "Dual-site FEM study failed without deleting the "
                        "original result or the first hotspot study: "
                        + str(exc) + ". Local stress remains UNVERIFIED."
                    )

            double=st.session_state.get("stable_dual_hotspot")
            if double is not None and (
                double["signature"]!=signature or
                double["source_sha256"]!=mesh.source_sha256 or
                double["centers"]!=selected_centers
            ):
                st.warning(
                    "Dual-hotspot results are stale after the CAD, "
                    "load or hotspot identification changed."
                )
                double=None
            if double is not None:
                audited=double["study"]
                st.write("**Dual-hotspot fixed-site screen:**",audited.status)
                st.write("**Moving peak stress screen:**",audited.global_peak_status)
                if audited.status=="PRELIMINARY_DUAL_SITE_NUMERICAL_STABILITY":
                    st.warning(
                        "The two fixed physical regions meet only a "
                        "PRELIMINARY NUMERICAL stress screen; "
                        "this does not prove moving peak convergence "
                        "or real fixture/contact strength."
                    )
                else:
                    st.error(
                        "DUAL-SITE NUMERICAL VERIFICATION INCOMPLETE — "
                        + audited.status
                    )
                st.write(audited.explanation)
                st.dataframe(
                    pd.DataFrame([r.as_dict() for r in audited.steps]),
                    hide_index=True,width="stretch",
                )
                if audited.site_rows:
                    st.dataframe(
                        pd.DataFrame(audited.site_rows),
                        hide_index=True,width="stretch",
                    )
                a,b,c=st.columns(3)
                a.metric(
                    "Peak movement (mm)",
                    f"{audited.global_peak_movement_mm:.3f}",
                )
                b.metric(
                    "Largest fixed-site mean difference",
                    (f"{audited.maximum_site_mean_change_percent:.2f}%"
                     if audited.maximum_site_mean_change_percent is not None
                     else "UNVERIFIED"),
                )
                c.metric(
                    "Largest fixed-site P90 difference",
                    (f"{audited.maximum_site_p90_change_percent:.2f}%"
                     if audited.maximum_site_p90_change_percent is not None
                     else "UNVERIFIED"),
                )
                st.caption(audited.limitations)
                st.download_button(
                    "Download dual-hotspot FEA evidence JSON",
                    json.dumps(audited.as_dict(),indent=2),
                    file_name="forceforge_dual_hotspot_stress_audit.json",
                    mime="application/json",
                    key="download_dual_hotspot_stress",
                )

st.subheader("Step 4 · Independently re-mesh a revised STEP")
st.write(
    "A second solver job uses a *different STEP file* and recomputes the "
    "complete 3D finite-element system."
)
revision_token = None
revision_blob = None
revision_name = None
if selection == "Editable 3D L-bracket":
    revision_mm = st.select_slider(
        "Proposed revised web thickness (mm)",
        options=[8, 10, 12, 14], value=12,
    )
    revision_token = f"bracket:{revision_mm}"
    revision_name = f"Parametric revised bracket ({revision_mm} mm)"
    if revision_mm == web:
        st.caption("Choose a different revision thickness to compare changed CAD.")
else:
    revised_upload = st.file_uploader(
        "Upload revised STEP file",
        type=["step", "stp"],
        key="stable_revision_upload",
    )
    if revised_upload is not None:
        revision_blob = revised_upload.getvalue()
        revision_token = sha256(revision_blob).hexdigest()
        revision_name = revised_upload.name

revision_signature = (signature, revision_token)
revision_disabled = revision_token is None or (
    selection == "Editable 3D L-bracket" and revision_mm == web
)
if st.button(
    "Re-mesh revised CAD and re-run 3D FEA",
    disabled=revision_disabled,
    key="stable_run_revision",
):
    st.session_state.pop("stable_revised", None)
    start = time.monotonic()
    try:
        with st.spinner(
            "Isolated STEP revision and independent 3D FEM solve..."
        ):
            revised_step = (
                generate_bracket_safely(float(revision_mm))
                if selection == "Editable 3D L-bracket"
                else revision_blob
            )
            if sha256(revised_step).hexdigest() == mesh.source_sha256:
                raise ValueError(
                    "Revised STEP matches the original file exactly. "
                    "Change geometry or upload a different CAD file."
                )
            redesigned = analyze_step_safely(
                revised_step, source_label=revision_name,
                mesh_size_mm=float(mesh_size), unit=unit, load=case,
            )
        st.session_state["stable_revised"] = {
            "signature": revision_signature,
            "source": revised_step,
            "result": redesigned,
            "seconds": time.monotonic() - start,
        }
    except (CadJobError, RuntimeError, ValueError, OSError) as exc:
        st.error(f"Revised CAD job failed safely: {exc}")

revised_record = st.session_state.get("stable_revised")
if revised_record is not None and (
    revised_record["signature"] != revision_signature
):
    st.warning(
        "The revision or loading inputs changed. The previous comparison "
        "is hidden until you re-run the revised CAD FEA."
    )
    revised_record = None

if revised_record is not None:
    improved = revised_record["result"]
    color_max = 1.01 * max(
        result.peak_von_mises_mpa, improved.peak_von_mises_mpa
    )
    st.success(
        f"Revised CAD independently meshed and solved in "
        f"{revised_record['seconds']:.1f} s."
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Original STEP geometry**")
        st.plotly_chart(
            surface_figure(
                result, deformation_scale=visual,
                stress_cmax_mpa=color_max,
            ), width="stretch", key="stable_before",
        )
    with col2:
        st.markdown("**Revised STEP geometry**")
        st.plotly_chart(
            surface_figure(
                improved, deformation_scale=visual,
                stress_cmax_mpa=color_max,
            ), width="stretch", key="stable_after",
        )
    st.caption(
        f"Shared 0–{color_max:.2f} MPa color scale. "
        f"Tetrahedra: {mesh.num_tets} → {improved.mesh.num_tets}."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Change in mass",
        f"{(improved.mass_kg/result.mass_kg - 1)*100:+.1f}%",
    )
    c2.metric(
        "Tip displacement",
        f"{result.tip_mm:.4f} → {improved.tip_mm:.4f} mm",
    )
    c3.metric(
        "Sampled von Mises",
        f"{result.peak_von_mises_mpa:.1f} → "
        f"{improved.peak_von_mises_mpa:.1f} MPa",
    )
    st.download_button(
        "Download revised STEP",
        revised_record["source"],
        "forceforge_revised.step", mime="application/step",
    )
    audit = {
        "base_sha256": mesh.source_sha256,
        "revised_sha256": improved.mesh.source_sha256,
        "source": saved["source_name"],
        "material_and_load": asdict(case),
        "before": {
            "mass_kg": result.mass_kg, "tip_mm": result.tip_mm,
            "sampled_stress_mpa": result.peak_von_mises_mpa,
            "tetra_elements": mesh.num_tets,
        },
        "after": {
            "mass_kg": improved.mass_kg, "tip_mm": improved.tip_mm,
            "sampled_stress_mpa": improved.peak_von_mises_mpa,
            "tetra_elements": improved.mesh.num_tets,
        },
        "validation_scope": "Assumed static elastic experiment, not certified",
    }
    st.download_button(
        "Export FEA comparison evidence (JSON)",
        data=json.dumps(audit, indent=2),
        file_name="forceforge_cad_fea.json",
        mime="application/json",
    )


# -------------------------------------------------------------------------
# Step 5: AI proposes bounded parametric CAD changes; ONLY independent
# tetra10 FEM + engineering quality gates may rank candidates. This is a
# transparent, reproducible opt-in feature for the hackathon live demo.
# -------------------------------------------------------------------------
st.subheader("Step 5 · Design Copilot: AI proposal → Real CAD → FEA verification")
if selection != "Editable 3D L-bracket":
    st.info(
        "The current Design Copilot edits ONLY the documented parametric "
        "8/10/12/14 mm drilled L-bracket. Imported arbitrary STEP topology "
        "cannot yet be automatically regenerated. Existing manual STEP "
        "comparison and genuine 3D FEA remain available above."
    )
else:
    st.write(
        "Enter an engineering objective. Optionally let a language model "
        "prioritize **bounded CAD dimensions**. Every alternative is then "
        "regenerated as a REAL STEP and independently meshed/solved with "
        "the same Gmsh + quadratic-tetra10 FEM. AI cannot invent stresses "
        "or override a failed engineering check."
    )
    copilot_brief = st.text_input(
        "Design objective (max 500 characters)",
        value=(
            "Reduce deflection and sampled stress while minimizing "
            "added material."
        ),
        max_chars=500,
        key="stable_copilot_brief",
    )
    c1, c2, c3 = st.columns(3)
    tip_limit = c1.number_input(
        "Target max tip displacement (mm)",
        min_value=.001, max_value=20., value=.015,
        step=.005, format="%.3f", key="stable_copilot_tip_limit",
    )
    stress_limit = c2.number_input(
        "Target max sampled von Mises (MPa)",
        min_value=1., max_value=1800.,
        value=min(16., float(yield_mpa)),
        step=1., key="stable_copilot_stress_limit",
    )
    mass_budget = c3.number_input(
        "Allowed mass increase (%)",
        min_value=0., max_value=250., value=40.,
        step=5., key="stable_copilot_mass_budget",
    )
    enable_llm = st.checkbox(
        "Ask an LLM to prioritize the CAD proposals (optional OpenAI API)",
        value=False, key="stable_copilot_use_llm",
    )
    secret_key = (
        st.text_input(
            "API key (used for this request only, never exported)",
            type="password", key="stable_copilot_secret",
            help="Leave blank to use OPENAI_API_KEY from the server environment. "
                 "If unavailable, the run is labeled rules-based.",
        ) if enable_llm else None
    )
    criteria = DesignLimits(
        max_tip_mm=float(tip_limit),
        max_sampled_stress_mpa=float(stress_limit),
        max_mass_increase_percent=float(mass_budget),
    )
    copilot_signature = (
        signature, float(web), copilot_brief, criteria, bool(enable_llm),
    )
    st.caption(
        "Permitted geometry variable: vertical web thickness 8, 10, 12, "
        "or 14 mm. Material, boundary conditions, mesh target and applied "
        "load remain identical. The finite search is bounded; this is NOT "
        "automatic arbitrary assembly reconstruction or CFD."
    )
    if st.button(
        "Generate CAD proposals + verify every candidate with real 3D FEA",
        type="primary", key="stable_copilot_run",
    ):
        st.session_state.pop("stable_cad_copilot", None)
        started = time.monotonic()
        try:
            with st.spinner("Parsing the brief and planning bounded CAD studies..."):
                proposal = propose_designs(
                    brief=copilot_brief,
                    original_thickness_mm=int(web),
                    baseline=result, limits=criteria,
                    use_api=bool(enable_llm), api_key=secret_key,
                )
            fe_rows = []
            cad_sources = {}
            fe_solutions = {}
            failures = []
            for n, thickness in enumerate(proposal.candidates_mm, start=1):
                try:
                    with st.spinner(
                        f"True 3D FEA {n}/{len(proposal.candidates_mm)}: "
                        f"generate {thickness} mm STEP → tetra mesh → solve..."
                    ):
                        candidate_step = generate_bracket_safely(float(thickness))
                        candidate_fea = analyze_step_safely(
                            candidate_step,
                            source_label=f"Copilot candidate {thickness} mm",
                            mesh_size_mm=float(mesh_size),
                            unit="mm", load=case,
                        )
                        evidence_row = evaluate_candidate(
                            original=result, candidate=candidate_fea,
                            thickness_mm=thickness, limits=criteria,
                        )
                    fe_rows.append(evidence_row)
                    cad_sources[thickness] = candidate_step
                    fe_solutions[thickness] = candidate_fea
                except (CadJobError, RuntimeError, ValueError, OSError) as exc:
                    failures.append({
                        "thickness_mm": thickness,
                        "error_type": type(exc).__name__,
                        "message": str(exc)[:400],
                    })
            selected = pick_lightest_feasible(fe_rows)
            # A design already meeting the stated numerical limits may be
            # lighter than all proposals; never force a needless redesign.
            original_qa = (
                result.relative_reaction_residual <= 1e-5
                and mesh.relative_volume_difference <= .20
                and mesh.min_shape_quality > 0
            )
            original_feasible = (
                original_qa
                and result.tip_mm <= criteria.max_tip_mm
                and result.peak_von_mises_mpa <= criteria.max_sampled_stress_mpa
                and result.peak_von_mises_mpa*1e6 <= case.yield_pa
            )
            if original_feasible and (
                selected is None or result.mass_kg <= fe_solutions[selected].mass_kg
            ):
                selected = int(web)
            if not fe_rows and not original_feasible:
                raise ValueError(
                    "All candidate FEA runs failed; no design is verified. "
                    "Inspect individual solver failures."
                )
            st.session_state["stable_cad_copilot"] = {
                "signature": copilot_signature,
                "proposal": proposal,
                "rows": tuple(fe_rows),
                "sources": cad_sources,
                "solutions": fe_solutions,
                "failures": tuple(failures),
                "selected": selected,
                "original_feasible": original_feasible,
                "duration_s": time.monotonic()-started,
            }
        except (RuntimeError, ValueError, OSError) as exc:
            st.error(
                "Design search did not complete a valid physical study: "
                + str(exc)
            )

    copilot_record = st.session_state.get("stable_cad_copilot")
    if copilot_record is not None and copilot_record["signature"] != copilot_signature:
        st.warning(
            "Design brief, limits, loading or geometry changed. "
            "Previous AI/FEA recommendation is stale and hidden until re-run."
        )
        copilot_record = None
    if copilot_record is not None:
        suggestion = copilot_record["proposal"]
        rows = list(copilot_record["rows"])
        failures = list(copilot_record["failures"])
        selected = copilot_record["selected"]
        st.write("**Proposal source:**", suggestion.mode)
        st.caption(suggestion.message)
        st.write("**Reasoning:**", suggestion.rationale)
        if failures:
            st.error(
                "INCOMPLETE CANDIDATE SET: "
                + str(len(failures))
                + " independent CAD/FEA studies failed. No global search "
                  "completeness or engineering safety is claimed."
            )
            st.dataframe(pd.DataFrame(failures),hide_index=True,width="stretch")
        view_rows = [{
            "Design": f"Original {int(web)} mm",
            "3D tetra": mesh.num_tets,
            "Mass (kg)": result.mass_kg,
            "Mass change (%)": 0.,
            "Tip (mm)": result.tip_mm,
            "Sampled stress (MPa)": result.peak_von_mises_mpa,
            "Model screen": (
                "PRELIMINARY_MEETS" if copilot_record["original_feasible"]
                else "FAILS_ASSUMED_LIMITS"
            ),
        }]
        view_rows.extend({
            "Design": f"CAD {r.thickness_mm} mm",
            "3D tetra": r.tetrahedra,
            "Mass (kg)": r.mass_kg,
            "Mass change (%)": r.mass_change_pct,
            "Tip (mm)": r.tip_mm,
            "Sampled stress (MPa)": r.peak_von_mises_mpa,
            "Model screen": r.status,
        } for r in rows)
        st.dataframe(
            pd.DataFrame(view_rows).round(5),
            hide_index=True,width="stretch",
        )
        fig = go.Figure()
        for item in view_rows:
            screened = item["Model screen"] in (
                "PRELIMINARY_MODEL_CONSTRAINTS_MET", "PRELIMINARY_MEETS",
            )
            fig.add_trace(go.Scatter(
                x=[item["Mass (kg)"]], y=[item["Tip (mm)"]],
                mode="markers+text",
                text=[item["Design"]], textposition="top center",
                name=item["Design"] + (" · meets screen" if screened else " · outside screen"),
                marker=dict(
                    size=14, symbol="circle" if screened else "x",
                    color="#23a89d" if screened else "#e9a34b",
                ),
                hovertemplate=(
                    "%{text}<extra></extra>"
                    + "<br>Mass %{x:.4f} kg"
                    + "<br>Tip %{y:.5f} mm"
                ),
            ))
        fig.add_hline(
            y=criteria.max_tip_mm, line_dash="dash",
            annotation_text="Illustrative displacement limit",
        )
        fig.update_layout(
            title="Actual FEM design trade-off · mass vs tip displacement",
            xaxis_title="Mass (kg)",
            yaxis_title="FE-computed tip displacement (mm)",
            height=360,
            showlegend=False,
            margin=dict(t=60,b=40,l=40,r=20),
        )
        st.plotly_chart(
            fig,width="stretch",key="stable_copilot_tradeoff",
        )
        if selected is None:
            st.error(
                "No design in the tested discrete set meets every "
                "illustrative constraint; no unverified winner is invented."
            )
        else:
            is_original = selected == int(web)
            complete = len(rows) == len(suggestion.candidates_mm) and not failures
            if complete:
                st.success(
                    "PHYSICS-VERIFIED DISCRETE SCREEN: "
                    + ("Retain original CAD" if is_original
                       else f"{selected} mm revised STEP is the lightest "
                            "FEA-screened candidate meeting all stated limits.")
                )
            else:
                st.warning(
                    f"Best among successfully tested variants: {selected} mm. "
                    "Candidate evaluation is incomplete."
                )
            if not is_original:
                winner = copilot_record["solutions"][selected]
                compare_cmax = 1.01*max(
                    result.peak_von_mises_mpa,winner.peak_von_mises_mpa
                )
                ca, cb = st.columns(2)
                with ca:
                    st.markdown("**Original CAD / true tetra10 FEA**")
                    st.plotly_chart(
                        surface_figure(
                            result,deformation_scale=visual,
                            stress_cmax_mpa=compare_cmax,
                        ),width="stretch",key="copilot_orig_fea",
                    )
                with cb:
                    st.markdown("**Selected revised STEP / independently solved**")
                    st.plotly_chart(
                        surface_figure(
                            winner,deformation_scale=visual,
                            stress_cmax_mpa=compare_cmax,
                        ),width="stretch",key="copilot_best_fea",
                    )
                st.caption(
                    f"Shared 0–{compare_cmax:.2f} MPa legend. "
                    "Both 3D stress fields come from independently "
                    "solved quadratic-tetra finite elements."
                )
                st.download_button(
                    f"Download FEA-verified candidate CAD ({selected} mm STEP)",
                    data=copilot_record["sources"][selected],
                    file_name=f"forceforge_copilot_{selected}mm.step",
                    mime="application/step",
                    key="stable_copilot_step_export",
                )
        audited = {
            "study": "Bounded CAD proposals evaluated by real Gmsh tetra10 FEA",
            "proposal": suggestion.as_dict(),
            "original_step_sha256": result.mesh.source_sha256,
            "material_force_fixture": asdict(case),
            "design_brief": copilot_brief,
            "limits": asdict(criteria),
            "baseline": view_rows[0],
            "candidates": [r.as_dict() for r in rows],
            "failed_jobs": failures,
            "selected_thickness_mm": selected,
            "all_candidates_evaluated": (
                len(rows) == len(suggestion.candidates_mm) and not failures
            ),
            "solve_duration_s": copilot_record["duration_s"],
            "verification_scope": (
                "Preliminary static 3D linear-elastic FEA and illustrative "
                "criteria only. No demonstrated converged local peak stress, "
                "contact, fatigue, material qualification, CFD, or safety approval."
            ),
        }
        st.download_button(
            "Export auditable AI-to-CAD-to-FEA evidence (JSON)",
            data=json.dumps(audited,indent=2),
            file_name="forceforge_copilot_real_fea_evidence.json",
            mime="application/json",
            key="stable_copilot_json_export",
        )
        st.caption(
            "AI outputs only bounded CAD proposals; 3D FEA is authoritative. "
            "Passing these illustrative limits is not a numerical convergence "
            "certificate, verified joint/bolt fixture or approval for use."
        )

with st.expander("Source, numerical limits and qualification gaps"):
    st.write(
        "The Gmsh STEP importer runs in a separate process and explicitly "
        "limits the input tetra count. The quadratic displacement tetra FE "
        "solver is linear elastic with idealized face constraints and traction."
    )
    st.write(
        "Caution: nonlinear contact, actual bolt preload, physical static "
        "strain measurements, fatigue, mesh-converged notch peak stress, "
        "and structural safety certification are not included."
    )
    st.write(
        "For the original NIST specimen, published manufacturing distortion "
        "measurements do not independently validate these assumed lateral "
        "load cases."
    )
