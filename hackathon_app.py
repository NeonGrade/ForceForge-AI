"""Judge-facing ForceForge X launcher: only genuine, integrity-verified local results.

This entrypoint never starts OpenFOAM and never modifies an old CFD job.
"""
from __future__ import annotations

from pathlib import Path
import re
import streamlit as st
from forceforge.rotating_cfd import ROOT, job_status, load_actual_frames

st.set_page_config(
    page_title="ForceForge X | Hack The Nest 2026",
    page_icon="🌀", layout="wide",
)
st.markdown("""
<style>
.block-container{max-width:1190px;padding-top:2rem}
.ff-tag{font-size:.8rem;letter-spacing:.12em;font-weight:700;color:#008b92}
.ff-hero{font-size:3rem;font-weight:800;letter-spacing:-.04em;line-height:1.08}
.ff-sub{color:#566976;font-size:1.08rem;max-width:800px}
</style>
""",unsafe_allow_html=True)
st.markdown('<div class="ff-tag">HACK THE NEST 2026 · PHYSICS-INFORMED ENGINEERING AI</div>',unsafe_allow_html=True)
st.markdown('<div class="ff-hero">ForceForge X</div>',unsafe_allow_html=True)
st.markdown(
    '<div class="ff-sub">Describe a mechanical product. Build genuine STEP CAD. '
    'Inspect independently calculated structural FEA and rotating-flow CFD evidence.</div>',
    unsafe_allow_html=True,
)
st.caption("Live prototype · four registered CAD families · real numerical solvers · source-linked results")
st.divider()

st.subheader("Your engineering workflow")
a,b,c=st.columns(3,gap="large")
with a:
    st.markdown("### 01 · Describe & design")
    st.write("Specify a wall fan, bracket, shaft or mounting plate in English or Chinese. Extract dimensions and generate a real STEP model.")
    st.page_link("pages/14_Natural_Language_Engineering.py",
                 label="Open Natural Language CAD",icon="🧩",use_container_width=True)
with b:
    st.markdown("### 02 · Solve structural mechanics")
    st.write("Run real 3D tetra10 bracket FEA and inspect displacement, von Mises stress, equilibrium and checked redesigns.")
    st.page_link("pages/13_Real_STEP_Engineering.py",
                 label="Open Structural FEA",icon="📐",use_container_width=True)
with c:
    st.markdown("### 03 · Inspect rotating flow")
    st.write("Review actual OpenFOAM U/p fields and source-STL blade motion. Solved snapshots are distinct from geometric animation.")
    st.page_link("pages/15_Transient_Rotating_CFD.py",
                 label="Open Transient CFD",icon="🌀",use_container_width=True)

st.divider()
with st.container(border=True):
    st.markdown("### 04 · Wall Mount Load Transfer")
    st.write(
        "Calculate physically balanced four-anchor reactions under explicit mass, "
        "offset, aerodynamic thrust and torque. This is a real free-body model "
        "with ideal anchors, not certified wall/fastener FEA or an invented CFD thrust."
    )
    st.page_link("pages/16_Wall_Mount_Loads.py",
                 label="Open Wall & Anchor Load Transfer",icon="🔩",use_container_width=True)

st.divider()
st.subheader("Replay an existing verified CFD result")
st.caption("Read existing local CFD results only: never start Docker or rerun Navier–Stokes.")

@st.cache_data(ttl=12,show_spinner=False)
def _local_proven_jobs(home:str)->list[dict]:
    path=Path(home)
    if not path.is_dir():
        return []
    try:
        folders=[p for p in path.iterdir() if p.is_dir() and
                 re.fullmatch(r"[0-9a-f]{16}",p.name)]
        folders.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    except OSError:
        return []
    found=[]
    for folder in folders[:30]:
        try:
            state=job_status(folder.name)
            if (state.get("status")!="COMPLETED" or
                    state.get("stage")!="REAL_TRANSIENT_FIELDS_READY"):
                continue
            arrays=load_actual_frames(folder.name)  # validates field SHA-256
            n=int(arrays["velocity_m_s"].shape[0])
            if n<2:
                continue
            found.append({
                "id":folder.name,"frames":n,
                "origin":str(state.get("geometry_origin","unknown")),
                "rpm":state.get("controls",{}).get("rpm","unknown"),
            })
        except (OSError,ValueError,KeyError,TypeError):
            # Never advertise an unverified CFD job as a ready demo.
            continue
    return found

proven=_local_proven_jobs(str(ROOT))
if proven:
    selected=st.selectbox(
        "Completed, integrity-checked CFD jobs",
        options=range(len(proven)),
        format_func=lambda i:(
            f"{proven[i]['id']} · {proven[i]['frames']} real U/p frames · "
            f"{proven[i]['rpm']} RPM · "
            f"{'custom STEP rotor' if proven[i]['origin'].startswith('USER_STEP') else 'official reference rotor'}"
        ),
    )
    item=proven[selected]
    st.success(f"Ready: {item['frames']} solver-derived flow frames. Geometry: {item['origin']}.")
    if st.button("Open verified CFD replay",type="primary",use_container_width=True):
        st.session_state["forceforge_reference_cfd_job"]=item["id"]
        st.switch_page("pages/15_Transient_Rotating_CFD.py")
else:
    st.info("No completed, integrity-verified CFD jobs were found on this machine. CI results live on separate runners.")
    st.page_link("pages/15_Transient_Rotating_CFD.py",
                 label="Open CFD page to restore by Job ID",icon="📂")

with st.expander("Verified capabilities and engineering limits"):
    st.markdown("""
- **Real CAD:** OpenCASCADE STEP solids for four registered families; arbitrary products are not supported.
- **Real structural FEA:** 3D tetra10 bracket calculations with documented simplified loads and supports.
- **Real transient CFD:** OpenFOAM pimpleFoam and sliding AMI in the reference room; a custom STEP rotor may be inserted.
- **Continuous blade playback:** actual solver-case STL geometry rotates; U/p is a frozen genuine snapshot during smooth playback. Intermediate blade positions are **not CFD solutions**.
- **Unverified:** actual wall, guard, bolts, CFD-to-FEA coupling, mesh convergence, certified fan curves.
""")

st.divider()
st.markdown("**Technical verification**")
st.link_button("Actual custom STEP rotor + OpenFOAM evidence",
               "https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795")
st.link_button("Chromium Play/Pause/loop browser evidence",
               "https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675405969")
st.caption("Source: github.com/NeonGrade/ForceForge-AI/tree/hack-the-nest-2026-submission")
