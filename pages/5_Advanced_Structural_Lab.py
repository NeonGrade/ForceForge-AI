"""Multi-physics and joint-reliability extension (separate Streamlit page)."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from forceforge.advanced_frame import cantilever_demo, solve_frame
from forceforge.fatigue import SNModel, StressBlock, miner_damage

st.set_page_config(page_title="ForceForge X | Advanced Structural Lab", layout="wide")
st.markdown("[← Back to Decision Studio](/)")
st.title("ForceForge X — Advanced Structural Lab")
st.caption("2D Euler–Bernoulli frame FEA | semi-rigid support joints | thermal stress | second-order P–Δ | fatigue spectrum")
st.warning(
    "Engineering analysis demonstrator, NOT structural certification. "
    "Requires case-specific design codes, material S–N data, real joint characterization and independent validation before safety use."
)

with st.sidebar:
    st.header("Structural model")
    length=st.slider("Member span (m)",0.5,3.0,1.0,0.1)
    radius=st.slider("Solid round bar radius (mm)",10,60,35,1)
    tip_force=st.slider("Transverse tip load (N)",0,3000,500,50)
    axial_compression=st.slider("Axial compression (N)",0,30000,10000,500)
    delta_T=st.slider("Uniform temperature increase (K)",-50,200,50,5)
    joint=st.selectbox("Base joint",["Fixed","Semi-rigid"],index=0)
    log_k=st.slider("log10 rotational stiffness (N m/rad)",3.0,10.0,5.0,0.25,disabled=joint=="Fixed")
    spring=None if joint=="Fixed" else 10**log_k
    st.header("Fatigue parameters (illustrative)")
    sn_ref=st.number_input("S-N reference alternating stress (MPa)",5.0,800.0,100.0,5.0)
    sn_cycles=st.number_input("S-N reference cycles",min_value=1000,max_value=100_000_000,value=1_000_000,step=100_000)
    sn_slope=st.slider("S-N slope m",1.0,12.0,3.0,0.5)
    sigma_u=st.number_input("Ultimate strength (MPa)",10.0,2000.0,450.0,10.0)
    cycles=st.number_input("Applied load cycles",100,100_000_000,100_000,10000)
    duty=st.selectbox("Duty cycle",["Fully reversed (R=-1)","Repeated 0-to-peak (R=0)"])

m=cantilever_demo(length_m=length,tip_force_n=tip_force,
                   radius_m=radius/1000,rotational_spring_nm_rad=spring,
                   temp_rise_k=delta_T,axial_force_n=-axial_compression)
linear=solve_frame(m)
try:
    second=solve_frame(m,second_order=True)
except ValueError as exc:
    st.error(f"Second-order solution lost stability: {exc}")
    st.stop()

st.subheader("Physics-verified response")
a,b,c,d=st.columns(4)
a.metric("Linear tip displacement",f"{linear.u[1,1]*1000:.3f} mm")
b.metric("P–Δ tip displacement",f"{second.u[1,1]*1000:.3f} mm")
c.metric("Second-order amplification",f"{abs(second.u[1,1]/linear.u[1,1]):.3f}×" if linear.u[1,1] else "N/A")
d.metric("Thermal tip expansion",f"{m.material.alpha_per_k*delta_T*length*1000:.3f} mm")

if abs(second.u[1,1])/length>0.05:
    st.warning("The calculated transverse deflection exceeds 5% of the span. "
               "Small-strain second-order beam assumptions may be inaccurate.")
if not second.converged:
    st.warning("Second-order iteration did not converge; do not use the displayed estimate.")

loads=np.linspace(0.,axial_compression,13)
responses=[]
for P in loads:
    test=cantilever_demo(length_m=length,tip_force_n=tip_force,
                         radius_m=radius/1000,rotational_spring_nm_rad=spring,
                         temp_rise_k=delta_T,axial_force_n=-P)
    try:
        u=solve_frame(test,second_order=True)
        responses.append(float(u.u[1,1]*1000) if u.converged else np.nan)
    except ValueError:
        responses.append(np.nan)
fig=go.Figure()
fig.add_trace(go.Scatter(x=loads,y=responses,mode="lines+markers",name="P–Δ estimate"))
fig.add_hline(y=linear.u[1,1]*1000,line_dash="dash",annotation_text="Linear response at selected load")
fig.update_layout(xaxis_title="Compressive axial force (N)",yaxis_title="Tip transverse displacement (mm)",height=350)
st.plotly_chart(fig,width="stretch")
st.caption("The curve comes from an iterative beam-column geometric-stiffness approximation. "
           "It is not a full finite-rotation plastic or contact solver.")

st.subheader("Stress and connection behavior")
p1,p2,p3=st.columns(3)
p1.metric("Beam peak stress (axial+bending)",f"{linear.member_max_stress_pa.max()/1e6:.2f} MPa")
p2.metric("Base rotation",f"{linear.u[0,2]*180/np.pi:.5f} deg")
p3.metric("Support vertical reaction",f"{linear.reactions[0,1]:.1f} N")
st.caption("The joint uses a single rotational spring at the support; it does not resolve bolts, contact pressure, "
           "preload loss, welds, slip or local stress concentrations.")

st.subheader("Variable-amplitude fatigue damage screen")
peak=float(linear.member_max_stress_pa.max())
if duty.startswith("Fully"):
    amplitude,mean=peak,0.
else:
    amplitude,mean=peak/2,peak/2
fatigue=miner_damage(SNModel(sn_ref*1e6,sn_cycles,sn_slope,sigma_u*1e6),
                     [StressBlock(amplitude,mean,cycles)])
c1,c2,c3=st.columns(3)
c1.metric("Stress amplitude",f"{amplitude/1e6:.2f} MPa")
c2.metric("Miner damage D",f"{fatigue['miner_damage']:.5g}")
c3.metric("Fatigue screen", "D < 1" if fatigue['passes_unit_damage_screen'] else "D ≥ 1")
st.dataframe(pd.DataFrame(fatigue['blocks']).T, width="stretch")
st.error("Fatigue inputs here are hypothetical by default. A real fatigue life estimate needs "
         "joint-specific S–N curves, load-history counting, size/surface corrections, "
         "and experimental validation. No service-life guarantee is implied.")

st.markdown("**Validated formulas:** cantilever bending, semi-rigid base rotation, "
            "free/fully restrained uniform thermal expansion, compression P–Δ amplification, "
            "Goodman–Basquin–Miner fatigue calculation.")
