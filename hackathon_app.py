"""ForceForge X competition cockpit.

Judge-facing UI: no synthetic physics and no OpenFOAM worker started here.
This module reads only SHA-verified local CFD field files and links to real
engineering workflows. Existing job results are never modified.
"""
from __future__ import annotations

from pathlib import Path
import re
import numpy as np
import plotly.graph_objects as go
import streamlit as st

from forceforge.rotating_cfd import ROOT, job_status, load_actual_frames


st.set_page_config(
    page_title="ForceForge X | Engineering AI",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg,#f0f5f9 0%,#f7fafc 43%,#f3f7fa 100%);
    }
    .block-container {max-width:1290px;padding-top:1.45rem;padding-bottom:3.6rem;}
    header[data-testid="stHeader"] {background:transparent;}
    .ff-hero {
        background:radial-gradient(ellipse at 93% 11%,rgba(39,193,212,.25),transparent 45%),
                   linear-gradient(130deg,#0a1e33,#16324f 68%,#174e5a);
        color:#fff;border:1px solid rgba(110,211,231,.25);
        border-radius:24px;padding:29px 38px 31px;overflow:hidden;
        box-shadow:0 18px 50px rgba(17,47,71,.12);position:relative;
    }
    .ff-hero:after {content:"";pointer-events:none;position:absolute;
        width:225px;height:225px;right:-55px;top:-70px;border-radius:50%;
        border:1px solid rgba(126,231,239,.3);
        box-shadow:0 0 0 32px rgba(126,231,239,.045),0 0 0 70px rgba(126,231,239,.025);
    }
    .ff-eyebrow {color:#8de5ee;letter-spacing:.18em;font-size:.77rem;font-weight:800;
                  text-transform:uppercase;margin-bottom:9px;}
    .ff-name {font-size:clamp(2.5rem,4.4vw,4.25rem);font-weight:850;
              line-height:1.04;letter-spacing:-.055em;margin:0 0 10px;}
    .ff-sub {max-width:825px;font-size:1.08rem;line-height:1.65;color:#d6e8f4;
             margin:0 0 20px;}
    .ff-chips {display:flex;flex-wrap:wrap;gap:9px;}
    .ff-chip {border:1px solid rgba(174,228,240,.4);color:#d9faff;
              background:rgba(255,255,255,.075);padding:6px 11px;
              border-radius:100px;font-size:.76rem;font-weight:700;}
    .ff-section {font-size:.83rem;letter-spacing:.1em;font-weight:800;
                 color:#527080;text-transform:uppercase;margin:20px 0 5px;}
    .ff-step {color:#0d8796;font-size:.78rem;letter-spacing:.11em;
              font-weight:800;margin:0 0 6px;}
    .ff-card-title {font-size:1.22rem;font-weight:790;color:#122e43;
                    margin:0 0 6px;letter-spacing:-.02em;}
    .ff-card-text {color:#4e6879;font-size:.91rem;line-height:1.52;
                   min-height:49px;margin-bottom:10px;}
    .ff-card-foot {border-top:1px solid #e5edf2;padding-top:9px;color:#6c8190;
                   font-size:.76rem;}
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius:18px;border-color:#dce7ed;
        background:#fff;box-shadow:0 6px 20px rgba(31,67,87,.045);
    }
    div[data-testid="stPageLink"] a {
        border-radius:11px !important;font-weight:750 !important;
        color:#087987 !important;text-decoration:none !important;
    }
    .ff-flow-head {font-size:1.38rem;letter-spacing:-.025em;font-weight:790;
                   color:#152e42;margin:0 0 6px;}
    .ff-note {font-size:.85rem;color:#647e8d;}
    .ff-source {border-left:3px solid #16a7b6;background:#edf7f8;
                padding:12px 15px;border-radius:0 10px 10px 0;
                color:#355667;font-size:.85rem;line-height:1.5;}
    .ff-footer {color:#8295a1;font-size:.78rem;text-align:center;
                padding:20px 0 5px;}
    @media(max-width:760px) {
        .block-container {padding-top:.75rem;}
        .ff-hero {padding:24px 21px 26px;border-radius:17px;}
        .ff-name {font-size:2.5rem;}
        .ff-sub {font-size:.96rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="ff-hero">
      <div class="ff-eyebrow">Hack the Nest 2026 &nbsp; / &nbsp; Engineering intelligence</div>
      <div class="ff-name">ForceForge X<span style="color:#6ee0e6">.</span></div>
      <p class="ff-sub">
        From a plain-language mechanical concept to <b>real STEP geometry</b>,
        independently calculated <b>3D structural FEA</b>, and
        <b>rotating-flow OpenFOAM evidence</b>.
      </p>
      <div class="ff-chips">
        <span class="ff-chip">4 registered CAD families</span>
        <span class="ff-chip">Quadratic tetra10 FEA</span>
        <span class="ff-chip">Transient rotating AMI CFD</span>
        <span class="ff-chip">Solver-source provenance</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="ff-section">01 / Explore engineering workflows</div>',unsafe_allow_html=True)
st.subheader("Your engineering workflow")

# Keep four real workflows above the fold in a compact 2x2 layout.
left,right=st.columns(2,gap="medium")
with left:
    with st.container(border=True):
        st.markdown(
            '<div class="ff-step">01 &nbsp; NATURAL LANGUAGE → CAD</div>'
            '<div class="ff-card-title">Describe a product. Generate STEP.</div>'
            '<div class="ff-card-text">Specify a fan, L-bracket, hollow shaft or mounting '
            'plate. Validate dimensions and export genuine OpenCASCADE geometry.</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/14_Natural_Language_Engineering.py",
                     label="Open Natural Language CAD",icon="🧩",
                     use_container_width=True)
        st.markdown('<div class="ff-card-foot">4 registered families · Real STEP exports</div>',
                    unsafe_allow_html=True)
with right:
    with st.container(border=True):
        st.markdown(
            '<div class="ff-step">02 &nbsp; CAD → FINITE ELEMENTS</div>'
            '<div class="ff-card-title">Solve stress and deformation.</div>'
            '<div class="ff-card-text">Import a supported STEP solid, apply stated '
            'fixtures and loads, and inspect real tetra10 displacement and stress.</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/13_Real_STEP_Engineering.py",
                     label="Open Structural FEA",icon="📐",
                     use_container_width=True)
        st.markdown('<div class="ff-card-foot">True FEM · Explicit boundary assumptions</div>',
                    unsafe_allow_html=True)

left2,right2=st.columns(2,gap="medium")
with left2:
    with st.container(border=True):
        st.markdown(
            '<div class="ff-step">03 &nbsp; ROTOR → NAVIER–STOKES</div>'
            '<div class="ff-card-title">Inspect real rotating flow.</div>'
            '<div class="ff-card-text">Review genuine OpenFOAM U/p snapshots, '
            'source STL geometry and continuously animated blade kinematics.</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/15_Transient_Rotating_CFD.py",
                     label="Open Transient CFD",icon="🌀",
                     use_container_width=True)
        st.markdown('<div class="ff-card-foot">pimpleFoam · Sliding AMI · Verified fields</div>',
                    unsafe_allow_html=True)
with right2:
    with st.container(border=True):
        st.markdown(
            '<div class="ff-step">04 &nbsp; MECHANICS → SUPPORT LOADS</div>'
            '<div class="ff-card-title">Calculate wall-anchor reactions.</div>'
            '<div class="ff-card-text">Balance a supplied fan mass, offset, thrust '
            'and torque across four ideal anchors with force/moment checks.</div>',
            unsafe_allow_html=True,
        )
        st.page_link("pages/16_Wall_Mount_Loads.py",
                     label="Open Wall Load Transfer",icon="🔩",
                     use_container_width=True)
        st.markdown('<div class="ff-card-foot">6-DOF statics · Not wall-contact FEA</div>',
                    unsafe_allow_html=True)

st.markdown('<div class="ff-section">02 / Real calculation, real source</div>',unsafe_allow_html=True)
st.markdown(
    '<div class="ff-flow-head">Verified OpenFOAM results</div>'
    '<div class="ff-note">Automatic local recovery; this page never launches Docker '
    'or repeats a CFD calculation.</div>',
    unsafe_allow_html=True,
)

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
            arrays=load_actual_frames(folder.name)
            n=int(arrays["velocity_m_s"].shape[0])
            if n<2 or arrays["sample_points"].shape[0]!=n:
                continue
            found.append({
                "id":folder.name,"frames":n,
                "origin":str(state.get("geometry_origin","unknown")),
                "rpm":state.get("controls",{}).get("rpm","unknown"),
            })
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            # Unverified fields must never be marketed as successful CFD.
            continue
    return found


def _sourced_velocity_plot(fields:dict)->go.Figure:
    """Plot actual solved field samples, not a fabricated CFD animation."""
    xyz=np.asarray(fields["sample_points"][-1],dtype=float)
    vel=np.asarray(fields["velocity_m_s"][-1],dtype=float)
    if xyz.ndim!=2 or xyz.shape[1]!=3 or vel.shape!=xyz.shape:
        raise ValueError("Invalid source-linked CFD array dimensions")
    mag=np.linalg.norm(vel,axis=1)
    mask=np.isfinite(xyz).all(axis=1)&np.isfinite(mag)
    if not mask.any():
        raise ValueError("No finite solver-backed velocity samples")
    pts=xyz[mask]
    v=mag[mask]
    top=max(float(v.max()),.001)
    fig=go.Figure(go.Scatter3d(
        x=pts[:,0],y=pts[:,1],z=pts[:,2],mode="markers",
        marker=dict(
            size=3.2,color=v,cmin=0,cmax=top,colorscale="Turbo",
            opacity=.84,
            colorbar=dict(
                title=dict(text="|U| m/s",font=dict(color="#afcfdd")),
                thickness=12,len=.75,tickfont=dict(color="#afcfdd")
            )
        ),
        customdata=v,
        hovertemplate="x=%{x:.2f} m<br>y=%{y:.2f} m<br>"
                      "z=%{z:.2f} m<br>|U|=%{customdata:.3f} m/s<extra></extra>",
    ))
    axis=dict(
        showbackground=False,showgrid=True,gridcolor="#264358",
        zeroline=False,tickfont=dict(color="#bfd3e0",size=9),
        color="#bfd3e0"
    )
    fig.update_layout(
        height=350,showlegend=False,margin=dict(l=0,r=0,t=0,b=0),
        paper_bgcolor="#0e2030",plot_bgcolor="#0e2030",
        scene=dict(xaxis={**axis,"title":"X (m)"},
                   yaxis={**axis,"title":"Y (m)"},
                   zaxis={**axis,"title":"Z (m)"},
                   bgcolor="#0e2030",aspectmode="data",
                   camera=dict(eye=dict(x=1.45,y=1.3,z=.9)))
    )
    return fig


proven=_local_proven_jobs(str(ROOT))
if proven:
    viz,control=st.columns([1.28,.9],gap="medium")
    with control:
        selected=st.selectbox(
            "Source-verified local CFD job",
            options=range(len(proven)),
            format_func=lambda i:(
                f"{proven[i]['id']} · "
                f"{'STEP rotor' if proven[i]['origin'].startswith('USER_STEP') else 'reference rotor'}"
            ),
        )
        item=proven[selected]
        origin=item["origin"]
        st.markdown("**Result status**")
        st.success("VERIFIED · COMPLETED")
        m1,m2=st.columns(2)
        with m1:
            st.metric("Solved U/p frames",str(item["frames"]))
        with m2:
            st.metric("Rotor RPM",str(item["rpm"]))
        st.caption(
            "Geometry: actual custom STEP rotor inside official reference room"
            if origin.startswith("USER_STEP") else
            "Geometry: official OpenFOAM reference rotor"
        )
        if st.button("Play real CFD & rotating blades",type="primary",
                     use_container_width=True,key="open_verified_cfd"):
            st.session_state["forceforge_reference_cfd_job"]=item["id"]
            st.switch_page("pages/15_Transient_Rotating_CFD.py")
    with viz:
        try:
            fields=load_actual_frames(item["id"])
            st.plotly_chart(_sourced_velocity_plot(fields),
                            use_container_width=True,
                            config={"displayModeBar":False})
            if "physical_time_s" in fields:
                label=f"Solver time {float(fields['physical_time_s'][-1]):.5f} s"
            else:
                label="Verified solver write index, physical seconds unconfirmed"
            st.caption(
                f"Actual sampled speed |U| (m/s) · {label} · "
                "not a synthetic velocity field"
            )
        except (OSError,ValueError,KeyError,TypeError,AttributeError):
            st.warning("Saved CFD sample failed its integrity or geometry checks.")
else:
    with st.container(border=True):
        st.info(
            "No completed SHA-verified OpenFOAM job is available on this computer. "
            "GitHub CI results are stored on a different runner; "
            "this homepage does not create fake data."
        )
        st.page_link("pages/15_Transient_Rotating_CFD.py",
                     label="Restore a completed OpenFOAM job by ID",icon="📂")

with st.expander("Engineering validity and scope"):
    st.markdown(
        "All visualized values come from actual solver files. The supported "
        "CAD catalog has four registered families; arbitrary text-to-any-CAD "
        "is not implemented. Bracket, shaft and plate FEA use stated simplified "
        "loads/fixtures. OpenFOAM uses a reference room even with a user "
        "STEP rotor. Smooth blade motion between saved CFD snapshots is "
        "**kinematic geometry**, not additional fluid solutions. "
        "Four-anchor forces describe rigid-body static equilibrium, "
        "**not** certified wall/bolt contact FEA."
    )

st.markdown('<div class="ff-section">03 / Independent verification</div>',unsafe_allow_html=True)
proof1,proof2,proof3=st.columns(3,gap="small")
with proof1:
    st.link_button("STEP rotor + real OpenFOAM",
                   "https://github.com/NeonGrade/ForceForge-AI/actions/runs/43674796795",
                   use_container_width=True)
with proof2:
    st.link_button("Chromium rotor Play/Pause",
                   "https://github.com/NeonGrade/ForceForge-AI/actions/runs/43675405969",
                   use_container_width=True)
with proof3:
    st.link_button("CAD / FEA / wall statics tests",
                   "https://github.com/NeonGrade/ForceForge-AI/actions/runs/43724741577",
                   use_container_width=True)
st.markdown(
    '<div class="ff-footer">FORCEFORGE X · RESEARCH PROTOTYPE · '
    'NO FABRICATED ENGINEERING RESULTS</div>',unsafe_allow_html=True
)
