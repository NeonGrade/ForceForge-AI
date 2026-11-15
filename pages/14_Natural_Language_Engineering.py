"""ForceForge X · natural-language mechanical engineering studio (v0.1).

Same Streamlit multipage application and same PR #16 branch. The UI only
runs native CAD/FEA on an EXPLICIT button press through bounded subprocesses.
CFD, thermal and fan mounting structural results are blocked, NEVER mocked.
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
    TaskState, plan_engineering, run_engineering,
)
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
    "Prototype capabilities: real L-bracket STEP + isolated tetra10 FEA; "
    "conceptual wall-fan STEP only. Multi-body fan contact, CFD and "
    "thermal results remain blocked until validated solvers are connected. "
    "No flow or wall-stress outputs are invented."
)
st.markdown(
    "[Open the existing Real STEP / dual-hotspot / Design Copilot study]"
    "(./Real_STEP_Engineering)"
)

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
        help="Currently registered: drilled L-bracket and conceptual wall fan. "
             "Any unregistered product family is explicitly rejected.",
    )
    parse_clicked=st.form_submit_button(
        "Interpret engineering requirements",type="primary",
    )

if parse_clicked:
    st.session_state["nl_interpretation"]=interpret_text(prompt)
    st.session_state.pop("nl_result",None)

interpretation=st.session_state.get("nl_interpretation")
if interpretation is None:
    st.caption("Parsing is local, bounded and does not launch Gmsh, CAD, CFD or FEA.")
    st.stop()
if interpretation.request is None:
    for issue in interpretation.issues:
        st.error(issue)
    st.caption("The generator registry can be extended; it cannot invent an arbitrary mechanical product family.")
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
    "A BLOCKED CFD or fan FEA stage does not produce results."
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
            title="Actual conceptual STEP surface mesh · NO CFD/FEA coloring",
            scene=dict(aspectmode="data",xaxis_title="X (mm)",
                       yaxis_title="Y (mm)",zaxis_title="Z (mm)"),
            margin=dict(l=0,r=0,t=50,b=0),height=500,
        )
        st.plotly_chart(fig,width="stretch")
    elif cad.concept_only:
        st.warning(
            "Concept fan STEP is available; surface preview could not be tessellated "
            "in this worker. No substitute stress/flow plot is shown."
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
