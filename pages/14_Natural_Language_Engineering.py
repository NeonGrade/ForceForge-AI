"""ForceForge X · natural-language mechanical engineering studio (v0.1).

Same Streamlit multipage application and same PR #16 branch. The UI only
runs native CAD/FEA on an EXPLICIT button press through bounded subprocesses.
CFD is only run by a separate real OpenFOAM job; no CFD/thermal or fan
mounting structural results are fabricated by this CAD page.
"""
from __future__ import annotations

from dataclasses import asdict
import json

import plotly.graph_objects as go
import streamlit as st

from forceforge.engineering_schema import (
    approve_demo_assumptions, interpret_text,
)
from forceforge.engineering_pipeline import (
    TaskState, plan_engineering, run_engineering, mesh_registered_fluid_domain,
)
from forceforge.rotor_surface import extract_rotor_from_step
from forceforge.isolated_cad import CadJobError
from forceforge.solid3d import surface_figure

st.set_page_config(
    page_title="ForceForge X | Natural Language Engineering",
    page_icon="🧩",layout="wide",
)
st.title("Natural Language → CAD → Engineering Simulation")
st.caption(
    "ForceForge X · registered mechanical product families · "
    "strict geometry/physics inputs · real STEP exports"
)
st.info(
    "CAD catalog: real L-bracket STEP + validated isolated tetra10 FEA; "
    "conceptual wall fan STEP + genuine air-domain Gmsh preprocessor; "
    "new parametric hollow shaft and plate STEP generators with user-approved "
    "isolated tetra10 structural FEA under explicitly simplified fixtures. "
    "Fan CFD runs in a separate real OpenFOAM page; structural wall-anchor "
    "equilibrium is separate from actual wall contact and fastener FEA."
)
st.markdown(
    "[Open the existing Real STEP / dual-hotspot / Design Copilot study]"
    "(./Real_STEP_Engineering)"
)
st.markdown("[Try the real OpenFOAM rotating-fan transient CFD reference lab](./Transient_Rotating_CFD)")
st.markdown("[Analyze wall mounting loads with force/moment equilibrium](./Wall_Mount_Loads)")

examples={
    "Wall fan (Chinese)": (
        "帮我做一个直径30厘米、转速1500 RPM的挂壁风扇，"
        "想看气流分布，以及墙壁和固定架怎么受力。"
    ),
    "Wall fan (English)": (
        "Design a wall fan with diameter 300 mm, speed 1500 RPM. "
        "Show airflow and stress on wall mounts."
    ),
    "Real bracket FEA (Chinese)": (
        "生成腹板厚度8毫米的L型支架，施加载荷250 N，"
        "计算结构受力、应力和变形。"
    ),
    "Hollow shaft / sleeve (Chinese)": (
        "设计一个空心轴，外径60mm，内径30mm，长度120mm。"
    ),
    "Hollow shaft (real FEA demo)": (
        "设计一个空心轴，外径30mm，内径10mm，长度60mm，分析受力和应力。"
    ),
    "Mounting plate with four holes (Chinese)": (
        "做一个矩形安装板，长度150mm，宽度100mm，厚度8mm，"
        "开4个孔，孔径6mm，孔中心距边缘15mm。"
    ),
    "Mounting plate (English)": (
        "Design a rectangular mounting plate length 150 mm width 100 mm "
        "thickness 8 mm with 4 holes, hole diameter 6 mm "
        "and hole edge offset 15 mm."
    ),
    "Mounting plate (real FEA demo)": (
        "做一个矩形安装板，长度60mm，宽度50mm，厚度12mm，计算应力和结构受力。"
    ),
}
st.markdown("### 1 · Describe the product in ordinary language")
if "nl_input_text" not in st.session_state:
    st.session_state["nl_input_text"]=examples["Wall fan (Chinese)"]

def use_selected_example():
    st.session_state["nl_input_text"]=examples[st.session_state["nl_example_choice"]]

st.selectbox(
    "Load a supported example",
    list(examples),
    key="nl_example_choice",on_change=use_selected_example,
)
with st.form("natural_engineering_input"):
    prompt=st.text_area(
        "What should ForceForge build and analyze?",
        key="nl_input_text",
        max_chars=1200,height=110,
        help="Registered: L-bracket, wall fan, hollow shaft, rectangular plate. "
             "Give exact dimensions. Unknown products are explicitly blocked.",
    )
    parse_clicked=st.form_submit_button(
        "Interpret engineering requirements",type="primary",
    )

if parse_clicked:
    st.session_state["nl_interpretation"]=interpret_text(prompt)
    st.session_state.pop("nl_result",None)
    # Consent is bound to the interpreted input, never silently inherited
    # after a user describes a different product or changes dimensions.
    st.session_state["nl_allow_defaults"]=False

interpretation=st.session_state.get("nl_interpretation")
if interpretation is None:
    st.caption("Parsing is local, bounded and does not launch Gmsh, CAD, CFD or FEA.")
    st.stop()
if interpretation.request is None:
    for issue in interpretation.issues:
        st.error(issue)
    st.caption(
        "This is a tested family catalog, not unrestricted text-to-any-CAD. "
        "Requesting a new product requires a validated generator and schema."
    )
    st.stop()
if interpretation.request.prompt!=prompt:
    st.warning("The text changed; press Interpret again before running any model.")
    st.stop()
for issue in interpretation.issues:
    st.warning(issue)

request=interpretation.request
st.markdown("### 2 · Review the unit-explicit product schema")
c1,c2=st.columns([2,1])
with c1:
    st.code(
        json.dumps(request.model_dump(mode="json"),indent=2,ensure_ascii=False),
        language="json",
    )
with c2:
    st.write("**Supported family:**", request.family.value)
    st.write("**Extractor:**", request.extraction_mode)
    st.caption("The local parser extracts only measurements actually mentioned in the text. Unknown values remain null.")
    confirmed=st.checkbox(
        "I authorize explicitly labeled DEMO geometry / material / fixture defaults",
        value=False,key="nl_allow_defaults",
        help="For a fan, this only fills blade geometry for conceptual STEP export. "
             "It never enables fictional CFD, bolts, contact or wall stress.",
    )

effective=request
if confirmed:
    try:
        effective=approve_demo_assumptions(request)
    except ValueError as exc:
        st.error(str(exc))
if effective.assumptions:
    st.markdown("**Explicit demonstration assumptions**")
    for assumption in effective.assumptions:
        st.caption("• "+assumption)

plan=plan_engineering(effective)
st.markdown("### 3 · CAD / mesh / FEA / CFD execution plan")
rows=[]
for task in plan.tasks:
    rows.append({
        "Task":task.name,
        "State":task.status.value,
        "Depends on":", ".join(task.depends_on) or "—",
        "Missing inputs":", ".join(task.missing_inputs) or "—",
        "Reason":task.reason,
    })
st.dataframe(rows,hide_index=True,width="stretch")
if plan.task("fluid_cfd").status==TaskState.AVAILABLE_EXTERNAL:
    st.info(
        "Actual source-STEP rotor OpenFOAM CFD is supported through the "
        "separate rotating-flow page. First generate the fan STEP and "
        "extract its real blade STL, then launch a genuine solver job. "
        "No velocities/pressures are computed by this geometry planner."
    )
for warning in plan.warnings:
    st.caption("Engineering limitation: "+warning)

cad_ready=plan.task("generate_cad").status==TaskState.READY
if not cad_ready:
    st.error(
        "CAD is not ready. Add missing dimensions to the plain-language "
        "description, or explicitly confirm the concept geometry defaults."
    )

st.markdown("### 4 · Execute real, isolated geometry and physics jobs")
st.caption(
    "A CAD button click runs real Gmsh in a disposable worker; "
    "FEA is executed only if the plan has all required inputs. "
    "The 3D air-domain tetra mesh is a separate explicit click. "
    "Unknown, unsupported or unavailable CFD/FEA jobs never produce fabricated results."
)
start=st.button(
    "Generate STEP and execute READY engineering stages",
    type="primary",disabled=not cad_ready,key="nl_execute",
)
signature=json.dumps(
    effective.model_dump(mode="json"),sort_keys=True,ensure_ascii=False,
)
if start:
    st.session_state.pop("nl_result",None)
    st.session_state.pop("forceforge_custom_rotor_input",None)
    try:
        with st.spinner("Running isolated OpenCASCADE CAD generator and permitted real FEA jobs..."):
            execution=run_engineering(effective)
        st.session_state["nl_result"]={
            "signature":signature,"execution":execution,
        }
    except (CadJobError,RuntimeError,ValueError,OSError) as exc:
        st.error(f"Engineering run failed; old app remains available: {exc}")

snapshot=st.session_state.get("nl_result")
if snapshot is not None and snapshot["signature"]!=signature:
    st.warning("Inputs or assumption confirmation changed. Old results are hidden.")
    snapshot=None

if snapshot is not None:
    execution=snapshot["execution"]
    cad=execution.cad
    st.success(
        f"Real STEP export completed ({len(cad.step_bytes):,} bytes, "
        f"{cad.solid_parts} solid bodies)."
    )
    st.write("**CAD source SHA-256:**",cad.sha256)
    st.caption(cad.description)
    st.download_button(
        "Download genuine CAD STEP",
        data=cad.step_bytes,
        file_name=f"forceforge_{cad.family}_{cad.sha256[:10]}.step",
        mime="application/step",
        key="nl_download_step",
    )
    if cad.family=="wall_fan":
        st.markdown("### Step 4B · Real rotating blade geometry for transient CFD")
        st.caption(
            "This stage reimports your exact STEP using OpenCASCADE and "
            "extracts the ACTUAL hub/rotor blade solid as a water-tight "
            "OpenFOAM STL in metres. It is then located in OpenFOAM's "
            "official reference room for sliding AMI simulation. "
            "The wall, guard, fasteners and supports from your STEP are "
            "NOT included in the reference-room flow."
        )
        if st.button(
            "Extract actual rotating blades from my STEP (real STL)",
            key="nl_real_rotor_extract",
        ):
            try:
                with st.spinner(
                    "Isolated OpenCASCADE: identify rotor solid, tessellate "
                    "its real STEP faces and verify closed-manifold surface..."
                ):
                    rotor=extract_rotor_from_step(effective,cad.step_bytes)
                if rotor.cad_source_sha256!=cad.sha256:
                    raise ValueError("Rotating rotor STL is not linked to the current CAD STEP")
                snapshot["rotor_stl"]=rotor
                st.session_state["forceforge_custom_rotor_input"]={
                    "stl_bytes":rotor.stl_bytes,
                    "cad_source_sha256":cad.sha256,
                    "diameter_mm":float(effective.geometry.diameter_mm),
                    "rpm":float(effective.geometry.rpm or 1500),
                    "rotor_stl_sha256":rotor.stl_sha256,
                }
            except (RuntimeError,ValueError,OSError) as exc:
                st.error("Actual CAD rotor surface preparation failed: "+str(exc))
        rotor=snapshot.get("rotor_stl")
        if rotor is not None:
            st.success(
                f"Actual CAD rotor STL: {rotor.triangles:,} water-tight "
                f"triangles; STEP source SHA {rotor.cad_source_sha256[:12]}…"
            )
            st.download_button(
                "Download real STEP-derived rotating blade STL",
                data=rotor.stl_bytes,
                file_name="forceforge_rotor_from_actual_STEP.stl",
                mime="model/stl",key="nl_actual_rotor_stl_export",
            )
            st.info(
                "Source STEP rotor is ready. The real OpenFOAM workflow "
                "will remesh this exact rotor in the official reference "
                "room. The optional actuator air mesh below is NOT "
                "required before starting that separate solver."
            )
            if st.button(
                "Continue to real OpenFOAM CFD using this STEP rotor",
                key="nl_continue_to_cfd",type="primary",
            ):
                st.switch_page("pages/15_Transient_Rotating_CFD.py")

    if cad.preview_nodes_mm is not None and cad.preview_faces is not None:
        nodes=cad.preview_nodes_mm
        faces=cad.preview_faces
        fig=go.Figure(go.Mesh3d(
            x=nodes[:,0],y=nodes[:,1],z=nodes[:,2],
            i=faces[:,0],j=faces[:,1],k=faces[:,2],
            opacity=1.0,color="#5d9cb6",flatshading=True,
            lighting=dict(ambient=.6,diffuse=.55),
            hovertemplate="X %{x:.1f} mm · Y %{y:.1f} mm · Z %{z:.1f} mm<extra>Real OCC surface mesh</extra>",
        ))
        fig.update_layout(
            title="Actual OpenCASCADE STEP surface mesh · no fabricated CFD/FEA",
            scene=dict(aspectmode="data",xaxis_title="X (mm)",
                       yaxis_title="Y (mm)",zaxis_title="Z (mm)"),
            margin=dict(l=0,r=0,t=50,b=0),height=500,
        )
        st.plotly_chart(fig,width="stretch")
    elif cad.concept_only:
        st.warning(
            "Actual STEP export is available; optional OCC surface preview failed. "
            "No substitute geometry or fake stress/flow plot is shown."
        )

    if execution.structural_fea is not None:
        fea=execution.structural_fea
        a,b,c=st.columns(3)
        a.metric("True 3D tetrahedra",f"{fea.mesh.num_tets:,}")
        b.metric("FE tip motion",f"{fea.tip_mm:.5f} mm")
        c.metric("Sampled von Mises",f"{fea.peak_von_mises_mpa:.3f} MPa")
        st.plotly_chart(
            surface_figure(fea,deformation_scale=80),
            width="stretch",
        )
        st.caption(
            "Real quadratic tetra10 linear-elastic FEA; ideal support and "
            "force loading. This does not prove convergence, contact, "
            "material certification or fatigue safety."
        )
    if plan.task("fluid_mesh").status == TaskState.READY:
        st.subheader("Step 5 · Genuine 3D air-volume mesh (CFD preprocessor only)")
        st.caption(
            "The virtual actuator zone is a conformal AIR volume, not "
            "resolved rotor blades. This worker independently imports the "
            "generated STEP to check provenance, then constructs a freestanding "
            "open-boundary idealization around the specified fan diameter. "
            "No Navier–Stokes equations or wall/anchor reactions are solved."
        )
        mesh_requested=st.button(
            "Build real 3D Gmsh fluid mesh + tagged boundary regions",
            key="nl_fluid_mesh_run",type="secondary",
        )
        if mesh_requested:
            try:
                with st.spinner(
                    "Isolated OCC/Gmsh: import fan STEP → create two conforming "
                    "air zones → tetrahedralize → check true volume and patches..."
                ):
                    mesh_registered_fluid_domain(effective,execution)
                st.success(
                    "Genuine 3D air mesh generated; blade-resolved CFD requires "
                    "a separately launched real OpenFOAM job."
                )
            except (RuntimeError,ValueError,OSError) as exc:
                st.error(
                    "3D fluid mesh could not be produced; the previous CAD "
                    "model remains intact: " + str(exc)
                )
        air=execution.fluid_domain
        if air is not None:
            a,b,c=st.columns(3)
            a.metric("Real fluid tetrahedra",f"{air.tetrahedra:,}")
            b.metric("Gmsh volume nodes",f"{air.nodes:,}")
            c.metric(
                "Volume consistency difference",
                f"{100*air.relative_volume_error:.2f}%",
            )
            st.write("**CFD meshing evidence, without CFD solution**")
            st.dataframe([
                {"Physical group":name,
                 "Mesh group ID":marker,
                 "Boundary triangles":air.boundary_triangles.get(name,"3D cell zone")}
                for name,marker in air.patch_ids.items()
            ],hide_index=True,width="stretch")
            if air.preview_points_mm is not None and air.preview_faces is not None:
                pts=air.preview_points_mm
                triangles=air.preview_faces
                fig=go.Figure(go.Mesh3d(
                    x=pts[:,0],y=pts[:,1],z=pts[:,2],
                    i=triangles[:,0],j=triangles[:,1],k=triangles[:,2],
                    color="#22a7a5",opacity=.88,flatshading=True,
                    name="ACTUAL meshed rotor-zone interface",
                    hovertemplate="X %{x:.1f} mm · Y %{y:.1f} mm · Z %{z:.1f} mm"
                                  "<extra>Mesh vertices, no velocity field</extra>",
                ))
                width=air.outer_width_mm/2
                lower=-air.upstream_length_mm
                upper=air.downstream_length_mm
                coords=[
                    (-width,-width,lower),(width,-width,lower),
                    (width,width,lower),(-width,width,lower),
                    (-width,-width,upper),(width,-width,upper),
                    (width,width,upper),(-width,width,upper),
                ]
                lines=[
                    (0,1),(1,2),(2,3),(3,0),(4,5),(5,6),
                    (6,7),(7,4),(0,4),(1,5),(2,6),(3,7),
                ]
                px=[];py=[];pz=[]
                for n,m in lines:
                    for idx in (n,m):
                        xx,yy,zz=coords[idx]
                        px.append(xx);py.append(yy);pz.append(zz)
                    px.append(None);py.append(None);pz.append(None)
                fig.add_trace(go.Scatter3d(
                    x=px,y=py,z=pz,
                    mode="lines",line=dict(color="#76879f",width=3),
                    name="Bounded farfield air domain",
                ))
                fig.update_layout(
                    title="Actual tetra-meshed 3D actuator interface + air box outline",
                    scene=dict(aspectmode="data",xaxis_title="X (mm)",
                               yaxis_title="Y (mm)",zaxis_title="Z (mm)"),
                    margin=dict(l=0,r=0,t=50,b=0),height=510,
                )
                st.plotly_chart(fig,width="stretch",key="nl_air_mesh_preview")
            st.download_button(
                "Download actual tagged 3D Gmsh mesh (.msh)",
                data=air.mesh_bytes,
                file_name=f"forceforge_actuator_air_{air.fluid_mesh_sha256[:10]}.msh",
                mime="application/octet-stream",
                key="nl_download_real_air_msh",
            )
            st.caption(
                "The Gmsh .msh contains TWO 3D air cell zones and physical "
                "upstream/downstream/farfield/internal surfaces. It is not "
                "yet a flow result or a blade-resolved fan geometry. The "
                "actual source STEP and mesh have independent SHA-256 hashes."
            )

    for task in execution.stage_results:
        if task.status==TaskState.BLOCKED:
            st.warning(f"{task.name} — BLOCKED: {task.reason}")
    st.download_button(
        "Download engineering pipeline provenance JSON",
        data=json.dumps(
            {"request":effective.model_dump(mode="json"),**execution.evidence()},
            indent=2,ensure_ascii=False,
        ),
        file_name="forceforge_natural_language_pipeline_evidence.json",
        mime="application/json",key="nl_download_evidence",
    )
