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
        "two progressively smaller 3D mesh-size fields centered at that "
        "physical location, while preserving the same force and support."
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
        if details.status=="PRELIMINARY_LOCAL_STRESS_SCREEN_MET":
            st.warning(
                "Numerical local-stress screening only. Physical contact, "
                "experimental material data and safety approval are not verified."
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
        st.caption(details.limitations)
        st.download_button(
            "Download local stress-verification JSON",
            json.dumps(details.as_dict(),indent=2),
            file_name="forceforge_hotspot_stress_audit.json",
            mime="application/json",key="download_hotspot_stress",
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
