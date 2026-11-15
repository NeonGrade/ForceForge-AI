"""ForceForge X — real transient rotating-blade CFD reference and results.

No fake CFD: only verified U,p fields from a successful OpenFOAM pimpleFoam
run are rendered as moving 3D flow glyphs/colored cloud. The reference
rotatingFanInRoom tutorial is visibly NOT the generated 300 mm fan STEP.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from forceforge.rotor_visual import sample_real_stl_triangles, rotating_triangle_frames
from forceforge.rotating_cfd import (
    IMAGE, SCENE_KIND, ReferenceControls,
    docker_ready, job_status, launch_reference_job, load_actual_frames,
    active_cfd_job_ids,
)

st.set_page_config(
    page_title="ForceForge X | Transient Rotating Fan CFD",
    page_icon="🌀", layout="wide",
)
st.title("Transient CFD · Rotating Blade Flow")
st.caption(
    "ForceForge X v0.3 · actual OpenFOAM pimpleFoam · rotatingMotion "
    "+ sliding AMI · time-dependent pressure and velocity"
)
st.markdown(
    "[Natural Language Engineering](./Natural_Language_Engineering) · "
    "[Real 3D Solid FEA](./Real_STEP_Engineering)"
)

rotor_source=st.session_state.get("forceforge_custom_rotor_input")
mode=st.radio(
    "Select provenance / geometry scope",
    [
        "Official OpenFOAM blade-resolved rotating-fan reference case",
        "My STEP-derived rotor in the official OpenFOAM reference room",
    ],index=0,
)
use_custom=mode.startswith("My STEP-derived")
if use_custom:
    if not isinstance(rotor_source,dict):
        st.error(
            "CUSTOM ROTOR NOT LOADED: open Natural Language Engineering, "
            "generate the fan STEP, then click Extract actual rotating blades. "
            "This workflow does not accept the earlier actuator-only air .msh "
            "as a blade-resolved CFD mesh."
        )
        st.stop()
    st.warning(
        "CUSTOM ROTOR + REFERENCE ROOM: the real rotating blade and hub "
        "surfaces come from the exact CAD STEP, but the air domain, static "
        "room, moving-cylinder AMI geometry and supports remain the official "
        "OpenFOAM tutorial. This is NOT validated wall-fan installation CFD."
    )
    st.caption(
        "Source STEP SHA-256: "+str(rotor_source["cad_source_sha256"])
        +" · rotor STL SHA-256: "+str(rotor_source["rotor_stl_sha256"])
    )
else:
    st.info(
        "OFFICIAL REFERENCE: This path solves OpenFOAM rotatingFanInRoom "
        "with its own original fan blades, a real moving grid and AMI. "
        "The flow fields are computed, but geometry is unrelated to your "
        "newly generated 300 mm STEP."
    )
ok,environment=docker_ready()
if not ok:
    st.warning("OpenFOAM runtime not ready: "+environment)
    st.code(
        "docker pull opencfd/openfoam-default:2512",
        language="bash",
    )
    st.caption(
        "Install/start Docker Desktop first on macOS. The image includes "
        "official OpenFOAM executables, source and tutorial assets. "
        "Run is disabled until the image exists locally."
    )
else:
    st.success("Official container available locally. Image ID: "+environment[:35])

active_jobs=active_cfd_job_ids() if ok else []
if active_jobs:
    st.warning(
        "An OpenFOAM solver is already active: "+
        ", ".join(active_jobs)+
        ". Restore and refresh the existing job; launching additional "
        "parallel solvers is disabled to avoid duplicate Docker containers."
    )

a,b,c=st.columns(3)
rpm=a.number_input(
    "Reference fan rotational speed (RPM)",
    min_value=100,max_value=2400,
    value=(int(rotor_source["rpm"]) if use_custom else 600),step=100,
)
end=b.number_input(
    "Real transient duration (s)",
    min_value=.008,max_value=.080,value=.040,step=.008,
    format="%.3f",
)
dt=c.number_input(
    "Save actual flow fields every (s)",
    min_value=.001,max_value=.016,value=.004,step=.001,
    format="%.3f",
)
try:
    controls=ReferenceControls(
        rpm=int(rpm),end_time_s=float(end),write_interval_s=float(dt),
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

st.write(
    f"**Rotation period:** {60/controls.rpm:.4f} s · "
    f"**Revolutions requested:** {controls.end_time_s*controls.rpm/60:.2f} · "
    f"**Angular velocity:** {controls.angular_velocity_rad_s:.2f} rad/s"
)
if use_custom:
    with st.expander("Real STEP blade rotation · GEOMETRY ONLY (not CFD)",expanded=True):
        st.caption(
            "Exact source-STEP rotor STL geometry, rigidly rotated about "
            "the physical shaft axis at the chosen RPM. This is a kinematic "
            "CAD preview shown at slowed-down playback speed; U and p "
            "are deliberately absent until a real CFD solve succeeds."
        )
        try:
            sampled=sample_real_stl_triangles(
                rotor_source["stl_bytes"],max_faces=450,
            )
            time_axis,moving=rotating_triangle_frames(
                sampled,rpm=controls.rpm,
                duration_s=controls.end_time_s,count=13,
            )
            topology=np.arange(moving.shape[1]).reshape(-1,3)
            def actual_rotor_frame(k):
                verts=moving[k]
                return go.Mesh3d(
                    x=verts[:,0],y=verts[:,1],z=verts[:,2],
                    i=topology[:,0],j=topology[:,1],k=topology[:,2],
                    color="#21b5aa",flatshading=True,opacity=1.0,
                    lighting=dict(ambient=.7,diffuse=.65,roughness=.35),
                    name="Source STEP rotor geometry ONLY",
                    hovertemplate="Source rotor geometry · meters<extra>NO CFD field</extra>",
                )
            actual_fig=go.Figure(
                data=[actual_rotor_frame(0)],
                frames=[
                    go.Frame(data=[actual_rotor_frame(k)],name=str(k))
                    for k in range(len(time_axis))
                ],
            )
            actual_fig.update_layout(
                title="Source-CAD blades · real RPM · slowed kinematic playback",
                height=480,margin=dict(l=0,r=0,t=65,b=0),
                scene=dict(aspectmode="data",xaxis_title="X (m)",
                           yaxis_title="Y (m)",zaxis_title="Z (m)"),
                updatemenus=[{
                    "type":"buttons","direction":"left",
                    "x":.02,"y":1.1,"showactive":False,
                    "buttons":[
                        {"label":"▶ Rotate actual STEP blades",
                         "method":"animate",
                         "args":[None,{
                             "frame":{"duration":160,"redraw":True},
                             "transition":{"duration":0},
                             "fromcurrent":True,
                         }]},
                        {"label":"❚❚ Pause","method":"animate",
                         "args":[[None],{
                             "mode":"immediate",
                             "frame":{"duration":0,"redraw":False},
                             "transition":{"duration":0},
                         }]},
                    ],
                }],
                sliders=[{
                    "active":0,
                    "steps":[{
                        "label":f"{t:.3f} s",
                        "method":"animate",
                        "args":[[str(k)],{
                            "mode":"immediate",
                            "frame":{"duration":0,"redraw":True},
                            "transition":{"duration":0},
                        }],
                    } for k,t in enumerate(time_axis)],
                }],
            )
            st.plotly_chart(
                actual_fig,width="stretch",
                key="cad_only_rotating_rotor_preview",
            )
        except (ValueError,KeyError,OSError) as exc:
            st.error("Cannot display original CAD blade kinematics: "+str(exc))

st.caption(
    "This is a real transient flow calculation, not a scripted animation. "
    "The mesh and Navier–Stokes solve may take minutes; live visualization "
    "is produced only after actual U and p field snapshots are exported."
)

if st.button(
    "Run genuine OpenFOAM rotating-mesh transient CFD (reference geometry)",
    disabled=(not ok or bool(active_jobs)),type="primary",key="reference_cfd_run",
):
    try:
        if use_custom:
            job=launch_reference_job(
                controls,
                custom_rotor_stl=rotor_source["stl_bytes"],
                custom_source_sha256=rotor_source["cad_source_sha256"],
                custom_diameter_mm=float(rotor_source["diameter_mm"]),
            )
        else:
            job=launch_reference_job(controls)
        st.session_state["forceforge_reference_cfd_job"]=job
    except (RuntimeError,OSError,ValueError) as exc:
        st.error("Could not start native CFD: "+str(exc))

# Persisted on disk as a bounded, hash-keyed job. A browser refresh or
# Streamlit WebSocket restart must NOT force re-running the Navier-Stokes solve.
with st.expander("Recover an existing real CFD job after browser reconnect"):
    remembered=st.text_input(
        "Existing verified local CFD job ID",
        max_chars=16,key="forceforge_restore_cfd_id",
    )
    if st.button("Restore existing CFD results",key="forceforge_restore_button"):
        try:
            snapshot=job_status(remembered.strip())
            if snapshot.get("status") not in (
                "RUNNING","SOLVER_FINISHED_UNVERIFIED_FIELDS","COMPLETED","FAILED"
            ):
                raise ValueError("No persisted actual CFD run exists for that job ID")
            st.session_state["forceforge_reference_cfd_job"]=remembered.strip()
            st.success("Recovered the original CFD job without starting another solver")
        except (ValueError,OSError,KeyError) as exc:
            st.error("Cannot restore requested real CFD job: "+str(exc))

job=st.session_state.get("forceforge_reference_cfd_job")
if job:
    with st.container(border=True):
        st.write("**Real CFD job:**",job)
        if st.button("Refresh CFD solver status",key="cfd_refresh"):
            st.rerun()
        try:
            status=job_status(job)
        except (OSError,ValueError) as exc:
            st.error("Invalid CFD job metadata: "+str(exc))
            st.stop()
        st.write("**Status:**",status.get("status","UNKNOWN"))
        st.write("**Stage:**",status.get("stage","UNKNOWN"))
        if status.get("warning"):
            st.warning(str(status["warning"]))
        st.caption("Reference geometry: "+str(status.get("geometry_origin")))
        with st.expander("Local CFD job diagnostic files"):
            st.code(
                'cat "$HOME/.forceforge_x/transient_cfd/'+job+'/status.json"\n'
                'tail -n 50 "$HOME/.forceforge_x/transient_cfd/'+job+'/launcher.log"\n'
                'tail -n 50 "$HOME/.forceforge_x/transient_cfd/'+job+'/solver_console.log"',
                language="bash",
            )
        if status.get("status")=="FAILED":
            st.error(
                str(status.get("error_type","WorkerError")) + ": " +
                str(status.get("message","Check local CFD logs"))
            )
        elif status.get("status") in ("RUNNING","SOLVER_FINISHED_UNVERIFIED_FIELDS"):
            st.warning(
                "OpenFOAM is working in a separate limited-memory process. "
                "Refreshing this page does not restart the solver. "
                "Only completed verified outputs will appear below."
            )
        elif status.get("status")=="COMPLETED":
            st.success(
                "Actual OpenFOAM transient U/p snapshots verified. "
                "Displaying real CFD fields, not a fake animation."
            )
            try:
                fields=load_actual_frames(job)
                xyz=fields["sample_points"]
                velocity=fields["velocity_m_s"]
                pressure=fields["kinematic_pressure_m2_s2"]
                ids=fields["vtk_record_indices"]
                if xyz.shape!=velocity.shape or (
                    pressure.shape!=xyz.shape[:2]
                ) or xyz.shape[0]<2:
                    raise ValueError("Invalid transient CFD frame arrays")
                n=xyz.shape[0]
                speed=np.linalg.norm(velocity,axis=2)
                color_max=max(float(np.percentile(speed,99)),1e-9)
                select=st.slider(
                    "Inspect real OpenFOAM VTK snapshot",
                    min_value=0,max_value=n-1,value=0,step=1,
                    key="transient_cfd_frame_select",
                )
                # Stable, comparable scale across every actual CFD frame.
                def physical_flow_trace(i):
                    pp=xyz[i]
                    uu=speed[i]
                    return go.Scatter3d(
                        x=pp[:,0],y=pp[:,1],z=pp[:,2],
                        mode="markers",name="Computed velocity magnitude",
                        marker=dict(
                            size=3,color=uu,cmin=0,cmax=color_max,
                            colorscale="Turbo",opacity=.65,
                            colorbar=dict(title="|U| m/s"),
                        ),
                        customdata=np.stack([
                            uu,pressure[i],
                        ],axis=1),
                        hovertemplate=(
                            "x=%{x:.3f} m; y=%{y:.3f} m; z=%{z:.3f} m"
                            "<br>|U|=%{customdata[0]:.3f} m/s"
                            "<br>p=%{customdata[1]:.3f} m²/s²"
                            "<extra>Actual OpenFOAM VTK</extra>"
                        ),
                    )

                def actual_vector_glyphs(i):
                    pp=xyz[i][::9]
                    vv=velocity[i][::9]
                    return go.Cone(
                        x=pp[:,0],y=pp[:,1],z=pp[:,2],
                        u=vv[:,0],v=vv[:,1],w=vv[:,2],
                        colorscale="Turbo",showscale=False,
                        anchor="tail",sizemode="absolute",sizeref=.15,
                        name="Actual U direction",
                        hoverinfo="skip",
                    )

                fig=go.Figure(
                    data=[
                        physical_flow_trace(select),
                        actual_vector_glyphs(select),
                    ],
                    frames=[
                        go.Frame(
                            data=[physical_flow_trace(i),actual_vector_glyphs(i)],
                            name=str(i),
                        ) for i in range(n)
                    ],
                )
                fig.update_layout(
                    title="Real transient OpenFOAM flow · U and kinematic p",
                    height=610,margin=dict(l=0,r=0,t=62,b=0),
                    scene=dict(
                        aspectmode="data",
                        xaxis_title="X (m)",
                        yaxis_title="Y (m)",
                        zaxis_title="Z (m)",
                    ),
                    updatemenus=[{
                        "type":"buttons","direction":"left",
                        "x":0.02,"y":1.07,"showactive":False,
                        "buttons":[
                            {
                                "label":"▶ Play real CFD frames",
                                "method":"animate",
                                "args":[None,{"frame":{"duration":260,"redraw":True},
                                               "transition":{"duration":0},
                                               "fromcurrent":True}],
                            },
                            {
                                "label":"❚❚ Pause",
                                "method":"animate",
                                "args":[[None],{"mode":"immediate",
                                                 "frame":{"duration":0,"redraw":False},
                                                 "transition":{"duration":0}}],
                            },
                        ],
                    }],
                    sliders=[{
                        "active":select,"pad":{"t":24},
                        "steps":[{
                            "label":str(i),
                            "method":"animate",
                            "args":[[str(i)],{
                                "mode":"immediate",
                                "frame":{"duration":0,"redraw":True},
                                "transition":{"duration":0},
                            }],
                        } for i in range(n)],
                    }],
                )
                st.plotly_chart(
                    fig,width="stretch",key="actual_openfoam_dynamic_animation",
                )
                # Offline hackathon fallback: the complete interactive
                # playback is generated ONLY from verified real CFD fields,
                # including embedded Plotly JS so no Wi-Fi is required.
                st.download_button(
                    "Download stand-alone REAL CFD animation (offline HTML)",
                    data=fig.to_html(
                        include_plotlyjs=True,full_html=True
                    ).encode("utf-8"),
                    file_name="forceforge_verified_openfoam_dynamic_flow.html",
                    mime="text/html",
                    key="download_authentic_cfd_animation",
                )
                mean_speed=np.mean(speed,axis=1)
                chart=go.Figure()
                chart.add_trace(go.Scatter(
                    x=np.arange(n),y=mean_speed,mode="lines+markers",
                    name="Average sampled speed",
                ))
                chart.update_layout(
                    title="Computed sampled velocity evolution",
                    xaxis_title="VTK record index (NOT physical time)",
                    yaxis_title="Mean |U| (m/s)",
                    height=270,margin=dict(l=40,r=20,t=50,b=40),
                )
                st.plotly_chart(chart,width="stretch")
                a,b,c=st.columns(3)
                a.metric("Actual CFD frames",str(n))
                b.metric(
                    "Selected max sampled velocity",
                    f"{float(np.max(speed[select])):.3f} m/s",
                )
                c.metric(
                    "Selected kinematic p range",
                    f"{float(np.ptp(pressure[select])):.3f} m²/s²",
                )
                st.caption(
                    "Field values are actual OpenFOAM outputs. Display samples "
                    "up to 500 real mesh vertices per frame, not every CFD cell. "
                    "VTK index labels are NOT claimed physical timestamps. "
                    "This is a reference fan / room case, with no "
                    "ForceForge STEP-to-CFD geometry identity or mesh-convergence proof."
                )
                details=json.dumps(status,indent=2)
                st.download_button(
                    "Download actual CFD numerical provenance (JSON)",
                    data=details,
                    file_name="forceforge_openfoam_reference_evidence.json",
                    mime="application/json",
                )
            except (ValueError,OSError,KeyError) as exc:
                st.error(
                    "Solver output was not rendered because its real physical "
                    "data validation failed: "+str(exc)
                )

st.divider()
st.markdown("#### Scope and engineering gates")
st.write(
    "This adapter can run official blades or replace the reference "
    "fan wall with a **source-STEP-derived rotating rotor STL**, then "
    "remesh and solve on the official OpenFOAM AMI reference-room flow. "
    "The uploaded actuator-only MSH is NOT the rotating-blade mesh. "
    "Physical wall-mount boundary conditions, actual fan casing/guard "
    "surfaces, source-specific AMI convergence and thrust/fixture validation "
    "are still missing. Live OpenFOAM results must pass CI before claims "
    "of correct custom transient CFD are made."
)
